# SPDX-License-Identifier: GPL-3.0-only
"""Cycle the Feather's USB host 5 V with the FM-1 plugged in and report whether it
re-attaches and answers identity. Writes nothing to the FM-1."""
import time

import board
import digitalio
import usb.core

import fm1proto as P
import fm1update as U
import fm1usb


def present():
    return usb.core.find(idVendor=0x4C4A, idProduct=0xC755) is not None


power = digitalio.DigitalInOut(board.USB_HOST_5V_POWER)
power.switch_to_output(True)
for n in range(1, 4):
    power.value = False
    time.sleep(2)
    power.value = True
    t0 = time.monotonic()
    while not present() and time.monotonic() - t0 < 10:
        time.sleep(0.25)
    if not present():
        print("cycle", n, "no attach")
        continue
    try:
        ident = P.identity(U.Link(fm1usb.finder()()[0], U.Clock()).query(P.CMD_IDENTITY, ms=750))
    except (P.FM1Error, IndexError) as e:
        ident = repr(e)
    print("cycle", n, "attach after %.1f s" % (time.monotonic() - t0), "identity:", ident)
power.deinit()
print("vbus cycle done")
