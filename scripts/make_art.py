"""
One-off: turn the profile picture into coloured ASCII art data (scripts/art.json).

Not run by the Action. Re-run locally only if the profile picture changes or
you want to re-tune the art:

    pip install pillow numpy scipy
    python scripts/make_art.py path/to/avatar.png

Each cell gets a character and a colour class:
    0-6  fur, darkest -> brightest
    E    iris (solid)     e  iris edge     p  pupil
    c    collar           b  bell
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

SRC = sys.argv[1] if len(sys.argv) > 1 else "avatar.png"
OUT = Path(__file__).with_name("art.json")

COLS = 46                       # art width in characters
ROW_ASPECT = 0.42               # char height/width compensation for monospace
CROP = (60, 10, 340, 345)       # head + collar, in 460x460 avatar pixels
FUR_RAMP = ".:-=+*#"            # index == fur level 0-6

# Hand-placed collar band and bell, in CROP pixel coordinates.
COLLAR_TOP = ((102, 293), (258, 220))
COLLAR_BOTTOM = ((107, 309), (261, 236))
BELL = (156, 321, 11)           # cx, cy, r


def largest_component(mask):
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


def main():
    img = Image.open(SRC).convert("RGB").resize((460, 460), Image.LANCZOS).crop(CROP)
    px = np.asarray(img.filter(ImageFilter.GaussianBlur(0.8))).astype(float)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    lum = px.mean(axis=2)
    h, w = lum.shape

    # Eyes: saturated amber irises, pupils are the holes inside them.
    iris = ndimage.binary_opening((r > 95) & (r - b > 45), iterations=1)
    lab, n = ndimage.label(iris)
    sizes = ndimage.sum(iris, lab, range(1, n + 1))
    iris = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 400])
    eye = ndimage.binary_fill_holes(ndimage.binary_closing(iris, iterations=6))

    # Cat silhouette: dark and not sky-blue, largest blob only.
    cat = ((lum < 82) & ((b - r) < 32)) | eye
    cat = ndimage.binary_closing(cat, iterations=3)
    cat = ndimage.binary_fill_holes(largest_component(cat))

    # Collar band (quad) and bell (circle).
    yy, xx = np.mgrid[0:h, 0:w]
    (tx0, ty0), (tx1, ty1) = COLLAR_TOP
    (bx0, by0), (bx1, by1) = COLLAR_BOTTOM
    t = np.clip((xx - tx0) / (tx1 - tx0), 0, 1)
    top_y = ty0 + (ty1 - ty0) * t
    bot_y = by0 + (by1 - by0) * t
    collar = (xx >= tx0) & (xx <= bx1) & (yy >= top_y) & (yy <= bot_y) & cat
    cx, cy, cr = BELL
    bell = ((xx - cx) ** 2 + (yy - cy) ** 2) <= cr ** 2

    rows = int(round(COLS * h / w * ROW_ASPECT))

    def cells(mask):
        return np.asarray(
            Image.fromarray(mask.astype(np.float32)).resize((COLS, rows), Image.BOX)
        )

    cat_c, eye_c, iris_c = cells(cat), cells(eye), cells(iris)
    collar_c, bell_c = cells(collar), cells(bell)
    fur_lum = cells(np.where(cat & ~eye, lum, 0.0)) / np.maximum(cat_c - eye_c, 1e-3)

    eye_cell = eye_c > 0.3
    halo = ndimage.binary_dilation(eye_cell, structure=np.ones((1, 3))) & ~eye_cell

    out_rows = []
    for y in range(rows):
        chars, classes = [], []
        for x in range(COLS):
            if bell_c[y, x] > 0.35:
                ch, cl = ("O" if bell_c[y, x] > 0.7 else "o"), "b"
            elif eye_cell[y, x]:
                if iris_c[y, x] > 0.45:
                    ch, cl = "@", "E"
                elif iris_c[y, x] > 0.2:
                    ch, cl = "%", "e"
                else:
                    ch, cl = ".", "p"
            elif halo[y, x] or cat_c[y, x] <= 0.3:
                ch, cl = " ", " "
            elif collar_c[y, x] > 0.35:
                ch, cl = "=", "c"
            else:
                v = float(np.clip((fur_lum[y, x] - 8) / 50, 0, 1)) ** 0.85
                lvl = min(len(FUR_RAMP) - 1, int(v * len(FUR_RAMP)))
                ch, cl = FUR_RAMP[lvl], str(lvl)
            chars.append(ch)
            classes.append(cl)
        out_rows.append(["".join(chars).rstrip(), "".join(classes)[: len("".join(chars).rstrip())]])

    while out_rows and not out_rows[0][0].strip():
        out_rows.pop(0)

    OUT.write_text(json.dumps({"cols": COLS, "rows": out_rows}, indent=1))
    for text, _ in out_rows:
        print(text)


if __name__ == "__main__":
    main()
