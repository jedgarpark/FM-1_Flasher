# SPDX-License-Identifier: GPL-3.0-only
"""Try to wake a silent FM-1 on the Feather's built-in (PIO) USB host port
without resetting the board.

A silent FM-1 holds D+/D- low and never attaches. Cycling VBUS doesn't wake it,
but a board reset did once. At boot CircuitPython shuts the D+/D- pads down
(pulls off) until the host port is rebuilt, so the lines float briefly. Here we
reproduce that by clearing the pads' pull-downs through memorymap, and as a
stronger nudge, briefly pull D+ up.

Run with `exec(open('fm1_wake.py').read())`. Power-cycle the FM-1 every ~20 s;
whenever it comes back silent, the ladder below runs and reports which step
(if any) brought it back. Writes nothing to the FM-1.
"""
import time

import memorymap
import usb.core

DURATION = 600
DP, DM = 16, 17  # GPIO numbers of USB_HOST_DATA_PLUS / MINUS
PADS = 0x4001C000  # PADS_BANK0: GPIOn at 4 + 4 * n
PUE, PDE = 1 << 3, 1 << 2
FM1_VIDS = (0x4C4A, 0x1209)

gpio_in = memorymap.AddressRange(start=0xD0000004, length=4)
pads = {n: memorymap.AddressRange(start=PADS + 4 + 4 * n, length=4) for n in (DP, DM)}


def pad(n):
    return int.from_bytes(bytes(pads[n][0:4]), "little")


def set_pad(n, value):
    pads[n][0:4] = value.to_bytes(4, "little")


def lines(sec=0.3):
    """Counts of line states over sec. Pico-PIO-USB inverts the inputs: 3 = SE0."""
    seen = {}
    t = time.monotonic()
    while time.monotonic() - t < sec:
        v = (int.from_bytes(bytes(gpio_in[0:4]), "little") >> DP) & 3
        seen[v] = seen.get(v, 0) + 1
    return seen


def present():
    return any(d.idVendor in FM1_VIDS for d in usb.core.find(find_all=True))


def wait_present(sec):
    t = time.monotonic()
    while time.monotonic() - t < sec:
        if present():
            return time.monotonic() - t
        time.sleep(0.25)
    return None


def nudge(name, ms, dp_bits, dm_bits):
    """Set the pads' pull bits for ms, then restore them."""
    saved = {DP: pad(DP), DM: pad(DM)}
    set_pad(DP, (saved[DP] & ~(PUE | PDE)) | dp_bits)
    set_pad(DM, (saved[DM] & ~(PUE | PDE)) | dm_bits)
    time.sleep(ms / 1000)
    set_pad(DP, saved[DP])
    set_pad(DM, saved[DM])
    print("   nudge %-22s %4d ms" % (name, ms))


LADDER = (
    ("float both", 50, 0, 0),
    ("float both", 500, 0, 0),
    ("float both", 2000, 0, 0),
    ("pull D+ up, D- float", 100, PUE, 0),
    ("pull D+ up, D- down", 500, PUE, PDE),
)

print("wake test (%d s): pads D+ 0x%02x D- 0x%02x" % (DURATION, pad(DP) & 0xFF, pad(DM) & 0xFF))
t0 = time.monotonic()
was = present()
print("start:", "attached" if was else "not attached", lines())
while time.monotonic() - t0 < DURATION:
    now = present()
    if now != was:
        print("%6.1f s %s" % (time.monotonic() - t0, "attach" if now else "detach"))
        was = now
        if not now:
            # Give the FM-1 time to come back by itself after a power cycle.
            back = wait_present(12)
            if back is not None:
                print("%6.1f s attach after %.1f s (normal)" % (time.monotonic() - t0, back))
                was = True
                continue
            print("%6.1f s SILENT, lines %s; trying the ladder" % (time.monotonic() - t0, lines()))
            for step in LADDER:
                nudge(*step)
                back = wait_present(6)
                if back is not None:
                    print("%6.1f s WOKE after '%s %d ms' (%.1f s later)" % (
                        time.monotonic() - t0, step[0], step[1], back))
                    was = True
                    break
            else:
                print("%6.1f s still silent after the ladder, lines %s" % (time.monotonic() - t0, lines()))
    time.sleep(0.25)
print("wake test done")
