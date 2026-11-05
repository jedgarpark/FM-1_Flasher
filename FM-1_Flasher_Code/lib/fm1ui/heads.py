# SPDX-FileCopyrightText: 2026 John Park for Adafruit Industries
#
# SPDX-License-Identifier: GPL-3.0-only
"""Will the firmware the FM-1 runs refuse this install, because of the flash head?

A few packages carry M-VAVE's own update loader (V15, Bubba, Amenity, Clatter
on the hub in November 2026). It writes the whole flash image, including the
head: the first 16 KiB, the FM-1's start-up code. Firmwares built on Felucca
(SLOOP, ZP12, Duell...) stage such a package only when its head is the one the
FM-1 has ("update failed -5" on SLOOP), and the head is whatever the last of
those packages wrote. Firmwares built on V15 don't check. advice() says when an
install will be refused and which firmware on the card gets round it: one whose
head is the FM-1's, which the running firmware accepts and which then installs
anything (docs/PLAN-v2.md, Phase 3).
"""
# Disabled for the Learn Guides lint check: modules are imported where they're needed, to keep RAM
# free and start-up quick.
# pylint: disable=import-outside-toplevel
import json

STOCK_PRODUCT = "FM-1_015"
_cache = {}  # (slug, version) -> (official loader, head CRC or None)


def info(app, slug):
    """(official loader, head CRC or None) for a firmware on the card, or None
    when its package can't be read. Read once per version."""
    e = app.entry(slug) if slug else None
    if e is None:
        return None
    key = (slug, e.version)
    if key not in _cache:
        import fm1proto as P
        try:
            with open(app.path(slug, "meta.json")) as f:
                name = json.load(f)["file"]
            with open(app.path(slug, name), "rb") as f:
                pkg = P.Package(f)
                pkg.inspect(verify=False, strict=False)
                official = P.official_loader(pkg)
                _cache[key] = (official, P.flash_head(pkg) if official else None)
        except (OSError, ValueError, KeyError, P.FM1Error):
            return None
    return _cache[key]


def _stock_slug(app):
    found = app.index.with_product(STOCK_PRODUCT)
    return found[0] if found else None


def _running(app):
    """(name, checks the head) for the firmware the FM-1 runs; checks is None
    when it's nothing we know."""
    import fm1proto as P
    ident = app.identity
    known = app.installed_slug()
    slugs = [known] if known else app.index.with_product(ident)
    runs = [i for i in (info(app, s) for s in slugs) if i]
    if any(i[0] for i in runs):
        checks = False  # built on V15: it doesn't check the head
    elif runs or P.community_identity(ident):
        checks = True  # built on Felucca
    else:
        checks = None
    return (app.entry(known).name if known else ident), checks


def _fm1_head(app):
    """(head, recorded, slug that wrote it): what the last install with
    M-VAVE's loader wrote, as recorded; without a record, V15's, as the FM-1
    leaves the factory."""
    rec = app.state.head
    if rec:
        return rec.get("head"), True, rec.get("slug")
    slug = _stock_slug(app)
    stock = info(app, slug)
    return (stock[1] if stock else None), False, slug


def advice(app, entry):
    """A warning for the confirm screen, or None: the way round first, so it
    shows even when the screen has room for only part of it."""
    target = info(app, entry.slug)
    if not app.identity or not target or not target[0]:
        return None  # a Felucca-style loader: accepted from anything
    running, checks = _running(app)
    if not checks:
        return None
    head, sure, via = _fm1_head(app)
    if head is None or head == target[1]:
        return None
    # A way round: a firmware on the card whose head is the FM-1's.
    bridge = None
    for s in (via, _stock_slug(app)):
        i = info(app, s)
        if s and s != entry.slug and i and i[0] and i[1] == head:
            bridge = app.entry(s).name
            break
    why = "%s will %srefuse it: the FM-1's start-up code differs." % (
        running, "" if sure else "probably ")
    if bridge:
        return "Install %s first, then %s. %s" % (bridge, entry.name, why)
    return "%s Install the firmware that last changed it first." % why
