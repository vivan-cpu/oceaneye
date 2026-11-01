"""make_logo.py - OceanEye logo: an eye. the iris is a radar screen with a sweep, the pupil is a drop of oil.
drawn big (supersampled) with Pillow, then shrunk so the edges are smooth."""
import math, os, sys
from PIL import Image, ImageDraw, ImageFilter

OUT = sys.argv[1] if len(sys.argv) > 1 else "web/img"   # run: python make_logo.py
S = 2048                    # work size
ABYSS = (4, 18, 28, 255)
HOLO = (111, 227, 255, 255)
PALE = (191, 244, 255, 255)
TEAL = (10, 52, 70, 255)
OIL = (255, 181, 71, 255)


def eye_points(cx, cy, w, h, n=200):
    """almond shape from two circle arcs"""
    # circle through (cx-w/2, cy), (cx+w/2, cy), (cx, cy-h/2)
    half = w / 2
    r = (half ** 2 + (h / 2) ** 2) / h
    top, bot = [], []
    a0 = math.asin(half / r)
    for i in range(n + 1):
        a = -a0 + 2 * a0 * i / n
        x = cx + r * math.sin(a)
        top.append((x, cy + (r - h / 2) - r * math.cos(a) + 0))
    for i in range(n + 1):
        a = a0 - 2 * a0 * i / n
        x = cx + r * math.sin(a)
        bot.append((x, cy - (r - h / 2) + r * math.cos(a)))
    return top, bot


def mark(size, background):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = S / 2
    if background:
        pad = S * 0.04
        d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.22, fill=ABYSS)
        d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.22, outline=(111, 227, 255, 90), width=int(S * 0.012))

    ew, eh = S * 0.80, S * 0.50
    stroke = S * 0.05
    top, bot = eye_points(c, c, ew, eh)                              # outer edge
    itop, ibot = eye_points(c, c, ew - stroke * 3.2, eh - stroke * 2)  # inner edge

    # glow under the eye
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(top + bot, fill=HOLO)
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.035))
    glow.putalpha(glow.getchannel("A").point(lambda v: v * 0.5))
    im = Image.alpha_composite(im, glow)
    d = ImageDraw.Draw(im)

    # outline = outer almond filled cyan, then the inside filled dark (clean edges, no line joins)
    d.polygon(top + bot, fill=HOLO)
    d.polygon(itop + ibot, fill=(6, 30, 42, 255))

    # iris = radar screen
    r = S * 0.19
    d.ellipse([c - r, c - r, c + r, c + r], fill=TEAL)
    # radar sweep: a wedge that fades behind the leading edge
    steps = 24
    for i in range(steps):
        a_end = -60
        a_start = a_end - 80 * (1 - i / steps)
        alpha = int(30 + 150 * (i / steps) ** 2)
        d.pieslice([c - r, c - r, c + r, c + r], a_start, a_end, fill=(111, 227, 255, alpha))
    # range ring + leading edge line
    rr = r * 0.6
    d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=(111, 227, 255, 110), width=int(S * 0.008))
    ang = math.radians(-60)
    d.line([(c, c), (c + r * math.cos(ang), c + r * math.sin(ang))], fill=PALE, width=int(S * 0.014))
    d.ellipse([c - r, c - r, c + r, c + r], outline=HOLO, width=int(S * 0.03))

    # pupil = drop of oil (slightly off centre, like something the radar just found)
    pr = S * 0.065
    px, py = c - S * 0.035, c + S * 0.035
    og = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(og).ellipse([px - pr * 1.6, py - pr * 1.6, px + pr * 1.6, py + pr * 1.6], fill=OIL)
    og = og.filter(ImageFilter.GaussianBlur(S * 0.02))
    og.putalpha(og.getchannel("A").point(lambda v: v * 0.6))
    im = Image.alpha_composite(im, og)
    d = ImageDraw.Draw(im)
    d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=OIL)
    d.ellipse([px - pr * 0.35 - pr * 0.25, py - pr * 0.35 - pr * 0.25, px - pr * 0.35 + pr * 0.15, py - pr * 0.35 + pr * 0.15],
              fill=(255, 236, 200, 255))   # little shine

    return im.resize((size, size), Image.LANCZOS)


os.makedirs(OUT, exist_ok=True)
mark(512, False).save(os.path.join(OUT, "logo.png"), optimize=True)           # see-through, for the page
mark(512, True).save(os.path.join(OUT, "logo_square.png"), optimize=True)     # with dark tile, for sharing
mark(180, True).save(os.path.join(OUT, "apple-touch-icon.png"), optimize=True)
for n in (16, 32, 48, 192):
    mark(n, True).save(os.path.join(OUT, f"favicon-{n}.png"), optimize=True)
print("done")
