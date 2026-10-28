# SPDX-License-Identifier: GPL-3.0-only
"""The Feather's hardware for the UI: the TFT FeatherWing V2 3.5" (HX8357
display, FT5336 touch, microSD), the FM-1 on the USB host port, and running
an install with a clean heap.

An install is started by saving the firmware's slug in NVM and reloading;
code.py then runs it before building any other screen. That keeps the
heap unfragmented, which CircuitPython 11's hashlib needs (DEVNOTES §6.7).
"""
import json
import time

import board
import displayio
import fourwire
import microcontroller
import supervisor
import usb.core

import fm1usb
from fm1ui import app as A
from fm1ui import catalog as C

# fm1proto and fm1update (the installer, ~20 KB of RAM) are imported only by
# run(), which code.py calls after a reload with a fresh heap. The list
# screen's FM-1 probe below needs just the identity query.

W, H = 480, 320
# FT5336 points come in the panel's portrait frame. Measured on the TFT
# FeatherWing V2 3.5" by holding nine targets (logs/cal2.log): display
# x = 1.077 * touch y - 17.7 and y = 321.2 - 1.087 * touch x, which is within
# ~15 px everywhere; the plain swap and flip was 20-30 px off near the edges.
# (ax, bx, ay, by): x = ax * raw_y + bx, y = ay * raw_x + by
TOUCH_CAL = (1.077, -17.7, -1.087, 321.2)
NVM_TAG = b"FM1P"
ANSWER_WAIT_S = 15  # for the FM-1 to answer again after the install's reload


def display_setup():
    import adafruit_hx8357
    displayio.release_displays()
    try:  # a card mounted by the last run, before a soft reload
        import storage
        storage.umount("/sd")
    except (OSError, ValueError):
        pass
    spi = board.SPI()
    # A lock the last run left on the shared bus would stall the display's
    # init forever ("display init failed" once interrupted).
    if not spi.try_lock():
        print("SPI was left locked; unlocking")
    spi.unlock()
    bus = fourwire.FourWire(spi, command=board.D10, chip_select=board.D9, baudrate=24_000_000)
    display = adafruit_hx8357.HX8357(bus, width=W, height=H, auto_refresh=False)
    return display, spi


def mount_sd(spi):
    """Mount the wing's microSD at /sd. False if there is no card."""
    try:
        import sdcardio
        import storage
        sd = sdcardio.SDCard(spi, board.D5)
        storage.mount(storage.VfsFat(sd), "/sd")
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def firmware_root(sd):
    for root in (("/sd/firmware",) if sd else ()) + ("/firmware",):
        try:
            open(root + "/index.txt").close()
            return root
        except OSError:
            pass
    return None


class Touch:
    """FT5336 polled into taps and swipes, in display coordinates."""

    def __init__(self, cal=TOUCH_CAL, debug=False):
        import adafruit_ft5336
        self.ft = adafruit_ft5336.Adafruit_FT5336(board.I2C(), max_touches=1)
        self.cal = cal
        self.debug = debug
        self.first = None
        self.gestures = A.Gestures()

    def map(self, x, y):
        ax, bx, ay, by = self.cal
        return (min(W - 1, max(0, int(ax * y + bx))),
                min(H - 1, max(0, int(ay * x + by))))

    def raw(self):
        try:
            if self.ft.touched:
                pts = self.ft.points
                if pts:
                    return pts[0][0], pts[0][1]
        except OSError:  # an I2C hiccup reads as no touch
            pass
        return None

    def event(self):
        p = self.raw()
        if self.debug and p and self.first is None:
            self.first = p
        self.gestures.sample(self.map(*p) if p else None)
        ev = self.gestures.event()
        if self.debug and p is None and self.first is not None:
            print("touch raw", self.first, "mapped", self.map(*self.first), "->", ev)
            self.first = None
        return ev


# fm1proto.frame(CMD_IDENTITY): the identity query, which never changes
IDENTITY_QUERY = bytes.fromhex("f0003245000000407ff7")
CMD_IDENTITY = 17


