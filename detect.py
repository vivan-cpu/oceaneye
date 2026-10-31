"""
detect.py - finds possible oil slicks in a Sentinel-1 radar image

The idea (from the papers we read, see docs/how_it_works.md):
  wind makes tiny ripples on the sea -> ripples bounce radar back to the satellite -> sea looks grey.
  oil makes the surface smooth -> radar bounces away -> oil looks DARK.
So we look for dark patches that are much darker than the sea around them,
then check their shape so we don't get fooled by calm-wind areas ("look-alikes").

Can also be run on its own:
    python detect.py some_scene.tif
"""

import sys
import json
import numpy as np
from scipy import ndimage as ndi
from skimage import measure, morphology, filters

try:
    from global_land_mask import globe
except ImportError:
    globe = None   # land mask is optional, works without it (just more false alarms near coast)


# default settings - we tuned these by trial and error on the test scene + Kerch strait images
SETTINGS = {
    "speckle_window": 7,        # lee filter window (pixels)
    "background_km": 3.0,       # how big the "surrounding sea" window is
    "contrast_db": 3.0,         # pixel must be this many dB darker than its surroundings
    "max_db": -18.0,            # and darker than this in absolute terms
    "min_area_km2": 0.05,       # ignore tiny specks
    "coast_buffer_km": 1.0,     # ignore stuff right next to land
}


# ---------- loading ----------

def load_geotiff(path):
    """reads a single band radar tif. returns dict with the image in dB + georef stuff"""
    import rasterio
    from rasterio.warp import transform as warp_transform

    with rasterio.open(path) as src:
        img = src.read(1).astype("float32")
        nodata = src.nodata
        valid = np.isfinite(img)
        if nodata is not None:
            valid &= img != nodata
        # our copernicus download has a 2nd band = dataMask
        if src.count >= 2:
            valid &= src.read(2) > 0
        tr = src.transform
        crs = src.crs

    # is it linear power or already in dB? linear sea values are like 0.001-0.1,
    # dB values are negative (-30 to 0)
    vals = img[valid]
    if vals.size and np.nanmedian(vals) < 0:
        db = img
    else:
        db = to_db(img)
    db[~valid] = np.nan

    rows, cols = db.shape

    def lonlat(r, c):
        r = np.asarray(r, dtype=float)
        c = np.asarray(c, dtype=float)
        xs = tr.c + (c + 0.5) * tr.a + (r + 0.5) * tr.b
        ys = tr.f + (c + 0.5) * tr.d + (r + 0.5) * tr.e
        if crs is not None and crs.to_epsg() != 4326:
            lon, lat = warp_transform(crs, "EPSG:4326", xs.ravel().tolist(), ys.ravel().tolist())
            return np.array(lon).reshape(xs.shape), np.array(lat).reshape(ys.shape)
        return xs, ys

    # pixel size in km (rough, good enough for areas)
    lon0, lat0 = lonlat(rows / 2, cols / 2)
    lon1, lat1 = lonlat(rows / 2, cols / 2 + 1)
    lon2, lat2 = lonlat(rows / 2 + 1, cols / 2)
    px_w = haversine_km(lat0, lon0, lat1, lon1)
    px_h = haversine_km(lat0, lon0, lat2, lon2)

    return {"db": db, "lonlat": lonlat, "px_w_km": float(px_w), "px_h_km": float(px_h)}


def to_db(lin):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(np.clip(lin, 1e-6, None))


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


# ---------- image processing ----------

def lee_filter(img, size):
    """lee speckle filter. radar images are super grainy ("speckle"), this smooths
    flat areas but keeps edges sharp. works on linear values not dB."""
    mean = ndi.uniform_filter(img, size)
    sq_mean = ndi.uniform_filter(img * img, size)
    var = np.clip(sq_mean - mean * mean, 0, None)
    noise_var = np.mean(var)
    w = var / (var + noise_var + 1e-12)
    return mean + w * (img - mean)


def masked_mean(img, valid, size):
    """moving average that ignores nan / land pixels"""
    a = np.where(valid, img, 0.0)
    num = ndi.uniform_filter(a, size)
    den = ndi.uniform_filter(valid.astype("float32"), size)
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def make_land_mask(scene, step=8):
    """true where land (or close to land). uses global-land-mask (1km data) on a
    coarse grid then blows it back up, otherwise its slow on big images"""
    db = scene["db"]
    if globe is None:
        return np.zeros(db.shape, bool)
    rows, cols = db.shape
    rr, cc = np.mgrid[0:rows:step, 0:cols:step]
    lon, lat = scene["lonlat"](rr, cc)
    lon = ((lon + 180) % 360) - 180
    small = globe.is_land(lat, lon)
    big = np.kron(small, np.ones((step, step), bool))[:rows, :cols]
    buf_px = int(round(SETTINGS["coast_buffer_km"] / max(scene["px_w_km"], 1e-6)))
    if buf_px > 0 and big.any():
        big = ndi.binary_dilation(big, iterations=buf_px)
    return big


