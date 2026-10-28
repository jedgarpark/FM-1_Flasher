# SPDX-License-Identifier: GPL-3.0-only
"""Power-cycle watcher for the silent-FM-1 investigation on the PIO host port.

Logs every attach/detach with the instrumented build's counters (set
FM1_STATS_ADDR to the address of `fm1_stats` from arm-none-eabi-nm), and marks
an FM-1 that hasn't come back 12 s after a detach as SILENT, with the line
state. Set FM1_DP if the host port isn't on GPIO16/17. On a debug build this output also lands in the TinyUSB UART log.
Run with `exec(open('fm1_cycle_watch.py').read())`. Writes nothing to the FM-1.
"""
import time

import memorymap
import usb.core

DURATION = 600
FM1_VIDS = (0x4C4A, 0x1209)
gpio_in = memorymap.AddressRange(start=0xD0000004, length=4)
DP = globals().get("FM1_DP", 16)  # GPIO number of D+; D- is DP + 1


def word(addr):
    return int.from_bytes(bytes(memorymap.AddressRange(start=addr, length=4)[0:4]), "little")


def stats():
    a = FM1_STATS_ADDR  # noqa: F821 (set by the caller)
    if word(a) != 0x464D3153:
        return "no stats"
    return "connect=%d ls_connect=%d disconnect=%d idle_disconnect=%d" % (
        word(a + 40), word(a + 4), word(a + 44), word(a + 28))


def lines(sec=0.5):
    seen = {}
    t = time.monotonic()
    while time.monotonic() - t < sec:
        v = (int.from_bytes(bytes(gpio_in[0:4]), "little") >> DP) & 3
        seen[v] = seen.get(v, 0) + 1
    return seen  # Pico-PIO-USB inverts inputs: 3 = SE0, 2 = J, 1 = K


def present():
    return any(d.idVendor in FM1_VIDS for d in usb.core.find(find_all=True))


t0 = time.monotonic()
was = present()
silent = False
detached_at = None
counts = {"attach": 0, "silent": 0}
print("### watch start:", "attached" if was else "not attached", stats())
while time.monotonic() - t0 < DURATION:
    now = present()
    t = time.monotonic() - t0
    if now != was:
        if now:
            counts["attach"] += 1
            print("### %6.1f s attach%s | %s" % (t, " (was SILENT)" if silent else "", stats()))
            silent = False
        else:
            print("### %6.1f s detach | %s" % (t, stats()))
            detached_at = t
        was = now
    elif not now and not silent and detached_at is not None and t - detached_at > 12:
        silent = True
        counts["silent"] += 1
        print("### %6.1f s SILENT lines %s | %s" % (t, lines(), stats()))
    time.sleep(0.25)
print("### watch done", counts, stats())
