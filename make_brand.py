#!/usr/bin/env python3
"""Generate HACS brand assets for the Proton Link integration.

HACS requires custom_components/<domain>/brand/{icon.png,icon@2x.png}.
Rendered at 4x then downsampled with LANCZOS for clean antialiased edges.
"""
from PIL import Image, ImageDraw

S = 1024                      # supersampled working size
FINAL = 512                   # icon@2x size; icon.png = 256


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(size, top, bottom):
    """Vertical linear gradient."""
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        d.line([(0, y), (size, y)], fill=lerp(top, bottom, y / (size - 1)))
    return img


# Deep Proton blue -> teal.  Original artwork; deliberately NOT the Proton
# tiger/shield trademark.
BG_TOP = (26, 78, 138)
BG_BOTTOM = (13, 155, 168)
WHITE = (255, 255, 255)
WHEEL = (18, 40, 66)

img = gradient(S, BG_TOP, BG_BOTTOM).convert("RGBA")

# Rounded-square mask (HA icons sit on a rounded tile).
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=225, fill=255)
tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
tile.paste(img, (0, 0), mask)
d = ImageDraw.Draw(tile)

# --- connectivity arcs (the "Link") ---------------------------------------
cx, cy = S // 2, 470
for i, r in enumerate((300, 214, 128)):
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, start=205, end=335, fill=WHITE, width=42)

# --- car silhouette -------------------------------------------------------
# cabin (trapezoid)
d.polygon([(352, 700), (438, 566), (612, 566), (688, 700)], fill=WHITE)
# body
d.rounded_rectangle([176, 672, 848, 800], radius=54, fill=WHITE)
# wheels
for wx in (312, 712):
    d.ellipse([wx - 74, 742, wx + 74, 890], fill=WHEEL)
    d.ellipse([wx - 28, 788, wx + 28, 844], fill=WHITE)

# --- emit -----------------------------------------------------------------
tile.resize((FINAL, FINAL), Image.LANCZOS).save(
    "custom_components/protonlink/brand/icon@2x.png"
)
tile.resize((FINAL // 2, FINAL // 2), Image.LANCZOS).save(
    "custom_components/protonlink/brand/icon.png"
)

# Optional wide logo with wordmark.
logo = Image.new("RGBA", (S * 2, S), (0, 0, 0, 0))
logo.paste(tile, (0, 0), tile)
dl = ImageDraw.Draw(logo)
from PIL import ImageFont

try:
    f1 = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150
    )
    f2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 78)
except OSError:
    f1 = f2 = ImageFont.load_default()

dl.text((S + 60, 350), "Proton Link", font=f1, fill=WHITE, anchor="lm")
dl.text((S + 64, 490), "Home Assistant", font=f2, fill=(200, 228, 240), anchor="lm")

logo.resize((FINAL * 2, FINAL), Image.LANCZOS).save(
    "custom_components/protonlink/brand/logo@2x.png"
)
logo.resize((FINAL, FINAL // 2), Image.LANCZOS).save(
    "custom_components/protonlink/brand/logo.png"
)

print("brand assets written:")
import os

for f in sorted(os.listdir("custom_components/protonlink/brand")):
    p = f"custom_components/protonlink/brand/{f}"
    print(f"  {f}  {os.path.getsize(p)} bytes")
