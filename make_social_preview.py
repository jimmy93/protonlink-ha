#!/usr/bin/env python3
"""Generate the GitHub social-preview card (1280x640) for the repo.

GitHub's social preview is UI-only (no REST API), so this script produces the
image and the operator uploads it once at:
  Settings -> General -> Social preview -> Upload an image

The card shows the REAL PROTON Link app icon (the same master make_brand.py
uses), so the repo card, the HACS icon and the README all show one product.

Layout is measured, not guessed: the headline is auto-fitted to the text
column so it can never collide with the icon, whatever font resolves.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1280, 640
SRC = "brand-src/protonlink-app-icon-1024.png"

BG_TOP = (18, 58, 104)      # deep navy
BG_BOTTOM = (12, 104, 118)  # deep teal
WHITE = (255, 255, 255)

TEXT_X = 88          # left margin
COL_RIGHT = 760      # text column must not cross this
CARD = 336           # light panel holding the app icon
ICON = 268           # icon size inside that panel
PANEL_X = 852
PANEL_Y = (H - CARD) // 2


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


def rounded(im, frac):
    """Round a full-bleed square to an app-icon squircle.

    The store master is full-bleed (Apple masks at render time, Google ships
    a pre-rounded copy at radius 80/512 = 15.6%), so we apply the same radius
    to present it as a genuine app tile rather than a square photo.
    """
    w, h = im.size
    ss = 4
    mask = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * ss - 1, h * ss - 1], radius=round(frac * w * ss), fill=255
    )
    out = im.convert("RGBA")
    out.putalpha(mask.resize((w, h), Image.LANCZOS))
    return out


# ------------------------------------------------------------- the canvas
card = Image.new("RGB", (W, H))
cd = ImageDraw.Draw(card)
for y in range(H):
    cd.line([(0, y), (W, y)], fill=lerp(BG_TOP, BG_BOTTOM, y / (H - 1)))
card = card.convert("RGBA")

# Calm veil behind the type only, so the text never fights the gradient.
veil = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(veil).rectangle([0, 0, COL_RIGHT + 40, H], fill=(5, 20, 36, 120))
card = Image.alpha_composite(card, veil)

# --------------------------------------------------- the real app icon
# Drop shadow, then a light rounded panel, then the authentic icon on top.
shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle(
    [PANEL_X + 8, PANEL_Y + 14, PANEL_X + CARD + 8, PANEL_Y + CARD + 14],
    radius=56, fill=(0, 0, 0, 170),
)
card = Image.alpha_composite(card, shadow.filter(ImageFilter.GaussianBlur(18)))

panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(panel).rounded_rectangle(
    [PANEL_X, PANEL_Y, PANEL_X + CARD, PANEL_Y + CARD],
    radius=52, fill=(247, 250, 252, 255),
)
card = Image.alpha_composite(card, panel)

icon = rounded(
    Image.open(SRC).convert("RGBA").resize((ICON, ICON), Image.LANCZOS),
    80 / 512,
)
card.alpha_composite(
    icon, (PANEL_X + (CARD - ICON) // 2, PANEL_Y + (CARD - ICON) // 2)
)

# ------------------------------------------------------------- the type
head_text = "Proton Link"
size = 104
while size > 40 and width(head_text, font(True, size)) > COL_RIGHT - TEXT_X:
    size -= 2
f_head = font(True, size)
f_sub = font(False, 46)
f_body = font(False, 33)
f_note = font(False, 29)

sub_text = "for Home Assistant"
body_text = "Odometer \u00b7 Fuel \u00b7 Trips \u00b7 Location"
note_text = "Read-only. No remote control."

head_h, sub_h, body_h, note_h = 108, 52, 40, 36
rule_gap, after_rule = 30, 34
stack = head_h + sub_h + rule_gap + 3 + after_rule + body_h + 20 + note_h
y = (H - stack) // 2

cd = ImageDraw.Draw(card)
cd.text((TEXT_X, y), head_text, font=f_head, fill=WHITE, anchor="la")
y += head_h
cd.text((TEXT_X + 2, y), sub_text, font=f_sub, fill=(203, 230, 243), anchor="la")
y += sub_h + rule_gap
rule_w = int(width(body_text, f_body))
cd.rectangle([TEXT_X, y, TEXT_X + rule_w, y + 3], fill=(255, 255, 255, 165))
y += 3 + after_rule
cd.text((TEXT_X, y), body_text, font=f_body, fill=(223, 241, 249), anchor="la")
y += body_h + 20
cd.text((TEXT_X, y), note_text, font=f_note, fill=(198, 224, 240), anchor="la")

card.convert("RGB").save("social-preview.png", optimize=True)
print(
    f"social-preview.png {card.size}  headline={size}px  "
    f"text_right={TEXT_X + max(width(head_text, f_head), rule_w)}  "
    f"panel_x={PANEL_X}  clearance="
    f"{PANEL_X - TEXT_X - max(width(head_text, f_head), rule_w)}px"
)
