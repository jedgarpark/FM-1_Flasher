# SPDX-License-Identifier: GPL-3.0-only
"""Phase 2 probe for the Feather RP2040 USB Host: run with `import fm1_probe`
from the REPL. Writes nothing to the FM-1."""

import time

import board
import digitalio
import usb.core

try:
    import usb_host
except ImportError:
    usb_host = None

import fm1proto as P
import fm1update as U
import fm1usb

print("hashlib:", P.hashlib.__name__ if P.hashlib else None,
      "sha256 ok" if P.sha256() is not None else "no sha256")
print("binascii.crc_hqx:", P._crc_hqx is not None)

# 5 V to the USB-A jack, then the PIO host port (as in the USB Host examples).
power = digitalio.DigitalInOut(board.USB_HOST_5V_POWER)
power.switch_to_output(value=True)
if usb_host is not None:
    try:
        port = usb_host.Port(board.USB_HOST_DATA_PLUS, board.USB_HOST_DATA_MINUS)
    except (RuntimeError, ValueError) as e:
        print("usb_host.Port:", e)

for _ in range(30):
    devs = list(usb.core.find(find_all=True))
    if devs:
        break
    time.sleep(0.1)
for d in devs:
    try:
        name = "%s / %s" % (d.manufacturer, d.product)
    except Exception:
        name = "?"
    print("usb device %04x:%04x %s midi=%s" % (d.idVendor, d.idProduct, name, fm1usb.midi_endpoints(d)))


def log(direction, msg):
    print("  %s %d bytes %s" % (direction, len(msg), bytes(msg[:12])))


t0 = time.monotonic()
clock = U.Clock()
for t in fm1usb.finder(log)():
    link = U.Link(t, clock)
    try:
        reply = link.query(P.CMD_IDENTITY, ms=750)
        print("identity (cmd 17):", P.identity(reply))
        try:
            cap = P.capability(link.query(P.CMD_CAPABILITY))
            print("capability (cmd 49):", cap)
        except U.FM1Timeout:
            print("capability (cmd 49): no reply")
    except P.FM1Error as e:
        print("error:", e)
    finally:
        link.close()
print("probe done in %.2f s" % (time.monotonic() - t0))
