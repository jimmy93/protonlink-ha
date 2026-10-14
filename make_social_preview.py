#!/usr/bin/env python3
"""Generate the GitHub social-preview card (1280x640) for the repo.

GitHub's social preview is UI-only (no REST API), so this script produces the
image and the operator uploads it once at:
  Settings -> General -> Social preview -> Upload an image

Reuses the exact gradient/mark from make_brand.py so the repo card, the HACS
icon and the README all look like one product.

Layout is measured, not guessed: headline size is auto-fitted to the text
column so it can never collide with the mark, whatever font resolves.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
S = 1024  # supersampled mark size

BG_TOP = (26, 78, 138)      # deep Proton blue
BG_BOTTOM = (13, 155, 168)  # teal
WHITE = (255, 255, 255)
WHEEL = (18, 40, 66)

TEXT_X = 88          # left margin
COL_RIGHT = 744      # text column must not cross this
GAP = 64             # clear space between text column and mark
PANEL = 392          # mark tile size
PANEL_X = COL_RIGHT + GAP
PANEL_Y = (H - PANEL) // 2


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def font(bold, size):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for p in (
        f"/usr/share/fonts/truetype/dejavu/{name}",
        f"/usr/share/fonts/truetype/liberation/LiberationSans"
        f"{'-Bold' if bold else '-Regular'}.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def width(text, f):
    return ImageDraw.Draw(Image.new("RGB", (8, 8))).textlength(text, font=f)


# ---------------------------------------------------------------- the mark
mark = Image.new("RGB", (S, S))
md = ImageDraw.Draw(mark)
for y in range(S):
    md.line([(0, y), (S, y)], fill=lerp(BG_TOP, BG_BOTTOM, y / (S - 1)))
mark = mark.convert("RGBA")

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=225, fill=255)
tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
tile.paste(mark, (0, 0), mask)
d = ImageDraw.Draw(tile)

# Wi-Fi arcs and car share one vertical axis (the tile centre, x = S/2).
cx, cy = S // 2, 470
for r in (300, 214, 128):
    d.arc([cx - r, cy - r, cx + r, cy + r], start=205, end=335, fill=WHITE, width=42)
d.polygon([(352, 700), (438, 566), (612, 566), (688, 700)], fill=WHITE)
d.rounded_rectangle([176, 672, 848, 800], radius=54, fill=WHITE)
for wx in (312, 712):
    d.ellipse([wx - 74, 742, wx + 74, 890], fill=WHEEL)
    d.ellipse([wx - 28, 788, wx + 28, 844], fill=WHITE)

# ------------------------------------------------------------- the canvas
card = Image.new("RGB", (W, H))
cd = ImageDraw.Draw(card)
for y in range(H):
    cd.line([(0, y), (W, y)], fill=lerp(BG_TOP, BG_BOTTOM, y / (H - 1)))
card = card.convert("RGBA")

# Calm panel behind the type only, so the text never fights the gradient.
veil = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(veil).rectangle([0, 0, PANEL_X - GAP // 2, H], fill=(6, 22, 40, 118))
card = Image.alpha_composite(card, veil)

mk = tile.resize((PANEL, PANEL), Image.LANCZOS)
card.alpha_composite(mk, (PANEL_X, PANEL_Y))

# ------------------------------------------------------------- the type
# Auto-fit the headline so it always clears the mark.
head_text = "Proton Link"
size = 100
while size > 40 and width(head_text, font(True, size)) > COL_RIGHT - TEXT_X:
    size -= 2
f_head = font(True, size)
f_sub = font(False, 46)
f_body = font(False, 33)
f_note = font(False, 29)

sub_text = "for Home Assistant"
body_text = "Odometer \u00b7 Fuel \u00b7 Trips \u00b7 Location"
note_text = "Read-only. No remote control."

# Vertically centre the whole text stack on the canvas centreline (H/2).
head_h, sub_h, body_h, note_h = 104, 52, 40, 36
rule_gap, after_rule = 30, 34
stack = head_h + sub_h + rule_gap + 3 + after_rule + body_h + 20 + note_h
y = (H - stack) // 2

cd = ImageDraw.Draw(card)
cd.text((TEXT_X, y), head_text, font=f_head, fill=WHITE, anchor="la")
y += head_h
cd.text((TEXT_X + 2, y), sub_text, font=f_sub, fill=(203, 230, 243), anchor="la")
y += sub_h + rule_gap
# rule spans the body line width -- it now means something.
rule_w = int(width(body_text, f_body))
cd.rectangle([TEXT_X, y, TEXT_X + rule_w, y + 3], fill=(255, 255, 255, 165))
y += 3 + after_rule
cd.text((TEXT_X, y), body_text, font=f_body, fill=(223, 241, 249), anchor="la")
y += body_h + 20
cd.text((TEXT_X, y), note_text, font=f_note, fill=(163, 203, 224), anchor="la")

card.convert("RGB").save("social-preview.png", optimize=True)
print(f"social-preview.png {card.size}  headline={size}px  "
      f"text_right={TEXT_X + max(width(head_text, f_head), rule_w)}  "
      f"panel_x={PANEL_X}  clearance="
      f"{PANEL_X - TEXT_X - max(width(head_text, f_head), rule_w)}px")
