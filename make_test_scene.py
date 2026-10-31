"""
make_test_scene.py - makes a FAKE radar image so we can test detect.py without internet.

It puts in:
  - normal windy sea with radar speckle (grainy noise)
  - a ship (bright dot) with a long curved oil trail behind it   -> should be "likely oil"
  - a big blurry calm-wind patch                                  -> should be "look-alike"
  - a small round dark rain cell                                  -> should be low score

We know exactly where the oil is, so we can check if the program finds it.
    python make_test_scene.py      (writes test_scene.tif)
"""
import numpy as np
from scipy import ndimage as ndi
import rasterio
from rasterio.transform import from_bounds

rng = np.random.default_rng(7)
H, W = 900, 1100
# somewhere in the open arabian sea, so the land mask doesnt cut anything
west, south, east, north = 66.0, 16.0, 66.0 + W * 0.0002, 16.0 + H * 0.0002   # ~20 m pixels

# windy sea around -15 dB, slowly varying because wind isn't the same everywhere
yy, xx = np.mgrid[0:H, 0:W]
sea_db = -15 + 1.5 * np.sin(xx / 260) + 0.8 * np.cos(yy / 190)

truth = np.zeros((H, W), bool)

# 1) oil trail: a curved band getting wider towards its old end
t = np.linspace(0, 1, 600)
cx = 850 - 620 * t
cy = 200 + 380 * t + 60 * np.sin(t * 5)
width = 3 + 14 * t
for x, y, w in zip(cx, cy, width):
    truth |= (xx - x) ** 2 + (yy - y) ** 2 < w ** 2
oil = ndi.gaussian_filter(truth.astype(float), 1.0)
sea_db = sea_db - 9 * oil     # oil damps the waves -> ~9 dB darker

# ship at the head of the trail (bright)
sea_db[(xx - 858) ** 2 + (yy - 195) ** 2 < 9] = 5

# 2) calm wind patch: huge and with soft edges
calm = np.exp(-(((xx - 300) / 260) ** 2 + ((yy - 230) / 160) ** 2))
sea_db = sea_db - 6 * calm

# 3) rain cell: small round dark spot with a bright ring
r = np.hypot(xx - 900, yy - 720)
sea_db = sea_db - 6 * np.exp(-(r / 25) ** 2) + 2 * np.exp(-((r - 45) / 8) ** 2)

# speckle: multiplicative gamma noise, 4 "looks" (that's about right for 20 m GRD)
lin = 10 ** (sea_db / 10)
lin = lin * rng.gamma(4.4, 1 / 4.4, size=lin.shape)

tr = from_bounds(west, south, east, north, W, H)
with rasterio.open("test_scene.tif", "w", driver="GTiff", height=H, width=W, count=2,
                   dtype="float32", crs="EPSG:4326", transform=tr) as dst:
    dst.write(lin.astype("float32"), 1)
    dst.write(np.ones((H, W), "float32"), 2)
np.save("test_scene_truth.npy", truth)
print("wrote test_scene.tif  (truth oil area:", round(truth.sum() * 0.0004, 2), "km2 approx)")
