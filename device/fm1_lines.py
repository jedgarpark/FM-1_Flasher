# SPDX-License-Identifier: GPL-3.0-only
"""Watch D+ (GP0) and D- (GP1) as plain inputs with pull-downs, with no USB host
running, and print every change of line state with a timestamp. Hot-plug the FM-1
while this runs to see whether and when it pulls D+ up."""
import time

import board
import digitalio

DURATION = 150
NAMES = {(0, 0): "SE0", (1, 0): "J (D+ up, full speed)", (0, 1): "K (D- up, low speed)", (1, 1): "SE1 (both high)"}

dp = digitalio.DigitalInOut(board.GP0)
dm = digitalio.DigitalInOut(board.GP1)
dp.pull = digitalio.Pull.DOWN
dm.pull = digitalio.Pull.DOWN
t0 = time.monotonic_ns()
last = None
changes = 0
print("line watch (%d s)" % DURATION)
while (time.monotonic_ns() - t0) < DURATION * 1_000_000_000:
    state = (int(dp.value), int(dm.value))
    if state != last:
        changes += 1
        if changes <= 200:
            print("%9.3f s %s" % ((time.monotonic_ns() - t0) / 1e9, NAMES[state]))
        last = state
print("line watch done, %d changes" % changes)
dp.deinit()
dm.deinit()
