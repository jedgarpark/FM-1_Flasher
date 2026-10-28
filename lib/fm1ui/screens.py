# SPDX-License-Identifier: GPL-3.0-only
"""The flasher's screens: firmware list, details, confirm and install progress.

Each screen builds its displayio group when shown and lets it go when another
screen covers it, so only one screen's objects are in RAM. Screens get
taps and swipes from the App and redraw by changing their objects in place.
"""
import json
import time

import displayio

from fm1ui import catalog as C
from fm1ui import ui

W, H = 480, 320
COLS, ROWS = 4, 2
PER_PAGE = COLS * ROWS
CARD_W, CARD_H, GAP = 112, 118, 6
GRID_X, GRID_Y = 7, 40
THUMB = 80
STOCK_PRODUCT = "FM-1_015"


def _hit(rect, x, y, slack=0):
    """Is (x, y) in rect, or within `slack` px of it? Small targets get
    slack: a fingertip lands 10-15 px from where it's aimed."""
    rx, ry, rw, rh = rect
    return rx - slack <= x < rx + rw + slack and ry - slack <= y < ry + rh + slack


class Screen:
    # Attributes that outlive a build; release() drops every other one, so
    # the displayio objects a screen keeps handles on are freed with its group.
    KEEP = ("app", "group")

    def __init__(self, app):
        self.app = app
        self.group = None

    def build(self):
        raise NotImplementedError

    def release(self):
        self.group = None
        for k in list(self.__dict__):
            if k not in self.KEEP:
                delattr(self, k)

    def tap(self, x, y):
        pass

    def swipe(self, dx):
        pass

    def tick(self, now):
        pass

    def fm1_changed(self):
        """The attached FM-1 (app.identity) changed."""


