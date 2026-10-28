# SPDX-License-Identifier: GPL-3.0-only
"""The flasher UI's main loop: a stack of screens over a display, touch input
and an FM-1 probe. The hardware is passed in, so the same code runs on the
Feather (fm1ui.device) and in the desktop simulator (tools/ui_sim.py).

display   a displayio display with auto_refresh off
touch     .event() -> ("tap", x, y), ("swipe", dx), or None
probe     .identity(force=False) -> the attached FM-1's identity or None
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
        self.identity = probe.identity() if probe else None
        self.next_probe = time.monotonic() + self.PROBE_EVERY_S
        self.stack = []
        self.blank = displayio.Group()

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

    def poll_fm1(self, now):
        if self.probe is None or now < self.next_probe:
            return
        self.next_probe = now + self.PROBE_EVERY_S
        ident = self.probe.identity()
        if ident != self.identity:
            self.identity = ident
            self.stack[-1].fm1_changed()

    def step(self):
        screen = self.stack[-1]
        ev = self.touch.event()
        if ev:
            if ev[0] == "tap":
                screen.tap(ev[1], ev[2])
            elif ev[0] == "swipe":
                screen.swipe(ev[1])
        now = time.monotonic()
        if not isinstance(self.stack[-1], S.ProgressScreen):
            self.poll_fm1(now)
        self.stack[-1].tick(now)

    def run(self, home=None):
        self.push(home or S.ListScreen(self))
        while True:
            self.step()
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
        self.start = self.last = None

    def event(self):
        return self.events.pop(0) if self.events else None
