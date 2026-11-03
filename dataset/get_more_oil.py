"""
get_more_oil.py - a second round of photos for the "oil" side, taken from Wikimedia Commons categories
that are about oil on water (the first round used free-text searches, which gave many unrelated pictures).

Same rules as get_photos.py: open licences only, no satellite pictures, slow downloads, credits.csv updated.

    python dataset/get_more_oil.py
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import get_photos as g

CATEGORIES = [
    "Oil sheen", "Oil slick", "Oil slick from Erika oil spill", "Oil slick from Prestige oil spill",
    "Oil slick from Amoco Cadiz", "New Orleans oil spill, July 2008", "New Orleans oil spill, April 2018",
    "Refugio oil spill", "San Juan River oil spill (Utah)",
]
MAX_NEW = 130


def members(category):
    for attempt in range(6):
        data = g.call({
            "action": "query", "generator": "categorymembers", "gcmtitle": "Category:" + category,
            "gcmtype": "file", "gcmlimit": 60, "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 960,
        })
        pages = list(data.get("query", {}).get("pages", {}).values())
        if pages:
            return pages
        time.sleep(60 * (attempt + 1))      # throttled or empty: wait, then try again
    return []


def main():
    credits_path = os.path.join(g.HERE, "credits.csv")
    with open(credits_path, newline="", encoding="utf-8") as f:
        have = list(csv.DictReader(f))
    titles = {r["title"] for r in have}
    fields = list(have[0].keys())
    os.makedirs(os.path.join(g.OUT, "oil"), exist_ok=True)

    new = []
    for cat in CATEGORIES:
        for page in members(cat):
            info = (page.get("imageinfo") or [{}])[0]
            title = page.get("title", "")
            meta = info.get("extmetadata", {})
            lic = g.clean_text(meta.get("LicenseShortName", {}).get("value", ""))
            if (title in titles or info.get("mime") != "image/jpeg" or not info.get("thumburl")
                    or g.SATELLITE.search(title) or not g.licence_ok(lic) or min(info.get("width", 0), info.get("height", 0)) < 400):
                continue
            titles.add(title)
            new.append({"file": f"oil/oil_{page['pageid']}.jpg", "query_label": "oil", "query": "category: " + cat, "title": title,
                        "author": g.clean_text(meta.get("Artist", {}).get("value", ""))[:120], "licence": lic,
                        "page": info.get("descriptionurl", ""), "thumb": info["thumburl"]})
        print(f"{cat:40s} total new so far {len(new)}", flush=True)
        time.sleep(5)
    new = new[:MAX_NEW]

    got = 0
    for i, r in enumerate(new):
        path = os.path.join(g.OUT, r["file"])
        if os.path.exists(path) or g.download(r["thumb"], path):
            have.append({k: r[k] for k in fields})
            got += 1
        time.sleep(6)
        if (i + 1) % 10 == 0:
            print(f"  downloaded {got}/{i + 1}", flush=True)
            with open(credits_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(have)
    with open(credits_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(have)
    print(f"done: {got} of {len(new)} new oil photos", flush=True)


if __name__ == "__main__":
    main()
