"""
Train the Stage 2 AI for crude_detect.py

1. Run:   python3 crude_detect.py --image photos/*.jpg --save-candidates
2. Open the candidates/ folder and MOVE each picture into:
       candidates/oil/      if the red outline is really oil
       candidates/not_oil/  if it is a shadow, rock, boat, reflection, weed...
3. Run:   python3 train_model.py
   -> creates oil_model.pkl, which crude_detect.py uses automatically.

Aim for at least 30 pictures in each folder. More = better AI.
"""
import csv
import json
import os

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict
import joblib

from crude_detect import CANDIDATE_DIR, FEATURE_NAMES, MODEL_PATH


def load_data():
    csv_path = os.path.join(CANDIDATE_DIR, "features.csv")
    if not os.path.exists(csv_path):
        raise SystemExit("No candidates/features.csv - run crude_detect.py with "
                         "--save-candidates first.")
    oil = set(os.listdir(os.path.join(CANDIDATE_DIR, "oil")))
    not_oil = set(os.listdir(os.path.join(CANDIDATE_DIR, "not_oil")))

    X, y, unsorted = [], [], 0
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            name = row["file"]
            if name in oil:
                label = 1
            elif name in not_oil:
                label = 0
            else:
                unsorted += 1
                continue
            X.append([float(row[k]) for k in FEATURE_NAMES])
            y.append(label)
    if unsorted:
        print(f"Note: {unsorted} picture(s) not sorted into oil/not_oil yet - skipped.")
    return np.array(X), np.array(y)


def main():
    X, y = load_data()
    n_oil, n_not = int(y.sum()), int(len(y) - y.sum())
    print(f"Training on {len(y)} patches: {n_oil} oil, {n_not} not oil")
    if min(n_oil, n_not) < 5:
        raise SystemExit("Need at least 5 of each (30+ recommended). Label more pictures.")
    if min(n_oil, n_not) < 30:
        print("Warning: under 30 of each - the AI will be weak. Keep collecting!")

    model = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                   min_samples_leaf=2, random_state=42)

    # Honest test: each patch is predicted by a model that never saw it
    folds = min(5, n_oil, n_not)
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    pred = cross_val_predict(model, X, y, cv=cv)
    acc = (pred == y).mean()
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()

    print(f"\nAccuracy (cross-validated): {acc * 100:.1f}%")
    print(f"  Oil correctly found:      {tp}/{tp + fn}")
    print(f"  Oil missed:               {fn}")
    print(f"  False alarms:             {fp}/{fp + tn}")
    print(f"  Non-oil correctly cleared:{tn}")

    model.fit(X, y)
    ranked = sorted(zip(model.feature_importances_, FEATURE_NAMES), reverse=True)
    print("\nWhat the AI relies on most:")
    for imp, name in ranked[:6]:
        print(f"  {name:22} {imp * 100:.0f}%")

    joblib.dump({"model": model, "features": FEATURE_NAMES,
                 "accuracy": f"{acc * 100:.1f}%"}, MODEL_PATH)
    print(f"\nSaved {MODEL_PATH} - crude_detect.py will now use the AI.")
    export_for_website(model, f"{acc * 100:.1f}%")


def export_for_website(model, accuracy, path=os.path.join("web", "oil_model.json")):
    """Saves the same AI as JSON so the website (web/ground.js) can run it in the browser."""
    trees = []
    for est in model.estimators_:
        t = est.tree_
        val = t.value[:, 0, :]
        p_oil = (val[:, 1] / np.maximum(val.sum(axis=1), 1e-12)).round(4)
        trees.append({"l": t.children_left.tolist(), "r": t.children_right.tolist(),
                      "f": t.feature.tolist(), "t": [round(float(x), 6) for x in t.threshold],
                      "p": p_oil.tolist()})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"features": FEATURE_NAMES, "accuracy": accuracy, "trees": trees}, f,
                  separators=(",", ":"))
    print(f"Saved {path} - push it to GitHub and the website uses the AI too.")


if __name__ == "__main__":
    main()
