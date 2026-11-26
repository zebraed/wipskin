"""
Unit tests for wipskin.xml_sniff (no Maya/Qt required).

xml_sniff holds the Maya-free root-tag sniffing behind the weight-file list
predicates, so it can be exercised outside a Maya session even though
xml_skin/deformer (which delegate to it) cannot. The (mtime, size) memoizing
it used to carry now lives in core.file_cache (see test_file_cache.py).

Split out of the former tests/test_xml_probe.py alongside xml_probe.py's own
split into xml_sniff.py (this) and xml_accel.py (see test_xml_accel.py).
"""

import os
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.formats import xml_sniff

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SKIN_FIXTURE = os.path.join(FIXTURES, "sample_skin.xml")
DEFORMER_FIXTURE = os.path.join(FIXTURES, "sample_deformer.xml")


class TestReadRootTag(unittest.TestCase):

    def setUp(self):
        xml_sniff.clear_cache()
        xml_sniff.reset_sniff_count()

    def test_skin_and_deformer_root_tags(self):
        self.assertEqual(xml_sniff.read_root_tag(SKIN_FIXTURE), "deformerWeight")
        self.assertEqual(
            xml_sniff.read_root_tag(DEFORMER_FIXTURE), "customDeformerWeight"
        )

    def test_missing_file_returns_none(self):
        self.assertIsNone(xml_sniff.read_root_tag(os.path.join(FIXTURES, "nope.xml")))

    def test_non_xml_returns_none(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False
        ) as handle:
            handle.write("not xml at all {")
            path = handle.name
        try:
            self.assertIsNone(xml_sniff.read_root_tag(path))
        finally:
            os.remove(path)

    def test_has_root_tag(self):
        self.assertTrue(xml_sniff.has_root_tag(SKIN_FIXTURE, "deformerWeight"))
        self.assertFalse(xml_sniff.has_root_tag(SKIN_FIXTURE, "customDeformerWeight"))
        self.assertFalse(xml_sniff.has_root_tag(DEFORMER_FIXTURE, "deformerWeight"))
        self.assertTrue(
            xml_sniff.has_root_tag(DEFORMER_FIXTURE, "customDeformerWeight")
        )


class TestClassifyCache(unittest.TestCase):

    def setUp(self):
        xml_sniff.clear_cache()
        xml_sniff.reset_sniff_count()

    def test_warm_lookups_do_not_reparse(self):
        # Cold: one parse. Warm: zero further parses (acceptance criterion b).
        self.assertEqual(xml_sniff.classify(SKIN_FIXTURE), "deformerWeight")
        self.assertEqual(xml_sniff.sniff_count(), 1)
        for _ in range(50):
            xml_sniff.classify(SKIN_FIXTURE)
        self.assertEqual(xml_sniff.sniff_count(), 1)

    def test_changed_file_is_resniffed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "w.xml")
            with open(path, "w") as handle:
                handle.write('<deformerWeight/>')
            self.assertEqual(xml_sniff.classify(path), "deformerWeight")
            self.assertEqual(xml_sniff.sniff_count(), 1)
            # Rewrite with a different tag and size; force a distinct mtime.
            time.sleep(0.01)
            with open(path, "w") as handle:
                handle.write('<customDeformerWeight></customDeformerWeight>')
            os.utime(path, None)
            self.assertEqual(xml_sniff.classify(path), "customDeformerWeight")
            self.assertEqual(xml_sniff.sniff_count(), 2)


if __name__ == "__main__":
    unittest.main()
