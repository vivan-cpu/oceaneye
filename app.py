"""
OilWatch - spotting oil spills from space with free Sentinel-1 radar images

run it with:
    streamlit run app.py
"""
import io
import os
import json
import datetime as dt

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

import detect
import fetch
from places import PLACES

st.set_page_config(page_title="OilWatch", page_icon="🛰", layout="wide")

st.title("OilWatch")
st.caption("Finding oil spills at sea using free radar images from the Sentinel-1 satellite (ESA / Copernicus)")

# ---------------- sidebar ----------------
with st.sidebar:
    st.header("1. Pick the image")
    source = st.radio("Where from?", ["Copernicus (download live)", "Upload a GeoTIFF", "Test scene (no internet)"])

    bbox = None
    day = None
    upload = None

    if source == "Copernicus (download live)":
        place = st.selectbox("Area", list(PLACES.keys()))
        p = PLACES[place]
        st.caption(p["note"])
        c1, c2 = st.columns(2)
        west = c1.number_input("West (lon)", value=float(p["bbox"][0]), format="%.3f")
        east = c2.number_input("East (lon)", value=float(p["bbox"][2]), format="%.3f")
        south = c1.number_input("South (lat)", value=float(p["bbox"][1]), format="%.3f")
        north = c2.number_input("North (lat)", value=float(p["bbox"][3]), format="%.3f")
        bbox = (west, south, east, north)
        d_from = st.date_input("From", dt.date.fromisoformat(p["from"]))
        d_to = st.date_input("To", dt.date.fromisoformat(p["to"]))

        if st.button("Find satellite passes"):
            try:
                with st.spinner("asking Copernicus..."):
                    st.session_state["passes"] = fetch.find_passes(bbox, d_from.isoformat(), d_to.isoformat())
                    st.session_state["passes_for"] = bbox
            except Exception as e:
                st.error(str(e))

        passes = st.session_state.get("passes", [])
        if passes and st.session_state.get("passes_for") == bbox:
            labels = [f"{t[:10]}  {t[11:16]} UTC  ({o.lower()})" for t, o in passes]
            pick = st.selectbox(f"{len(passes)} passes found", labels)
            day = pick[:10]
        elif passes:
            st.info("Area changed - click 'Find satellite passes' again.")
        else:
            st.caption("Sentinel-1 passes over most places every 6-12 days.")

        res_m = st.select_slider("Pixel size (m)", options=[20, 30, 40, 60, 80], value=40,
                                 help="smaller = sharper but slower and uses more of the free quota")
        want_s2 = st.checkbox("Also get a normal colour photo (Sentinel-2)", value=False)

    elif source == "Upload a GeoTIFF":
        upload = st.file_uploader("Sentinel-1 VV image (.tif)", type=["tif", "tiff"])
        st.caption("e.g. downloaded from browser.dataspace.copernicus.eu -> Sentinel-1 -> VV, as 32-bit TIFF")
    else:
        st.caption("A fake radar image with an oil trail, a calm-wind patch and a rain cell. "
                   "Used to check the program works.")

    st.header("2. Settings")
    with st.expander("Detection settings"):
        contrast = st.slider("How much darker than sea (dB)", 1.5, 8.0, detect.SETTINGS["contrast_db"], 0.5)
        min_area = st.slider("Smallest slick (km²)", 0.01, 2.0, detect.SETTINGS["min_area_km2"], 0.01)
        bg_km = st.slider("Background window (km)", 1.0, 10.0, detect.SETTINGS["background_km"], 0.5)
    settings = {"contrast_db": contrast, "min_area_km2": min_area, "background_km": bg_km}

    go = st.button("Run detection", type="primary")


# ---------------- work ----------------
@st.cache_data(show_spinner=False)
def run_on_file(path, settings_json):
    scene = detect.load_geotiff(path)
    res = detect.analyse(scene, json.loads(settings_json))
    fig = detect.make_figure(scene, res)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    rows = detect.summary_rows(res)
    gj = detect.to_geojson(res)
    # only return plain stuff so streamlit can cache it
    lon0, lat0 = scene["lonlat"](0, 0)
    lon1, lat1 = scene["lonlat"](scene["db"].shape[0] - 1, scene["db"].shape[1] - 1)
    return {"png": buf.getvalue(), "rows": rows, "geojson": gj, "warnings": res["warnings"],
            "bg": res["scene_bg_db"], "px_m": scene["px_w_km"] * 1000,
            "bounds": [[float(lat1), float(lon0)], [float(lat0), float(lon1)]]}


