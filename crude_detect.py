"""
Crude Oil Spill Detector - YCL 2026 (two-stage)

STAGE 1 (rules):  finds suspicious patches in a photo of water
                  DARK  = thick crude (much darker than the water)
                  SHEEN = thin crude film (rainbow / patchy colours)
STAGE 2 (AI):     a trained model checks every patch -> OIL or NOT OIL + confidence

Examples:
  python3 crude_detect.py --image spill.jpg
  python3 crude_detect.py --image photos/*.jpg --save-candidates   (collect training data)
  python3 crude_detect.py --camera 0

Training the AI: see train_model.py
"""
import argparse
import csv
import os

import cv2
import numpy as np

# ---------------- Settings you can tune ----------------
DARK_DROP = 35          # how much darker than normal water counts as DARK (0-255)
SHEEN_COLOUR = 14       # extra colour variation that counts as SHEEN
MIN_PATCH_AREA = 800    # ignore patches smaller than this (pixels)
WINDOW = 21             # size of the area used to measure texture/colour (odd)
AI_OIL = 0.60           # AI confidence needed to CONFIRM oil
AI_NOT_OIL = 0.40       # below this the AI REJECTS the patch
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oil_model.pkl")
MODEL_SUMMARY = ""
CANDIDATE_DIR = "candidates"
MAX_WIDTH = 1400
WORK_SIDE = 800         # photos are shrunk to this before analysis (same in the website's JS)
# --------------------------------------------------------

FEATURE_NAMES = [
    "brightness", "brightness_var", "colour_a", "colour_b",
    "colour_a_var", "colour_b_var", "darker_than_water", "sheen_inside",
    "sheen_vs_water", "texture_inside", "smoother_than_water",
    "saturation", "area_fraction", "elongation", "solidity",
]

RED, ORANGE, GREY, GREEN = (60, 60, 230), (40, 150, 245), (150, 150, 150), (90, 175, 60)
WHITE, PANEL = (255, 255, 255), (40, 34, 32)


# ======================= STAGE 1: rules =======================
def to_work_size(img):
    """Shrink big photos so analysis is fast (the website does exactly the same)."""
    h, w = img.shape[:2]
    s = WORK_SIDE / max(h, w)
    if s >= 1:
        return img
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


def local_std(ch):
    m = cv2.blur(ch, (WINDOW, WINDOW))
    m2 = cv2.blur(ch * ch, (WINDOW, WINDOW))
    return np.sqrt(np.maximum(m2 - m * m, 0))


