# OceanEye

Spotting oil spills at sea from free satellite radar images.
YCL 2026 (Plaksha University) - theme: **Water Security**

Team **OceanEye** · The Galaxy School, Wadi, Rajkot (Gujarat)

- Rian Palan - team leader
- Nivaan Alex - presenter
- Vivan Sojitra - researcher
- Mentor: Toral Dwivedi

**Website (try it in your browser):** https://vivan-cpu.github.io/oceaneye/

**Full app (live satellite images):** https://oceaneye-ycl.streamlit.app

---

## What it does

Pick an area of sea and a date. The program downloads the Sentinel-1 radar image for that day
from ESA's Copernicus service (free), finds dark patches that could be oil, decides how
likely each one is to really be oil, and shows them on a map with their size in km².

Why radar and not normal photos? Radar works through clouds and at night. During monsoon
(when the Kerala ship sank in 2025) normal satellite photos are mostly just clouds.

There is also a physical model (`hardware/ripple_tank/`) that shows the science on a table.

**Camera & photo check.** A second tab checks water from the ground with a phone or laptop camera, a photo,
or a phone's light sensor (Phyphox app). Rules find dark or rainbow-coloured patches. A small AI model is
meant to give each one an oil probability, but it is **not trained yet** (it needs labelled photos), so for
now only the rules run. The app can compare the spot with the Sentinel-1 result: a slick within 5 km counts
as confirmed by satellite. Area is shown in cm² if you enter the real size of the camera's view. The same
camera and photo check also runs on the website (in the browser, nothing uploaded), and its "Confirm with
the satellite" button opens the full app with the spot filled in. It has not been tested on real spills.

## Folder

```
index.html, web/     the website (same detection rewritten in javascript, runs in the browser)
app.py               the full app (opens in your browser, runs on your own laptop)
detect.py            the detection logic - the main part
fetch.py             downloads images from Copernicus
places.py            preset areas (real spills + Indian oil fields)
make_test_scene.py   makes a fake radar image for testing without internet
ground_check.py      the "Camera & photo check" tab (camera, photo, light sensor, satellite confirm)
crude_detect.py      camera/photo detection: stage 1 rules + stage 2 AI
train_model.py       trains the AI (makes oil_model.pkl + web/oil_model.json for the website)
web/ground-core.js   the camera/photo check rewritten in javascript (same maths as crude_detect.py)
web/ground.js        the website's "Check from the ground" section
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

Good first tries: Oil Rocks (Caspian) 17 Oct 2026 (huge slick); Kerch Strait 18 or 19 Dec 2024
(harder, the slicks there are faint).

## Training the camera AI

1. Put 40+ photos of water in a folder called `photos/` - with oil (cooking oil stirred with cocoa powder
   looks like crude) and without (leaves, stones, shadows, dark cloth).
2. `python3 crude_detect.py --image photos/*.jpg --save-candidates`
3. Open `candidates/` and drag every picture into `candidates/oil/` or `candidates/not_oil/`.
4. `python3 train_model.py` - prints accuracy, missed oil and false alarms, saves `oil_model.pkl`
   (for the app) and `web/oil_model.json` (the same AI for the website).
5. Push both files to GitHub. The online app and the website then use the AI.

Test on photos the AI has never seen before quoting an accuracy number.

The light sensor only works when the app runs on a laptop on the same Wi-Fi as the phone,
not in the online version.

## Limits (be honest about these in the interview)

- Calm sea (wind below ~3 m/s), rain cells, algae films and ship wakes can also look dark.
  We reduce false alarms with shape/contrast rules but a person must still check.
- Very strong wind (above ~10-12 m/s) mixes oil into the water so it can disappear from radar.
- Sentinel-1 passes each place only every few days, so it's for checking, not instant alarms.
- Satellite rules were tuned on a few cases, not proven on hundreds. Next step would be training a
  machine-learning model on a labelled radar dataset.
- The camera check has not been tested on real spills. Once the AI is trained it will only be as good as the
  photos it learned from, and a tray of dyed oil is a model, not the sea. Satellite passes are days apart and oil drifts, so "not confirmed" can just be timing.

Contains modified Copernicus Sentinel data.
