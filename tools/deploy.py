#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Copy the flasher UI to a CIRCUITPY drive, compiled to .mpy.

  .venv/bin/python tools/deploy.py --mpy-cross ref/circuitpython/mpy-cross/build/mpy-cross

Copies code.py, fonts/ (.fmf), lib/fm1ui and the fm1 libraries, and compiles
the board's adafruit_hx8357/ft5336/register .py files in place. The
mpy-cross must match the board's CircuitPython version. A .py of the same
name on the board is removed, so the .mpy is the one imported.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FM1_LIBS = ("fm1proto.py", "fm1update.py", "fm1usb.py")
VENDOR = ()  # (package, (files...)) from the venv, compiled; none needed now
VENDOR_MODULES = ()
# Already on the board as .py (from the bundle): compiled in place to save RAM.
BOARD_PY = ("adafruit_hx8357.py", "adafruit_ft5336.py", "adafruit_register/i2c_bits.py")


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
    args = ap.parse_args()

    lib = os.path.join(args.drive, "lib")
    n = 0
    for name in FM1_LIBS:
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
    shutil.copy(os.path.join(ROOT, "device", "code.py"), os.path.join(args.drive, "code.py"))
    os.sync()
    print("deployed %d modules, fonts and code.py to %s" % (n, args.drive))


if __name__ == "__main__":
    sys.exit(main())
