# SPDX-License-Identifier: GPL-3.0-only
"""The FM-1 Firmware Hub catalogue and the card's firmware folders, for
tools/make_sd.py (CPython) and the Metro ESP32-P4's Update firmwares screen
(CircuitPython). No network code: callers pass in how to fetch.

A card holds firmware/<slug>/ folders (the package, meta.json, pictures) and
firmware/index.txt, the list the device's UI reads. Folders made from the
catalogue are named by its id and carry it as meta.json's "catalog_id"; only
those are ever updated or removed here, so hand-added firmwares stay.

Writes are made safe against a power cut: files are written under a ".part"
name and renamed into place, meta.json last, and index.txt is rewritten the
same way. An interrupted update leaves a working card, and the next one
continues where it stopped (finished firmwares already match the catalogue).

Only os functions both Pythons have are used (no os.path, os.makedirs, shutil).
"""
import json
import os

import fm1proto as P

HUB = "https://thefirmwarehub.com/"
STOCK_ID = "stock-v15"
PART = ".part"


# -- the catalogue -------------------------------------------------------------

def own_installer(e):
    """True for a firmware the hub sends to its own installer ("Install on its
    page"): it writes data the package doesn't carry, so installing just the
    package leaves it asking for that data (FIZZ)."""
    return bool(e.get("install"))


def entries(cat, ids=None):
    """The catalogue's installable firmwares (all, or only `ids`), with stock
    V15 first. Firmwares with their own installer are left out. Raises
    KeyError naming ids that aren't there."""
    out = [e for e in cat["firmwares"] if e.get("pkg") and not own_installer(e)]
    stock = cat.get("stock")
    if stock and stock.get("pkg"):
        s = dict(stock)
        s.update(id=STOCK_ID, name="M-VAVE V15", author="M-VAVE", version="V15", kind="official",
                 lic="Apache-2.0",
                 what="The FM-1's official firmware, with its factory voices restored after the install.")
        out.insert(0, s)
    if ids:
        known = set(e["id"] for e in out)
        missing = [i for i in ids if i not in known]
        if missing:
            raise KeyError(", ".join(missing))
        out = [e for e in out if e["id"] in ids]
    return out


def meta_for(e):
    """meta.json's catalogue fields for entry `e` (finish() adds the rest)."""
    kind = e.get("kind")
    meta = {"name": e.get("name") or e["id"], "author": e.get("author"), "version": e.get("version"),
            "product": e["product"], "sha256": e["sha256"], "catalog_id": e["id"],
            "source_url": e.get("source") or e.get("release") or
            ("https://github.com/" + e["repo"] if e.get("repo") else None),
            "genre": ",".join(kind) if isinstance(kind, list) else kind, "beta": bool(e.get("beta")),
            "release_version": e.get("version"), "description": e.get("what"),
            "license": e.get("lic"), "date": e.get("date"), "installs": e.get("installs")}
    return dict((k, v) for k, v in meta.items() if v is not None)


def finish(meta, f):
    """Complete meta.json for the package in file `f` and run the full checks
    the device runs before an install (fm1proto.prepare). Returns the new
    meta; raises fm1proto.FM1Error if the package is rejected."""
    meta = dict(meta)
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    meta.setdefault("schema", 1)
    meta.setdefault("family", P.FAMILY)
    meta.setdefault("bytes", size)
    if "sha256" not in meta:
        meta["sha256"] = sha256_file(f)
    pkg = P.Package(f)
    pkg.inspect(strict=False)
    meta.setdefault("product", pkg.product)
    meta.setdefault("loader_sha256", pkg.loader_sha256())
    if meta["sha256"] == P.STOCK_SHA256:
        meta.setdefault("kind", "stock")
        meta.setdefault("build_id", P.STOCK_SHA256)
        meta.setdefault("release_version", "V15")
    if "kind" not in meta:
        if P.open_identity(meta["product"]) and "build_id" in meta:
            meta["kind"] = "open"
        elif P.community_identity(meta["product"]):
            meta["kind"] = "community"
        else:
            meta["kind"] = "open"
    if meta["kind"] == "open" and "build_id" not in meta:
        raise P.FM1Error("%s: build_id unknown; pass --build-id or use the release's Update.html" % meta["product"])
    meta.setdefault("name", meta.get("profile") or meta["product"])
    if meta["kind"] == "stock" and not meta.get("source_url"):
        meta["source_url"] = "https://github.com/m-vave/fm1_open"
        meta.setdefault("license", "Apache-2.0")
    f.seek(0)
    _, checked = P.prepare(meta, f)
    meta["loader_identity"] = checked["loader_identity"]
    meta["file"] = meta["product"] + ".fwsc"
    return meta


def sha256_file(f):
    h = _sha256()
    f.seek(0)
    buf = bytearray(8192)
    while True:
        n = f.readinto(buf)
        if not n:
            break
        h.update(memoryview(buf)[:n])
    f.seek(0)
    return _hex(h.digest())


def _sha256():
    import hashlib
    return hashlib.new("sha256")  # CircuitPython's hashlib has only new()


def _hex(b):
    return "".join("%02x" % c for c in b)


# -- the card ------------------------------------------------------------------

def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def is_dir(path):
    try:
        return os.stat(path)[0] & 0x4000 != 0
    except OSError:
        return False


def mkdirs(path):
    """os.makedirs(path, exist_ok=True)."""
    parts = path.split("/")
    for i in range(1, len(parts) + 1):
        p = "/".join(parts[:i])
        if p and not is_dir(p):
            os.mkdir(p)


def rmtree(path):
    for name in os.listdir(path):
        p = path + "/" + name
        if is_dir(p):
            rmtree(p)
        else:
            os.remove(p)
    os.rmdir(path)


