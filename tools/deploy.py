#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Copy the flasher UI to a CIRCUITPY drive, compiled to .mpy.

  .venv/bin/python tools/deploy.py --mpy-cross ref/circuitpython/mpy-cross/build/mpy-cross

Copies code.py, fonts/ (.fmf), the splash (art/splash_text.png, or
art/splash_text_320.png on the Metro ESP32-P4, as a 16-colour splash.bmp,
needs Pillow), lib/fm1ui and the fm1 libraries, compiles
the board's adafruit_hx8357/ft5336/register .py files in place, and sets
CIRCUITPY_SDCARD_USB = false in settings.toml (takes effect after a reset). The
mpy-cross must match the board's CircuitPython version. A .py of the same
name on the board is removed, so the .mpy is the one imported.

The board (feather or metro-p4) comes from the drive's boot_out.txt; --board
overrides it. The Metro also needs adafruit_ili9341, adafruit_focaltouch,
adafruit_bus_device, adafruit_usb_host_descriptors, adafruit_requests and
adafruit_connection_manager from the bundle in lib/.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FM1_LIBS = ("fm1proto.py", "fm1update.py", "fm1usb.py")
BOARD_LIBS = {"metro-p4": ("fm1catalog.py", "fm1pic.py")}  # Update firmwares over WiFi
VENDOR = ()  # (package, (files...)) from the venv, compiled; none needed now
VENDOR_MODULES = ()
# Already on the board as .py (from the bundle): compiled in place to save RAM.
BOARD_PY = ("adafruit_hx8357.py", "adafruit_ft5336.py", "adafruit_register/i2c_bits.py")
# Keeps the computer from reading /sd over USB while the flasher uses it: the two
# collide on the SPI bus and FatFs gets stale sectors (DEVNOTES §6.18).
SETTINGS = {"CIRCUITPY_SDCARD_USB": "false"}
SPLASH = {"feather": "art/splash_text.png",  # 480x320 (tools/make_splash.py); fm1ui.device.SPLASH
          "metro-p4": "art/splash_text_320.png"}  # 320x240
BOARD_IDS = {"adafruit_metro_esp32p4": "metro-p4"}  # anything else: feather


def detect_board(drive):
    """feather or metro-p4, from the drive's boot_out.txt."""
    try:
        with open(os.path.join(drive, "boot_out.txt")) as f:
            for line in f:
                if line.startswith("Board ID:"):
                    return BOARD_IDS.get(line.split(":", 1)[1].strip(), "feather")
    except OSError:
        pass
    return "feather"


def write_splash(drive, board="feather"):
    """Convert the splash PNG to an 8-bit BMP with 16 colours, which OnDiskBitmap
    reads (154 KB; Pillow writes no 4-bit BMP). Written only when it changed,
    so the board doesn't reload."""
    from PIL import Image
    im = Image.open(os.path.join(ROOT, SPLASH[board])).convert("RGB")
    im = im.quantize(16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    buf = BytesIO()
    im.save(buf, "BMP")
    data = buf.getvalue()
    dst = os.path.join(drive, "splash.bmp")
    try:
        with open(dst, "rb") as f:
            if f.read() == data:
                return
    except OSError:
        pass
    with open(dst, "wb") as f:
        f.write(data)


def update_settings(drive):
    """Set SETTINGS in the board's settings.toml, keeping any other lines."""
    path = os.path.join(drive, "settings.toml")
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    lines = [ln for ln in lines if ln.split("=", 1)[0].strip() not in SETTINGS]
    lines += ["%s = %s" % kv for kv in SETTINGS.items()]
    text = "\n".join(lines) + "\n"
    try:
        with open(path) as f:
            if f.read() == text:
                return
    except OSError:
        pass
    with open(path, "w") as f:
        f.write(text)


def compile_to(mpy_cross, src, dst_dir):
    """Compile locally, then copy the whole file: mpy-cross's small writes
    straight to the CIRCUITPY drive are very slow."""
    name = os.path.splitext(os.path.basename(src))[0]
    dst = os.path.join(dst_dir, name + ".mpy")
    os.makedirs(dst_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, name + ".mpy")
        subprocess.run([mpy_cross, "-s", os.path.basename(src), "-o", out, src], check=True)
        with open(out, "rb") as f:
            data = f.read()
    try:
        with open(dst, "rb") as f:
            if f.read() == data:
                return dst  # unchanged: don't make the board reload
    except OSError:
        pass
    with open(dst, "wb") as f:
        f.write(data)
    stale = os.path.join(dst_dir, name + ".py")
    if os.path.exists(stale):
        os.remove(stale)
    return dst


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", default="/Volumes/CIRCUITPY")
    ap.add_argument("--mpy-cross", required=True)
    ap.add_argument("--site-packages", help="where VENDOR libraries come from")
    ap.add_argument("--board", choices=sorted(SPLASH), help="default: from the drive's boot_out.txt")
    args = ap.parse_args()
    board = args.board or detect_board(args.drive)

    lib = os.path.join(args.drive, "lib")
    n = 0
    for name in FM1_LIBS + BOARD_LIBS.get(board, ()):
        compile_to(args.mpy_cross, os.path.join(ROOT, "lib", name), lib)
        n += 1
    for src in sorted(glob.glob(os.path.join(ROOT, "lib", "fm1ui", "*.py"))):
        compile_to(args.mpy_cross, src, os.path.join(lib, "fm1ui"))
        n += 1
    site = args.site_packages
    for package, files in VENDOR:
        for f in files:
            compile_to(args.mpy_cross, os.path.join(site, package, f), os.path.join(lib, package))
            n += 1
    for f in BOARD_PY:
        src = os.path.join(lib, f)
        if os.path.exists(src):
            with tempfile.TemporaryDirectory() as tmp:
                local = os.path.join(tmp, os.path.basename(f))
                shutil.copy(src, local)
                compile_to(args.mpy_cross, local, os.path.dirname(src))
            n += 1
    for f in VENDOR_MODULES:
        compile_to(args.mpy_cross, os.path.join(site, f), lib)
        n += 1
    fonts = os.path.join(args.drive, "fonts")
    os.makedirs(fonts, exist_ok=True)
    for f in glob.glob(os.path.join(ROOT, "fonts", "*.fmf")):
        dst = os.path.join(fonts, os.path.basename(f))
        if not (os.path.exists(dst) and open(dst, "rb").read() == open(f, "rb").read()):
            shutil.copy(f, fonts)
    write_splash(args.drive, board)
    update_settings(args.drive)
    shutil.copy(os.path.join(ROOT, "device", "code.py"), os.path.join(args.drive, "code.py"))
    os.sync()
    print("deployed %d modules, fonts, the splash, settings.toml and code.py to %s (%s)" % (n, args.drive, board))


if __name__ == "__main__":
    sys.exit(main())
