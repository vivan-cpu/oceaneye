"""
OceanEye - "Camera & photo check" tab

Ground-level check of the water with a camera, a photo or the phone light sensor:
  Stage 1 (rules)  crude_detect.py finds DARK (thick crude) and SHEEN (thin film) patches
  Stage 2 (AI)     oil_model.pkl (from train_model.py) gives an oil probability per patch
Then it can be checked against the Sentinel-1 result from the "Scan the sea" tab.

Used from app.py:   with tab_ground: ground_check.render()
"""
import datetime as dt
import json
import ipaddress
import math
import os
import urllib.parse
import urllib.request

import cv2
import numpy as np
import pandas as pd
import streamlit as st

import crude_detect as crude

NEAR_KM = 5          # satellite slick within this distance of the spot counts as a match
SCAN_BOX_DEG = 0.15  # half-size of the scan box made around a spot (~30 km box)
SENSOR_CHANGE = 20   # % light change that counts as a sensor spill


# ======================= pure logic (no UI) =======================
@st.cache_resource(show_spinner=False)
def get_model():
    return crude.load_model()


def decode_image(uploaded):
    data = np.frombuffer(uploaded.getvalue(), np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def load_example(kind):
    """The two example photos that come with the repo (openly licensed, from Wikimedia Commons)."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "web", "examples", "examples.json")) as f:
            ex = json.load(f)[kind]
        img = cv2.imread(os.path.join(here, ex["file"].replace("/", os.sep)))
    except (OSError, KeyError, ValueError):
        return None
    if img is None:
        return None
    return img, f"Example photo: {ex['title']} by {ex['author']} ({ex['licence']}). {ex['page']}"


def analyse_image(img, model, width_cm=None, height_cm=None):
    """Run both stages and return a plain dict for display/saving."""
    img = crude.to_work_size(img)
    patches = crude.analyse(img, model)
    annotated, status = crude.draw(img, patches, model)
    total = img.shape[0] * img.shape[1]
    cm2_px = (width_cm * height_cm / total) if width_cm and height_cm else None

    rows = []
    for i, p in enumerate(patches, 1):
        a = float(p["area"])
        rows.append({
            "#": i,
            "type": p["kind"],
            "verdict": p["verdict"],
            "AI oil %": round(p["prob"] * 100) if p["prob"] is not None else None,
            "area (% of view)": round(100 * a / total, 2),
            "area (cm²)": round(a * cm2_px, 1) if cm2_px else None,
        })
    kept = [r for r in rows if r["verdict"] != "AI REJECTED"]
    probs = [r["AI oil %"] for r in kept if r["AI oil %"] is not None]
    pct = sum(r["area (% of view)"] for r in kept)
    return {
        "status": status,
        "is_spill": status != "CLEAR",
        "annotated": annotated,
        "rows": rows,
        "area_pct": round(pct, 2),
        "area_cm2": round(pct / 100 * width_cm * height_cm, 1) if cm2_px else None,
        "ai_conf": max(probs) if probs else None,
    }


def km_between(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []


def satellite_check(lat, lon, out):
    """Compare a ground spot with the Sentinel-1 result (ss.out from app.py)."""
    (s, w), (n, e) = out["bounds"]
    if not (s <= lat <= n and w <= lon <= e):
        return "OUTSIDE", "The satellite image doesn't cover this spot. Scan an area around it first.", None

    best = None
    for f in out["geojson"]["features"]:
        label = f["properties"]["label"]
        for ring in _rings(f["geometry"]):
            for x, y in ring:
                d = km_between(lat, lon, y, x)
                if best is None or d < best[0]:
                    best = (d, label, f["properties"].get("id"))

    if best is None or best[0] > NEAR_KM:
        return ("NOT CONFIRMED",
                f"The satellite saw no slick within {NEAR_KM} km of this spot.", best)
    d, label, fid = best
    if label == "likely oil":
        return "CONFIRMED", f"Satellite detection #{fid} ({label}) is {d:.1f} km away.", best
    if label == "possible oil":
        return "PARTLY CONFIRMED", f"Satellite detection #{fid} ({label}) is {d:.1f} km away.", best
    return ("NOT CONFIRMED",
            f"The nearest satellite patch (#{fid}, {d:.1f} km) is probably a look-alike.", best)


HOME_NETWORKS = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]


def check_home_network(url):
    """The online app runs on someone else's server, so it must not fetch whatever address a visitor
    types. Only the three standard home-network ranges are allowed (a phone's address on wifi).
    Everything else is refused, including 127.x and 169.254.x (cloud servers keep secrets there)."""
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("Use the phone's number address, like 192.168.1.5:8080")
    if not any(ip in net for net in HOME_NETWORKS):
        raise ValueError("That isn't a home-network address (it should start with 192.168, 10. or 172.16 to 172.31).")


def read_phyphox_lux(address):
    url = address if address.startswith("http") else "http://" + address
    url = url.rstrip("/")
    check_home_network(url)
    try:
        urllib.request.urlopen(url + "/control?cmd=start", timeout=2)
    except Exception:
        pass
    with urllib.request.urlopen(url + "/get?illum", timeout=3) as r:
        data = json.loads(r.read().decode())
    vals = [v for v in data["buffer"]["illum"]["buffer"] if v is not None]
    if not vals:
        raise ValueError("Phyphox sent no light readings yet - press play in the app.")
    return float(vals[-1])


KNOWN_STATUS = {"OIL SPILL CONFIRMED", "POSSIBLE SPILL - AI UNSURE", "POSSIBLE SPILL (no AI yet)",
                "POSSIBLE SPILL (sensor)", "CLEAR"}


def _qstatus(v):
    return v if v in KNOWN_STATUS else None


def _num(text, allow_negative=False):
    """Reads a number typed in a text box. Empty or not a number gives None."""
    try:
        v = float(str(text).strip().replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(v) or (v <= 0 and not allow_negative):
        return None
    return v


def _qfloat(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _qdate(v):
    try:
        return dt.date.fromisoformat(v) if v else None
    except ValueError:
        return None


# ======================= UI =======================
def _show_result(res):
    colour = "red" if "CONFIRMED" in res["status"] else ("orange" if res["is_spill"] else "green")
    st.markdown(f"### :{colour}[{res['status']}]")
    c1, c2, c3 = st.columns(3)
    area = f"{res['area_cm2']} cm²" if res["area_cm2"] is not None else f"{res['area_pct']}% of view"
    c1.metric("Spill area", area)
    c2.metric("AI confidence", f"{res['ai_conf']}%" if res["ai_conf"] is not None else "—")
    c3.metric("Patches checked", len(res["rows"]))
    st.image(res["annotated"], channels="BGR", width="stretch")
    if res["rows"]:
        st.dataframe(pd.DataFrame(res["rows"]), hide_index=True, width="stretch")
    st.caption("Red = both stages say oil · Orange = rules only / AI unsure · "
               "Grey = AI says it's not oil (shadow, rock, weed...)")


def _sensor_ui(ss):
    st.caption("Phyphox app → Light → ⋮ → Allow remote access. Only works when this app "
               "runs on a laptop on the **same Wi-Fi** as the phone (not the online version).")
    addr = st.text_input("Phyphox address", key="gc_addr", placeholder="192.168.1.5:8080")
    c1, c2 = st.columns(2)
    if c1.button("Save clean-water reading", width="stretch", disabled=not addr):
        try:
            ss.gc_baseline = read_phyphox_lux(addr)
        except Exception as e:
            st.error(f"Couldn't reach the phone: {e}")
    check = c2.button("Check now", type="primary", width="stretch", disabled=not addr)
    base = ss.get("gc_baseline")
    if base is not None:
        st.caption(f"Clean water = {base:.0f} lux")
    if check:
        if base is None:
            st.warning("Save a clean-water reading first.")
            return None
        try:
            lux = read_phyphox_lux(addr)
        except Exception as e:
            st.error(f"Couldn't reach the phone: {e}")
            return None
        change = abs(lux - base) / max(base, 1) * 100
        spill = change > SENSOR_CHANGE
        return {"status": "POSSIBLE SPILL (sensor)" if spill else "CLEAR",
                "is_spill": spill, "lux": lux, "change": change}
    return None


def render():
    ss = st.session_state
    model = get_model()

    # opened from the website's "Confirm with the satellite" link?
    qp = st.query_params
    q_lat, q_lon, q_date = _qfloat(qp.get("lat")), _qfloat(qp.get("lon")), _qdate(qp.get("date"))
    q_ground = _qstatus(qp.get("ground"))
    if q_ground and "ground" not in ss:
        ss.ground = {"status": q_ground, "is_spill": q_ground != "CLEAR",
                     "area_cm2": None, "area_pct": None, "ai_conf": None, "method": "website",
                     "lat": q_lat, "lon": q_lon,
                     "date": (q_date or dt.date.today()).isoformat()}
    if q_ground:
        st.success("Opened from the website: the ground check is filled in below. "
                   "Scroll down to **Confirm with the satellite**.")

    st.markdown("Check water **from the ground** - a phone or laptop camera, a photo, or the phone's "
                "light sensor. Then compare it with what the **satellite** saw at the same place.")
    if model is None:
        st.info("The AI model file wasn't found, so only Stage 1 (rules) is used.")
    else:
        st.caption("AI model: " + (crude.MODEL_SUMMARY or "loaded") + ".")

    st.caption("On a phone or tablet the [website version](https://vivan-cpu.github.io/oceaneye/#ground) "
               "of this check is quicker and works without this app. It does the same check.")
    left, right = st.columns([1, 1.6], gap="large")

    with left:
        method = st.radio("How do you want to check?",
                          ["Camera", "Photo", "Light sensor"],
                          horizontal=True, key="gc_method")
        img = None
        sensor_res = None
        if method == "Camera":
            shot = st.camera_input("Point at the water and take a picture", key="gc_cam")
            if shot is not None:
                img = decode_image(shot)
                if img is None:
                    st.error("Couldn't read that picture.")
        elif method == "Photo":
            e1, e2 = st.columns(2)
            if e1.button("Example: oil on water", width="stretch"):
                ss.gc_example = "oil"
            if e2.button("Example: clean water", width="stretch"):
                ss.gc_example = "clean"
            f = st.file_uploader("Or drop a photo of the water here", type=["jpg", "jpeg", "png", "webp"], key="gc_photo")
            if f is not None:
                ss.pop("gc_example", None)
                img = decode_image(f)
                if img is None:
                    st.error("Couldn't read that image - try a JPG or PNG.")
            elif ss.get("gc_example") in ("oil", "clean"):
                ex = load_example(ss.gc_example)
                if ex is not None:
                    img, credit = ex
                    st.caption(credit)
        else:
            sensor_res = _sensor_ui(ss)

        with st.expander("Real size of the view (for area in cm²)"):
            w_cm = _num(st.text_input("Width (cm)", key="gc_w", placeholder="e.g. 40"))
            h_cm = _num(st.text_input("Height (cm)", key="gc_h", placeholder="e.g. 30"))
            st.caption("e.g. the tray is 40 × 30 cm. Leave empty to show % of the picture instead.")

        with st.expander("Where and when (for the satellite check)", expanded=True):
            c1, c2 = st.columns(2)
            if q_lat is not None and "gc_lat" not in ss:
                ss.gc_lat = str(q_lat)
            if q_lon is not None and "gc_lon" not in ss:
                ss.gc_lon = str(q_lon)
            lat = _num(c1.text_input("Latitude", key="gc_lat", placeholder="e.g. 22.47"), allow_negative=True)
            lon = _num(c2.text_input("Longitude", key="gc_lon", placeholder="e.g. 69.62"), allow_negative=True)
            when = st.date_input("Date seen", value=q_date or dt.date.today(), key="gc_date")

    with right:
        if img is not None:
            with st.spinner("checking the water..."):
                res = analyse_image(img, model, w_cm, h_cm)
            _show_result(res)
            ss.ground = {"status": res["status"], "is_spill": res["is_spill"],
                         "area_cm2": res["area_cm2"], "area_pct": res["area_pct"],
                         "ai_conf": res["ai_conf"], "method": method,
                         "lat": lat, "lon": lon, "date": when.isoformat()}
        elif sensor_res is not None:
            colour = "orange" if sensor_res["is_spill"] else "green"
            st.markdown(f"### :{colour}[{sensor_res['status']}]")
            c1, c2 = st.columns(2)
            c1.metric("Light now", f"{sensor_res['lux']:.0f} lux")
            c2.metric("Change", f"{sensor_res['change']:.0f}%")
            ss.ground = {"status": sensor_res["status"], "is_spill": sensor_res["is_spill"],
                         "area_cm2": None, "area_pct": None, "ai_conf": None, "method": method,
                         "lat": lat, "lon": lon, "date": when.isoformat()}
        else:
            st.info("Take a picture, upload a photo or read the sensor - the result shows here.")

    # ---------------- satellite confirmation ----------------
    st.divider()
    st.subheader("Confirm with the satellite")
    g = ss.get("ground")
    if not g:
        st.caption("Do a camera, photo or sensor check first.")
        return

    st.write(f"Ground check: **{g['status']}** ({g['method']}, {g['date']})")
    if g["lat"] is None or g["lon"] is None:
        st.caption("Add the latitude and longitude above to compare with the satellite.")
        return

    if st.button("Set the satellite scan to this spot", width="content"):
        lat, lon = g["lat"], g["lon"]
        ss.bbox = (round(lon - SCAN_BOX_DEG, 3), round(lat - SCAN_BOX_DEG, 3),
                   round(lon + SCAN_BOX_DEG, 3), round(lat + SCAN_BOX_DEG, 3))
        day = dt.date.fromisoformat(g["date"])
        ss.d_from = day - dt.timedelta(days=6)
        ss.d_to = day + dt.timedelta(days=6)
        ss.pop("passes", None)
        ss.map_key = ss.get("map_key", 0) + 1
        ss.gc_scan_set = True
        st.rerun()
    if ss.pop("gc_scan_set", False):
        st.success("Done. Open **Scan the sea**, choose **Live satellite**, then "
                   "① Find passes → pick the closest date → ③ Run detection. Come back here after.")

    out = ss.get("out")
    if not out:
        st.caption("No satellite result yet - run a scan in **Scan the sea**.")
        return

    verdict, detail, _ = satellite_check(g["lat"], g["lon"], out)
    colours = {"CONFIRMED": "red", "PARTLY CONFIRMED": "orange",
               "NOT CONFIRMED": "green", "OUTSIDE": "gray"}
    st.markdown(f"### :{colours[verdict]}[{verdict}]")
    st.write(detail)
    st.caption(f"Compared with: {out['label']}. Satellite passes are days apart and oil drifts, "
               "so a mismatch can be timing - a person should always check.")