class ListScreen(Screen):
    """Eight cards a page, a favourites filter, and the FM-1 in the header."""

    KEEP = Screen.KEEP + ("page", "favorites_only")

    def __init__(self, app):
        super().__init__(app)
        self.page = 0
        self.favorites_only = False
        self.cards = []  # (entry, card rect, heart rect, heart tile)

    def items(self):
        """Index positions of the entries the filter shows."""
        return self.app.index.select(self.app.state.favorites if self.favorites_only else None)

    def build(self):
        app = self.app
        items = self.items()
        pages = C.page_count(len(items), PER_PAGE)
        self.page = min(self.page, pages - 1)
        shown = [app.index.entry(i) for i in C.page_slice(items, self.page, PER_PAGE)]
        del items
        installed = app.installed_slug()

        names = [e.name for e in shown] + ["FM-1 Flasher", "All", "Prev", "Next"]

        g = displayio.Group()
        g.append(ui.rect(0, 0, W, H, ui.BG))
        # header
        g.append(ui.text(ui.NAME, "FM-1 Flasher", ui.CYAN, 12, 18, (0, 0.5)))
        self.tab_all = ui.Button("All", 140, 5, 52, 26, fill=ui.PANEL if not self.favorites_only else ui.BG,
                                 edge=ui.CYAN if not self.favorites_only else ui.LINE,
                                 color=ui.FG if not self.favorites_only else ui.DIM)
        g.append(self.tab_all.group)
        self.tab_fav = (198, 5, 64, 26)
        on = self.favorites_only
        g.append(ui.outlined(198, 5, 64, 26, ui.PANEL if on else ui.BG, ui.CYAN if on else ui.LINE))
        g.append(ui.heart_tile(True, 208, 12))
        g.append(ui.text(ui.SMALL, "%d" % len(app.state.favorites), ui.FG if on else ui.DIM, 228, 18, (0, 0.5)))
        self.status = ui.text(ui.SMALL, self.status_text(), ui.FG if app.identity else ui.DIM, 468, 18, (1, 0.5))
        g.append(self.status)
        self.dot = ui.rect(468 - ui.width(ui.SMALL, self.status.text) - 14, 14, 8, 8, ui.OK if app.identity else ui.LINE)
        g.append(self.dot)

        # cards
        self.cards = []
        if not shown:
            g.append(ui.text(ui.BODY if self.favorites_only else ui.NAME,
                             "No favourites yet. Tap the heart on a card to add one." if self.favorites_only
                             else "No firmware found on the card.", ui.DIM, W // 2, 160, (0.5, 0.5)))
        for i, e in enumerate(shown):
            x = GRID_X + (i % COLS) * (CARD_W + GAP)
            y = GRID_Y + (i // COLS) * (CARD_H + GAP)
            g.append(self.card(e, x, y, e.slug == installed, i))

        # footer
        self.prev = (7, 286, 64, 32)
        self.next = (409, 286, 64, 32)
        for (bx, by, bw, bh), left in ((self.prev, True), (self.next, False)):
            active = (self.page > 0) if left else (self.page < pages - 1)
            g.append(ui.outlined(bx, by, bw, bh, ui.PANEL if active else ui.BG, ui.LINE))
            g.append(ui.triangle(bx + bw // 2 - 5, by + bh // 2 - 8, 10, 16, ui.CYAN if active else ui.LINE, left))
        g.append(ui.text(ui.SMALL, "Page %d of %d" % (self.page + 1, pages), ui.FG, W // 2, 296, (0.5, 0.5)))
        if app.updated:
            g.append(ui.text(ui.SMALL, "Catalogue " + C.nice_date(app.updated), ui.DIM, W // 2, 311, (0.5, 0.5)))
        self.pages = pages
        self.group = g
        return g

    def status_text(self):
        app = self.app
        if not app.identity:
            return "No FM-1"
        slug = app.installed_slug()
        e = app.entry(slug) if slug else None
        return ("FM-1: " + C.display_name(e)) if e else ("FM-1: " + app.identity)

    def card(self, e, x, y, installed, slot):
        g = ui.outlined(x, y, CARD_W, CARD_H, ui.PANEL, ui.CYAN if installed else ui.LINE)
        if installed:  # a second line makes the outline read at a glance
            g.append(ui.panel(x + 1, y + 1, CARD_W - 2, CARD_H - 2, ui.CYAN, 3))
            g.append(ui.panel(x + 2, y + 2, CARD_W - 4, CARD_H - 4, ui.PANEL, 2))
        g.append(ui.rect(x + 4, y + 2, CARD_W - 8, 3, ui.kind_color(e.kind)))
        g.append(ui.thumbnail(self.app.path(e.slug, "thumb.bmp"), x + 16, y + 8, THUMB, e.version, slot))
        if installed:
            g.append(ui.rect(x + 16, y + 76, THUMB, 12, ui.CYAN))
            g.append(ui.text(ui.SMALL, "INSTALLED", ui.BG, x + 56, y + 82, (0.5, 0.5)))
        fav = e.slug in self.app.state.favorites
        tile = ui.heart_tile(fav, x + CARD_W - 15, y + 10)
        g.append(tile)
        name = C.ellipsize(e.name, lambda s: ui.width(ui.NAME, s), CARD_W - 8)
        g.append(ui.text(ui.NAME, name, ui.FG, x + CARD_W // 2, y + 90, (0.5, 0)))
        version = C.ellipsize(e.version, lambda s: ui.width(ui.SMALL, s), CARD_W - (50 if e.beta else 8))
        if e.beta:
            vw, bw = ui.width(ui.SMALL, version + " "), ui.width(ui.SMALL, "beta")
            left = x + (CARD_W - vw - bw) // 2
            g.append(ui.text(ui.SMALL, version, ui.DIM, left, y + 106, (0, 0)))
            g.append(ui.text(ui.SMALL, "beta", ui.WARN, left + vw, y + 106, (0, 0)))
        else:
            g.append(ui.text(ui.SMALL, version, ui.DIM, x + CARD_W // 2, y + 106, (0.5, 0)))
        self.cards.append((e, (x, y, CARD_W, CARD_H), (x + 84, y - GAP, CARD_W - 84 + GAP, 50), tile))
        return g

    def turn(self, delta):
        page = self.page + delta
        if 0 <= page < self.pages:
            self.page = page
            self.app.show()

    def tap(self, x, y):
        if y < GRID_Y - 2 and 110 <= x < 290:
            # The tabs take the header's full height (taps there land high)
            # and split at the gap between them.
            fav = x >= (self.tab_all.rect[0] + self.tab_all.rect[2] + self.tab_fav[0]) // 2
            if fav != self.favorites_only:
                self.favorites_only = fav
                self.page = 0
                self.app.show()
        elif y >= self.prev[1] - 8 and x < 140:
            self.turn(-1)
        elif y >= self.next[1] - 8 and x >= W - 140:
            self.turn(1)
        else:
            for e, card, heart, tile in self.cards:
                if _hit(heart, x, y):
                    ui.set_heart(tile, self.app.state.toggle_favorite(e.slug))
                    if self.favorites_only:
                        self.app.show()
                    else:
                        self.app.refresh()
                    return
                if _hit(card, x, y):
                    self.app.push(DetailScreen(self.app, e))
                    return

    def swipe(self, dx):
        self.turn(1 if dx < 0 else -1)

    def fm1_changed(self):
        self.app.show()


class DetailScreen(Screen):
    """The picture, name, author, version, tags and description, with Back,
    a favourite toggle and Install."""

    KEEP = Screen.KEEP + ("entry", "meta")

    def __init__(self, app, entry):
        super().__init__(app)
        self.entry = entry
        self.meta = None

    def build(self):
        e, app = self.entry, self.app
        if self.meta is None:
            try:
                with open(app.path(e.slug, "meta.json")) as f:
                    self.meta = json.load(f)
            except (OSError, ValueError):
                self.meta = {}
        m = self.meta
        author = m.get("author") or ""
        desc = m.get("description") or ""
        size = m.get("bytes")
        info = "  ".join(s for s in (C.version_label(e.version), e.product,
                                     "%d KB" % (size // 1024) if size else "") if s)
        tags = [(g, ui.kind_color(g)) for g in e.genre.split(",") if g]
        if e.beta:
            tags.append(("beta", ui.WARN))
        if m.get("license"):
            tags.append((m["license"], ui.DIM))
        installed = app.installed_slug() == e.slug


        g = displayio.Group()
        g.append(ui.rect(0, 0, W, H, ui.BG))
        g.append(ui.rect(0, 0, W, 3, ui.kind_color(e.kind)))
        self.back = ui.Button("Back", 8, 8, 84, 30)
        g.append(self.back.group)
        self.heart_rect = (424, 8, 48, 30)
        g.append(ui.outlined(424, 8, 48, 30, ui.PANEL, ui.LINE))
        self.heart = ui.heart_tile(e.slug in app.state.favorites, 442, 18)
        g.append(self.heart)

        g.append(ui.outlined(11, 47, 162, 162, ui.THUMB_BG, ui.LINE, 1))
        g.append(ui.thumbnail(app.path(e.slug, "large.bmp"), 12, 48, 160, e.version))

        x0 = 186
        tf = ui.title_font(e.name)
        name = C.ellipsize(e.name, lambda s: ui.width(tf, s), W - x0 - 60)
        g.append(ui.text(tf, name, ui.FG, x0, 48, (0, 0)))
        y = 76
        if author:
            g.append(ui.text(ui.BODY, C.ellipsize("by " + author, lambda s: ui.width(ui.BODY, s), W - x0 - 12),
                             ui.DIM, x0, y, (0, 0)))
            y += 22
        g.append(ui.text(ui.SMALL, info, ui.DIM, x0, y, (0, 0)))
        y += 20
        tx = x0
        for label, color in tags:
            w = ui.width(ui.SMALL, label) + 14
            if tx + w > W - 8:
                break
            g.append(ui.outlined(tx, y, w, 20, ui.PANEL, ui.LINE, 3))
            g.append(ui.text(ui.SMALL, label, color, tx + w // 2, y + 10, (0.5, 0.5)))
            tx += w + 6
        y += 30

        # Description: beside the picture, then full width under it.
        lines = []
        rest = desc
        width_of = lambda s: ui.width(ui.BODY, s)  # noqa: E731
        while rest and y + 16 <= 276:
            left = x0 if y < 212 else 12
            line = C.wrap(rest, width_of, W - left - 12)[0]
            rest = rest[len(line):].lstrip(" ")
            if rest and y + 34 > 276:  # last line that fits
                line = C.ellipsize(line + " " + rest, width_of, W - left - 12 if left == x0 else 300)
                rest = ""
            lines.append((left, y, line))
            y += 18
        for left, ly, line in lines:
            g.append(ui.text(ui.BODY, line, ui.TEXT, left, ly, (0, 0)))

        self.install = ui.Button("Install again" if installed else "Install", 330, 282, 142, 34,
                                 fill=ui.CYAN, edge=ui.CYAN, color=ui.BG)
        g.append(self.install.group)
        if installed:
            g.append(ui.text(ui.SMALL, "Installed on this FM-1", ui.CYAN, 12, 299, (0, 0.5)))
        self.group = g
        return g

    def tap(self, x, y):
        if self.back.hit(x, y):
            self.app.pop()
        elif _hit(self.heart_rect, x, y, 14):
            ui.set_heart(self.heart, self.app.state.toggle_favorite(self.entry.slug))
            self.app.refresh()
        elif self.install.hit(x, y):
            self.app.push(ConfirmScreen(self.app, self.entry))

    def swipe(self, dx):
        if dx > 0:
            self.app.pop()


class ConfirmScreen(Screen):
    """Install X over what the FM-1 is running? Waits for an FM-1 if none is attached."""

    KEEP = Screen.KEEP + ("entry",)

    def __init__(self, app, entry):
        super().__init__(app)
        self.entry = entry

    def message(self):
        app, e = self.app, self.entry
        ident = app.identity
        if not ident:
            return False, ("Connect the FM-1 to the USB port and turn it on. "
                           "This screen continues when it appears.")
        current = app.installed_slug()
        cur = app.entry(current) if current else None
        running = C.display_name(cur) if cur else ident
        if current == e.slug:
            text = "%s is already on the FM-1. Install it again?" % e.name
        elif e.product == STOCK_PRODUCT:
            text = ("This puts back M-VAVE's official firmware and its factory voices, "
                    "replacing %s." % running)
        elif ident == STOCK_PRODUCT:
            text = ("The FM-1 runs M-VAVE's official V15. %s replaces it; the M-VAVE V15 card "
                    "puts it back any time." % e.name)
        else:
            text = "%s replaces %s on the FM-1." % (e.name, running)
        return True, text + " Keep the FM-1 on and connected; it takes one to two minutes."

    def build(self):
        e = self.entry
        ready, msg = self.message()
        self.ready = ready
        title = "Install %s?" % e.name
        width_of = lambda s: ui.width(ui.BODY, s)  # noqa: E731
        g = displayio.Group()
        g.append(ui.rect(0, 0, W, H, ui.BG))
        g.append(ui.outlined(30, 30, 420, 260, ui.PANEL, ui.LINE))
        g.append(ui.rect(34, 32, 412, 3, ui.kind_color(e.kind)))
        tf = ui.title_font(title)
        g.append(ui.text(tf, C.ellipsize(title, lambda s: ui.width(tf, s), 380), ui.FG, 50, 52, (0, 0)))
        y = 92
        for line in C.wrap(msg, width_of, 380)[:7]:
            g.append(ui.text(ui.BODY, line, ui.TEXT, 50, y, (0, 0)))
            y += 19
        self.cancel = ui.Button("Cancel", 50, 234, 170, 40)
        self.go = ui.Button("Install", 260, 234, 170, 40, fill=ui.CYAN if ready else ui.BG,
                            edge=ui.CYAN if ready else ui.LINE, color=ui.BG if ready else ui.LINE)
        g.append(self.cancel.group)
        g.append(self.go.group)
        self.group = g
        return g

    def tap(self, x, y):
        if self.cancel.hit(x, y):
            self.app.pop()
        elif self.go.hit(x, y) and self.ready:
            self.app.start_install(self.entry)

    def fm1_changed(self):
        self.app.show()


class ProgressScreen(Screen):
    """Install progress: the phase, a bar, elapsed time and hints. The
    installer drives it through phase(), wait() and finish()."""

    BAR = (40, 156, 400, 26)
    KEEP = Screen.KEEP + ("entry", "t0", "waiting_since", "done", "last_draw")
    LONG_WAIT_S = 20

    def __init__(self, app, entry):
        super().__init__(app)
        self.entry = entry
        self.t0 = time.monotonic()
        self.waiting_since = None
        self.done = None
        self.last_draw = 0

    def build(self):
        e = self.entry
        g = displayio.Group()
        g.append(ui.rect(0, 0, W, H, ui.BG))
        g.append(ui.rect(0, 0, W, 3, ui.kind_color(e.kind)))
        tf = ui.title_font(e.name)
        self.title = ui.text(tf, C.ellipsize("Installing %s" % e.name, lambda s: ui.width(tf, s), 440),
                             ui.FG, W // 2, 50, (0.5, 0))
        g.append(self.title)
        self.sub = ui.text(ui.BODY, "Keep the FM-1 on and connected.", ui.DIM, W // 2, 84, (0.5, 0))
        g.append(self.sub)
        bx, by, bw, bh = self.BAR
        self.phase_label = ui.text(ui.NAME, "Preparing", ui.FG, bx, by - 10, (0, 1))
        g.append(self.phase_label)
        self.pct = ui.text(ui.NAME, "", ui.FG, bx + bw, by - 10, (1, 1))
        g.append(self.pct)
        g.append(ui.outlined(bx, by, bw, bh, ui.PANEL, ui.LINE))
        self.fill = ui.rect(bx + 3, by + 3, 1, bh - 6, ui.CYAN)
        self.fill_group = displayio.Group()  # shapes can't hide themselves; groups can
        self.fill_group.append(self.fill)
        self.fill_group.hidden = True
        g.append(self.fill_group)
        self.elapsed = ui.text(ui.SMALL, "Elapsed 0:00", ui.DIM, bx, by + bh + 14, (0, 0.5))
        g.append(self.elapsed)
        self.note = ui.text(ui.BODY, " ", ui.WARN, W // 2, 232, (0.5, 0.5))
        g.append(self.note)
        self.ok = ui.Button("OK", 170, 266, 140, 40, fill=ui.CYAN, edge=ui.CYAN, color=ui.BG)
        self.ok.group.hidden = True
        g.append(self.ok.group)
        self.group = g
        return g

    def _bar(self, pct, color=None):
        bx, by, bw, bh = self.BAR
        w = max(1, (bw - 6) * pct // 100)
        self.fill.width = w
        if color is not None:
            self.fill.pixel_shader = ui.palette(color)
        self.fill_group.hidden = pct <= 0

    def _clock(self, now):
        s = int(now - self.t0)
        self.elapsed.set("Elapsed %d:%02d" % (s // 60, s % 60))

    def phase(self, name, pct):
        """Installer status callback."""
        if self.waiting_since is not None:
            self.waiting_since = None
            self.note.set(" ")
        self.phase_label.set(name)
        self.pct.set("%d%%" % pct)
        self._bar(pct)
        self.redraw()

    def wait(self, what):
        """The installer is waiting for the FM-1 to come back."""
        self.waiting_since = time.monotonic()
        self.note.color = ui.WARN
        self.note.set("Waiting for the FM-1 to restart...")
        self.redraw(force=True)

    def found(self):
        if self.waiting_since is not None:
            self.waiting_since = None
            self.note.set(" ")
            self.redraw(force=True)

    def tick(self, now):
        if self.done is not None:
            return
        if self.waiting_since is not None and now - self.waiting_since > self.LONG_WAIT_S:
            self.note.set("If it doesn't come back, turn the FM-1 off and on again.")
        self.redraw()

    def redraw(self, force=False):
        now = time.monotonic()
        if force or now - self.last_draw >= 1:
            self._clock(now)
            self.last_draw = now
            self.app.refresh()

    def finish(self, ok, message=""):
        self.done = ok
        self._clock(time.monotonic())
        if ok:
            self.title.set("Installed %s" % self.entry.name)
            self.title.color = ui.OK
            self.phase_label.set("Done")
            self.pct.set("100%")
            self._bar(100, ui.OK)
            self.sub.set(" ")
            self.note.color = ui.DIM
            self.note.set(message or " ")
        else:
            self.title.set("Install failed")
            self.title.color = ui.BAD
            self.sub.set(message[:60] if message else " ")
            self._bar(max(1, self.fill.width * 100 // (self.BAR[2] - 6)), ui.BAD)
            self.note.color = ui.WARN
            self.note.set("Power-cycle the FM-1; the firmware it had still boots.")
        self.ok.group.hidden = False
        self.app.refresh()

    def tap(self, x, y):
        if self.done is not None and self.ok.hit(x, y):
            self.app.finish_install()
