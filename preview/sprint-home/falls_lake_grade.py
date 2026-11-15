"""Crop + gentle neutral grade for the Falls Lake hero. Deterministic; parameters saved to grade-params.json."""
import json, hashlib, numpy as np
from PIL import Image
SRC = "/workspace/falls-lake/Falls_Lake_Galyonkin_52741376400.jpg"
OUT = "/workspace/cb-design/.wt-sprint/preview/sprint-home/photos/falls-lake-pier"
P = {
    "source_sha256": "54e27cdd2b952fe432de46c362ee237c0d43fe28e2830fa81a75ecc5f7d78f25",
    "source_size": [9528, 6328],
    "crop_box_xywh": [2466, 186, 5208, 3906],   # 4:3, original pixel coords
    "levels_black": {"R": 14, "G": 14, "B": 6},  # per-channel input black point: halves the lifted matte and neutralises its warm tint
    "levels_white": {"R": 248, "G": 252, "B": 248},  # per-channel input white point; G slightly higher = ~1.6% less green to ease the teal cast
    "gamma": 1.04,   # tiny midtone lift so the black-point change does not darken the grass
    "saturation": 0.92,   # slight desaturation (luma-preserving blend toward Rec.709 grey)
    "resample": "LANCZOS",
    "outputs": {"800": [800, 600], "1280": [1280, 960]},
    "avif_quality": 50, "webp_quality": 76,
    "no_other_adjustments": "no added saturation, sharpening, vignette, filters or local edits",
}
assert hashlib.sha256(open(SRC, "rb").read()).hexdigest() == P["source_sha256"]
im = Image.open(SRC).convert("RGB")
x, y, w, h = P["crop_box_xywh"]
a = np.asarray(im.crop((x, y, x + w, y + h))).astype(np.float32)
for i, ch in enumerate("RGB"):
    b, wp = P["levels_black"][ch], P["levels_white"][ch]
    a[..., i] = np.clip((a[..., i] - b) / (wp - b), 0, 1) ** (1 / P["gamma"]) * 255
lum = (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2])[..., None]
a = np.clip(lum + (a - lum) * P["saturation"], 0, 255)
g = Image.fromarray(a.round().astype(np.uint8))
g.save("/tmp/fl-graded-full.png")
for k, (ow, oh) in P["outputs"].items():
    r = g.resize((ow, oh), Image.LANCZOS)
    r.save("%s-%s.avif" % (OUT, k), quality=P["avif_quality"])
    r.save("%s-%s.webp" % (OUT, k), quality=P["webp_quality"], method=6)
json.dump(P, open("/workspace/sprint-home/falls-lake/grade-params.json", "w"), indent=2)
print("ok")
