# SPDX-License-Identifier: GPL-3.0-only
"""v2 spike 2 (docs/PLAN-v2.md): the FM-1 on the Metro ESP32-P4's USB-A
host port. Copy to CIRCUITPY as code.py with fm1proto, fm1update, fm1usb
and adafruit_usb_host_descriptors in lib/. Writes nothing to the FM-1.

Lists what enumerates on the port for 20 s (the FM-1 needs a 293-byte
configuration descriptor buffer; stock builds have 288), then runs the
identity and capability queries on any FM-1 it finds.
"""
import time

import board
import digitalio
import usb.core
import usb_host

import fm1proto as P
import fm1update as U
import fm1usb

power = digitalio.DigitalInOut(board.USB_HOST_POWER)
power.switch_to_output(value=True)
try:
    port = usb_host.Port(board.USB_HOST_DP, board.USB_HOST_DM)
    print("usb_host.Port started")
except (RuntimeError, ValueError) as e:
    print("usb_host.Port:", e)

devs = []
t0 = time.monotonic()
while time.monotonic() - t0 < 20 and not devs:
    devs = list(usb.core.find(find_all=True))
    time.sleep(0.2)
print("after %.1f s: %d device(s)" % (time.monotonic() - t0, len(devs)))
for d in devs:
    try:
        name = "%s / %s" % (d.manufacturer, d.product)
    except Exception as e:
        name = "? (%s)" % e
    try:
        midi = fm1usb.midi_endpoints(d)
    except Exception as e:
        midi = "error: %r" % e
    print("usb device %04x:%04x %s midi=%s" % (d.idVendor, d.idProduct, name, midi))


def log(direction, msg):
    print("  %s %d bytes %s" % (direction, len(msg), bytes(msg[:12])))


t0 = time.monotonic()
clock = U.Clock()
for t in fm1usb.finder(log)():
    link = U.Link(t, clock)
    try:
        print("identity (cmd 17):", P.identity(link.query(P.CMD_IDENTITY, ms=750)))
        try:
            print("capability (cmd 49):", P.capability(link.query(P.CMD_CAPABILITY)))
        except U.FM1Timeout:
            print("capability (cmd 49): no reply")
    except P.FM1Error as e:
        print("error:", e)
    finally:
        link.close()
print("probe done in %.2f s" % (time.monotonic() - t0))
