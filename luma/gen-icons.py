#!/usr/bin/env python3
"""Renders LumaBrowser's launcher icons and splash into luma/icons/.

    python3 luma/gen-icons.py [--font PATH]     # needs cairosvg and Pillow

The finish matches LumaTV's app family (lumaglass generators/gen-app-icons.py): a full-bleed opaque square (Home rounds
the corners), a top-left gloss, a bottom shade, one white glyph over a soft shadow. The glyph is Chromium's three-part
wheel drawn as glass: white panes at three opacities round an iris-violet lens.

iconColor in appinfo is the largeIcon's pixel (1,1), printed here.
"""
import argparse
import io
import math
import os

import cairosvg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icons")
SIZES = (("icon.png", 80), ("largeIcon.png", 130), ("extraLargeIcon.png", 240), ("icon160.png", 160))
V = 1024
C1, C2, SHADOW = "#7f8cff", "#3a2a9c", "#1d1160"
LENS = ("#b9a6ff", "#6a4ae0")


def glyph():
    cx = cy = 512
    R, r = 300, 124  # wheel and lens radii
    t = math.sqrt(R * R - r * r)
    panes = []
    for k, op in enumerate((1.0, 0.72, 0.46)):
        a0, a1 = math.radians(-90 + 120 * k), math.radians(30 + 120 * k)
        # each pane runs from a point on the lens along the lens's tangent to the rim, round the rim, and back along
        # the next tangent: Chromium's swirl
        tx0, ty0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        tx1, ty1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        ox0, oy0 = tx0 - t * math.sin(a0), ty0 + t * math.cos(a0)
        ox1, oy1 = tx1 - t * math.sin(a1), ty1 + t * math.cos(a1)
        panes.append(
            f'<path d="M{tx0:.1f} {ty0:.1f} L{ox0:.1f} {oy0:.1f} A{R} {R} 0 0 1 {ox1:.1f} {oy1:.1f} '
            f'L{tx1:.1f} {ty1:.1f} A{r} {r} 0 0 0 {tx0:.1f} {ty0:.1f} Z" fill="#fff" fill-opacity="{op}"/>')
    return f"""
<defs><linearGradient id="lens" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{LENS[0]}"/><stop offset="1" stop-color="{LENS[1]}"/></linearGradient></defs>
{''.join(panes)}
<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff"/>
<circle cx="{cx}" cy="{cy}" r="{r - 26}" fill="url(#lens)"/>
<path d="M{cx - 58} {cy - 22} q0 -40 40 -40 h30" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="22" stroke-linecap="round"/>
"""


def bg_svg():
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {V} {V}">
<defs>
<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{C1}"/><stop offset="1" stop-color="{C2}"/></linearGradient>
<radialGradient id="gloss" cx=".22" cy=".12" r=".75"><stop offset="0" stop-color="#fff" stop-opacity=".26"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<linearGradient id="shade" x1="0" y1=".62" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".18"/></linearGradient>
</defs>
<rect width="{V}" height="{V}" fill="url(#g)"/><rect width="{V}" height="{V}" fill="url(#gloss)"/><rect width="{V}" height="{V}" fill="url(#shade)"/>
</svg>"""


def raster(svg, n):
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=n, output_height=n)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def tile(n):
    im = raster(bg_svg(), n)
    g = raster(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {V} {V}">{glyph()}</svg>', n)
    sh = g.getchannel("A").filter(ImageFilter.GaussianBlur(max(1, round(n * 0.022)))).point(lambda v: int(v * 0.55))
    sh_img = Image.new("RGBA", (n, n), SHADOW + "ff")
    sh_img.putalpha(sh)
    im.alpha_composite(sh_img, (0, round(n * 0.020)))
    im.alpha_composite(g)
    return im.convert("RGB")


def splash(font):
    # LumaTV's splash ground (a dark violet diagonal), the rounded tile, the name in Manrope SemiBold
    w, h = 1920, 1080
    ground = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#191724"/><stop offset="1" stop-color="#26233a"/></linearGradient>
<radialGradient id="glow" cx=".5" cy=".5" r=".45"><stop offset="0" stop-color="#6a4ae0" stop-opacity=".22"/><stop offset="1" stop-color="#6a4ae0" stop-opacity="0"/></radialGradient></defs>
<rect width="{w}" height="{h}" fill="url(#g)"/><rect width="{w}" height="{h}" fill="url(#glow)"/></svg>"""
    img = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=ground.encode(), output_width=w, output_height=h))).convert("RGB")
    size = 340
    big = tile(size).convert("RGBA")
    m = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], size * 4 * 22 // 120, fill=255)
    big.putalpha(m.resize((size, size), Image.LANCZOS))
    img.paste(big, ((w - size) // 2, 300), big)
    draw = ImageDraw.Draw(img)
    f = ImageFont.truetype(font, 76)
    text = "LumaBrowser"
    draw.text(((w - draw.textlength(text, font=f)) / 2, 690), text, font=f, fill=(224, 222, 244))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", default=os.path.join(HERE, "..", "..", "lumaglass", "payload", "fonts", "Manrope-SemiBold.ttf"))
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for name, n in SIZES:
        im = tile(n)
        im.save(os.path.join(OUT, name), optimize=True)
        if name == "largeIcon.png":
            print("iconColor #%02x%02x%02x" % im.getpixel((1, 1)))
    splash(a.font).save(os.path.join(OUT, "splash.png"), optimize=True)


if __name__ == "__main__":
    main()