def find_dark_spots(scene, s=None):
    s = dict(SETTINGS, **(s or {}))
    db = scene["db"]
    valid = np.isfinite(db)

    land = make_land_mask(scene)
    sea = valid & ~land

    # 1. speckle filter (in linear units), back to dB
    lin = np.where(sea, 10 ** (np.nan_to_num(db, nan=-25) / 10), 0)
    smooth_db = to_db(lee_filter(lin, s["speckle_window"]))
    smooth_db[~sea] = np.nan

    # 2. local background = average sea level around each pixel
    win = int(round(s["background_km"] / scene["px_w_km"]))
    win = max(win | 1, 15)   # odd, at least 15 px
    bg = masked_mean(np.nan_to_num(smooth_db), sea, win)

    # 3. threshold: darker than surroundings by contrast_db AND dark in absolute terms
    dark = sea & ((bg - smooth_db) > s["contrast_db"]) & (smooth_db < s["max_db"])

    # 4. clean up the mask a bit
    dark = ndi.binary_opening(dark, structure=morphology.disk(1))
    dark = ndi.binary_closing(dark, structure=morphology.disk(2))
    dark = ndi.binary_fill_holes(dark)
    px_km2 = scene["px_w_km"] * scene["px_h_km"]
    min_px = max(int(s["min_area_km2"] / px_km2), 10)
    # throw away blobs smaller than min_px
    lab, n = ndi.label(dark)
    if n:
        sizes = np.bincount(lab.ravel())
        keep = sizes >= min_px
        keep[0] = False
        dark = keep[lab]

    return dark, smooth_db, bg, sea, land


# ---------- deciding oil vs look-alike ----------

def score_blob(f, scene_bg_db, scene_sea_km2):
    """simple points system. we chose rules from what papers say oil looks like:
    - oil is MUCH darker than surrounding sea (high contrast)
    - ship spills are long and thin (elongated)
    - oil has sharp edges, calm-wind areas fade out slowly
    - calm wind patches are often huge
    returns (score, label, reasons)"""
    pts = 0
    why = []

    if f["contrast_db"] >= 6:
        pts += 2; why.append("very dark vs sea (+2)")
    elif f["contrast_db"] >= 4:
        pts += 1; why.append("dark vs sea (+1)")

    if f["elongation"] >= 3:
        pts += 2; why.append("long & thin like a ship trail (+2)")
    elif f["elongation"] >= 1.8:
        pts += 1; why.append("stretched shape (+1)")

    if f["edge_sharpness"] >= 0.9:
        pts += 1; why.append("sharp edges (+1)")
    elif f["edge_sharpness"] < 0.45:
        pts -= 1; why.append("fuzzy edges, could be calm wind (-1)")

    if f["area_km2"] > 0.25 * scene_sea_km2:
        pts -= 3; why.append("covers huge part of scene, probably low wind (-3)")

    # sea below about -22 dB means wind is very low (< ~3 m/s), whole scene is unreliable
    if scene_bg_db < -22:
        pts -= 1; why.append("very calm sea overall, hard to tell (-1)")

    if pts >= 4:
        label = "likely oil"
    elif pts >= 2:
        label = "possible oil"
    else:
        label = "probably look-alike"
    return pts, label, why