if go:
    try:
        s2_path = None
        if source == "Copernicus (download live)":
            if not day:
                st.warning("First click 'Find satellite passes' and choose a date.")
                st.stop()
            with st.spinner(f"downloading Sentinel-1 image for {day}..."):
                path, cached = fetch.download_s1(bbox, day, res_m)
            if want_s2:
                try:
                    with st.spinner("downloading Sentinel-2 photo..."):
                        s2_path, _ = fetch.download_s2(bbox, day)
                except Exception as e:
                    st.warning(f"Couldn't get Sentinel-2 photo: {e}")
            label = f"Sentinel-1 VV, {day}"
        elif source == "Upload a GeoTIFF":
            if upload is None:
                st.warning("Upload a file first.")
                st.stop()
            path = os.path.join(fetch.CACHE, "upload_" + upload.name)
            with open(path, "wb") as fh:
                fh.write(upload.getbuffer())
            label = upload.name
        else:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_scene.tif")
            if not os.path.exists(path):
                import subprocess, sys
                subprocess.run([sys.executable, "make_test_scene.py"], cwd=os.path.dirname(path), check=True)
            label = "Test scene (simulated)"

        with st.spinner("looking for dark patches..."):
            out = run_on_file(path, json.dumps(settings, sort_keys=True))
        st.session_state["out"] = out
        st.session_state["label"] = label
        st.session_state["s2"] = s2_path
    except Exception as e:
        st.error(f"Something went wrong: {e}")


# ---------------- show results ----------------
out = st.session_state.get("out")
if not out:
    st.info("Pick an image on the left and press **Run detection**.")
    with st.expander("How does this work?", expanded=True):
        st.markdown("""
Sentinel-1 is a radar satellite. It sends microwaves down and measures how much bounces back.
Wind makes small ripples on the sea, and ripples scatter the radar back, so normal sea looks **grey**.
Oil makes the water surface smooth (it damps the ripples), so the radar bounces away like off a mirror,
and oil looks **dark**.

Radar works through clouds and at night, which normal photos can't do.

The program:
1. removes the grainy noise ("speckle") with a Lee filter
2. compares each pixel to the sea around it and marks pixels that are much darker
3. joins them into patches and measures each one: how dark, how long and thin, how sharp the edges are
4. gives points for things that look like oil (dark, long, sharp edges) and takes away points for
   things that look like calm wind or rain (huge, fuzzy, round)

It is **not perfect**. Calm water, rain, algae and ship wakes can also look dark.
Anything it flags should be checked by a person.
""")
    st.stop()

st.subheader(st.session_state.get("label", ""))
for w in out["warnings"]:
    st.warning(w)

rows = out["rows"]
n_oil = sum(r["verdict"] == "likely oil" for r in rows)
n_pos = sum(r["verdict"] == "possible oil" for r in rows)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Likely oil", n_oil)
c2.metric("Possible oil", n_pos)
c3.metric("Total oil area (km²)", round(sum(r["area (km²)"] for r in rows if r["verdict"] != "probably look-alike"), 2))
c4.metric("Sea brightness (dB)", round(out["bg"], 1), help="around -12 to -20 dB is normal windy sea. "
          "below -22 means very calm, results less reliable")

st.image(out["png"], width="stretch")

if st.session_state.get("s2"):
    st.image(st.session_state["s2"], caption="Sentinel-2 normal colour, closest clear-ish day "
             "(oil is usually hard to see here, which is why we use radar)", width="stretch")

if rows:
    st.markdown("#### Detected patches")
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch")

    st.markdown("#### On the map")
    b = out["bounds"]
    m = folium.Map(location=[(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2], zoom_start=9,
                   tiles="CartoDB positron")
    folium.Rectangle(b, color="#555", weight=1, fill=False, dash_array="4").add_to(m)
    for f in out["geojson"]["features"]:
        pr = f["properties"]
        colour = detect.COLOURS[pr["label"]]
        folium.GeoJson(f, style_function=lambda _, c=colour: {"color": c, "weight": 2, "fillOpacity": 0.35},
                       tooltip=f"#{pr['id']} {pr['label']} - {pr['area_km2']} km²").add_to(m)
    st_folium(m, height=450, use_container_width=True, returned_objects=[])

    c1, c2, c3 = st.columns(3)
    c1.download_button("Download GeoJSON (for Google Earth / QGIS)", json.dumps(out["geojson"]),
                       file_name="oilwatch_detections.geojson")
    c2.download_button("Download table (CSV)", df.to_csv(index=False), file_name="oilwatch_detections.csv")
    c3.download_button("Download picture (PNG)", out["png"], file_name="oilwatch_result.png")
else:
    st.success("No dark patches found that look like oil.")

st.caption(f"Pixel size ≈ {out['px_m']:.0f} m. Contains modified Copernicus Sentinel data. "
           "Detections are suggestions only and must be checked by a person.")
