# SPDX-License-Identifier: GPL-3.0-only
"""TFT FeatherWing V2 3.5" (HX8357, FT5336 touch) check next to the USB host.

Draws colour bars, then mirrors the console on the screen, reports touches
for TOUCH_SECONDS and the FM-1 if one is attached, and prints free RAM at
each step. Run with `exec(open('tft_check.py').read())`. Needs
adafruit_hx8357, adafruit_ft5336 and adafruit_register in lib/.
"""
import gc
import time

import adafruit_ft5336
import adafruit_hx8357
import board
import displayio
import fourwire
import usb.core
import vectorio

TOUCH_SECONDS = 15
FM1_VIDS = (0x4C4A, 0x1209)

gc.collect()
print("free RAM before display: %d" % gc.mem_free())
displayio.release_displays()
bus = fourwire.FourWire(board.SPI(), command=board.D10, chip_select=board.D9, baudrate=24_000_000)
display = adafruit_hx8357.HX8357(bus, width=480, height=320)

bars = displayio.Group()
colours = (0xFF0000, 0x00FF00, 0x0000FF, 0xFFFFFF)
for i, c in enumerate(colours):
    p = displayio.Palette(1)
    p[0] = c
    bars.append(vectorio.Rectangle(pixel_shader=p, width=120, height=320, x=i * 120, y=0))
display.root_group = bars
gc.collect()
print("free RAM with colour bars: %d" % gc.mem_free())
time.sleep(2)

display.root_group = displayio.CIRCUITPYTHON_TERMINAL
fm1 = ["%04x:%04x" % (d.idVendor, d.idProduct) for d in usb.core.find(find_all=True)
       if d.idVendor in FM1_VIDS]
print("FM-1 on the USB host:", fm1 or "none")

touch = adafruit_ft5336.Adafruit_FT5336(board.I2C())
print("touch the screen for %d s" % TOUCH_SECONDS)
end = time.monotonic() + TOUCH_SECONDS
seen = 0
while time.monotonic() < end:
    if touch.touched:
        seen += 1
        print("touch", touch.points)
        time.sleep(0.2)
    time.sleep(0.02)
gc.collect()
print("touch reports: %d, free RAM: %d" % (seen, gc.mem_free()))
