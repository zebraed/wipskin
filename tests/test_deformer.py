"""Tests for wipskin.deformer (no Maya required for parse / detect)."""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

try:
    from wipskin.formats.deformer import xml as deformer
except ImportError:
    deformer = None


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_DEFORMER = os.path.join(FIXTURE_DIR, "sample_deformer.xml")
SAMPLE_DEFORMER_LEGACY = os.path.join(FIXTURE_DIR, "sample_deformer_legacy.xml")
SAMPLE_DEFORMER_MULTI = os.path.join(FIXTURE_DIR, "sample_deformer_multi_shape.xml")
SAMPLE_SKIN = os.path.join(FIXTURE_DIR, "sample_skin.xml")


class TestDeformerIo(unittest.TestCase):
    def setUp(self):
        if deformer is None:
            self.skipTest("wipskin.deformer not importable")

    def test_is_deformer_weight_file_true(self):
        self.assertTrue(deformer.is_deformer_weight_file(SAMPLE_DEFORMER))
        self.assertEqual(deformer.ROOT_TAG, "customDeformerWeight")

    def test_is_deformer_weight_file_accepts_legacy_root_tag(self):
        self.assertTrue(deformer.is_deformer_weight_file(SAMPLE_DEFORMER_LEGACY))

    def test_is_deformer_weight_file_false_for_skin_xml(self):
        self.assertFalse(deformer.is_deformer_weight_file(SAMPLE_SKIN))

    def test_parse_file_info(self):
        info = deformer.parse_file_info(SAMPLE_DEFORMER)
        self.assertEqual(info["deformer"], "cluster1")
        self.assertEqual(info["shape"], "pSphereShape1")
        self.assertEqual(info["vertex_count"], 100)
        self.assertEqual(info["influences"], ["baseLayer"])

    def test_parse_file_info_legacy(self):
        info = deformer.parse_file_info(SAMPLE_DEFORMER_LEGACY)
        self.assertEqual(info["deformer"], "cluster1")
        self.assertEqual(info["shape"], "pSphereShape1")
        self.assertEqual(info["influences"], ["baseLayer"])

    def test_parse_file_info_multi_shape(self):
        info = deformer.parse_file_info(SAMPLE_DEFORMER_MULTI)
        self.assertEqual(info["deformer"], "cluster1")
        self.assertEqual(info["shape"], "pSphereShape1")
        self.assertEqual(
            [entry["name"] for entry in info["shapes"]],
            ["pSphereShape1", "pCubeShape1"],
        )
        self.assertEqual(info["influences"], ["baseLayer", "baseLayer"])

    def test_node_short_name(self):
        self.assertEqual(
            deformer._node_short_name("|grp|pSphere1|pSphereShape1"),
            "pSphereShape1",
        )


class TestResolveShapeExportFilename(unittest.TestCase):
    def setUp(self):
        if deformer is None:
            self.skipTest("wipskin.deformer not importable")

    def test_auto_version_strips_existing_version_from_filename(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "body_deltaMush.0002.xml"), "w").close()
            result = deformer._resolve_shape_export_filename(
                "deltaMush1",
                "body",
                directory,
                "body_deltaMush.0002.xml",
                auto_name=False,
                auto_version=True,
            )
            self.assertEqual(result, "body_deltaMush.0003.xml")

    def test_auto_name_uses_shape_and_deformer_name(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            result = deformer._resolve_shape_export_filename(
                "deltaMush1",
                "|grp|body|bodyShape",
                directory,
                None,
                auto_name=True,
                auto_version=False,
            )
            self.assertEqual(result, "bodyShape_deltaMush1.xml")


if __name__ == "__main__":
    unittest.main()
