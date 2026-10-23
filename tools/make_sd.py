#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prepare firmware folders for the flasher's microSD card.

Each firmware becomes  <out>/firmware/<slug>/<product>.fwsc + meta.json,
fully verified with the same checks the device runs (fm1proto.prepare).

Sources:
  --html Update.html     an FM1 Open-style release page; its embedded
                         FM1_PACKAGE JSON carries the package and metadata
  --fwsc FILE --meta M   a package plus a JSON file of metadata fields
  --fwsc FILE            stock V15 is recognized by its SHA-256, FM-1_<n>
                         packages install by the community route; FM1 Open
                         packages need --build-id
  --catalog [ID ...]     download from the FM-1 Firmware Hub catalogue
                         (all firmwares, or only the given ids), verifying
                         each package's SHA-256 against the catalogue

Examples:
  tools/make_sd.py --out /Volumes/FM1SD --fwsc ref/fm1_open/sdk/firmware/FM-1_015.fwsc \\
      --name "M-VAVE V15 (stock)" --author M-VAVE --license Apache-2.0
  tools/make_sd.py --out /Volumes/FM1SD --html ~/Downloads/Update.html --source-url https://...
  tools/make_sd.py --out /Volumes/FM1SD --catalog sloop felucca
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import fm1proto as P  # noqa: E402

FIELDS = ("schema", "kind", "product", "family", "build_id", "bytes", "sha256", "loader_sha256",
          "release_version", "profile")
EXTRA = ("name", "author", "version", "source_url", "license", "notes")
HUB = "https://thefirmwarehub.com/"
UA = {"User-Agent": "FM-1_Flasher make_sd.py"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def from_catalog(ids):
    cat = json.loads(fetch(HUB + "catalog.json"))
    entries = [e for e in cat["firmwares"] if e.get("pkg")]
    if ids:
        known = {e["id"] for e in entries}
        missing = [i for i in ids if i not in known]
        if missing:
            sys.exit("not in the catalogue (or no package): " + ", ".join(missing))
        entries = [e for e in entries if e["id"] in ids]
    out = []
    for e in entries:
        data = fetch(HUB + e["pkg"])
        if hashlib.sha256(data).hexdigest() != e["sha256"] or len(data) != e["size"]:
            print("skipping %s: download does not match the catalogue" % e["id"], file=sys.stderr)
            continue
        meta = {"name": e.get("name") or e["id"], "author": e.get("author"), "version": e.get("version"),
                "product": e["product"], "sha256": e["sha256"], "catalog_id": e["id"],
                "source_url": e.get("source") or e.get("release") or
                ("https://github.com/" + e["repo"] if e.get("repo") else None),
                "genre": e.get("kind"), "beta": bool(e.get("beta")), "release_version": e.get("version")}
        out.append((data, {k: v for k, v in meta.items() if v is not None}, e["id"]))
    return out


def from_html(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"const FM1_PACKAGE = (\{.*?\});", text, re.S)
    if not m or m.group(1) == "null":
        sys.exit("%s: no embedded FM1_PACKAGE" % path)
    pkg = json.loads(m.group(1))
    out = []
    for meta in (pkg, pkg.get("stock")):
        if not meta:
            continue
        data = base64.b64decode(meta["data"])
        meta = {k: v for k, v in meta.items() if k not in ("data", "stock")}
        out.append((data, meta))
    return out


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "firmware"


def build(data, meta, args):
    meta = dict(meta)
    meta.setdefault("schema", 1)
    meta.setdefault("family", P.FAMILY)
    meta.setdefault("bytes", len(data))
    meta.setdefault("sha256", hashlib.sha256(data).hexdigest())
    pkg = P.Package(io.BytesIO(data))
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
        sys.exit("%s: build_id unknown; pass --build-id or use the release's Update.html" % meta["product"])
    for k in EXTRA:
        v = getattr(args, k.replace("-", "_"), None)
        if v:
            meta[k] = v
    meta.setdefault("name", meta.get("profile") or meta["product"])
    _, checked = P.prepare(meta, io.BytesIO(data))
    meta["loader_identity"] = checked["loader_identity"]
    return meta


def write(out, data, meta, slug=None):
    slug = slug or slugify(meta["name"] + "-" + meta.get("release_version", meta["sha256"][:8]))
    d = os.path.join(out, "firmware", slug)
    os.makedirs(d, exist_ok=True)
    meta["file"] = meta["product"] + ".fwsc"
    with open(os.path.join(d, meta["file"]), "wb") as f:
        f.write(data)
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1, sort_keys=True)
        f.write("\n")
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="SD card root (or a staging folder)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--html", help="release Update.html with an embedded FM1_PACKAGE")
    src.add_argument("--fwsc", help="a .fwsc package")
    src.add_argument("--catalog", nargs="*", metavar="ID", help="FM-1 Firmware Hub catalogue ids (none: all)")
    ap.add_argument("--meta", help="JSON file with metadata fields for --fwsc")
    ap.add_argument("--build-id", help="64-hex build identity for --fwsc")
    ap.add_argument("--slug", help="folder name under firmware/")
    ap.add_argument("--no-stock", action="store_true", help="with --html, skip the bundled V15")
    for k in EXTRA:
        ap.add_argument("--" + k.replace("_", "-"))
    args = ap.parse_args(argv)

    slugs = {}
    if args.catalog is not None:
        items = []
        for data, meta, cid in from_catalog(args.catalog):
            items.append((data, meta))
            slugs[id(meta)] = cid
    elif args.html:
        items = from_html(args.html)
        if args.no_stock:
            items = [i for i in items if i[1].get("kind") != "stock"]
    else:
        data = open(args.fwsc, "rb").read()
        meta = json.load(open(args.meta)) if args.meta else {}
        if args.build_id:
            meta["build_id"] = args.build_id.lower()
        items = [(data, meta)]

    failed = 0
    for data, meta in items:
        slug = slugs.get(id(meta)) or (args.slug if len(items) == 1 else None)
        try:
            meta = build(data, meta, args)
        except P.FM1Error as e:
            print("rejected %s: %s" % (meta.get("product") or meta.get("name"), e), file=sys.stderr)
            failed += 1
            continue
        if meta["kind"] == "stock" and not meta.get("source_url"):
            meta["source_url"] = "https://github.com/m-vave/fm1_open"
            meta.setdefault("license", "Apache-2.0")
        d = write(args.out, data, meta, slug)
        print("%-20s %-12s %7d bytes  loader %s  -> %s" % (
            meta["product"], meta["kind"], meta["bytes"], meta["loader_identity"], d))
    if failed:
        sys.exit("%d package(s) rejected" % failed)


if __name__ == "__main__":
    main()
