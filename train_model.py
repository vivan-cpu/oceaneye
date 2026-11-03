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
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
import joblib

from crude_detect import AI_NOT_OIL, AI_OIL, CANDIDATE_DIR, FEATURE_NAMES, MODEL_PATH


LABELS_CSV = os.path.join("dataset", "labels.csv")


def photo_of(name):
    """candidates are named <photo>_<number>.png, so everything before the last _ is the photo"""
    return name.rsplit("_", 1)[0]


def load_data():
    """Returns X (numbers per patch), y (1 = oil, 0 = not oil) and which photo each patch came from.
    Labels come from dataset/labels.csv (file,label) if it exists, otherwise from the folders
    candidates/oil and candidates/not_oil."""
    csv_path = os.path.join(CANDIDATE_DIR, "features.csv")
    if not os.path.exists(csv_path):
        raise SystemExit("No candidates/features.csv - run crude_detect.py with "
                         "--save-candidates first.")
    if os.path.exists(LABELS_CSV):
        with open(LABELS_CSV) as f:
            labels = {r["file"]: int(r["label"]) for r in csv.DictReader(f)}
    else:
        labels = {n: 1 for n in os.listdir(os.path.join(CANDIDATE_DIR, "oil"))}
        labels.update({n: 0 for n in os.listdir(os.path.join(CANDIDATE_DIR, "not_oil"))})

    holdout = set()
    if os.path.exists(os.path.join("dataset", "holdout.txt")):      # photos kept out of training on purpose
        holdout = {l.strip() for l in open(os.path.join("dataset", "holdout.txt")) if l.strip() and not l.startswith("#")}

    X, y, groups, unsorted = [], [], [], 0
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            name = row["file"]
            if photo_of(name) in holdout:
                continue
            if name not in labels:
                unsorted += 1
                continue
            X.append([float(row[k]) for k in FEATURE_NAMES])
            y.append(labels[name])
            groups.append(photo_of(name))
    if unsorted:
        print(f"Note: {unsorted} patch(es) not labelled yet - skipped.")
    return np.array(X), np.array(y), np.array(groups)


def pick_cutoffs(y, prob):
    oil_p, other_p = prob[y == 1], prob[y == 0]
    reject_at = float(np.quantile(oil_p, 0.10)) if len(oil_p) else AI_NOT_OIL
    confirm_at = float(np.quantile(other_p, 0.97)) if len(other_p) else AI_OIL
    reject_at = round(min(reject_at, 0.5), 2)
    confirm_at = round(max(confirm_at, reject_at + 0.05), 2)
    return reject_at, confirm_at


def main():
    X, y, groups = load_data()
    n_oil, n_not = int(y.sum()), int(len(y) - y.sum())
    print(f"Training on {len(y)} patches from {len(set(groups))} photos: {n_oil} oil, {n_not} not oil")
    if min(n_oil, n_not) < 5:
        raise SystemExit("Need at least 5 of each (30+ recommended). Label more pictures.")
    if min(n_oil, n_not) < 30:
        print("Warning: under 30 of each - the AI will be weak. Keep collecting!")

    model = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                   min_samples_leaf=2, random_state=42)

    # Honest test: every patch is predicted by a model that never saw ANY patch from the same photo.
    # (Patches from one photo look alike, so splitting patch by patch would flatter the result.)
    folds = min(5, n_oil, n_not)
    cv = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=42)
    prob = cross_val_predict(model, X, y, cv=cv, groups=groups, method="predict_proba")[:, 1]
    pred = (prob >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    recall = tp / max(tp + fn, 1)               # how much of the real oil it finds
    false_alarm = fp / max(fp + tn, 1)          # how many non-oil patches it calls oil
    balanced = (recall + (1 - false_alarm)) / 2
    baseline = max(n_oil, n_not) / len(y)       # accuracy of a "model" that always says the same thing
    auc = roc_auc_score(y, prob)
    # the app confirms a patch above one cut-off and rejects it below another, in between is "unsure".
    # we pick the cut-offs from these test results: reject only the clearly-not-oil end (so at most ~10% of
    # real oil gets thrown out) and confirm only the clearly-oil end (at most ~3% of non-oil confirmed).
    # (the cut-offs are chosen on the same test results they are scored on, so the numbers below are a bit optimistic)
    reject_at, confirm_at = pick_cutoffs(y, prob)
    confirmed = prob >= confirm_at
    rejected = prob < reject_at
    thrown_out = int(((y == 1) & rejected).sum())
    wrongly_confirmed = int(((y == 0) & confirmed).sum())

    print(f"\nHonest test (each photo kept out of training while it is tested):")
    print(f"  Plain accuracy:            {(pred == y).mean() * 100:.1f}%   <- always saying '{'not oil' if n_not >= n_oil else 'oil'}' scores {baseline * 100:.1f}%, so this number alone means little")
    print(f"  Oil found:                 {tp}/{tp + fn}  ({recall * 100:.0f}%)")
    print(f"  Oil missed:                {fn}")
    print(f"  False alarms:              {fp}/{fp + tn}  ({false_alarm * 100:.1f}% of non-oil patches)")
    print(f"  Balanced accuracy:         {balanced * 100:.0f}%  (average of oil found and non-oil cleared)")
    print(f"  Area under ROC curve:      {auc:.2f}   (0.5 = guessing, 1.0 = perfect)")
    print(f"  Cut-offs chosen: reject below {reject_at}, confirm from {confirm_at}")
    print(f"  With those cut-offs: {int((confirmed & (y == 1)).sum())} oil patches confirmed, "
          f"{int(((y == 1) & ~confirmed & ~rejected).sum())} left 'unsure', {thrown_out} real oil patches wrongly thrown out; "
          f"{wrongly_confirmed} non-oil patches wrongly confirmed")
    acc = balanced

    model.fit(X, y)
    ranked = sorted(zip(model.feature_importances_, FEATURE_NAMES), reverse=True)
    print("\nWhat the AI relies on most:")
    for imp, name in ranked[:6]:
        print(f"  {name:22} {imp * 100:.0f}%")

    summary = (f"found {recall * 100:.0f}% of oil with {false_alarm * 100:.0f}% false alarms on photos it had never seen, "
               f"trained on {len(y)} patches ({n_oil} oil) from {len(set(groups))} photos")
    cutoffs = {"oil": confirm_at, "reject": reject_at}
    joblib.dump({"model": model, "features": FEATURE_NAMES, "accuracy": f"{acc * 100:.0f}% balanced",
                 "summary": summary, "thresholds": cutoffs}, MODEL_PATH)
    print(f"\nSaved {MODEL_PATH} - crude_detect.py will now use the AI.")
    export_for_website(model, f"{acc * 100:.0f}% balanced", summary, cutoffs)


def export_for_website(model, accuracy, summary, thresholds, path=os.path.join("web", "oil_model.json")):
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
        json.dump({"features": FEATURE_NAMES, "accuracy": accuracy, "summary": summary, "thresholds": thresholds, "trees": trees}, f,
                  separators=(",", ":"))
    print(f"Saved {path} - push it to GitHub and the website uses the AI too.")


if __name__ == "__main__":
    main()
