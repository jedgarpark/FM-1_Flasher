#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Render the start-up splash from text and two colours (480x320 PNG).

  tools/make_splash.py --font ~/Library/Fonts/Gotham-Black.ttf \
      --bg 000000 --fg b061ff --out art/splash_text.png

Same layout as art/fff_splash.png: "FM-1" large, "FIRMWARE" and "FLASHER"
small, centred. The font isn't in the repo (any heavy sans works); only the
PNG is. tools/deploy.py turns the PNG into CIRCUITPY/splash.bmp.
"""
import argparse

from PIL import Image, ImageDraw, ImageFont

W, H = 480, 320
# (text, cap height, top of the caps), measured from art/fff_splash.png
LINES = (("FM-1", 66, 72), ("FIRMWARE", 27, 146), ("FLASHER", 27, 180))


def colour(s):
    return tuple(int(s.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def font_for(path, cap):
    """The font size whose capital H is cap pixels tall."""
    size = cap
    for _ in range(4):
        top, bottom = ImageFont.truetype(path, size).getbbox("H", anchor="ls")[1::2]
        size = max(1, round(size * cap / (bottom - top)))
    return ImageFont.truetype(path, size)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--font", required=True, help="a heavy sans .ttf/.otf")
    ap.add_argument("--bg", default="000000", help="background, hex RGB")
    ap.add_argument("--fg", default="b061ff", help="text, hex RGB")
    ap.add_argument("--out", default="art/splash_text.png")
    a = ap.parse_args()
    im = Image.new("RGB", (W, H), colour(a.bg))
    d = ImageDraw.Draw(im)
    for text, cap, top in LINES:
        # "ls" anchors at the baseline; caps sit cap pixels above it.
        d.text((W // 2, top + cap), text, font=font_for(a.font, cap),
               fill=colour(a.fg), anchor="ms")
    im.save(a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
