# SPDX-License-Identifier: GPL-3.0-only
"""The flasher UI's main loop: a stack of screens over a display, touch input
and an FM-1 probe. The hardware is passed in, so the same code runs on the
Feather (fm1ui.device) and in the desktop simulator (tools/ui_sim.py).

display   a displayio display with auto_refresh off
touch     .event() -> ("down", x, y) when a touch starts, then ("tap", x, y),
          ("swipe", dx) or ("up",) when it ends; or None
probe     .connect() -> the FM-1's identity, or None if none answered
          (Connect FM-1: nothing is sent to the FM-1 before it);
          .present() -> is the connected FM-1 still attached
installer .start(app, entry): run, or arrange to run, the install;
          optional .finish(app) after the user dismisses the result
"""
import gc
import time

import displayio

from fm1ui import catalog as C
from fm1ui import screens as S
from fm1ui import ui


class App:
    PROBE_EVERY_S = 2

    def __init__(self, display, touch, root, state, probe=None, installer=None, pictures=True):
        # The picture pool and the fonts are made first and kept, while the heap
        # is still in one piece: made and freed per screen, their 3-8 KB blocks
        # soon no longer fit between the small objects screens leave behind.
        if pictures:  # not while installing: the installer wants the RAM
            ui.slots()
        for name in (ui.TITLE, ui.NAME, ui.BODY, ui.SMALL):
            ui.font(name)
        self.display = display
        self.touch = touch
        self.root = root  # folder holding index.txt and one folder per firmware
        self.state = state
        self.probe = probe
        self.installer = installer
        self.index = C.Index(root + "/index.txt")
        self.updated = self.index.updated
        self.tags = self.index.tags()  # for the list's tag filter, most used first
        self.identity = None  # set by connect()
        self.connecting = False
        self.connect_failed = False
        self.next_probe = 0
        self.stack = []
        self.blank = displayio.Group()
        self.pressed = None  # (screen, its group, pressed group, release token)

    # -- data -----------------------------------------------------------------

    def path(self, slug, name):
        return "%s/%s/%s" % (self.root, slug, name)

    def entry(self, slug):
        return self.index.find(slug) if slug else None

    def installed_slug(self):
        return self.state.installed_slug(self.identity, self.index)

    # -- screens --------------------------------------------------------------

    def show(self):
        """Rebuild the top screen. The old group goes first so its RAM is free."""
        # A pressed element's tuple holds its screen's whole group (~25 KB
        # for the list), which would stay alive under the new screen: opening
        # a card ran out of memory that way. The group is going anyway.
        self.pressed = None
        for s in self.stack:
            s.release()
        self.display.root_group = self.blank
        gc.collect()
        self.display.root_group = self.stack[-1].build()
        self.refresh()

    def push(self, screen):
        self.stack.append(screen)
        self.show()

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()
        self.show()

    def home(self):
        del self.stack[1:]
        self.show()

    def refresh(self):
        self.display.refresh()

    # -- installs -------------------------------------------------------------

    def start_install(self, entry):
        self.installer.start(self, entry)

    def finish_install(self):
        if hasattr(self.installer, "finish"):
            self.installer.finish(self)
        else:
            self.home()

    # -- loop -----------------------------------------------------------------

    def connect(self):
        """Connect FM-1: ask the attached FM-1 who it is. Blocks for up to
        a few seconds, with the screens showing "Connecting"."""
        if self.probe is None or self.connecting:
            return
        self.connecting = True
        self.connect_failed = False
        self.stack[-1].fm1_changed()
        self.identity = self.probe.connect()
        self.connecting = False
        self.connect_failed = self.identity is None
        self.next_probe = time.monotonic() + self.PROBE_EVERY_S
        self.stack[-1].fm1_changed()

    def poll_fm1(self, now):
        """Notice the connected FM-1 going away. Sends nothing to it."""
        if self.probe is None or self.identity is None or now < self.next_probe:
            return
        self.next_probe = now + self.PROBE_EVERY_S
        if not self.probe.present():
            self.identity = None
            self.stack[-1].fm1_changed()

    def press(self, screen, x, y):
        """Light up what's under a touch as it lands, so a tap shows at once
        even when its action takes a moment."""
        target = screen.target(x, y)
        if target is not None:
            self.pressed = (screen, screen.group, target, ui.press(target))
            self.refresh()

    def unpress(self):
        """Put the pressed element back, unless its screen was rebuilt or
        replaced meanwhile (then it's gone already)."""
        if self.pressed is None:
            return
        screen, group, target, old = self.pressed
        self.pressed = None
        if self.stack[-1] is screen and screen.group is group:
            ui.release(target, old)
            self.refresh()

    def step(self):
        screen = self.stack[-1]
        ev = self.touch.event()
        if ev:
            if ev[0] == "down":
                self.press(screen, ev[1], ev[2])
            else:  # the touch ended: act with the element still lit, then let go
                if ev[0] == "tap":
                    screen.tap(ev[1], ev[2])
                elif ev[0] == "swipe":
                    screen.swipe(ev[1])
                self.unpress()
        now = time.monotonic()
        if not isinstance(self.stack[-1], S.ProgressScreen):
            self.poll_fm1(now)
        self.stack[-1].tick(now)

    def run(self, home=None):
        self.push(home or S.ListScreen(self))
        while True:
            try:
                self.step()
            except MemoryError as e:  # back to the list rather than stop
                print("MemoryError:", e, "on", type(self.stack[-1]).__name__)
                try:
                    import traceback
                    traceback.print_exception(e)
                except (ImportError, MemoryError):
                    pass
                e = None  # its traceback holds the failed screen's objects
                self.pressed = None
                del self.stack[1:]
                self.display.root_group = self.blank
                gc.collect()
                print("free RAM:", gc.mem_free())
                self.show()
            time.sleep(0.01)


class Gestures:
    """Turns touch samples into taps and horizontal swipes. Feed it
    sample(point or None) each poll; event() returns what finished."""

    SWIPE_PX = 60
    TAP_PX = 30  # a fingertip rolls 20-30 px on a firm tap

    def __init__(self):
        self.start = None
        self.last = None
        self.events = []

    def sample(self, point):
        if point is not None:
            if self.start is None:
                self.start = point
                self.events.append(("down", point[0], point[1]))
            self.last = point
            return
        if self.start is None:
            return
        (x0, y0), (x1, y1) = self.start, self.last
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) >= self.SWIPE_PX and abs(dx) > 2 * abs(dy):
            self.events.append(("swipe", dx))
        elif abs(dx) <= self.TAP_PX and abs(dy) <= self.TAP_PX:
            self.events.append(("tap", x0, y0))
        else:
            self.events.append(("up",))
        self.start = self.last = None

    def event(self):
        return self.events.pop(0) if self.events else None
