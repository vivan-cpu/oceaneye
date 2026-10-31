# OilWatch

Spotting oil spills at sea from free satellite radar images.
YCL 2026 (Plaksha University) - theme: **Water Security**

Team: _(add names)_  ·  School: _(add)_

**Website (try it in your browser):** https://vivan-cpu.github.io/oilwatch/

---

## What it does

Pick an area of sea and a date. The program downloads the Sentinel-1 radar image for that day
from ESA's Copernicus service (free), finds dark patches that could be oil, decides how
likely each one is to really be oil, and shows them on a map with their size in km².

Why radar and not normal photos? Radar works through clouds and at night. During monsoon
(when the Kerala ship sank in 2025) normal satellite photos are mostly just clouds.

There is also a physical model (`hardware/ripple_tank/`) that shows the science on a table.

## Folder

```
index.html, web/     the website (same detection rewritten in javascript, runs in the browser)
app.py               the full app (opens in your browser, runs on your own laptop)
detect.py            the detection logic - the main part
fetch.py             downloads images from Copernicus
places.py            preset areas (real spills + Indian oil fields)
make_test_scene.py   makes a fake radar image for testing without internet
hardware/            ripple tank model (ESP32 code + build guide)
docs/                how it works, sources, video plan
cache/               downloaded images get saved here
```

## Setup (about 15 min, once)

**1. Python stuff**

Install Python 3.10 or newer (python.org, tick "Add to PATH" on Windows). Then in this folder:

```
pip install -r requirements.txt
```

**2. Free Copernicus account** (needed only for live download, not for the test scene)

1. Sign up at https://dataspace.copernicus.eu (free, needs an email).
2. Go to https://shapps.dataspace.copernicus.eu/dashboard/ -> User settings -> OAuth clients -> **+ Create**.
3. Copy the client ID and secret (the secret is shown only once!).
4. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste them in.

The free account gives 10,000 "processing units" a month. One 40 m image of a
60×60 km box uses roughly 10-30, so we can do hundreds of runs. Re-running the same
image costs nothing because it's saved in `cache/`.

**3. Run**

```
streamlit run app.py
```

It opens at http://localhost:8501. Nothing is published online.

Quick test without internet: choose **Test scene** and press Run detection.
From the command line: `python detect.py some_image.tif`

## Using it

1. Choose an area (e.g. *Kerch Strait - Dec 2024*), keep the dates, click **Find satellite passes**.
2. Pick a date from the list, press **Run detection**.
3. Red = likely oil, orange = possible, blue = probably a look-alike. The table says *why* for each one.
4. Download the GeoJSON and open it in Google Earth or QGIS if you want.

Good first tries: Kerch Strait 18 or 19 Dec 2024; Oil Rocks (Caspian) any date.

## Limits (be honest about these in the interview)

- Calm sea (wind below ~3 m/s), rain cells, algae films and ship wakes can also look dark.
  We reduce false alarms with shape/contrast rules but a person must still check.
- Very strong wind (above ~10-12 m/s) mixes oil into the water so it can disappear from radar.
- Sentinel-1 passes each place only every few days, so it's for checking, not instant alarms.
- Rules were tuned on a few cases, not proven on hundreds. Next step would be training a
  machine-learning model on a labelled dataset.

Contains modified Copernicus Sentinel data.
