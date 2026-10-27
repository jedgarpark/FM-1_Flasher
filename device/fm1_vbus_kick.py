# SPDX-License-Identifier: GPL-3.0-only
"""Hot-plug workaround test: whenever no FM-1 has shown up for KICK_AFTER seconds,
cycle the host port's 5 V so the FM-1 redoes its port detection. Reports each
attach with an identity probe. Writes nothing to the FM-1."""
import time

import board
import digitalio
import usb.core

import fm1proto as P
import fm1update as U
import fm1usb

DURATION = 180
KICK_AFTER = 4
OFF_TIME = 1.0


def present():
    return usb.core.find(idVendor=0x4C4A, idProduct=0xC755) is not None


power = digitalio.DigitalInOut(board.USB_HOST_5V_POWER)
power.switch_to_output(True)
t0 = time.monotonic()
missing_since = None
was = False
kicks = 0
print("vbus kick test (%d s)" % DURATION)
while time.monotonic() - t0 < DURATION:
    now = time.monotonic()
    stamp = "%5.1f s" % (now - t0)
    if present():
        if not was:
            try:
                ident = P.identity(U.Link(fm1usb.finder()()[0], U.Clock()).query(P.CMD_IDENTITY, ms=750))
            except (P.FM1Error, IndexError) as e:
                ident = repr(e)
            print(stamp, "attach after", kicks, "kicks, identity:", ident)
            kicks = 0
        was = True
        missing_since = None
    else:
        if was:
            print(stamp, "detach")
        was = False
        if missing_since is None:
            missing_since = now
        elif now - missing_since > KICK_AFTER:
            kicks += 1
            print(stamp, "kick", kicks)
            power.value = False
            time.sleep(OFF_TIME)
            power.value = True
            missing_since = time.monotonic()
    time.sleep(0.25)
power.value = True
power.deinit()
print("vbus kick done")
