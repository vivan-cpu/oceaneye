"""
apply_labels.py - turns dataset/sheet_labels.txt into dataset/labels.csv (file,label) for train_model.py

sheet_labels.txt has one line per contact sheet from make_candidates.py, for example:
    03 oil=1,4,7,9 skip=5,12
meaning: on sheet 03 the numbered patches 1, 4, 7 and 9 are oil on water, patches 5 and 12 are unclear
(skipped, not used for training), and every other patch on that sheet is NOT oil (shadow, rock, weed,
reflection, foam, wake, boat ...). The labels were made by looking at each patch, not by a program.

    python dataset/apply_labels.py
"""
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def numbers(text):
    return {int(n) for n in re.findall(r"\d+", text or "")}


def main():
    index = {}
    with open(os.path.join("candidates", "index.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            index.setdefault(int(r["sheet"]), []).append((int(r["pos"]), r["file"]))

    out, done, seen = [], set(), set()
    with open(os.path.join("dataset", "sheet_labels.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue
            m = re.match(r"(\d+)\s*(.*)", line)
            sheet = int(m.group(1))
            oil = numbers(re.search(r"oil=([\d, ]*)", line).group(1)) if "oil=" in line else set()
            skip = numbers(re.search(r"skip=([\d, ]*)", line).group(1)) if "skip=" in line else set()
            done.add(sheet)
            for pos, name in index.get(sheet, []):
                if pos in skip or name in seen:
                    continue
                seen.add(name)
                out.append((name, 1 if pos in oil else 0))
    # rule for everything not listed: patches from photos of clean water are not oil, the rest is left out
    with open(os.path.join("candidates", "index.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["file"] not in seen and r["file"].startswith("clean_"):
                seen.add(r["file"])
                out.append((r["file"], 0))
    with open(os.path.join("dataset", "labels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "label"])
        w.writerows(out)
    n_oil = sum(l for _, l in out)
    print(f"{len(out)} labelled patches from {len(done)} sheets: {n_oil} oil, {len(out) - n_oil} not oil")
    left = sorted(set(index) - done)
    if left:
        print("sheets not labelled yet:", left)


if __name__ == "__main__":
    main()
