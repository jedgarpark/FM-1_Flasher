# SPDX-License-Identifier: GPL-3.0-only
"""Read the MAX3421E debug counters from a build with the stats patch
(patches/cp11-feather-rp2350-max3421e-stats.diff). Set FM1_STATS_ADDR to the
address of `fm1_stats` from `arm-none-eabi-nm firmware.elf`, then
`exec(open('fm1_max_stats.py').read())` and call show() or rates()."""
import time

import memorymap

NAMES = ("magic", "int_handler", "frame", "condet", "rcvdav", "hxfrdn", "nak",
         "last_nak", "nak_ep0", "pin_irq", "cb_deferred", "task_runs",
         "task_deferred", "task_max_us", "task_total_us", "cs_lock_fail",
         "delay_calls", "delay_ms", "lock_holder", "lock_ms", "lock_timeouts",
         "timeout_holder", "timeout_held_ms")


def stats(addr=None):
    addr = addr or FM1_STATS_ADDR  # noqa: F821 (set by the caller)
    r = memorymap.AddressRange(start=addr, length=4 * len(NAMES))
    raw = bytes(r[0:4 * len(NAMES)])
    vals = [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw), 4)]
    if vals[0] != 0x464D3153:
        raise ValueError("no fm1_stats at 0x%08x" % addr)
    return dict(zip(NAMES[1:], vals[1:]))


def last_nak(v):
    return "addr %d ep %d %s" % (v >> 8, v & 0x0F, "IN" if v & 0x80 else "OUT")


def show(label=""):
    s = stats()
    s["last_nak"] = last_nak(s["last_nak"])
    for k in ("lock_holder", "timeout_holder"):
        s[k] = "0x%08x" % s[k]
    print("stats", label, " ".join("%s=%s" % kv for kv in sorted(s.items())))


def rates(seconds=1.0, label=""):
    """Counts per second over `seconds`, for the counters that grew."""
    a = stats()
    t = time.monotonic()
    time.sleep(seconds)
    b = stats()
    dt = time.monotonic() - t
    grew = {k: int((b[k] - a[k]) / dt) for k in b
            if k not in ("last_nak", "task_max_us", "lock_holder", "lock_ms", "timeout_holder",
                         "timeout_held_ms") and b[k] != a[k]}
    print("per s", label, " ".join("%s=%d" % kv for kv in sorted(grew.items())),
          "| last_nak", last_nak(b["last_nak"]), "task_max_us", b["task_max_us"])
