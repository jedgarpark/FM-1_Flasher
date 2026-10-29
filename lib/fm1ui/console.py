# SPDX-License-Identifier: GPL-3.0-only
"""The note on CircuitPython's console while the flasher restarts.

Each install restarts twice (to install on a fresh heap, then back to the
list), and a restart shows the console until the UI's first frame. code.py
calls show() first thing, then drops this module, so its code doesn't take
RAM for the rest of the run."""
import microcontroller


def show():
    """Clear the console and say what's happening. The pending install is
    read as fm1ui.device stores it (NVM_TAG), without importing that."""
    nvm = microcontroller.nvm
    if nvm is not None and bytes(nvm[0:4]) == b"FM1P":
        queued = bytes(nvm[6:6 + (nvm[4] | nvm[5] << 8)]).decode()  # slug, tab, name
        what = "Getting ready to install\n%s..." % queued.rpartition("\t")[2]
    else:
        what = "Loading the firmware list..."
    print("\x1b[2J\nFM-1 Flasher\n\n%s\n\nThe touchscreen comes back\nin a few seconds.\n" % what)
