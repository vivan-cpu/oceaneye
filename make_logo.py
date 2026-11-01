"""make_logo.py - OceanEye logo: an eye. the iris is a radar screen, the pupil is a drop of oil
(red, the same red the program draws around oil). flat, no glow.
drawn big with Pillow, then shrunk so the edges are smooth.
    python make_logo.py          (writes into web/img)
"""
import math, os, sys
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else "web/img"
S = 2048                    # work size
INK = (21, 25, 28, 255)
WHITE = (255, 255, 255, 255)
GREY = (150, 158, 163, 255)
RED = (226, 76, 56, 255)


def eye_points(cx, cy, w, h, n=240):
    """almond shape made from two circle arcs"""
    half = w / 2
    r = (half ** 2 + (h / 2) ** 2) / h
    a0 = math.asin(half / r)
    top = [(cx + r * math.sin(-a0 + 2 * a0 * i / n), cy + (r - h / 2) - r * math.cos(-a0 + 2 * a0 * i / n)) for i in range(n + 1)]
    bot = [(cx + r * math.sin(a0 - 2 * a0 * i / n), cy - (r - h / 2) + r * math.cos(a0 - 2 * a0 * i / n)) for i in range(n + 1)]
    return top, bot


def mark(size):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = S / 2
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=S * 0.2, fill=INK)

    # eye outline = white almond with a smaller ink almond inside
    ew, eh, stroke = S * 0.80, S * 0.48, S * 0.05
    top, bot = eye_points(c, c, ew, eh)
    itop, ibot = eye_points(c, c, ew - stroke * 3.2, eh - stroke * 2)
    d.polygon(top + bot, fill=WHITE)
    d.polygon(itop + ibot, fill=INK)

    # iris = radar screen: ring, one range circle and a sweep line
    r = S * 0.185
    d.ellipse([c - r, c - r, c + r, c + r], outline=WHITE, width=int(S * 0.03))
    rr = r * 0.58
    d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=GREY, width=int(S * 0.012))
    ang = math.radians(-55)
    d.line([(c, c), (c + (r - S * 0.02) * math.cos(ang), c + (r - S * 0.02) * math.sin(ang))], fill=GREY, width=int(S * 0.016))

    # pupil = drop of oil, a bit off centre like something the radar just found
    pr = S * 0.072
    px, py = c - S * 0.04, c + S * 0.04
    d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=RED)

    return im.resize((size, size), Image.LANCZOS)


os.makedirs(OUT, exist_ok=True)
big = mark(512)
big.save(os.path.join(OUT, "logo.png"), optimize=True)
big.save(os.path.join(OUT, "logo_square.png"), optimize=True)
mark(64).save(os.path.join(OUT, "logo-64.png"), optimize=True)
mark(180).save(os.path.join(OUT, "apple-touch-icon.png"), optimize=True)
for n in (16, 32, 48, 192):
    mark(n).save(os.path.join(OUT, f"favicon-{n}.png"), optimize=True)
print("done")
