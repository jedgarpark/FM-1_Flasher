#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run the flasher UI on the desktop with Blinka displayio.

  .venv/bin/python tools/ui_sim.py --root sd_out/full/firmware            # window; click and drag
  .venv/bin/python tools/ui_sim.py --root ... --do "shot list.png" --do "tap 60,100" --do "shot detail.png"

Needs a venv with adafruit-blinka-displayio, adafruit-circuitpython-display-text,
adafruit-circuitpython-bitmap-font, Pillow and (for the window) pygame.
The FM-1 is faked (--identity) and installs only animate the progress screen.

Script steps (--do, in order): "tap X,Y", "press X,Y" (touch down, held), "swipe DX", "shot FILE.png",
"identity ID" (or "identity none": unplugged), "connect", "phase NAME PCT", "wait", "found",
"finish ok [MSG]", "finish fail MSG".
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

import busdisplay  # noqa: E402
from displayio._area import Area  # noqa: E402
from PIL import Image  # noqa: E402

from fm1ui import app as A  # noqa: E402
from fm1ui import catalog as C  # noqa: E402
from fm1ui import screens as S  # noqa: E402
from fm1ui import ui  # noqa: E402

ui.FONT_DIR = os.path.join(ROOT, "fonts")


class SimDisplay(busdisplay.BusDisplay):
    """A displayio display that draws into a Pillow image."""

    def __init__(self, width=480, height=320):
        self.image = Image.new("RGB", (width, height))
        self.on_refresh = None
        super().__init__(None, (), width=width, height=height, auto_refresh=False)

    def _background(self):
        pass

    def _write(self, command, data):
        pass

    def _get_refresh_areas(self):
        return [self._core.area]

    def _refresh_area(self, area):
        c = Area()
        if not self._core.clip_area(area, c):
            return True
        n = c.size()
        buf = memoryview(bytearray(n * 2 + 4))
        mask = memoryview(bytearray(((n // 32) + 1) * 4)).cast("I")
        self._core.fill_area(c, mask, buf)
        raw = bytes(buf)[:n * 2]
        img = Image.frombuffer("RGB", (c.width(), c.height()), bytes(_rgb565_to_rgb(raw)), "raw", "RGB", 0, 1)
        self.image.paste(img, (c.x1, c.y1))
        return True

    def refresh(self, *args, **kwargs):
        super().refresh(*args, **kwargs)
        if self.on_refresh:
            self.on_refresh(self.image)


def _rgb565_to_rgb(raw):
    out = bytearray(len(raw) // 2 * 3)
    o = 0
    for i in range(0, len(raw), 2):
        v = (raw[i] << 8) | raw[i + 1]
        out[o] = ((v >> 11) & 31) * 255 // 31
        out[o + 1] = ((v >> 5) & 63) * 255 // 63
        out[o + 2] = (v & 31) * 255 // 31
        o += 3
    return out


class FakeProbe:
    """An FM-1 that answers as `ident` (None: nothing attached)."""

    def __init__(self, ident):
        self.ident = ident

    def connect(self):
        return self.ident

    def present(self):
        return self.ident is not None

    def close(self):
        pass


class ScriptTouch:
    def __init__(self):
        self.queue = []

    def event(self):
        return self.queue.pop(0) if self.queue else None


class FakeInstaller:
    """Shows the progress screen. In the window it animates a whole install."""

    PHASES = (("Staging loader", 4), ("Restarting", 3), ("Writing firmware", 8), ("Verifying", 1))

    def __init__(self, animate):
        self.animate = animate

    def start(self, app, entry):
        screen = S.ProgressScreen(app, entry)
        app.push(screen)
        if not self.animate:
            return
        t0 = time.monotonic()
        steps = []
        t = t0
        for name, secs in self.PHASES:
            steps.append((t, name, secs))
            t += secs
        orig_tick = screen.tick

        def tick(now):
            if screen.done is None:
                for start, name, secs in steps:
                    if start <= now < start + secs:
                        if name == "Restarting":
                            if screen.waiting_since is None:
                                screen.wait("app")
                        else:
                            screen.phase(name, min(99, int((now - start) * 100 / secs)))
                if now >= t:
                    app.state.record_install(entry.slug, entry.product)
                    app.identity = entry.product
                    screen.finish(True, "The FM-1 restarted with %s." % entry.name)
            orig_tick(now)
        screen.tick = tick


def run_script(app, touch, steps):
    app.push(S.ListScreen(app))
    for step in steps:
        cmd, _, arg = step.partition(" ")
        screen = app.stack[-1]
        if cmd == "tap":
            x, y = (int(v) for v in arg.split(","))
            touch.queue.append(("tap", x, y))
            app.step()
        elif cmd == "press":
            x, y = (int(v) for v in arg.split(","))
            touch.queue.append(("down", x, y))
            app.step()
        elif cmd == "swipe":
            touch.queue.append(("swipe", int(arg)))
            app.step()
        elif cmd == "shot":
            app.display.image.save(arg)
            print("wrote", arg)
        elif cmd == "identity":
            app.probe.ident = None if arg == "none" else arg
            app.next_probe = 0
            app.step()
        elif cmd == "connect":
            app.connect()
        elif cmd == "phase":
            name, _, pct = arg.rpartition(" ")
            screen.phase(name, int(pct))
        elif cmd == "wait":
            screen.wait("app")
        elif cmd == "found":
            screen.found()
        elif cmd == "finish":
            ok, _, msg = arg.partition(" ")
            screen.finish(ok == "ok", msg)
        else:
            sys.exit("unknown step: " + step)


def run_window(app, scale):
    import pygame
    pygame.init()
    win = pygame.display.set_mode((480 * scale, 320 * scale))
    pygame.display.set_caption("FM-1 Flasher (simulator)")
    gestures = A.Gestures()
    app.touch = gestures

    def blit(image):
        surf = pygame.image.frombuffer(image.tobytes(), image.size, "RGB")
        if scale != 1:
            surf = pygame.transform.scale(surf, (480 * scale, 320 * scale))
        win.blit(surf, (0, 0))
        pygame.display.flip()

    app.display.on_refresh = blit
    app.push(S.ListScreen(app))
    down = False
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.MOUSEBUTTONDOWN:
                down = True
            elif ev.type == pygame.MOUSEBUTTONUP:
                down = False
                gestures.sample(None)
            elif ev.type == pygame.KEYDOWN and ev.unicode == "f":
                # plug or unplug an FM-1 running stock V15 (then Connect FM-1)
                app.probe.ident = None if app.probe.ident else "FM-1_015"
        if down:
            mx, my = pygame.mouse.get_pos()
            gestures.sample((mx // scale, my // scale))
        app.step()
        time.sleep(0.01)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.join(ROOT, "sd_out", "full", "firmware"))
    ap.add_argument("--state", help="state JSON (default: flasher-sim.json next to --root)")
    ap.add_argument("--identity", default="FM-1_015", help="what the fake FM-1 answers to Connect, or 'none'")
    ap.add_argument("--do", action="append", default=[], help="script step (headless)")
    ap.add_argument("--scale", type=int, default=2, help="window zoom")
    args = ap.parse_args()

    state = C.State(args.state or os.path.join(os.path.dirname(args.root.rstrip("/")), "flasher-sim.json"))
    touch = ScriptTouch()
    probe = FakeProbe(None if args.identity == "none" else args.identity)
    app = A.App(SimDisplay(), touch, args.root, state, probe, FakeInstaller(animate=not args.do))
    if args.do:
        run_script(app, touch, args.do)
    else:
        run_window(app, args.scale)


if __name__ == "__main__":
    main()
