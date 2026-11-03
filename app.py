"""
OceanEye - spotting oil spills from space with free Sentinel-1 radar images

run it with:
    streamlit run app.py
"""
import os
import io
import sys
import json
import math
import base64
import subprocess
import datetime as dt

import pandas as pd
import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium

import detect
import fetch
from places import PLACES
import ground_check

ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "img", "favicon-192.png")
st.set_page_config(page_title="OceanEye", page_icon=ICON, layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
h1 {margin-bottom: 0 !important;}
div[data-testid="stMetricValue"] {font-size: 1.7rem;}
</style>
""", unsafe_allow_html=True)

ESRI_SAT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_LABELS = "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Esri, Maxar, Earthstar Geographics"

HERE = os.path.dirname(os.path.abspath(__file__))
HAVE_KEYS = all(fetch.get_credentials())


def add_basemaps(m):
    # carto tiles now want an API key, so plain map = openstreetmap.
    # show=False so the satellite one is the one you see first
    folium.TileLayer(ESRI_SAT, attr=ESRI_ATTR, name="Satellite", overlay=False).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Plain map", overlay=False, show=False).add_to(m)
    folium.TileLayer(ESRI_LABELS, attr=ESRI_ATTR, name="Place names", overlay=True, control=True).add_to(m)


def bbox_bounds(b):
    return [[b[1], b[0]], [b[3], b[2]]]


# ---------------- state ----------------
ss = st.session_state
if "place" not in ss:
    ss.place = list(PLACES.keys())[0]
    p = PLACES[ss.place]
    ss.bbox = tuple(p["bbox"])
    ss.d_from = dt.date.fromisoformat(p["from"])
    ss.d_to = dt.date.fromisoformat(p["to"])


def on_place_change():
    p = PLACES[ss.place]
    ss.bbox = tuple(p["bbox"])
    ss.d_from = dt.date.fromisoformat(p["from"])
    ss.d_to = dt.date.fromisoformat(p["to"])
    ss.pop("passes", None)
    ss.map_key = ss.get("map_key", 0) + 1   # redraw the map centred on the new place


# ---------------- header ----------------
st.title("OceanEye")
st.caption("Spotting oil spills at sea with free Sentinel-1 radar images · YCL 2026 · Water Security")

tab_scan, tab_ground, tab_how = st.tabs(["Scan the sea", "Camera & photo check", "How it works"])

# ground check: camera / photo / light sensor + AI, then compared with the satellite result.
# keep this block here (before the results part below, which calls st.stop())
with tab_ground:
    ground_check.render()

with tab_how:
    st.markdown("""
#### Why radar?
Sentinel-1 is a radar satellite run by ESA. It sends microwaves down at a slant and measures the echo.
It makes its own signal, so it sees **through clouds and at night** (normal satellite photos can't).

#### Why oil looks dark
Wind makes small ripples on the sea. Ripples scatter the radar back, so normal sea looks **grey**.
Oil forms a thin film that flattens the ripples. Flat water reflects the beam away like a mirror,
almost no echo comes back, so **oil looks dark**.

#### What the program does
1. Downloads the VV radar image for your area and date from Copernicus (free).
2. Hides land and 1 km of coast (coasts cause false alarms).
3. Removes radar "speckle" (grainy noise) with a Lee filter.
4. Compares each pixel to the sea around it (~3 km) and marks pixels at least 3 dB darker.
   Then does it again leaving out the dark pixels, so the middle of big slicks is found too.
5. Joins them into patches and scores each one:

| Rule | Points |
|---|---|
| very dark vs sea (≥6 dB / ≥4 dB) | +2 / +1 |
| long and thin like a ship trail (≥3 / ≥1.8) | +2 / +1 |
| sharp edges | +1 |
| fuzzy edges (calm wind fades slowly) | −1 |
| covers > ¼ of the sea (that's weather) | −3 |
| whole sea very calm (< −22 dB) | −1 |

4+ = **likely oil**, 2–3 = **possible**, less = **probably a look-alike**.

#### Checking from the ground (Camera & photo check tab)
Radar from space is the main tool, but someone on a boat, a drone or the coast can also check the water.
1. Stage 1 (rules) finds patches much darker than the water (thick crude) or with rainbow colours (thin film).
2. Stage 2 (AI) gives each patch an oil probability and rejects shadows, rocks and weed. We trained it on 782
   patches from 145 openly licensed photos. On photos it had never seen it found about half of the oil patches
   and wrongly called about 3% of the others oil, so it helps but it isn't reliable yet.
3. If you enter where and when it was seen, the app compares it with the Sentinel-1 result:
   a slick within 5 km of the spot counts as confirmed by satellite.

#### Limits
Calm water (wind < ~3 m/s), rain cells, algae films and ship wakes can also look dark, and very strong wind
can hide oil. Anything flagged should be checked by a person.
The camera AI learned from only 70 patches of oil, mostly thin rainbow films seen up close, and has not been
tested on real spills at sea.
""")

with tab_scan:
    left, right = st.columns([1, 2.2], gap="large")

    # ---------------- controls ----------------
    with left:
        source = st.radio("Image source", ["Live satellite", "Upload GeoTIFF", "Test scene"],
                          horizontal=True, label_visibility="collapsed")
        bbox = ss.bbox
        day = None
        upload = None
        res_m = 40
        want_s2 = False

        if source == "Live satellite":
            if not HAVE_KEYS:
                st.warning("Copernicus keys aren't set up yet, so live download won't work. "
                           "Add CDSE_CLIENT_ID and CDSE_CLIENT_SECRET in the app's Secrets. "
                           "Test scene and upload still work.")
            st.selectbox("Jump to", list(PLACES.keys()), key="place", on_change=on_place_change)
            st.caption(PLACES[ss.place]["note"] + "  \nOr draw your own box on the map with the ▢ tool.")

            c1, c2 = st.columns(2)
            c1.date_input("From", key="d_from")
            c2.date_input("To", key="d_to")

            w_km = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
            h_km = (bbox[3] - bbox[1]) * 110.57
            st.caption(f"Area: {w_km:.0f} × {h_km:.0f} km  ·  "
                       f"{bbox[1]:.2f}°N {bbox[0]:.2f}°E → {bbox[3]:.2f}°N {bbox[2]:.2f}°E")
            if max(w_km, h_km) > 150:
                st.info("Big box - the image will be less sharp. Smaller boxes (under ~100 km) work best.")

            if st.button("① Find satellite passes", width="stretch", disabled=not HAVE_KEYS):
                try:
                    with st.spinner("asking Copernicus..."):
                        ss.passes = fetch.find_passes(bbox, ss.d_from.isoformat(), ss.d_to.isoformat())
                        ss.passes_for = bbox
                    if not ss.passes:
                        st.warning("No Sentinel-1 passes in those dates. Try a longer date range.")
                except Exception as e:
                    st.error(str(e))

            passes = ss.get("passes", [])
            if passes and ss.get("passes_for") == bbox:
                labels = [f"{t[:10]}  ·  {t[11:16]} UTC  ·  {o.lower()}" for t, o in passes]
                pick = st.selectbox(f"② Pick a date ({len(passes)} found)", labels)
                day = pick[:10]
            elif passes:
                st.info("Area changed - find passes again.")

            with st.expander("Options"):
                res_m = st.select_slider("Pixel size (m)", options=[20, 30, 40, 60, 80], value=40,
                                         help="smaller = sharper, but slower and uses more free quota")
                want_s2 = st.checkbox("Also get a normal colour photo (Sentinel-2)")

        elif source == "Upload GeoTIFF":
            st.caption("Don't have a radar file? Use Live satellite (it downloads one for you) or the Test scene.")
            upload = st.file_uploader("Drop a Sentinel-1 radar file here (.tif)", type=["tif", "tiff"])
            with st.expander("What is a GeoTIFF?"):
                st.markdown(
                    "A GeoTIFF is a picture that knows where it is on Earth. A normal photo file is only a grid of "
                    "coloured dots. A GeoTIFF also stores which piece of the Earth the grid covers and how big each "
                    "dot is on the ground, so a computer can put it on a map and measure an area in km².\n\n"
                    "For a radar picture each dot holds a number for how strong the echo was, not a colour. OceanEye "
                    "needs those real numbers, which a screenshot can't give it.\n\n"
                    "To get one yourself: browser.dataspace.copernicus.eu → Sentinel-1 → VV → Download → "
                    "Analytical → TIFF 32-bit.")
        else:
            st.caption("A simulated radar image with an oil trail, a calm-wind patch and a rain cell, "
                       "to check the program works.")

        with st.expander("Detection settings"):
            contrast = st.slider("How much darker than sea (dB)", 1.5, 8.0, detect.SETTINGS["contrast_db"], 0.5)
            min_area = st.slider("Smallest patch (km²)", 0.01, 2.0, detect.SETTINGS["min_area_km2"], 0.01)
            bg_km = st.slider("Background window (km)", 1.0, 10.0, detect.SETTINGS["background_km"], 0.5)
        settings = {"contrast_db": contrast, "min_area_km2": min_area, "background_km": bg_km}

        go = st.button("③ Run detection" if source == "Live satellite" else "Run detection",
                       type="primary", width="stretch")

    # ---------------- area map ----------------
    with right:
        out = ss.get("out")
        if out and out.get("source") == source:
            map_bounds = out["bounds"]
        else:
            map_bounds = bbox_bounds(bbox)
        m = folium.Map(tiles=None, control_scale=True)
        add_basemaps(m)
        m.fit_bounds(map_bounds)

        if source == "Live satellite":
            folium.Rectangle(bbox_bounds(bbox), color="#ffd400", weight=2, fill=False,
                             tooltip="area to scan").add_to(m)
            plugins.Draw(export=False, position="topleft",
                         draw_options={"polyline": False, "polygon": False, "circle": False,
                                       "marker": False, "circlemarker": False,
                                       "rectangle": {"shapeOptions": {"color": "#ffd400"}}},
                         edit_options={"edit": False, "remove": False}).add_to(m)

        if out and out.get("source") == source:
            fg = folium.FeatureGroup(name="Radar image", show=True)
            folium.raster_layers.ImageOverlay(out["overlay"], bounds=out["bounds"], opacity=0.85,
                                              interactive=False, zindex=2).add_to(fg)
            fg.add_to(m)
            if out.get("s2"):
                fg2 = folium.FeatureGroup(name="Sentinel-2 photo", show=False)
                folium.raster_layers.ImageOverlay(out["s2"], bounds=out["bounds"], opacity=1,
                                                  zindex=1).add_to(fg2)
                fg2.add_to(m)
            det = folium.FeatureGroup(name="Detections", show=True)
            for f in out["geojson"]["features"]:
                pr = f["properties"]
                colour = detect.COLOURS[pr["label"]]
                popup = (f"<b>#{pr['id']} {pr['label']}</b><br>area {pr['area_km2']} km² · "
                         f"length {pr['length_km']} km<br>contrast {pr['contrast_db']} dB · "
                         f"elongation {pr['elongation']}<br><small>{pr['reasons']}</small>")
                folium.GeoJson(f, style_function=lambda _, c=colour: {"color": c, "weight": 2.5, "fillOpacity": 0.15},
                               tooltip=f"#{pr['id']} {pr['label']}",
                               popup=folium.Popup(popup, max_width=320)).add_to(det)
            det.add_to(m)

        plugins.Fullscreen(position="topright").add_to(m)
        plugins.MousePosition(position="bottomleft", separator=" , ", num_digits=3, prefix="lat, lon:", empty_string="",
                              lat_formatter="function(n){return n.toFixed(3)}",
                              lng_formatter="function(n){return n.toFixed(3)}").add_to(m)
        folium.LayerControl(collapsed=True).add_to(m)

        res = st_folium(m, height=560, use_container_width=True,
                        key=f"map_{source}_{ss.get('map_key', 0)}",
                        returned_objects=["last_active_drawing"])

        drawn = (res or {}).get("last_active_drawing")
        if source == "Live satellite" and drawn and drawn.get("geometry", {}).get("type") == "Polygon":
            pts = drawn["geometry"]["coordinates"][0]
            lons = [p[0] for p in pts]
            lats = [p[1] for p in pts]
            new = (round(min(lons), 3), round(min(lats), 3), round(max(lons), 3), round(max(lats), 3))
            if new != tuple(ss.bbox) and new[2] > new[0] and new[3] > new[1]:
                ss.bbox = new
                ss.pop("passes", None)
                st.rerun()


# ---------------- work ----------------
@st.cache_data(show_spinner=False, max_entries=20)
def run_on_file(path, settings_json):
    scene = detect.load_geotiff(path)
    res = detect.analyse(scene, json.loads(settings_json))
    fig = detect.make_figure(scene, res)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    h, w = scene["db"].shape
    lon0, lat0 = scene["lonlat"](-0.5, -0.5)
    lon1, lat1 = scene["lonlat"](h - 0.5, w - 0.5)
    ov = "data:image/png;base64," + base64.b64encode(detect.overlay_png(res)).decode()
    return {"png": buf.getvalue(), "rows": detect.summary_rows(res), "geojson": detect.to_geojson(res),
            "warnings": res["warnings"], "bg": res["scene_bg_db"], "px_m": scene["px_w_km"] * 1000,
            "overlay": ov,
            "bounds": [[float(min(lat0, lat1)), float(min(lon0, lon1))],
                       [float(max(lat0, lat1)), float(max(lon0, lon1))]]}


if go:
    try:
        s2 = None
        if source == "Live satellite":
            if not day:
                st.warning("First press ① Find satellite passes and pick a date.")
                st.stop()
            with st.spinner(f"downloading Sentinel-1 image for {day}..."):
                path, _ = fetch.download_s1(bbox, day, res_m)
            if want_s2:
                try:
                    with st.spinner("downloading Sentinel-2 photo..."):
                        p2, _ = fetch.download_s2(bbox, day)
                        s2 = "data:image/png;base64," + base64.b64encode(open(p2, "rb").read()).decode()
                except Exception as e:
                    st.warning(f"Couldn't get Sentinel-2 photo: {e}")
            label = f"Sentinel-1 VV · {day} · {ss.place if PLACES[ss.place]['bbox'] == tuple(bbox) else 'custom area'}"
        elif source == "Upload GeoTIFF":
            if upload is None:
                st.warning("Upload a file first.")
                st.stop()
            path = os.path.join(fetch.CACHE, "upload_" + os.path.basename(upload.name))
            with open(path, "wb") as fh:
                fh.write(upload.getbuffer())
            label = upload.name
        else:
            path = os.path.join(fetch.CACHE, "test_scene.tif")
            if not os.path.exists(path):
                subprocess.run([sys.executable, os.path.join(HERE, "make_test_scene.py")],
                               cwd=fetch.CACHE, check=True)
            label = "Test scene (simulated)"

        with st.spinner("looking for dark patches..."):
            result = dict(run_on_file(path, json.dumps(settings, sort_keys=True)))
        result.update({"label": label, "source": source, "s2": s2})
        ss.out = result
        ss.map_key = ss.get("map_key", 0) + 1
        st.rerun()
    except Exception as e:
        st.error(f"Something went wrong: {e}")


# ---------------- results ----------------
out = ss.get("out")
with tab_scan:
    if not out or out.get("source") != source:
        st.info("Pick an area and date, then run detection. Results show up on the map above and here.")
        st.stop()

    st.divider()
    st.subheader(out["label"])
    for w in out["warnings"]:
        st.warning(w)

    rows = out["rows"]
    n_oil = sum(r["verdict"] == "likely oil" for r in rows)
    n_pos = sum(r["verdict"] == "possible oil" for r in rows)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Likely oil", n_oil)
    c2.metric("Possible oil", n_pos)
    c3.metric("Oil area (km²)", round(sum(r["area (km²)"] for r in rows if r["verdict"] != "probably look-alike"), 2))
    c4.metric("Sea brightness (dB)", round(out["bg"], 1),
              help="-12 to -20 dB is normal windy sea. Below -22 means very calm, results less reliable.")

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"why": st.column_config.TextColumn(width="large")})
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇ GeoJSON (Google Earth / QGIS)", json.dumps(out["geojson"]),
                           file_name="oceaneye_detections.geojson", width="stretch")
        d2.download_button("⬇ Table (CSV)", df.to_csv(index=False), file_name="oceaneye_detections.csv",
                           width="stretch")
        d3.download_button("⬇ Picture (PNG)", out["png"], file_name="oceaneye_result.png", width="stretch")
    else:
        st.success("No dark patches that look like oil.")

    with st.expander("Side-by-side radar picture"):
        st.image(out["png"], width="stretch")

    st.caption(f"Pixel ≈ {out['px_m']:.0f} m · Contains modified Copernicus Sentinel data · "
               "Detections are suggestions and must be checked by a person.")