def describe_blobs(dark, smooth_db, bg, sea, scene):
    lab = measure.label(dark, connectivity=2)
    props = measure.regionprops(lab, intensity_image=np.nan_to_num(smooth_db, nan=0))
    px_km2 = scene["px_w_km"] * scene["px_h_km"]
    scene_bg_db = float(np.nanmedian(smooth_db[sea])) if sea.any() else float("nan")
    scene_sea_km2 = sea.sum() * px_km2

    # edge strength image (sobel in dB). normalised later by contrast
    grad = filters.sobel(np.nan_to_num(smooth_db, nan=scene_bg_db))

    out = []
    for p in props:
        mask = lab == p.label
        # ring around the blob = "nearby sea"
        ring = ndi.binary_dilation(mask, iterations=6) & ~ndi.binary_dilation(mask, iterations=2) & sea
        inner = float(np.nanmean(smooth_db[mask]))
        outer = float(np.nanmean(smooth_db[ring])) if ring.any() else float(np.nanmean(bg[mask]))
        contrast = outer - inner

        edge = mask & ~ndi.binary_erosion(mask)
        edge_grad = float(grad[edge].mean()) if edge.any() else 0.0
        # sobel of a step of size C ~ C/4 per pixel, so this is roughly 1 for a clean sharp edge
        sharp = edge_grad / (contrast / 4 + 1e-6) if contrast > 0 else 0

        # names changed between scikit-image versions, so try both
        major = getattr(p, "axis_major_length", None) or p.major_axis_length
        minor = max(getattr(p, "axis_minor_length", None) or p.minor_axis_length, 1.0)
        f = {
            "area_km2": p.area * px_km2,
            "mean_db": inner,
            "contrast_db": contrast,
            "elongation": major / minor,
            "complexity": p.perimeter / (2 * np.sqrt(np.pi * p.area)),
            "edge_sharpness": float(sharp),
            "length_km": major * scene["px_w_km"],
        }
        pts, label, why = score_blob(f, scene_bg_db, scene_sea_km2)
        cy, cx = p.centroid
        lon, lat = scene["lonlat"](cy, cx)

        # outline for the map
        contours = measure.find_contours(np.pad(mask, 1).astype(float), 0.5)
        biggest = max(contours, key=len) - 1   # undo pad
        biggest = biggest[:: max(1, len(biggest) // 300)]  # dont need 5000 points
        plon, plat = scene["lonlat"](biggest[:, 0], biggest[:, 1])
        ring_coords = [[float(a), float(b)] for a, b in zip(plon, plat)]
        ring_coords.append(ring_coords[0])

        f.update({"score": pts, "label": label, "reasons": why,
                  "lat": float(lat), "lon": float(lon),
                  "outline": ring_coords, "pixel_outline": biggest})
        out.append(f)

    out.sort(key=lambda d: (-d["score"], -d["area_km2"]))
    for i, d in enumerate(out, 1):
        d["id"] = i
    return out, scene_bg_db


def analyse(scene, settings=None):
    dark, smooth_db, bg, sea, land = find_dark_spots(scene, settings)
    blobs, scene_bg = describe_blobs(dark, smooth_db, bg, sea, scene)

    warnings = []
    if scene_bg < -22:
        warnings.append("Sea is very calm in this image (low wind). Calm water also looks dark, "
                        "so results here are not reliable.")
    if scene_bg > -10:
        warnings.append("Sea is very rough/bright (strong wind). Oil gets mixed into the water "
                        "above ~10-12 m/s wind and may not show up.")
    if land.mean() > 0.6:
        warnings.append("Most of this area is land. Pick a box over the sea.")

    return {"blobs": blobs, "dark_mask": dark, "smooth_db": smooth_db,
            "land": land, "scene_bg_db": scene_bg, "warnings": warnings}


# ---------- outputs ----------

COLOURS = {"likely oil": "#e63b2e", "possible oil": "#f2a516", "probably look-alike": "#3d8bd9"}


def make_figure(scene, result, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    db = result["smooth_db"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), sharex=True, sharey=True)
    for ax in axes:
        ax.imshow(db, cmap="gray", vmin=-28, vmax=-8)
        ax.set_xticks([]); ax.set_yticks([])
    land = np.ma.masked_where(~result["land"], result["land"])
    axes[0].imshow(land, cmap="Greens", alpha=0.35, vmin=0, vmax=1.5)
    axes[0].set_title("Radar image (VV, dB) - dark = smooth water")

    axes[1].imshow(land, cmap="Greens", alpha=0.35, vmin=0, vmax=1.5)
    for b in result["blobs"]:
        pts = b["pixel_outline"]
        c = COLOURS[b["label"]]
        axes[1].plot(pts[:, 1], pts[:, 0], color=c, lw=1.6)
        cy, cx = pts[:, 0].mean(), pts[:, 1].mean()
        axes[1].text(cx, cy, str(b["id"]), color="white", fontsize=9, weight="bold",
                     ha="center", va="center",
                     bbox=dict(boxstyle="round,pad=0.15", fc=c, ec="none", alpha=0.85))
    axes[1].set_title("Detections")
    handles = [plt.Line2D([], [], color=c, lw=3, label=k) for k, c in COLOURS.items()]
    axes[1].legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.8)
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    return fig


def to_geojson(result, meta=None):
    feats = []
    for b in result["blobs"]:
        props = {k: (round(v, 3) if isinstance(v, float) else v)
                 for k, v in b.items() if k not in ("outline", "pixel_outline")}
        props["reasons"] = "; ".join(b["reasons"])
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": [b["outline"]]}})
    return {"type": "FeatureCollection", "features": feats, "properties": meta or {}}


def summary_rows(result):
    rows = []
    for b in result["blobs"]:
        rows.append({
            "#": b["id"], "verdict": b["label"], "score": b["score"],
            "area (km²)": round(b["area_km2"], 2), "length (km)": round(b["length_km"], 1),
            "contrast (dB)": round(b["contrast_db"], 1), "elongation": round(b["elongation"], 1),
            "edge": round(b["edge_sharpness"], 2),
            "lat": round(b["lat"], 4), "lon": round(b["lon"], 4),
            "why": "; ".join(b["reasons"]),
        })
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python detect.py scene.tif")
        sys.exit(1)
    path = sys.argv[1]
    sc = load_geotiff(path)
    res = analyse(sc)
    print(f"sea background: {res['scene_bg_db']:.1f} dB, pixel ~{sc['px_w_km']*1000:.0f} m")
    for w in res["warnings"]:
        print("WARNING:", w)
    for r in summary_rows(res):
        print(f"  #{r['#']:<3} {r['verdict']:<20} {r['area (km²)']:>8} km2  contrast {r['contrast (dB)']} dB  "
              f"elong {r['elongation']}  edge {r['edge']}  ({r['lat']}, {r['lon']})")
    out = path.rsplit(".", 1)[0]
    make_figure(sc, res, path).savefig(out + "_result.png", dpi=130)
    with open(out + "_result.geojson", "w") as fh:
        json.dump(to_geojson(res), fh)
    print("saved", out + "_result.png and .geojson")