def _unpack(sysex):
    """(command, data) from a valid FM-1 reply, else None: fm1proto.parse,
    kept here so probing doesn't load the installer."""
    n = len(sysex)
    if n < 10 or n > 608 or sysex[0] != 0xF0 or sysex[n - 1] != 0xF7:
        return None
    raw = bytearray()
    bits = value = 0
    for i in range(1, n - 1):
        if sysex[i] > 127:
            return None
        value |= sysex[i] << bits
        bits += 7
        if bits >= 8:
            raw.append(value & 0xFF)
            value >>= 8
            bits -= 8
    if bits >= 7 or value or len(raw) < 7 or raw[0] or raw[1] != 0x59:
        return None
    if raw[3] | (raw[4] << 8) | (raw[5] << 16) != len(raw) - 7 or sum(raw[6:]) & 0xFF != 0xFF:
        return None
    return raw[2], bytes(raw[6:-1])


def query_identity(transport, ms=750):
    """The FM-1's identity string, or None if it doesn't answer in time."""
    while transport.recv(0) is not None:
        pass
    transport.send(IDENTITY_QUERY)
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end and not transport.lost:
        msg = transport.recv(250)
        p = _unpack(msg) if msg else None
        if p and p[0] == CMD_IDENTITY:
            data = p[1]
            s = bytes(data).split(b"\0", 1)[0].decode()
            if len(data) == 27 and s and all(0x20 <= ord(c) <= 0x7E for c in s):
                return s
    return None


class Probe:
    """The attached FM-1's identity. It is asked only when the set of USB
    devices changes, or after a failed attempt, so an idle FM-1 sees no traffic.
    The transports stay open until the devices change: after a reload the
    FM-1 answers only once a transport has had a query or two (see
    wait_for_fm1)."""

    def __init__(self):
        self.key = None
        self.devices = None
        self.ident = None
        self.found = []

    def close(self):
        for t in self.found:
            t.close()
        self.found = []

    def identity(self):
        try:
            key = tuple((d.idVendor, d.idProduct) for d in usb.core.find(find_all=True))
        except (usb.core.USBError, OSError):
            return self.ident
        if key == self.key:
            return self.ident
        if key != self.devices or any(t.lost for t in self.found):
            self.close()
            self.devices = key
        self.ident = None
        self.key = key
        if not key:
            return None
        try:
            if not self.found:
                self.found = fm1usb.finder(None, 64, 0)()
            for t in self.found:
                ident = query_identity(t) or query_identity(t)  # one retry, as the installer does
                if ident:
                    self.ident = ident
        except (usb.core.USBError, OSError, ValueError):
            self.close()
        if self.ident is None:
            self.key = None  # ask again next time
        return self.ident


class DeviceState(C.State):
    """C.State that falls back to NVM when the file can't be written
    (CIRCUITPY is read-only to code while it's mounted on a computer)."""

    NVM_STATE = b"FM1S"

    def __init__(self, path):
        super().__init__(path)
        if not self.favorites and not self.installed:
            data = _nvm_read(self.NVM_STATE, 512)
            if data:
                try:
                    d = json.loads(data)
                    self.favorites = set(d.get("favorites", ()))
                    self.installed = d.get("installed")
                except ValueError:
                    pass

    def save(self):
        if super().save():
            return True
        data = json.dumps({"favorites": sorted(self.favorites), "installed": self.installed})
        return _nvm_write(self.NVM_STATE, 512, data.encode())


def _nvm_read(tag, at):
    nvm = microcontroller.nvm
    if nvm is None or bytes(nvm[at:at + 4]) != tag:
        return None
    n = nvm[at + 4] | (nvm[at + 5] << 8)
    return bytes(nvm[at + 6:at + 6 + n]).decode()


def _nvm_write(tag, at, data):
    nvm = microcontroller.nvm
    if nvm is None or at + 6 + len(data) > len(nvm):
        return False
    nvm[at:at + 6 + len(data)] = tag + bytes((len(data) & 0xFF, len(data) >> 8)) + data
    return True


def pending_install():
    """The slug of an install queued before the last reload; clears it."""
    slug = _nvm_read(NVM_TAG, 0)
    if slug:
        microcontroller.nvm[0:4] = b"\0\0\0\0"
    return slug


