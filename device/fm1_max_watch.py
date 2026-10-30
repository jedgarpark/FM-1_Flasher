# SPDX-License-Identifier: GPL-3.0-only
"""Power-cycle watcher for the MAX3421E USB Host FeatherWing.

Logs every FM-1 attach and detach, and marks an FM-1 that hasn't come back
12 s after a detach as SILENT. Counts V15's update loader (4D4A:4155) too.
fm1_cycle_watch.py reads the PIO port's pins and counters, which don't exist
here. Start the host first (fm1_max_setup.py), then
`exec(open('fm1_max_watch.py').read())`. Writes nothing to the FM-1.
"""
import time

import usb.core

DURATION = globals().get("FM1_WATCH_S", 600)
FM1_VIDS = (0x4C4A, 0x1209, 0x4D4A)


def present():
    return ["%04x:%04x" % (d.idVendor, d.idProduct) for d in usb.core.find(find_all=True)
            if d.idVendor in FM1_VIDS]


t0 = time.monotonic()
was = present()
silent = False
detached_at = None
counts = {"attach": 0, "detach": 0, "silent": 0}
print("### watch start:", was or "not attached")
while time.monotonic() - t0 < DURATION:
    now = present()
    t = time.monotonic() - t0
    if bool(now) != bool(was):
        if now:
            counts["attach"] += 1
            back = "" if detached_at is None else " after %.1f s" % (t - detached_at)
            print("### %6.1f s attach %s%s%s" % (t, now, back, " (was SILENT)" if silent else ""))
            silent = False
            detached_at = None
        else:
            counts["detach"] += 1
            print("### %6.1f s detach" % t)
            detached_at = t
        was = now
    elif not now and not silent and detached_at is not None and t - detached_at > 12:
        silent = True
        counts["silent"] += 1
        print("### %6.1f s SILENT" % t)
    time.sleep(0.25)
print("### watch done", counts)