def replace(src, dst):
    """os.replace: FAT can't rename onto an existing file."""
    try:
        os.remove(dst)
    except OSError:
        pass
    os.rename(src, dst)


def read_meta(folder):
    try:
        with open(folder + "/meta.json") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    with open(path + PART, "w") as f:
        f.write(json.dumps(data, sort_keys=True))
        f.write("\n")
    replace(path + PART, path)


def clean_parts(root):
    """Remove the .part files an interrupted update left."""
    if not is_dir(root):
        return
    for slug in os.listdir(root):
        d = root + "/" + slug
        if not is_dir(d):
            if slug.endswith(PART):
                os.remove(d)
            continue
        for name in os.listdir(d):
            if name.endswith(PART):
                os.remove(d + "/" + name)


def matches(root, e):
    """Is catalogue entry `e` already on the card, unchanged?"""
    d = root + "/" + e["id"]
    m = read_meta(d)
    return bool(m and m.get("sha256") == e["sha256"] and m.get("catalog_id") == e["id"]
                and exists(d + "/" + m.get("file", "")))


class Plan:
    """What an update would do: new and updated catalogue entries to download,
    and the card's catalogue folders the hub no longer lists (removed)."""

    def __init__(self, cat, root, ids=None):
        self.updated_at = cat.get("updated")
        self.new, self.changed, self.same, self.removed = [], [], [], []
        wanted = entries(cat, ids)
        for e in wanted:
            if matches(root, e):
                self.same.append(e)
            elif read_meta(root + "/" + e["id"]):
                self.changed.append(e)
            else:
                self.new.append(e)
        if ids is None:  # a full update: drop what the hub dropped
            keep = set(e["id"] for e in wanted)
            for slug in (os.listdir(root) if is_dir(root) else ()):
                m = read_meta(root + "/" + slug)
                if m and m.get("catalog_id") and m["catalog_id"] == slug and slug not in keep:
                    self.removed.append(slug)
            self.removed.sort()

    @property
    def downloads(self):
        return self.new + self.changed

    @property
    def bytes(self):
        return sum(e.get("size", 0) for e in self.downloads)

    def summary(self):
        """'12 new, 3 updated, 2 removed, 8.1 MB', or 'Up to date'."""
        parts = []
        for n, what in ((len(self.new), "new"), (len(self.changed), "updated"), (len(self.removed), "removed")):
            if n:
                parts.append("%d %s" % (n, what))
        if not parts:
            return "Up to date"
        if self.bytes:
            parts.append("%.1f MB" % (self.bytes / 1e6))
        return ", ".join(parts)


def remove(root, slug):
    """Delete a catalogue folder: meta.json first, so a power cut mid-way
    leaves a folder the index ignores."""
    d = root + "/" + slug
    try:
        os.remove(d + "/meta.json")
    except OSError:
        pass
    rmtree(d)


def store(root, e, meta):
    """Put the downloaded, finished package (<root>/<id>/<file>.part) in
    place, then its meta.json."""
    d = root + "/" + e["id"]
    old = read_meta(d)
    if old and old.get("file") and old["file"] != meta["file"]:
        try:
            os.remove(d + "/" + old["file"])
        except OSError:
            pass
    replace(d + "/" + meta["file"] + PART, d + "/" + meta["file"])
    write_json(d + "/meta.json", meta)


def download(root, e, stream, chunk=None):
    """A generator: stream catalogue entry `e`'s package to the card, check its
    size and SHA-256 against the catalogue, run the full package checks and
    store it with meta.json. stream(url) yields the package's bytes in chunks.
    Yields the bytes written so far after each chunk; raises ValueError for a
    download that doesn't match, fm1proto.FM1Error for a rejected package."""
    d = root + "/" + e["id"]
    mkdirs(d)
    part = d + "/" + e["product"] + ".fwsc" + PART
    h = _sha256()
    n = 0
    chunks = stream(HUB + e["pkg"])
    try:
        with open(part, "wb") as f:
            for data in chunks:
                f.write(data)
                h.update(data)
                n += len(data)
                yield n
    finally:
        if hasattr(chunks, "close"):
            chunks.close()  # a stopped download: let the connection go
    if n != e["size"] or _hex(h.digest()) != e["sha256"]:
        os.remove(part)
        raise ValueError("%s: the download doesn't match the catalogue" % e["id"])
    try:
        with open(part, "rb") as f:
            meta = finish(meta_for(e), f)
    except Exception:
        os.remove(part)
        raise
    store(root, e, meta)


def write_index(root, updated=None):
    """firmware/index.txt: what the device's list screen reads, one tab-separated
    line per firmware (slug, name, version, genre, beta, product), stock first,
    then by name. The first line is the catalogue date. Returns the count."""
    path = root + "/index.txt"
    if updated is None:
        try:
            with open(path) as f:
                updated = f.readline().rstrip("\n").partition("\t")[2] or None
        except OSError:
            pass
    rows = []
    for slug in os.listdir(root):
        m = read_meta(root + "/" + slug)
        if not m or "product" not in m:
            continue
        fields = (slug, m.get("name", slug), m.get("version", ""), m.get("genre") or m.get("kind", ""),
                  1 if m.get("beta") else 0, m["product"])
        line = "\t".join(str(v).replace("\t", " ").replace("\n", " ") for v in fields)
        rows.append((m.get("kind") != "stock", m.get("name", slug).lower(), line))
    rows.sort()
    with open(path + PART, "w") as f:
        f.write("updated\t%s\n" % (updated or ""))
        for row in rows:
            f.write(row[2] + "\n")
    replace(path + PART, path)
    return len(rows)
