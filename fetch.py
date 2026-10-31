"""
fetch.py - downloads Sentinel-1 radar images from Copernicus Data Space (free).

You need a free account + an "OAuth client" (see README step 2).
Put the id/secret in .streamlit/secrets.toml or as environment variables:
    CDSE_CLIENT_ID=...
    CDSE_CLIENT_SECRET=...

Every image we download is saved in cache/ so we don't use up our monthly
quota downloading the same thing again (and so the demo works offline).
"""
import os
import json
import time
import math
import hashlib
import requests

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(CACHE, exist_ok=True)

_token = {"value": None, "expires": 0}


def get_credentials():
    cid = os.environ.get("CDSE_CLIENT_ID")
    sec = os.environ.get("CDSE_CLIENT_SECRET")
    if not (cid and sec):
        try:
            import streamlit as st
            cid = st.secrets.get("CDSE_CLIENT_ID")
            sec = st.secrets.get("CDSE_CLIENT_SECRET")
        except Exception:
            pass
    return cid, sec


def get_token():
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    cid, sec = get_credentials()
    if not cid:
        raise RuntimeError("No Copernicus login found. Add CDSE_CLIENT_ID and CDSE_CLIENT_SECRET "
                           "to .streamlit/secrets.toml (see README).")
    r = requests.post(TOKEN_URL, data={"grant_type": "client_credentials",
                                       "client_id": cid, "client_secret": sec}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Login to Copernicus failed ({r.status_code}): {r.text[:200]}")
    j = r.json()
    _token["value"] = j["access_token"]
    _token["expires"] = time.time() + j.get("expires_in", 600)
    return _token["value"]


def find_passes(bbox, date_from, date_to, limit=60):
    """which days did Sentinel-1 fly over this box? returns list of (datetime_str, orbit_direction)"""
    body = {
        "bbox": list(bbox),
        "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
        "collections": ["sentinel-1-grd"],
        "limit": limit,
        "filter": "sar:instrument_mode = 'IW'",
        "filter-lang": "cql2-text",
    }
    r = requests.post(CATALOG_URL, json=body, timeout=60,
                      headers={"Authorization": f"Bearer {get_token()}"})
    if r.status_code != 200:
        # some versions dont like the filter, try again without it
        body.pop("filter"); body.pop("filter-lang")
        r = requests.post(CATALOG_URL, json=body, timeout=60,
                          headers={"Authorization": f"Bearer {get_token()}"})
    r.raise_for_status()
    seen = {}
    for f in r.json().get("features", []):
        p = f.get("properties", {})
        dt = p.get("datetime", "")[:19]
        day = dt[:10]
        # one satellite pass = several "tiles" with almost the same time, keep one per day
        if day not in seen:
            seen[day] = (dt, p.get("sat:orbit_state", "?"))
    return [seen[d] for d in sorted(seen, reverse=True)]


def image_size(bbox, res_m):
    """width/height in pixels for a lon/lat box at roughly res_m metres per pixel.
    sentinel hub allows max 2500 px each side."""
    w_km = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    h_km = (bbox[3] - bbox[1]) * 110.57
    w = int(w_km * 1000 / res_m)
    h = int(h_km * 1000 / res_m)
    scale = max(w / 2500, h / 2500, 1)
    return max(int(w / scale), 64), max(int(h / scale), 64)


EVAL_S1 = """//VERSION=3
function setup() {
  return {
    input: [{bands: ["VV", "dataMask"]}],
    output: {bands: 2, sampleType: "FLOAT32"}
  };
}
function evaluatePixel(s) {
  return [s.VV, s.dataMask];
}
"""

EVAL_S2 = """//VERSION=3
function setup() {
  return {input: ["B04", "B03", "B02", "dataMask"], output: {bands: 4}};
}
function evaluatePixel(s) {
  let g = 2.8;
  return [g * s.B04, g * s.B03, g * s.B02, s.dataMask];
}
"""


def _cached_post(body, ext):
    key = hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    path = os.path.join(CACHE, f"{key}.{ext}")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path, True
    r = requests.post(PROCESS_URL, json=body, timeout=180,
                      headers={"Authorization": f"Bearer {get_token()}"})
    if r.status_code != 200:
        raise RuntimeError(f"Copernicus said {r.status_code}: {r.text[:300]}")
    with open(path, "wb") as fh:
        fh.write(r.content)
    return path, False


def download_s1(bbox, day, res_m=40):
    """downloads the VV radar image (sigma0, linear) for one day. returns (path, from_cache)"""
    w, h = image_size(bbox, res_m)
    body = {
        "input": {
            "bounds": {"bbox": list(bbox),
                       "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {
                    "timeRange": {"from": f"{day}T00:00:00Z", "to": f"{day}T23:59:59Z"},
                    "acquisitionMode": "IW",
                    "resolution": "HIGH",
                    "mosaickingOrder": "mostRecent",
                },
                "processing": {
                    "backCoeff": "SIGMA0_ELLIPSOID",   # sigma0 is what most oil papers use
                    "orthorectify": True,
                    "demInstance": "COPERNICUS_30",
                    "speckleFilter": {"type": "NONE"},  # we do our own lee filter
                },
            }],
        },
        "output": {"width": w, "height": h,
                   "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": EVAL_S1,
    }
    return _cached_post(body, "tif")


def download_s2(bbox, day, days_around=3, max_cloud=60):
    """normal colour photo from Sentinel-2 near the same date, just to look at.
    (often cloudy, and oil is hard to see in normal photos - that's why we use radar)"""
    import datetime as dt
    d = dt.date.fromisoformat(day)
    a = (d - dt.timedelta(days=days_around)).isoformat()
    b = (d + dt.timedelta(days=days_around)).isoformat()
    w, h = image_size(bbox, 40)
    body = {
        "input": {
            "bounds": {"bbox": list(bbox),
                       "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{"type": "sentinel-2-l2a",
                      "dataFilter": {"timeRange": {"from": f"{a}T00:00:00Z", "to": f"{b}T23:59:59Z"},
                                     "maxCloudCoverage": max_cloud,
                                     "mosaickingOrder": "leastCC"}}],
        },
        "output": {"width": w, "height": h,
                   "responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": EVAL_S2,
    }
    return _cached_post(body, "png")


if __name__ == "__main__":
    # quick test:  python fetch.py
    box = (36.3, 44.75, 37.3, 45.35)   # kerch strait
    print(find_passes(box, "2024-12-17", "2024-12-31"))
