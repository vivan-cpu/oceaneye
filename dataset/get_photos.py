"""
get_photos.py - downloads openly licensed photos from Wikimedia Commons to train the camera check.

Only photos with these licences are used: public domain, CC0, CC BY, CC BY-SA.
The photos themselves are not kept in the repo (too big, and they belong to their authors).
credits.csv lists every photo that was used: title, author, licence and link.

    python dataset/get_photos.py            (needs internet, writes photos/ and dataset/credits.csv)
"""
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "OceanEyeStudentProject/1.0 (YCL 2026 school project; github.com/vivan-cpu/oceaneye)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "photos")

# what to look for. "oil" = photos where oil is on water. "clean" = water without oil, with the things
# that fool a detector (shadows, reflections, weed, rocks, foam, wakes, glitter)
QUERIES = {
    "oil": [
        "oil slick on sea", "oil spill sea surface", "oil sheen water", "oil spill beach water",
        "oil slick ship aerial", "oil spill close up water", "crude oil floating water",
        "rainbow oil film water", "oil pollution harbour water", "oil on water puddle rainbow",
        "oil spill containment boom water", "fuel oil spill sea", "deepwater horizon oil sea surface",
        "oil spill river", "oil leak water surface",
    ],
    "clean": [
        "water ripples surface", "calm sea surface", "lake surface reflection", "river water dark",
        "seaweed floating water", "rocks in shallow water", "shadow on water", "sunlight glitter water",
        "boat wake water", "foam on water surface", "algae bloom water", "harbour water boats",
        "dark water pond leaves", "sea waves close up", "muddy river water", "tidal pool rocks",
        "reflection of clouds in water", "ocean water texture", "stream water stones", "dock water surface",
    ],
}
PER_QUERY = 25


def call(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(3 + attempt * 5)
    return {}


def search(query):
    data = call({
        "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": PER_QUERY,
        "gsrsearch": query + " filemime:image/jpeg", "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 960,
    })
    return list(data.get("query", {}).get("pages", {}).values())


def clean_text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


# this check is for ground-level photos, so satellite pictures that turn up in the searches are skipped
SATELLITE = re.compile(r"(?<![a-z])(esa|nasa|modis|aster|landsat|envisat|sentinel|satellite|iss\d+|sar|aerial|nara)(?![a-z])", re.I)
WANT = {"oil": 110, "clean": 110}   # how many photos of each kind to download (kept small on purpose, to go easy on Wikimedia)


def licence_ok(licence):
    l = licence.lower()
    return "public domain" in l or l.startswith(("cc0", "cc by", "pd"))


def download(url, path):
    """polite download. if Wikimedia says 'too many requests' we stop for 5 minutes instead of retrying"""
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("  too many requests, waiting 5 minutes", flush=True)
                time.sleep(300)
            else:
                return False
        except Exception:
            time.sleep(3)
    return False


def main():
    # 1. search first and write credits.csv, so every photo we use is credited
    seen, rows = set(), []
    for label, queries in QUERIES.items():
        for q in queries:
            got = 0
            for page in search(q):
                info = (page.get("imageinfo") or [{}])[0]
                title = page.get("title", "")
                meta = info.get("extmetadata", {})
                licence = clean_text(meta.get("LicenseShortName", {}).get("value", ""))
                if (title in seen or info.get("mime") != "image/jpeg" or not info.get("thumburl")
                        or SATELLITE.search(title) or not licence_ok(licence) or min(info.get("width", 0), info.get("height", 0)) < 400):
                    continue
                seen.add(title)
                rows.append({
                    "file": f"{label}/{label}_{page['pageid']}.jpg", "query_label": label, "query": q, "title": title,
                    "author": clean_text(meta.get("Artist", {}).get("value", ""))[:120], "licence": licence,
                    "page": info.get("descriptionurl", ""), "thumb": info["thumburl"],
                })
                got += 1
            print(f"{label:5s} {q:40s} +{got}", flush=True)
            time.sleep(1)
    # pick a balanced subset: take photos from each search in turn, so one search doesn't dominate
    chosen = []
    for label, n in WANT.items():
        by_query = {}
        for r in rows:
            if r["query_label"] == label:
                by_query.setdefault(r["query"], []).append(r)
        picked = []
        while len(picked) < n and any(by_query.values()):
            for q in list(by_query):
                if by_query[q] and len(picked) < n:
                    picked.append(by_query[q].pop(0))
        chosen += picked
    print(f"{len(rows)} photos found, downloading {len(chosen)}", flush=True)

    for label in QUERIES:
        os.makedirs(os.path.join(OUT, label), exist_ok=True)
    got = []
    for i, r in enumerate(chosen):
        path = os.path.join(OUT, r["file"])
        if os.path.exists(path) or download(r["thumb"], path):
            got.append(r)
        time.sleep(6)
        if (i + 1) % 10 == 0:
            print(f"  downloaded {len(got)}/{i + 1}", flush=True)
        if (i + 1) % 20 == 0 or i + 1 == len(chosen):      # keep credits.csv up to date as we go
            with open(os.path.join(HERE, "credits.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=[k for k in chosen[0] if k != "thumb"], extrasaction="ignore")
                w.writeheader()
                w.writerows(got)
    print(f"done: {len(got)} of {len(chosen)} photos", flush=True)


if __name__ == "__main__":
    main()
