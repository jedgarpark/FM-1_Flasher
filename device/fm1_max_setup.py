# SPDX-License-Identifier: GPL-3.0-only
"""Start USB host on the MAX3421E USB Host FeatherWing (CS D10, IRQ D9).
Needs a build with CIRCUITPY_MAX3421E = 1. Keep `host` alive while using `usb`.
Run with `exec(open('fm1_max_setup.py').read())` from the REPL."""
import board
import max3421e

host = max3421e.Max3421E(board.SPI(), chip_select=board.D10, irq=board.D9)
print("MAX3421E host started")
