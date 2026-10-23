# SPDX-License-Identifier: GPL-3.0-only
"""Print USB host device changes for a while: `import fm1_watch` from the REPL."""
import time

import board
import digitalio
import usb.core
import usb_host

t0 = time.monotonic()


def say(*a):
    print("%6.1f" % (time.monotonic() - t0), *a)


say("start")
try:
    pw = digitalio.DigitalInOut(board.USB_HOST_5V_POWER)
    pw.switch_to_output(value=True)
    say("5V on")
except ValueError as e:
    say("5V pin:", e)
say("creating usb_host.Port")
port = usb_host.Port(board.USB_HOST_DATA_PLUS, board.USB_HOST_DATA_MINUS)
say("port ready", port)
last = None
while time.monotonic() - t0 < 90:
    devs = []
    for d in usb.core.find(find_all=True):
        devs.append("%04x:%04x" % (d.idVendor, d.idProduct))
    if devs != last:
        say("devices:", devs)
        last = devs
    time.sleep(0.25)
say("watch done")
