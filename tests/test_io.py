"""
Unit tests for wipskin.io (no Maya required).
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import io as tio


class TestNormPath(unittest.TestCase):

    def test_forward_slashes(self):
        self.assertEqual(tio.norm_path(r"D:\weights\arm.xml"), "D:/weights/arm.xml")

    def test_empty(self):
        self.assertEqual(tio.norm_path(""), "")


class TestParseVersionedFilename(unittest.TestCase):

    def test_versioned(self):
        base, version, ext = tio.parse_versioned_filename("body.0003.dat")
        self.assertEqual(base, "body")
        self.assertEqual(version, 3)
        self.assertEqual(ext, "dat")

    def test_unversioned(self):
        base, version, ext = tio.parse_versioned_filename("arm.xml")
        self.assertEqual(base, "arm")
        self.assertEqual(version, 0)
        self.assertEqual(ext, "xml")

    def test_mgear_extension(self):
        base, version, ext = tio.parse_versioned_filename("geo.0001.jSkin")
        self.assertEqual(base, "geo")
        self.assertEqual(version, 1)
        self.assertEqual(ext, "jSkin")


class TestFilterFilesForView(unittest.TestCase):

    def test_latest(self):
        names = ["a.0001.dat", "a.0002.dat", "b.dat"]
        result = tio.filter_files_for_view(names, mode="latest")
        self.assertEqual(result, ["a.0002.dat", "b.dat"])


class TestResolveExportPath(unittest.TestCase):

    def test_auto_version(self):
        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "body.0001.dat"), "w").close()
            open(os.path.join(directory, "body.0002.dat"), "w").close()
            path = tio.resolve_export_path(directory, "body", "dat", auto_version=True)
            self.assertTrue(path.endswith("body.0003.dat"))

    def test_no_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = tio.resolve_export_path(directory, "arm", "xml", auto_version=False)
            self.assertTrue(path.endswith("arm.xml"))


class TestExportBaseNameHelpers(unittest.TestCase):

    def test_list_base_names_for_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in (
                "zebra.xml",
                "Alpha.0001.xml",
                "Alpha.0002.xml",
                "skip.dat",
            ):
                open(os.path.join(directory, name), "w").close()
            names = tio.list_base_names_for_extension(directory, "xml")
            self.assertEqual(names, ["Alpha", "zebra"])

    def test_list_base_names_strips_multi_export_index(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in (
                "body_0001.xml",
                "body_0002.0001.xml",
                "body_0003.0002.xml",
                "solo.xml",
            ):
                open(os.path.join(directory, name), "w").close()
            names = tio.list_base_names_for_extension(directory, "xml")
            self.assertEqual(names, ["body", "solo"])

    def test_multi_export_index_helpers(self):
        self.assertEqual(tio.apply_multi_export_index("body", 1), "body_0001")
        self.assertEqual(tio.apply_multi_export_index("body", 12), "body_0012")
        self.assertEqual(tio.strip_multi_export_index("body_0001"), "body")
        self.assertEqual(tio.strip_multi_export_index("body_0001_extra"), "body_0001_extra")
        self.assertEqual(tio.strip_multi_export_index("body"), "body")

    def test_sanitize_export_base_name(self):
        self.assertEqual(
            tio.sanitize_export_base_name("  body.xml  ", strip_extensions=("xml",)),
            "body",
        )
        self.assertEqual(
            tio.sanitize_export_base_name("path/to/rig.XML", strip_extensions=("xml",)),
            "rig",
        )
        self.assertEqual(tio.sanitize_export_base_name("   "), "")

    def test_find_latest_versioned_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("body.0001.jSkin", "body.0004.jSkin", "body.jSkin"):
                open(os.path.join(directory, name), "w").close()
            latest = tio.find_latest_versioned_filename(directory, "body", "jSkin")
            self.assertEqual(latest, "body.0004.jSkin")

    def test_resolve_pack_member_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("arm.0001.jSkin", "arm.0002.jSkin"):
                open(os.path.join(directory, name), "w").close()
            self.assertEqual(
                tio.resolve_pack_member_filename(
                    directory, "arm.0001.jSkin", prefer_latest=True
                ),
                "arm.0002.jSkin",
            )
            self.assertEqual(
                tio.resolve_pack_member_filename(
                    directory, "arm.0001.jSkin", prefer_latest=False
                ),
                "arm.0001.jSkin",
            )


class TestConvertWeightFiles(unittest.TestCase):

    def test_content_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            src_path = os.path.join(directory, "mesh_L.xml")
            with open(src_path, "w", encoding="utf-8", newline="\n") as file_id:
                file_id.write("<weights source=\"jnt_L\" />\n")
            created = tio.convert_weight_files(
                directory,
                ["mesh_L.xml"],
                "_L",
                "_R",
                replace_content=True,
            )
            self.assertEqual(len(created), 1)
            dst_name = created[0][1]
            dst_path = os.path.join(directory, dst_name)
            with open(dst_path, encoding="utf-8") as file_id:
                data = file_id.read()
            self.assertIn("jnt_R", data)
            self.assertNotIn("jnt_L", data)


if __name__ == "__main__":
    unittest.main()