class Installer:
    def start(self, app, entry):
        if _nvm_write(NVM_TAG, 0, entry.slug.encode()):
            supervisor.reload()
        else:  # no NVM: install in place
            if app.probe is not None:
                app.probe.close()  # its transports would share the installer's endpoints
            run(app, entry)

    def finish(self, app):
        supervisor.reload()


def wait_for_fm1(screen, seconds=ANSWER_WAIT_S):
    """The transport of an FM-1 that answers an identity query, or None.

    After a reload the first query or two on the FM-1 get no reply, then it
    answers at once, but only on the same transport: reopening each try
    (endpoints closed and opened again) never got an answer in 15 s
    (logs/ui-install1.log). So one transport is kept for the whole wait,
    and the installer is handed that same one."""
    t0 = time.monotonic()
    waiting = False
    t = None
    tries = 0
    while time.monotonic() - t0 < seconds:
        try:
            if t is None or t.lost:
                if t is not None:
                    t.close()
                found = fm1usb.finder(None, 64, 0)()
                for other in found[1:]:
                    other.close()
                t = found[0] if found else None
            if t is not None:
                tries += 1
                ident = query_identity(t)
                if ident:
                    print("install: %s answered after %.1f s, query %d" % (ident, time.monotonic() - t0, tries))
                    if waiting:
                        screen.found()
                    return t
        except (usb.core.USBError, OSError, ValueError) as e:
            print("install: waiting:", repr(e))
            if t is not None:
                t.close()
            t = None
        if not waiting:
            screen.wait("connect", "Waiting for the FM-1 to connect...")
            waiting = True
        screen.tick(time.monotonic())
        time.sleep(0.25)
    if t is not None:
        t.close()
    print("install: no FM-1 answered in %d s (%d queries)" % (seconds, tries))
    return None


def run(app, entry):
    """Install `entry` with a progress screen. Returns True on success.
    Stages, waits and errors also go to the serial console."""
    import fm1proto as P
    import fm1update as U
    from fm1ui import screens as S

    class UIClock(U.Clock):
        """Lets the progress screen tick (elapsed time, hints) while the
        installer waits for the FM-1."""

        def __init__(self, screen):
            self.screen = screen

        def sleep_ms(self, ms):
            self.screen.tick(time.monotonic())
            super().sleep_ms(ms)

    screen = S.ProgressScreen(app, entry)
    app.push(screen)
    folder = app.root + "/" + entry.slug
    t0 = time.monotonic()
    last = [None]

    def status(name, pct):
        if name != last[0]:  # one line per stage, not per percent
            last[0] = name
            print("install: %.1f s %s" % (time.monotonic() - t0, name))
        screen.phase(name, pct)

    print("install:", entry.slug)
    try:
        status("Checking package", 0)
        with open(folder + "/meta.json") as f:
            meta = json.load(f)
        pkg_file = open(folder + "/" + meta["file"], "rb")
        pkg, meta = P.prepare(meta, pkg_file, verify=True)

        def trace(event, *values):
            if event == "wait":
                screen.wait(values[0])
            elif event == "found":
                screen.found()
            if event != "read":
                print("install: %.1f s trace" % (time.monotonic() - t0), event, *values)

        status("Connecting", 0)
        held = [wait_for_fm1(screen)]
        fresh = fm1usb.finder(None, 64, 0)

        def finder():
            # The first search gets the transport that already answered; any
            # later one (after the FM-1 restarts) finds new devices.
            t, held[0] = held[0], None
            return [t] if t is not None and not t.lost else fresh()

        up = U.Updater(finder, pkg, meta, status=status, clock=UIClock(screen))
        up.trace = trace
        print("install: connect", up.connect(force=True))
        up.install(force=True)
        up.disconnect()
        app.state.record_install(entry.slug, meta["product"])
        print("install: done in %.1f s" % (time.monotonic() - t0))
        screen.finish(True, "The FM-1 restarted with %s." % entry.name)
        return True
    except Exception as e:  # FM1Error, USBError, OSError
        print("install: failed after %.1f s:" % (time.monotonic() - t0), repr(e))
        screen.finish(False, str(e) or repr(e))
        return False
