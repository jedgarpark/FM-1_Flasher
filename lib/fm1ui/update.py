# SPDX-License-Identifier: GPL-3.0-only
"""Update firmwares: bring the card up to date with the FM-1 Firmware Hub over
WiFi (docs/PLAN-v2.md, Phase 2). Only on boards with a network (the Metro
ESP32-P4); v1 never imports this.

The work is a generator (job()) that the screen advances a step at a time
from tick(), so the screen keeps drawing and Stop works between steps: one
download chunk, a few rows of a picture, one removal.

net is passed in: .connect() -> None or an error message; .get_json(url);
.get(url) -> bytes; .stream(url) -> a generator of byte chunks. Errors are
OSError (network) or ValueError.
"""
import os
import time

import displayio

import fm1catalog as K
from fm1ui import catalog as C
from fm1ui import ui
from fm1ui.layout import L

PIC = "thumb.bmp"
NO_PIC = "thumb.none"  # the hub has no picture for this one: don't ask again
BYTES_PER_S = 200_000  # measured: 0.21 MB/s to the card (docs/PLAN-v2.md)
CHECK_S = 3  # the full package checks, per firmware


def needs_picture(root, slug):
    d = root + "/" + slug
    return not (K.exists(d + "/" + PIC) or K.exists(d + "/" + NO_PIC))


def picture_list(root, plan):
    """Catalogue ids on the card (after the plan runs) without a picture yet."""
    fresh = set(e["id"] for e in plan.downloads)
    out = []
    for e in plan.same + plan.downloads:
        if e["id"] == K.STOCK_ID:
            continue
        if e["id"] in fresh or needs_picture(root, e["id"]):
            out.append(e)
    return out


def estimate_s(plan, pictures):
    return plan.bytes // BYTES_PER_S + CHECK_S * len(plan.downloads) + 3 * len(pictures)


def job(root, plan, net, stats):
    """A generator: download, then fetch pictures, yielding (phase, done,
    total, name) as it goes. Counts land in `stats`. Nothing is removed."""
    K.clean_parts(root)

    total = plan.bytes
    base = 0
    since_index = 0
    for e in plan.downloads:
        name = e.get("name") or e["id"]
        yield ("Downloading", base, total, name)
        dl = K.download(root, e, net.stream)
        try:
            for n in dl:
                yield ("Downloading", base + n, total, name)
            for old in (PIC, NO_PIC, "large.bmp"):  # a new version may have a new picture
                try:
                    os.remove(root + "/" + e["id"] + "/" + old)
                except OSError:
                    pass
            stats["new" if e in plan.new else "updated"] += 1
            since_index += 1
            if since_index >= 10:  # so a power cut loses little of the list
                K.write_index(root)
                since_index = 0
        except Exception as ex:  # a bad download or package: skip it, go on
            print("update: %s failed: %r" % (e["id"], ex))
            stats["failed"].append(e["id"])
            if isinstance(ex, OSError) and len(stats["failed"]) >= 3 and stats["new"] + stats["updated"] == 0:
                raise  # the network is down, not one package
        finally:
            dl.close()  # on Stop: closes its file and download (MicroPython
            # doesn't close a dropped generator for us)
        base += e.get("size", 0)
    K.write_index(root, plan.updated_at)
    stats["index"] = True

    import fm1pic
    pics = [e for e in picture_list(root, plan) if K.exists(root + "/" + e["id"] + "/meta.json")]
    for i, e in enumerate(pics):
        name = e.get("name") or e["id"]
        yield ("Pictures", i, len(pics), name)
        d = root + "/" + e["id"]
        try:
            data = net.get(K.HUB + "img/%s.png" % e["id"])
        except OSError as ex:
            if "404" in str(ex):
                with open(d + "/" + NO_PIC, "w") as f:
                    f.write("404\n")
            else:
                print("update: picture %s: %r" % (e["id"], ex))
            continue
        try:
            for _ in fm1pic.convert(data, d + "/" + PIC):
                yield ("Pictures", i, len(pics), name)
            stats["pictures"] += 1
        except (ValueError, MemoryError, OSError) as ex:
            print("update: picture %s: %r" % (e["id"], ex))
        data = None


