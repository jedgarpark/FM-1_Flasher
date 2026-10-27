# SPDX-License-Identifier: GPL-3.0-only
"""Pico replug test with the TinyUSB debug log: a debug build sends the log out
UART0 TX on GP12, jumpered to UART1 RX on GP5, and this copies it to the usb_cdc data port (printing it would
loop back through the console UART) while probing each FM-1 attach. Needs
usb_cdc.enable(console=True, data=True) in boot.py. Run after creating usb_host.Port(board.GP0, board.GP1)."""
import time

import board
import busio
import memorymap
import usb.core
import usb_cdc

import fm1proto as P
import fm1update as U
import fm1usb

DURATION = 300
# Raw GPIO input register (SIO GPIO_IN); GP0/GP1 are D+/D-. Pico-PIO-USB inverts
# the pad inputs, so 1 here means the line is low.
gpio_in = memorymap.AddressRange(start=0xD0000004, length=4)
LINES = {0: "SE1?", 1: "K", 2: "J", 3: "SE0"}
last_lines = None
uart = busio.UART(None, board.GP5, baudrate=115200, receiver_buffer_size=16384)
t0 = time.monotonic()
present = False
print("replug log test (%d s)" % DURATION)
while time.monotonic() - t0 < DURATION:
    data = uart.read(uart.in_waiting or 1) if uart.in_waiting else None
    if data:
        usb_cdc.data.write(data)
    lines = bytes(gpio_in[0:4])[0] & 3
    if lines != last_lines:
        usb_cdc.data.write(b"\n@@ %.3f s lines %s\n" % (time.monotonic() - t0, LINES[lines]))
        last_lines = lines
    found = usb.core.find(idVendor=0x4C4A, idProduct=0xC755) is not None
    if found and not present:
        try:
            ident = P.identity(U.Link(fm1usb.finder()()[0], U.Clock()).query(P.CMD_IDENTITY, ms=750))
        except (P.FM1Error, IndexError) as e:
            ident = repr(e)
        event = "### %.1f s FM-1 mounted, identity: %s" % (time.monotonic() - t0, ident)
        print(event)
        usb_cdc.data.write(b"\n" + event.encode() + b"\n")
    elif present and not found:
        event = "### %.1f s FM-1 gone" % (time.monotonic() - t0)
        print(event)
        usb_cdc.data.write(b"\n" + event.encode() + b"\n")
    present = found
    time.sleep(0.01)
uart.deinit()
print("replug log done")
