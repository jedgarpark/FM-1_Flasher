# SPDX-License-Identifier: GPL-3.0-only
"""Tests for the UI's data layer (fm1ui.catalog) and touch gestures.
Plain CPython: python3 -m unittest discover tests"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "lib"), os.path.join(ROOT, "tools")]

from fm1ui import catalog as C  # noqa: E402

INDEX = (
    "updated\t2026-10-28 03:02 UTC\n"
    "stock-v15\tM-VAVE V15\tV15\tofficial\t0\tFM-1_015\n"
    "hortator\tHortator\t0.25.0\tdrums\t1\tFM-1_900\n"
    "sloop\tSLOOP\t2.8.3\tgroove,dev\t0\tFM-1_900\n"
    "zp12\tzp12\t2.5\tdrums\t0\tFM-1_975\n"
    "broken line\n"
)


class Catalog(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.index = os.path.join(self.dir.name, "index.txt")
        with open(self.index, "w") as f:
            f.write(INDEX)
        self.state_path = os.path.join(self.dir.name, "state.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_load_index(self):
        updated, entries = C.load_index(self.index)
        self.assertEqual(updated, "2026-10-28 03:02 UTC")
        self.assertEqual([e.slug for e in entries], ["stock-v15", "hortator", "sloop", "zp12"])
        self.assertTrue(entries[1].beta)
        self.assertEqual(entries[2].kind, "groove")

    def test_dates_and_labels(self):
        self.assertEqual(C.nice_date("2026-10-28 03:02 UTC"), "28 Oct 2026")
        self.assertEqual(C.nice_date("soon"), "soon")
        self.assertEqual(C.version_label("2.8"), "v2.8")
        self.assertEqual(C.version_label("V15"), "V15")
        _, entries = C.load_index(self.index)
        self.assertEqual(C.display_name(entries[0]), "M-VAVE V15")
        self.assertEqual(C.display_name(entries[2]), "SLOOP 2.8.3")

    def test_paging(self):
        items = list(range(17))
        self.assertEqual(C.page_count(17, 8), 3)
        self.assertEqual(C.page_count(0, 8), 1)
        self.assertEqual(C.page_slice(items, 2, 8), [16])

    def test_favorites_persist(self):
        s = C.State(self.state_path)
        self.assertTrue(s.toggle_favorite("zp12"))
        self.assertTrue(s.toggle_favorite("sloop"))
        self.assertFalse(s.toggle_favorite("zp12"))
        self.assertEqual(C.State(self.state_path).favorites, {"sloop"})

    def test_unwritable_state_is_not_fatal(self):
        s = C.State(os.path.join(self.dir.name, "missing", "state.json"))
        self.assertTrue(s.toggle_favorite("zp12"))
        self.assertFalse(s.save())

    def test_index_lookups(self):
        index = C.Index(self.index)
        self.assertEqual(len(index), 4)
        self.assertEqual(index.find("sloop").version, "2.8.3")
        self.assertIsNone(index.find("slo"))
        self.assertEqual(index.select({"zp12", "sloop", "gone"}), [2, 3])
        self.assertEqual(index.with_product("FM-1_900"), ["hortator", "sloop"])

    def test_installed_badge(self):
        entries = C.Index(self.index)
        s = C.State(self.state_path)
        self.assertIsNone(s.installed_slug(None, entries))
        # unique identity
        self.assertEqual(s.installed_slug("FM-1_975", entries), "zp12")
        self.assertEqual(s.installed_slug("FM-1_015", entries), "stock-v15")
        # shared identity: unknown until we installed it ourselves
        self.assertIsNone(s.installed_slug("FM-1_900", entries))
        s.record_install("hortator", "FM-1_900")
        self.assertEqual(C.State(self.state_path).installed_slug("FM-1_900", entries), "hortator")
        # a different firmware is on it now
        self.assertEqual(s.installed_slug("FM-1_975", entries), "zp12")
        with open(self.state_path) as f:
            self.assertIsNone(json.load(f)["pending"])

    def test_wrap_and_ellipsize(self):
        width = len
        self.assertEqual(C.wrap("one two three four", width, 9), ["one two", "three", "four"])
        self.assertEqual(C.ellipsize("Bubba Machine", width, 8), "Bubba...")
        self.assertEqual(C.ellipsize("short", width, 8), "short")


class Gestures(unittest.TestCase):
    def setUp(self):
        try:
            from fm1ui.app import Gestures
        except ImportError as e:  # needs displayio (Blinka) on CPython
            self.skipTest("no displayio: %s" % e)
        self.g = Gestures()

    def feed(self, *points):
        for p in points:
            self.g.sample(p)
        self.g.sample(None)
        return self.g.event()

    def test_tap(self):
        self.assertEqual(self.feed((100, 50), (104, 52)), ("tap", 100, 50))

    def test_swipe(self):
        self.assertEqual(self.feed((300, 150), (250, 152), (200, 160)), ("swipe", -100))

    def test_drag_is_ignored(self):
        self.assertIsNone(self.feed((100, 50), (140, 90)))


if __name__ == "__main__":
    unittest.main()
