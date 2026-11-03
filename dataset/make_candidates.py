"""
make_candidates.py - runs stage 1 (the rules) on every photo in photos/ and saves each patch it finds.

Writes:
  candidates/features.csv          the numbers of every patch (what the AI learns from)
  candidates/<photo>_<n>.png       a picture of the patch, outlined in red
  candidates/sheets/sheet_XX.jpg   numbered contact sheets, so patches can be looked at and labelled quickly
  candidates/index.csv             patch name, photo, sheet number, position on the sheet

    python dataset/make_candidates.py
"""
import csv
import glob
import os
import re
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import crude_detect as crude

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
CELL, COLS, ROWS = 220, 6, 4          # contact sheet layout: 24 patches per sheet
OUT = crude.CANDIDATE_DIR


def main():
    os.makedirs(os.path.join(OUT, "sheets"), exist_ok=True)
    # this check is for ground-level photos, so skip satellite pictures that turned up in the searches
    skip = re.compile(r"(?<![a-z])(esa|nasa|modis|aster|landsat|envisat|sentinel|satellite|iss\d+|sar)(?![a-z])")
    titles = {}
    with open(os.path.join("dataset", "credits.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            titles[r["file"].replace("/", os.sep)] = r["title"].lower()
    photos = [p for p in sorted(glob.glob("photos/*/*.jpg"))
              if not skip.search(titles.get(p[len("photos") + 1:], ""))]
    # --append N: only look at photos we haven't done yet, add them to the existing files, new sheets start at N
    append = int(sys.argv[sys.argv.index("--append") + 1]) if "--append" in sys.argv else None
    if append:
        with open(os.path.join(OUT, "features.csv"), encoding="utf-8") as f:
            done = {r["file"].rsplit("_", 1)[0] for r in csv.DictReader(f)}
        photos = [p for p in photos if os.path.splitext(os.path.basename(p))[0] not in done]
    print(f"{len(photos)} ground-level photos")
    rows, crops = [], []
    for k, path in enumerate(photos):
        img = cv2.imread(path)
        if img is None:
            continue
        img = crude.to_work_size(img)
        patches = crude.analyse(img, None)
        base = os.path.splitext(os.path.basename(path))[0]
        for i, p in enumerate(patches, 1):
            x, y, bw, bh = cv2.boundingRect(p["contour"])
            m = 30
            x0, y0 = max(x - m, 0), max(y - m, 0)
            crop = img[y0:y + bh + m, x0:x + bw + m].copy()
            cv2.drawContours(crop, [p["contour"] - [x0, y0]], -1, (0, 0, 255), 2)
            name = f"{base}_{i}.png"
            cv2.imwrite(os.path.join(OUT, name), crop)
            rows.append([name] + [f"{v:.4f}" for v in p["features"]])
            crops.append((name, os.path.basename(os.path.dirname(path)), p["kind"], crop))
        if (k + 1) % 50 == 0:
            print(f"  {k + 1}/{len(photos)} photos, {len(rows)} patches")

    with open(os.path.join(OUT, "features.csv"), "a" if append else "w", newline="") as f:
        w = csv.writer(f)
        if not append:
            w.writerow(["file"] + crude.FEATURE_NAMES)
        w.writerows(rows)

    per = COLS * ROWS
    first_sheet = append or 1
    with open(os.path.join(OUT, "index.csv"), "a" if append else "w", newline="") as f:
        w = csv.writer(f)
        if not append:
            w.writerow(["file", "photo_search", "kind", "sheet", "pos"])
        for s in range(0, len(crops), per):
            sheet = np.full((ROWS * CELL, COLS * CELL, 3), 255, np.uint8)
            for j, (name, search, kind, crop) in enumerate(crops[s:s + per]):
                h, wd = crop.shape[:2]
                sc = (CELL - 8) / max(h, wd)
                small = cv2.resize(crop, (max(1, int(wd * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA)
                r, c = divmod(j, COLS)
                y, x = r * CELL + 4, c * CELL + 4
                sheet[y:y + small.shape[0], x:x + small.shape[1]] = small
                label = str(j + 1)
                cv2.rectangle(sheet, (x, y), (x + 8 + 12 * len(label), y + 22), (0, 0, 0), -1)
                cv2.putText(sheet, label, (x + 4, y + 17), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
                w.writerow([name, search, kind, first_sheet + s // per, j + 1])
            cv2.imwrite(os.path.join(OUT, "sheets", f"sheet_{first_sheet + s // per:02d}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(f"{len(rows)} patches from {len(photos)} photos, {-(-len(crops) // per)} sheets")


if __name__ == "__main__":
    main()