class UpdateScreen:
    """Connect to WiFi, read the hub's catalogue, show what would change,
    then run the update with a progress bar and a Stop button."""

    STEP_S = 0.05  # work per tick before the screen gets a look in

    def __init__(self, app):
        self.app = app
        self.group = None
        self.mode = "start"  # start, plan, run, done, error
        self.plan = None
        self.pics = []
        self.message = ""
        self.work = None
        self.stats = None
        self.t0 = 0
        self.last_draw = 0
        self.stopping = False

    # -- the Screen protocol (fm1ui.screens.Screen) ------------------------------

    def release(self):
        self.group = None

    def build(self):
        W, H = L.W, L.H
        g = displayio.Group()
        g.append(ui.rect(0, 0, W, H, ui.BG))
        g.append(ui.rect(0, 0, W, 3, ui.CYAN))
        self.title = ui.text(ui.TITLE, "Update firmwares", ui.FG, W // 2, L.PROGRESS_TITLE_Y, (0.5, 0))
        g.append(self.title)
        self.sub = ui.text(ui.BODY, " ", ui.DIM, W // 2, L.PROGRESS_SUB_Y, (0.5, 0))
        g.append(self.sub)
        bx, by, bw, bh = L.BAR
        self.phase = ui.text(ui.NAME, " ", ui.FG, bx, by - 10, (0, 1))
        g.append(self.phase)
        self.pct = ui.text(ui.NAME, " ", ui.FG, bx + bw, by - 10, (1, 1))
        g.append(self.pct)
        self.bar_group = displayio.Group()
        self.bar_group.append(ui.outlined(bx, by, bw, bh, ui.PANEL, ui.LINE))
        self.fill = ui.rect(bx + 3, by + 3, 1, bh - 6, ui.CYAN)
        self.fill_group = displayio.Group()
        self.fill_group.append(self.fill)
        self.bar_group.append(self.fill_group)
        g.append(self.bar_group)
        self.info = ui.text(ui.SMALL, " ", ui.DIM, bx, by + bh + 14, (0, 0.5))
        g.append(self.info)
        self.note = ui.text(ui.BODY, " ", ui.TEXT, W // 2, L.PROGRESS_NOTE_Y, (0.5, 0.5))
        self.note2 = ui.text(ui.BODY, " ", ui.TEXT, W // 2, L.PROGRESS_NOTE_Y + 18, (0.5, 0.5))
        g.append(self.note)
        g.append(self.note2)
        self.lines_at = len(g)
        g.append(displayio.Group())  # the plan's or an error's lines (_lines)
        cx, cy, cw, ch = L.CANCEL_BTN
        gx, gy, gw, gh = L.GO_BTN
        by2 = L.OK_BTN[1]
        self.left = ui.Button("Back", cx, by2, cw, ch)
        self.right = ui.Button("Update", gx, by2, gw, gh, fill=ui.CYAN, edge=ui.CYAN, color=ui.BG)
        g.append(self.left.group)
        g.append(self.right.group)
        self.group = g
        self._show()
        return g

    def _set_note(self, s, color=ui.TEXT):
        width_of = lambda t: ui.width(ui.BODY, t)  # noqa: E731
        parts = C.wrap(s, width_of, L.W - 24) if width_of(s) > L.W - 24 else [s]
        for label, part in ((self.note, parts[0] or " "), (self.note2, " ".join(parts[1:]) or " ")):
            label.color = color
            label.set(part)

    def _bar(self, done, total, color=ui.CYAN):
        bw = L.BAR[2] - 6
        w = max(1, bw * done // total) if total else 1
        self.fill.width = min(w, bw)
        self.fill.pixel_shader = ui.palette(color)
        self.fill_group.hidden = not total or done <= 0
        self.pct.set("%d%%" % (100 * done // total) if total else " ")

    def _lines(self, items):
        """Centred lines under the subtitle, for the plan and errors: items
        are (font, text, colour), each wrapped to the screen."""
        g = displayio.Group()
        y = L.PROGRESS_SUB_Y + 40
        for name, s, color in items:
            for part in C.wrap(s, lambda t: ui.width(name, t), L.W - 24):
                g.append(ui.text(name, part, color, L.W // 2, y, (0.5, 0)))
                y += 20
            y += 6
        self.group[self.lines_at] = g

    def _buttons(self, left, right):
        """Labels for the two buttons, or None to hide one."""
        for b, label in ((self.left, left), (self.right, right)):
            b.group.hidden = label is None
            if label:
                b.label.set(label)

    def _show(self):
        """Lay the screen out for the current mode."""
        m = self.mode
        self.bar_group.hidden = m not in ("run", "done")
        self.phase.hidden = self.pct.hidden = m not in ("run", "done")
        self._lines(())
        if m == "start":
            self.sub.set("Connecting to WiFi...")
            self._set_note(" ")
            self.info.set(" ")
            self._buttons("Back", None)
        elif m == "plan":
            p = self.plan
            self.sub.set("Catalogue " + C.nice_date(p.updated_at))
            self._set_note(" ")
            self.info.set(" ")
            if p.downloads or self.pics:
                counts = []
                for n, what in ((len(p.new), "new"), (len(p.changed), "updated")):
                    if n:
                        counts.append("%d %s" % (n, what))
                size = []
                if p.bytes:
                    size.append("%.1f MB to download" % (p.bytes / 1e6))
                if self.pics:
                    size.append("%d pictures" % len(self.pics))
                mins = max(1, (estimate_s(p, self.pics) + 30) // 60)
                self._lines(((ui.NAME, ", ".join(counts) or "Firmwares up to date", ui.FG),
                             (ui.BODY, ", ".join(size), ui.TEXT),
                             (ui.BODY, "About %d min. Keep the flasher powered." % mins, ui.DIM)))
                self._buttons("Back", "Update")
            else:
                self._lines(((ui.NAME, "Up to date", ui.OK),
                             (ui.BODY, "The card has all %d firmwares on the hub." % len(p.same), ui.TEXT)))
                self._buttons("Back", None)
        elif m == "run":
            self.sub.set(" ")
            self._set_note("You can keep using the flasher afterwards; Stop keeps what's done.", ui.DIM)
            self._buttons(None, "Stop")
        elif m == "done":
            s = self.stats
            done = []
            for k, label in (("new", "added"), ("updated", "updated"), ("pictures", "pictures")):
                if s[k]:
                    done.append("%d %s" % (s[k], label))
            failed = s["failed"]
            self.title.set("Stopped" if self.stopping else "Card updated")
            self.title.color = ui.WARN if (failed or self.stopping) else ui.OK
            self.sub.set(", ".join(done) or "Nothing changed")
            if failed:
                self._set_note("Failed: %s. Try again later." % ", ".join(failed[:4]), ui.WARN)
            elif self.stopping:
                self._set_note("What finished is on the card; Update again to go on.", ui.DIM)
            else:
                self._set_note(" ")
            self._buttons(None, "OK")
        elif m == "error":
            self.title.set("Update firmwares")
            self.sub.set(" ")
            self._set_note(" ")
            self._lines(((ui.BODY, self.message, ui.WARN),))
            self._buttons("Back", "Try again")

    def target(self, x, y):
        for b in (self.left, self.right):
            if not b.group.hidden and b.hit(x, y):
                return b.group
        return None

    def tap(self, x, y):
        if not self.left.group.hidden and self.left.hit(x, y):
            self.app.pop()
        elif not self.right.group.hidden and self.right.hit(x, y):
            if self.mode == "plan":
                self.start_run()
            elif self.mode == "run":
                self.stopping = True
                self.right.label.set("Stopping")
                self.app.refresh()
            elif self.mode == "done":
                self.app.reload_index()
                self.app.home()
            elif self.mode == "error":
                self.mode = "start"
                self._show()
                self.app.refresh()
                self.t0 = 0

    def swipe(self, dx):
        pass

    def fm1_changed(self):
        pass

    # -- work ------------------------------------------------------------------

    def tick(self, now):
        if self.mode == "start" and self.group is not None:
            if not self.t0:  # draw "Connecting" first; the next tick blocks
                self.t0 = now
                return
            self.check()
        elif self.mode == "run":
            self.advance(now)

    def check(self):
        """Connect and read the catalogue: blocks a few seconds."""
        app = self.app
        err = app.updater.connect()
        if err is None:
            self.sub.set("Reading the hub's catalogue...")
            app.refresh()
            try:
                cat = app.updater.get_json(K.HUB + "catalog.json")
                self.plan = K.Plan(cat, app.root)
                cat = None
                self.pics = picture_list(app.root, self.plan)
            except (OSError, ValueError, KeyError) as e:
                err = "Couldn't read the hub's catalogue (%s)." % (str(e) or repr(e))
        self.message = err or ""
        self.mode = "error" if err else "plan"
        self._show()
        app.refresh()

    def start_run(self):
        self.mode = "run"
        self.stats = {"new": 0, "updated": 0, "pictures": 0, "failed": [], "index": False}
        self.work = job(self.app.root, self.plan, self.app.updater, self.stats)
        self.t0 = time.monotonic()
        self._show()
        self.app.refresh()

    def advance(self, now):
        end = now + self.STEP_S
        status = None
        try:
            while time.monotonic() < end and not self.stopping:
                status = next(self.work)
        except StopIteration:
            self.finish()
            return
        except Exception as e:  # the network went away
            print("update: stopped: %r" % e)
            self.stats["failed"].append("network")
            self.finish()
            return
        if self.stopping:
            self.finish()
            return
        if status is not None:
            phase, done, total, name = status
            self.phase.set(phase)
            self.sub.set(C.ellipsize(name, lambda s: ui.width(ui.BODY, s), L.W - 24))
            self._bar(done, total)
            if phase == "Downloading":
                self.info.set("%.1f of %.1f MB" % (done / 1e6, total / 1e6))
            else:
                self.info.set("%d of %d" % (done + 1, total))
        if now - self.last_draw >= 0.5:
            self.last_draw = now
            self.app.refresh()

    def finish(self):
        work, self.work = self.work, None
        if work is not None:
            try:
                work.close()  # closes an open download
            except Exception:
                pass
        if not self.stats["index"]:  # stopped: the list, without a new date
            try:
                K.write_index(self.app.root)
            except OSError as e:
                print("update: index: %r" % e)
        self.mode = "done"
        self._bar(1, 1, ui.WARN if (self.stopping or self.stats["failed"]) else ui.OK)
        self.phase.set("Done" if not self.stopping else "Stopped")
        s = int(time.monotonic() - self.t0)
        self.info.set("Took %d:%02d" % (s // 60, s % 60))
        self._show()
        self.app.refresh()
