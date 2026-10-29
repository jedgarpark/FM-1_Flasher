# SPDX-License-Identifier: GPL-3.0-only
"""What the UI shows, without any display code (runs on CPython for tests).

The firmware list comes from firmware/index.txt, written by tools/make_sd.py:
a first line "updated<TAB>date", then one line per firmware with slug, name,
version, genre, beta (0/1) and product. Favourites, the last install and a
pending install live in a small JSON state file on the card.
"""
import json

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class Entry:
    __slots__ = ("slug", "name", "version", "genre", "beta", "product")

    def __init__(self, slug, name, version, genre, beta, product):
        self.slug = slug
        self.name = name
        self.version = version
        self.genre = genre
        self.beta = beta
        self.product = product

    @property
    def kind(self):
        """The first genre: what colours the card."""
        return self.genre.split(",")[0]


class Index:
    """The firmware list, left on the card: only where each line starts is
    kept in RAM (parsed entries would cost the Feather ~20 KB, the lines
    themselves ~6 KB), and Entry objects are made only for the cards on screen."""

    def __init__(self, path):
        self.path = path
        self.updated = None
        self.starts = []
        with open(path, "rb") as f:
            pos = 0
            for n, raw in enumerate(f):
                line = raw.rstrip(b"\r\n")
                if n == 0 and line.startswith(b"updated\t"):
                    self.updated = line[8:].decode() or None
                elif line.count(b"\t") == 5:
                    self.starts.append(pos)
                pos += len(raw)

    def __len__(self):
        return len(self.starts)

    def _lines(self):
        """(position, line) for every entry, from one pass over the file."""
        with open(self.path, "rb") as f:
            for i, start in enumerate(self.starts):
                f.seek(start)
                yield i, f.readline().rstrip(b"\r\n").decode()

    def entry(self, i):
        with open(self.path, "rb") as f:
            f.seek(self.starts[i])
            fields = f.readline().rstrip(b"\r\n").decode().split("\t")
        return Entry(fields[0], fields[1], fields[2], fields[3], fields[4] == "1", fields[5])

    def slug(self, i):
        return self.entry(i).slug

    def find(self, slug):
        key = slug + "\t"
        for i, line in self._lines():
            if line.startswith(key):
                return self.entry(i)
        return None

    def select(self, slugs=None, tag=None):
        """Positions of the entries whose slug is in `slugs` (all if None)
        and that carry `tag` among their genres (any if None)."""
        if slugs is None and tag is None:
            return list(range(len(self.starts)))
        out = []
        for i, line in self._lines():
            fields = line.split("\t", 4)
            if (slugs is None or fields[0] in slugs) and (tag is None or tag in fields[3].split(",")):
                out.append(i)
        return out

    def tags(self):
        """Every genre tag, the most used first (ties by name)."""
        counts = {}
        for _, line in self._lines():
            for g in line.split("\t", 4)[3].split(","):
                if g:
                    counts[g] = counts.get(g, 0) + 1
        return [g for g, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    def with_product(self, product):
        tail = "\t" + product
        return [line.split("\t", 1)[0] for _, line in self._lines() if line.endswith(tail)]


def load_index(path):
    """(catalogue date or None, [Entry]): the whole list, parsed."""
    index = Index(path)
    return index.updated, [index.entry(i) for i in range(len(index))]


def nice_date(s):
    """'2026-10-28 03:02 UTC' -> '28 Oct 2026'; anything else unchanged."""
    if not s:
        return ""
    try:
        y, m, d = s.split(" ")[0].split("-")
        return "%d %s %s" % (int(d), MONTHS[int(m) - 1], y)
    except (ValueError, IndexError):
        return s


def version_label(version):
    """'2.8' -> 'v2.8'; 'V15' stays 'V15'."""
    if not version:
        return ""
    return version if version[0] in "vV" else "v" + version


def display_name(e):
    """Name and version, without repeating a version the name already has."""
    if not e.version or e.version.lower() in e.name.lower():
        return e.name
    return "%s %s" % (e.name, e.version)


def page_count(n, per_page):
    return max(1, (n + per_page - 1) // per_page)


def page_slice(items, page, per_page):
    return items[page * per_page:(page + 1) * per_page]


class State:
    """Favourites, the last install, a pending install and the list view
    ("grid" or "list"), kept in a JSON file.
    Writes are best effort: a read-only card just means nothing is remembered."""

    def __init__(self, path):
        self.path = path
        self.favorites = set()
        self.installed = None  # {"slug": ..., "product": ...}
        self.pending = None    # slug of an install to run after a reload
        self.view = "grid"
        try:
            with open(path) as f:
                data = json.load(f)
            self.favorites = set(data.get("favorites", ()))
            self.installed = data.get("installed")
            self.pending = data.get("pending")
            self.view = data.get("view", "grid")
        except (OSError, ValueError):
            pass

    def save(self):
        data = {"favorites": sorted(self.favorites), "installed": self.installed, "pending": self.pending,
                "view": self.view}
        try:
            with open(self.path, "w") as f:
                json.dump(data, f)
            return True
        except OSError:
            return False

    def toggle_favorite(self, slug):
        if slug in self.favorites:
            self.favorites.remove(slug)
        else:
            self.favorites.add(slug)
        self.save()
        return slug in self.favorites

    def record_install(self, slug, product):
        self.installed = {"slug": slug, "product": product}
        self.pending = None
        self.save()

    def installed_slug(self, identity, index):
        """The firmware the FM-1 is running, if we can tell. Many firmwares
        share an identity (19 report FM-1_900), so trust our own last install
        when it matches, and otherwise only an identity no other entry has."""
        if not identity:
            return None
        if self.installed and self.installed.get("product") == identity:
            return self.installed.get("slug")
        found = index.with_product(identity)
        return found[0] if len(found) == 1 else None


def wrap(text, width_of, max_width):
    """Split text into lines no wider than max_width; width_of(s) measures a string."""
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            trial = word if not line else line + " " + word
            if line and width_of(trial) > max_width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def ellipsize(text, width_of, max_width):
    """text, shortened with '...' to fit max_width."""
    if width_of(text) <= max_width:
        return text
    while text and width_of(text + "...") > max_width:
        text = text[:-1]
    return text.rstrip() + "..."
