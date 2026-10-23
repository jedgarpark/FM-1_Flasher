#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Desktop FM-1 flasher over USB-MIDI (python-rtmidi): the reference for the
CircuitPython device, run from a computer where problems are easy to see.

  flash_cli.py ports                list MIDI ports and which ones would be probed
  flash_cli.py probe                identity (cmd 17) and capability (cmd 49); writes nothing
"""

import argparse
import os
import queue
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import fm1proto as P  # noqa: E402
import fm1update as U  # noqa: E402

try:
    import rtmidi
except ImportError:
    sys.exit("needs python-rtmidi: .venv/bin/pip install python-rtmidi")

# The Firmware Hub's list of names the FM-1 shows up under, in app and loader
# mode, on macOS, Windows, and Linux ("USB Composite Device" for stock V15).
FM1_PORT = re.compile(r"fm-1|felucca|sloop|clipper|etch|jiant|ota|update|composite|sinco|usb-midi", re.I)


def candidate_pairs(pattern=FM1_PORT):
    """(name, in_index, out_index) for each FM-1-looking port with a same-named output."""
    ins = rtmidi.MidiIn().get_ports()
    outs = rtmidi.MidiOut().get_ports()
    pairs = []
    for i, name in enumerate(ins):
        if not pattern.search(name):
            continue
        same = [j for j, o in enumerate(outs) if o == name]
        if len(same) == 1:
            pairs.append((name, i, same[0]))
    return pairs


class RtMidiTransport:
    """fm1update transport over a python-rtmidi input/output pair."""

    def __init__(self, name, in_index, out_index, log=None):
        self.name = name
        self.q = queue.Queue()
        self.log = log
        self.closed = False
        self._checked = 0
        self._lost = False
        self.mi = rtmidi.MidiIn()
        self.mi.ignore_types(sysex=False, timing=True, active_sense=True)
        self.mi.set_callback(self._on_message)
        self.mi.open_port(in_index)
        self.mo = rtmidi.MidiOut()
        self.mo.open_port(out_index)

    def _on_message(self, event, data=None):
        msg, _ = event
        if msg and msg[0] == 0xF0:
            if self.log:
                self.log("<-", msg)
            self.q.put(bytes(msg))

    @property
    def lost(self):
        if self.closed or self._lost:
            return True
        now = time.monotonic()
        if now - self._checked > 0.25:
            self._checked = now
            self._lost = self.name not in rtmidi.MidiIn().get_ports()
        return self._lost

    def send(self, sysex):
        if self.log:
            self.log("->", sysex)
        self.mo.send_message(list(sysex))

    def recv(self, timeout_ms):
        try:
            if timeout_ms <= 0:
                return self.q.get_nowait()
            return self.q.get(timeout=timeout_ms / 1000)
        except queue.Empty:
            return None

    def close(self):
        if not self.closed:
            self.closed = True
            self.mi.cancel_callback()
            self.mi.close_port()
            self.mo.close_port()


def make_log(verbose):
    if not verbose:
        return None

    def log(direction, msg):
        b = bytes(msg)
        text = b.hex(" ") if len(b) <= 24 else b[:16].hex(" ") + " … (%d bytes)" % len(b)
        p = P.parse(b)
        extra = "  cmd %d, %d data bytes" % (p[0], len(p[1])) if p else ""
        print("  %s %s%s" % (direction, text, extra))
    return log


def cmd_ports(args):
    ins = rtmidi.MidiIn().get_ports()
    outs = rtmidi.MidiOut().get_ports()
    print("inputs: ", ins)
    print("outputs:", outs)
    print("would probe:", [p[0] for p in candidate_pairs()] or "none")


def cmd_probe(args):
    pairs = candidate_pairs()
    if not pairs:
        sys.exit("no FM-1-looking MIDI port; is it on and plugged in? (try: flash_cli.py ports)")
    clock = U.Clock()
    for name, i, o in pairs:
        print("port:", name)
        t = RtMidiTransport(name, i, o, make_log(args.verbose))
        link = U.Link(t, clock)
        try:
            reply = None
            for attempt in range(2):
                try:
                    reply = link.query(P.CMD_IDENTITY, ms=750)
                    break
                except U.FM1Timeout:
                    if attempt:
                        raise
            ident = P.identity(reply)
            print("  identity (cmd 17):   %s" % ident)
            kind = ("loader" if P.is_loader(ident) else "stock V15" if ident == P.STOCK_PRODUCT
                    else "FM1 Open" if P.open_identity(ident)
                    else "community" if P.community_identity(ident) else "unknown")
            print("  identity kind:       %s" % kind)
            try:
                started = time.monotonic()
                cap = P.capability(link.query(P.CMD_CAPABILITY))
                print("  capability (cmd 49): family %d, state %d, build %s (%.0f ms)" % (
                    cap["family"], cap["state"], cap["build"], (time.monotonic() - started) * 1000))
            except U.FM1Timeout:
                print("  capability (cmd 49): no reply (expected for stock and community firmwares)")
        except U.FM1Timeout:
            print("  no reply to cmd 17")
        except P.FM1Error as e:
            print("  error:", e)
        finally:
            link.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="print every SysEx message")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports").set_defaults(fn=cmd_ports)
    sub.add_parser("probe").set_defaults(fn=cmd_probe)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
