# SPDX-License-Identifier: GPL-3.0-only
"""Read the FM-1 patch counters from an instrumented build (patches/*-stats.diff).
Set FM1_STATS_ADDR to the address of `fm1_stats` from `arm-none-eabi-nm firmware.elf`."""
import memorymap

NAMES = ("magic", "rx_ok", "rx_over_3us", "rx_max_us", "rx_timeout", "se0_absorbed",
         "se0_max_frames", "idle_disconnect", "enum_retry", "enum_retry_ok", "connect",
         "disconnect")


def stats(addr):
    r = memorymap.AddressRange(start=addr, length=4 * len(NAMES))
    raw = bytes(r[0:4 * len(NAMES)])
    vals = [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw), 4)]
    if vals[0] != 0x464D3153:
        raise ValueError("no fm1_stats at 0x%08x" % addr)
    return dict(zip(NAMES[1:], vals[1:]))


def show(addr, label=""):
    print("stats", label, " ".join("%s=%d" % kv for kv in sorted(stats(addr).items())))
