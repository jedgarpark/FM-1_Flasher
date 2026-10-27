# SPDX-License-Identifier: GPL-3.0-only
"""Replug test: report each FM-1 attach and detach, and probe identity on each attach.
Run with `exec(open('fm1_replug.py').read())` from the REPL. Writes nothing to the FM-1."""
import time

import usb.core

import fm1proto as P
import fm1update as U
import fm1usb

DURATION = 180
t0 = time.monotonic()
present = False
attaches = ok = 0
print("replug test (%d s)" % DURATION)
while time.monotonic() - t0 < DURATION:
    found = usb.core.find(idVendor=0x4C4A, idProduct=0xC755) is not None
    now = "%5.1f s" % (time.monotonic() - t0)
    if found and not present:
        attaches += 1
        try:
            ident = P.identity(U.Link(fm1usb.finder()()[0], U.Clock()).query(P.CMD_IDENTITY, ms=750))
            ok += 1
        except (P.FM1Error, IndexError) as e:
            ident = repr(e)
        print(now, "attach", attaches, "identity:", ident)
    elif present and not found:
        print(now, "detach")
    present = found
    time.sleep(0.5)
print("replug done: %d attaches, %d identities" % (attaches, ok))
