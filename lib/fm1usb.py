# SPDX-License-Identifier: GPL-3.0-only
"""USB-MIDI host transport for fm1update on CircuitPython (usb.core).

Finds MIDI streaming interfaces (class 1, subclass 3) on the USB host port,
sends SysEx as USB-MIDI 1.0 event packets on cable 0, and reassembles
incoming SysEx. Same interface as the desktop RtMidiTransport:
send(sysex), recv(timeout_ms), lost, close().
"""

import time

import adafruit_usb_host_descriptors as D
import usb.core

# Code index numbers (USB MIDI 1.0, table 4-1)
CIN_SYSEX = 0x4  # SysEx start or continue, 3 bytes
CIN_END1 = 0x5  # SysEx ends with 1 byte (or a single-byte system common)
CIN_END2 = 0x6
CIN_END3 = 0x7


def _ticks_ms():
    return time.monotonic_ns() // 1000000


def midi_endpoints(device):
    """(interface, in_ep, out_ep, in_packet_size) of the first MIDI streaming
    interface with both bulk endpoints, or None."""
    cfg = D.get_configuration_descriptor(device, 0)
    i = 0
    midi = False
    iface = in_ep = out_ep = None
    size = 64
    while i < len(cfg):
        length, kind = cfg[i], cfg[i + 1]
        if length == 0:
            break
        if kind == D.DESC_INTERFACE:
            if midi and in_ep and out_ep:
                break
            midi = cfg[i + 5] == 1 and cfg[i + 6] == 3
            if midi:
                iface = cfg[i + 2]
                in_ep = out_ep = None
        elif kind == D.DESC_ENDPOINT and midi:
            addr = cfg[i + 2]
            if cfg[i + 3] & 3 == 2:  # bulk
                if addr & 0x80:
                    in_ep = addr
                    size = cfg[i + 4] | (cfg[i + 5] << 8)
                else:
                    out_ep = addr
        i += length
    if midi and in_ep and out_ep:
        return iface, in_ep, out_ep, size
    return None


def encode_sysex(msg):
    """USB-MIDI event packets (cable 0) for one complete F0..F7 message."""
    n = len(msg)
    out = bytearray(((n + 2) // 3) * 4)
    body = (n - 1) // 3 * 3  # bytes sent in 3-byte CIN 4 packets; the rest end the message
    o = 0
    for i in range(0, body, 3):
        out[o] = CIN_SYSEX
        out[o + 1] = msg[i]
        out[o + 2] = msg[i + 1]
        out[o + 3] = msg[i + 2]
        o += 4
    left = n - body
    out[o] = (CIN_END1, CIN_END2, CIN_END3)[left - 1]
    for k in range(left):
        out[o + 1 + k] = msg[body + k]
    return out


class USBMidiTransport:
    def __init__(self, device, endpoints, log=None):
        self.device = device
        self.iface, self.in_ep, self.out_ep, size = endpoints
        self.buf = bytearray(max(size, 4))
        self.partial = bytearray()
        self.inbox = []
        self.log = log
        self.closed = False
        self._lost = False
        # Optional pacing for slow device firmware: send in chunks of this many
        # bytes (a multiple of 4), pausing gap_ms between them. None sends at once.
        self.chunk = None
        self.gap_ms = 0
        self.read_errors = 0
        device.set_configuration()
        try:
            device.detach_kernel_driver(self.iface)
        except (usb.core.USBError, NotImplementedError):
            pass

    @property
    def lost(self):
        return self.closed or self._lost

    def slow_down(self):
        """One step gentler: 64-byte writes with a 1 ms gap, then double the gap
        up to 8 ms. Returns False once at the slowest setting."""
        if not self.chunk or self.chunk > 64:
            self.chunk, self.gap_ms = 64, max(1, self.gap_ms)
            return True
        if self.gap_ms < 8:
            self.gap_ms = max(1, self.gap_ms * 2)
            return True
        return False

    def send(self, sysex):
        if self.log:
            self.log("->", sysex)
        data = encode_sysex(sysex)
        try:
            if self.chunk:
                for i in range(0, len(data), self.chunk):
                    if i and self.gap_ms:
                        time.sleep(self.gap_ms / 1000)
                    self.device.write(self.out_ep, data[i:i + self.chunk], 1000)
            else:
                self.device.write(self.out_ep, data, 1000)
        except usb.core.USBError:
            self._lost = True
            raise

    def _decode(self, n):
        for i in range(0, n - 3, 4):
            cin = self.buf[i] & 0xF
            if cin == CIN_SYSEX:
                if self.buf[i + 1] == 0xF0:
                    if self.partial and self.log:
                        self.log("<!", self.partial)  # a message cut short
                    self.partial = bytearray()
                self.partial.extend(self.buf[i + 1:i + 4])
            elif cin in (CIN_END1, CIN_END2, CIN_END3) and self.partial:
                self.partial.extend(self.buf[i + 1:i + 1 + cin - 4])
                if self.partial[-1] == 0xF7:
                    msg = bytes(self.partial)
                    if self.log:
                        self.log("<-", msg)
                    self.inbox.append(msg)
                self.partial = bytearray()
            # Anything else (notes, clock, ...) is ignored.

    def recv(self, timeout_ms):
        if self.inbox:
            return self.inbox.pop(0)
        if self.lost:
            return None
        end = _ticks_ms() + timeout_ms
        while True:
            try:
                n = self.device.read(self.in_ep, self.buf, max(1, end - _ticks_ms()))
                self.read_errors = 0
                self._decode(n)
            except usb.core.USBTimeoutError:
                pass
            except usb.core.USBError:
                # A single read error can be transient (seen with a busy IN pipe on
                # the MAX3421E); only a run of them means the device has gone.
                self.read_errors += 1
                if self.read_errors >= 3:
                    self._lost = True
                    return None
            if self.inbox:
                return self.inbox.pop(0)
            if _ticks_ms() >= end:
                return None

    def close(self):
        self.closed = True


def finder(log=None, chunk=None, gap_ms=0):
    """A finder for fm1update.Updater: one transport per attached device with
    a MIDI streaming interface. chunk/gap_ms set the transports' send pacing."""
    def find():
        found = []
        for dev in usb.core.find(find_all=True):
            try:
                ep = midi_endpoints(dev)
                if ep:
                    t = USBMidiTransport(dev, ep, log)
                    t.chunk, t.gap_ms = chunk, gap_ms
                    found.append(t)
            except usb.core.USBError:
                pass
        return found
    return find
