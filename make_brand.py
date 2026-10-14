#!/usr/bin/env python3
"""Generate HACS brand assets for the Proton Link integration.

Source of truth: brand-src/protonlink-app-icon-1024.png -- the official
PROTON Link app icon, retrieved from the Apple App Store lookup API for
bundle id cn.com.ecarx.protonlink (seller: Proton Holdings Berhad) and
cross-checked pixel-for-pixel against the launcher icon inside the APK of
that same package.

Emits the files Home Assistant's brand directory accepts:
  icon.png / icon@2x.png            square avatar (the app tile)
  logo.png / logo@2x.png            wide lockup, for LIGHT backgrounds
  dark_logo.png / dark_logo@2x.png  wide lockup, for DARK backgrounds

Lockup hierarchy: the app tile sits on the left, then the brand name in
large type with "for Home Assistant" set beneath it as a subordinate
descriptor.  Measured, not eyeballed: at 1024px the tile's own baked-in
wordmark is only ~41px tall (~9px once scaled into the lockup), so the
brand name is repeated in readable type rather than left to the tile.

Run:  python make_brand.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

SRC = "brand-src/protonlink-app-icon-1024.png"
OUT = "custom_components/protonlink/brand"

ICON_1X, ICON_2X = 256, 512
LOGO_H = 256          # logo@2x height; logo.png is exactly half
SS = 4                # supersample factor for text/corner crispness

# Proton's own store assets use a corner radius of 80/512 = 15.6% of the tile
# width.  Matching it keeps our tile identical to their presentation.
CORNER_FRAC = 80 / 512

BRAND = "Proton Link"
DESCR = "for Home Assistant"

LIGHT_FILL = (31, 54, 71)      # dark slate for light backgrounds
DARK_FILL = (233, 240, 244)    # near-white for dark backgrounds
LIGHT_DESC = (88, 104, 118)    # muted but legible, keeps the brand name dominant
DARK_DESC = (168, 185, 198)


def font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for path in (
        f"/usr/share/fonts/truetype/dejavu/{name}",
        "/usr/share/fonts/truetype/liberation/LiberationSans"
        f"{'-Bold' if bold else '-Regular'}.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(im, radius):
    """Mask an image to a rounded square with an antialiased edge."""
    w, h = im.size
    mask = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * SS - 1, h * SS - 1], radius=radius * SS, fill=255
    )
    out = im.convert("RGBA")
    out.putalpha(mask.resize((w, h), Image.LANCZOS))
    return out


# ------------------------------------------------------------------ the tile
master = Image.open(SRC).convert("RGBA")
if master.size != (1024, 1024):
    raise SystemExit(f"unexpected master size {master.size}")
tile = rounded(master, round(CORNER_FRAC * master.size[0]))

for name, size in (("icon.png", ICON_1X), ("icon@2x.png", ICON_2X)):
    tile.resize((size, size), Image.LANCZOS).save(f"{OUT}/{name}")


# ------------------------------------------------------------------- the logo
def build_logo(height, brand_fill, desc_fill):
    """Wide two-line lockup at `height`, width measured from the glyphs."""
    H = height
    tile_h = round(H * 0.90)
    pad = round(H * 0.035)
    gap = round(H * 0.13)
    lead = round(H * 0.025)

    f_brand = font(round(tile_h * 0.36))
    f_desc = font(round(tile_h * 0.20), bold=False)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = max(
        int(probe.textlength(BRAND, font=f_brand)),
        int(probe.textlength(DESCR, font=f_desc)),
    )
    W = pad * 2 + tile_h + gap + tw

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(
        tile.resize((tile_h, tile_h), Image.LANCZOS), (pad, (H - tile_h) // 2)
    )

    ab = f_brand.getmetrics()
    ad = f_desc.getmetrics()
    block = ab[0] + ab[1] + lead + ad[0] + ad[1]
    x = pad + tile_h + gap
    y = (H - block) // 2

    draw = ImageDraw.Draw(img)
    draw.text((x, y), BRAND, font=f_brand, fill=brand_fill, anchor="la")
    draw.text(
        (x, y + ab[0] + ab[1] + lead), DESCR, font=f_desc, fill=desc_fill,
        anchor="la",
    )
    return img


for base, bf, df in (
    ("logo", LIGHT_FILL, LIGHT_DESC),
    ("dark_logo", DARK_FILL, DARK_DESC),
):
    # Build at 2x then halve, so logo.png is EXACTLY half of logo@2x.png.
    big = build_logo(LOGO_H * 2, bf, df)
    big.resize((big.width // 2, LOGO_H), Image.LANCZOS).save(f"{OUT}/{base}@2x.png")
    big.resize((big.width // 4, LOGO_H // 2), Image.LANCZOS).save(f"{OUT}/{base}.png")

# ------------------------------------------------- README hero (plain <img>)
# HACS renders the README through HA's ha-markdown, whose sanitiser whitelist
# allows <img> but NOT <picture>/<source> -- those get escaped and shown as
# literal code.  A transparent lockup would also be unreadable against one of
# GitHub's two themes, so the hero is composited onto an OPAQUE light panel:
# a single plain <img> that is correct in HACS, and on GitHub light and dark.
PANEL_BG = (247, 249, 250)
PANEL_EDGE = (223, 230, 236)
HERO_H = 256


def build_hero():
    """Opaque card: app tile + two-line lockup, legible on any background.

    The panel width is measured from the glyphs and the tile rather than being
    fixed, so the card has even margins instead of a dead pocket under the
    shorter second line.
    """
    H = HERO_H
    tile_h = round(H * 0.60)
    pad = round(H * 0.11)
    gap = round(H * 0.09)
    lead = round(H * 0.02)

    f_brand = font(round(tile_h * 0.46))
    f_desc = font(round(tile_h * 0.24), bold=False)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = max(
        int(probe.textlength(BRAND, font=f_brand)),
        int(probe.textlength(DESCR, font=f_desc)),
    )
    W = pad * 2 + tile_h + gap + tw

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [0, 0, W - 1, H - 1],
        radius=round(H * 0.10),
        fill=PANEL_BG,
        outline=PANEL_EDGE,
        width=2,
    )

    img.alpha_composite(
        tile.resize((tile_h, tile_h), Image.LANCZOS),
        (pad, (H - tile_h) // 2),
    )

    ab, ad = f_brand.getmetrics(), f_desc.getmetrics()
    block = ab[0] + ab[1] + lead + ad[0] + ad[1]
    x = pad + tile_h + gap
    y = (H - block) // 2

    d.text((x, y), BRAND, font=f_brand, fill=LIGHT_FILL, anchor="la")
    d.text(
        (x, y + ab[0] + ab[1] + lead), DESCR, font=f_desc, fill=LIGHT_DESC,
        anchor="la",
    )
    return img


os.makedirs("assets", exist_ok=True)
hero = build_hero()
hero.save("assets/logo-hero.png")
hero.resize((hero.width // 2, hero.height // 2), Image.LANCZOS).save(
    "assets/logo-hero@1x.png"
)
print(f"hero: {hero.size[0]}x{hero.size[1]}")


# ------------------------------------------------------------------- report
print("brand assets written from", SRC)
for f in sorted(os.listdir(OUT)):
    p = f"{OUT}/{f}"
    with Image.open(p) as im:
        print(f"  {f:18} {im.size[0]:4}x{im.size[1]:<4} {os.path.getsize(p):>6} bytes")