def make_maps(img):
    """Brightness, colour, sheen and texture maps of the whole photo."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, a, b = cv2.split(lab)
    L = cv2.GaussianBlur(L, (7, 7), 0)
    sheen = local_std(a) + local_std(b)               # rainbow film = colour changes
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    texture = cv2.blur(np.abs(cv2.Laplacian(gray, cv2.CV_32F)), (WINDOW, WINDOW))
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1].astype(np.float32)
    water = {"L": float(np.median(L)), "sheen": float(np.median(sheen)),
             "texture": float(np.median(texture))}
    return {"L": L, "a": a, "b": b, "sheen": sheen, "texture": texture,
            "sat": sat, "water": water}


def find_candidates(img, maps):
    """Stage 1: suspicious DARK and SHEEN patches."""
    w = maps["water"]
    dark = (maps["L"] < w["L"] - DARK_DROP).astype(np.uint8)
    shiny = (maps["sheen"] > w["sheen"] + SHEEN_COLOUR).astype(np.uint8)
    mask = ((dark | shiny) * 255).astype(np.uint8)
    k = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in contours:
        inside = np.zeros(mask.shape, np.uint8)
        cv2.drawContours(inside, [c], -1, 255, -1)
        if cv2.countNonZero(inside) < MIN_PATCH_AREA:
            continue
        d = cv2.mean(dark * 255, inside)[0] > 127
        s = cv2.mean(shiny * 255, inside)[0] > 127
        kind = "DARK+SHEEN" if d and s else ("DARK" if d else "SHEEN")
        out.append({"contour": c, "inside": inside, "kind": kind,
                    "area": int(cv2.countNonZero(inside))})
    out.sort(key=lambda p: p["area"], reverse=True)
    return out


# ================= features shared with training =================
def patch_features(maps, contour, inside):
    """Numbers that describe one patch. The AI learns from these."""
    ring = cv2.dilate(inside, np.ones((31, 31), np.uint8))
    ring = cv2.bitwise_and(ring, cv2.bitwise_not(inside))
    if cv2.countNonZero(ring) == 0:
        ring = cv2.bitwise_not(inside)

    def stats(name, m):
        mean, std = cv2.meanStdDev(maps[name], mask=m)
        return float(mean[0][0]), float(std[0][0])

    L_in, L_sd = stats("L", inside)
    L_out, _ = stats("L", ring)
    a_in, a_sd = stats("a", inside)
    b_in, b_sd = stats("b", inside)
    sh_in, _ = stats("sheen", inside)
    sh_out, _ = stats("sheen", ring)
    tx_in, _ = stats("texture", inside)
    tx_out, _ = stats("texture", ring)
    sat_in, _ = stats("sat", inside)

    ys, xs = np.nonzero(inside)
    area = float(len(xs))
    cov = np.cov(np.vstack([xs, ys]).astype(np.float64), bias=True) if len(xs) > 1 else np.zeros((2, 2))
    l1, l2 = sorted(np.linalg.eigvalsh(cov), reverse=True)
    elong = float(np.sqrt(max(l1, 0.25) / max(l2, 0.25)))
    pts = np.column_stack([xs, ys]).astype(np.int32)
    hull = cv2.contourArea(cv2.convexHull(pts)) if len(pts) >= 3 else 0
    solidity = min(area / hull, 1.0) if hull else 1.0

    return [L_in, L_sd, a_in, b_in, a_sd, b_sd, L_out - L_in, sh_in,
            sh_in - sh_out, tx_in, tx_out / (tx_in + 1), sat_in,
            area / inside.size, elong, solidity]


# ======================= STAGE 2: AI =======================
def load_model():
    if not os.path.exists(MODEL_PATH):
        return None
    import joblib
    data = joblib.load(MODEL_PATH)
    global AI_OIL, AI_NOT_OIL, MODEL_SUMMARY
    MODEL_SUMMARY = data.get("summary", "")
    if "thresholds" in data:          # train_model.py picked these from its honest test
        AI_OIL, AI_NOT_OIL = data["thresholds"]["oil"], data["thresholds"]["reject"]
    print(f"AI model loaded ({data.get('summary', data.get('accuracy', '?'))})")
    return data["model"]


def judge(model, feats):
    """Returns (verdict, oil probability or None)."""
    if model is None:
        return "RULE ONLY", None
    p = float(model.predict_proba([feats])[0][1])
    if p >= AI_OIL:
        return "CONFIRMED OIL", p
    if p < AI_NOT_OIL:
        return "AI REJECTED", p
    return "UNCERTAIN", p


def analyse(img, model):
    maps = make_maps(img)
    patches = find_candidates(img, maps)
    for p in patches:
        p["features"] = patch_features(maps, p["contour"], p["inside"])
        p["verdict"], p["prob"] = judge(model, p["features"])
    return patches


# ======================= display =======================
def overall(patches, model):
    v = [p["verdict"] for p in patches]
    if "CONFIRMED OIL" in v:
        return "OIL SPILL CONFIRMED", RED
    if "UNCERTAIN" in v or "RULE ONLY" in v:
        return ("POSSIBLE SPILL - AI UNSURE" if model else "POSSIBLE SPILL (no AI yet)"), ORANGE
    return "CLEAR", GREEN


def draw(img, patches, model):
    out = img.copy()
    overlay = out.copy()
    colours = {"CONFIRMED OIL": RED, "UNCERTAIN": ORANGE,
               "RULE ONLY": ORANGE, "AI REJECTED": GREY}
    for i, p in enumerate(patches, 1):
        col = colours[p["verdict"]]
        cv2.drawContours(overlay, [p["contour"]], -1, col, -1)
        cv2.drawContours(out, [p["contour"]], -1, col, 2, cv2.LINE_AA)
        x, y, _, _ = cv2.boundingRect(p["contour"])
        ai = f" AI {p['prob'] * 100:.0f}%" if p["prob"] is not None else ""
        label = f"#{i} {p['kind']}{ai}"
        cv2.putText(out, label, (x, max(y - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, label, (x, max(y - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, col, 1, cv2.LINE_AA)
    out = cv2.addWeighted(overlay, 0.3, out, 0.7, 0)

    status, col = overall(patches, model)
    n_conf = sum(p["verdict"] == "CONFIRMED OIL" for p in patches)
    n_rej = sum(p["verdict"] == "AI REJECTED" for p in patches)
    panel = np.full((84, img.shape[1] * 2, 3), PANEL, np.uint8)
    cv2.rectangle(panel, (0, 0), (8, 84), col, -1)
    cv2.putText(panel, status, (20, 34), cv2.FONT_HERSHEY_DUPLEX, 0.85, WHITE, 1, cv2.LINE_AA)
    stage2 = (f"Stage 2 AI: {n_conf} confirmed, {n_rej} rejected" if model
              else "Stage 2 AI: not trained yet (run train_model.py)")
    cv2.putText(panel, f"Stage 1 rules: {len(patches)} suspicious patch(es)   |   {stage2}",
                (20, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

    result = np.vstack([panel, np.hstack([img, out])])
    if result.shape[1] > MAX_WIDTH:
        s = MAX_WIDTH / result.shape[1]
        result = cv2.resize(result, None, fx=s, fy=s)
    return result, status


# ================= saving training data =================
def save_candidates(img, patches, source):
    """Save each patch as a picture + its numbers, for you to label."""
    os.makedirs(os.path.join(CANDIDATE_DIR, "oil"), exist_ok=True)
    os.makedirs(os.path.join(CANDIDATE_DIR, "not_oil"), exist_ok=True)
    csv_path = os.path.join(CANDIDATE_DIR, "features.csv")
    new = not os.path.exists(csv_path)
    base = os.path.splitext(os.path.basename(source))[0]
    with open(csv_path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["file"] + FEATURE_NAMES)
        for i, p in enumerate(patches, 1):
            x, y, bw, bh = cv2.boundingRect(p["contour"])
            m = 30
            crop = img[max(y - m, 0):y + bh + m, max(x - m, 0):x + bw + m].copy()
            cv2.drawContours(crop, [p["contour"] - [max(x - m, 0), max(y - m, 0)]],
                             -1, (0, 0, 255), 2)
            name = f"{base}_{i}.png"
            cv2.imwrite(os.path.join(CANDIDATE_DIR, name), crop)
            w.writerow([name] + [f"{v:.4f}" for v in p["features"]])
    print(f"  saved {len(patches)} candidate(s) to {CANDIDATE_DIR}/")


# ======================= main =======================
def main():
    ap = argparse.ArgumentParser(description="Two-stage crude oil spill detector")
    ap.add_argument("--image", nargs="+", help="one or more photos")
    ap.add_argument("--camera", type=int, help="camera number (0 = Mac, 1 = iPhone)")
    ap.add_argument("--save-candidates", action="store_true",
                    help="save each suspicious patch for labelling")
    ap.add_argument("--no-window", action="store_true", help="don't open windows")
    args = ap.parse_args()

    model = load_model()
    if model is None:
        print("No AI model yet - showing Stage 1 (rules) only.")

    if args.image:
        for path in args.image:
            img = cv2.imread(path)
            if img is None:
                print(f"Could not open {path}")
                continue
            img = to_work_size(img)
            patches = analyse(img, model)
            result, status = draw(img, patches, model)
            name = os.path.splitext(os.path.basename(path))[0]
            cv2.imwrite(f"crude_result_{name}.png", result)
            print(f"{path}: {status}")
            for i, p in enumerate(patches, 1):
                ai = f"AI oil {p['prob'] * 100:.0f}%" if p["prob"] is not None else "no AI"
                print(f"  #{i} {p['kind']:10} -> {p['verdict']:13} ({ai})")
            if args.save_candidates:
                save_candidates(img, patches, path)
            if not args.no_window and len(args.image) == 1:
                cv2.imshow("Crude oil detector (any key to close)", result)
                cv2.waitKey(0)

    elif args.camera is not None:
        cap = cv2.VideoCapture(args.camera)
        if not cap.isOpened():
            print("Could not open camera. Try --camera 1")
            return
        shot = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = to_work_size(frame)
            patches = analyse(frame, model)
            result, status = draw(frame, patches, model)
            cv2.imshow("Crude oil detector  (q quit, s save)", result)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("s"):
                shot += 1
                cv2.imwrite(f"crude_screenshot_{shot}.png", result)
                if args.save_candidates:
                    save_candidates(frame, patches, f"camera_{shot}")
                print(f"Saved crude_screenshot_{shot}.png ({status})")
        cap.release()
    else:
        ap.print_help()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
