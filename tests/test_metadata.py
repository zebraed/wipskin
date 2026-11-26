"""
Unit tests for wipskin.metadata (no Maya required).
"""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import metadata
from wipskin.core.path_utils import norm_path


class TestSidecarPath(unittest.TestCase):

    def test_sidecar_path(self):
        weight_path = os.path.join("/tmp/weights", "arm.0001.xml")
        expected = os.path.join("/tmp/weights", ".arm.0001.xml.info")
        self.assertEqual(metadata.sidecar_path(weight_path), norm_path(expected))

    def test_is_sidecar_filename(self):
        self.assertTrue(metadata.is_sidecar_filename(".arm.0001.xml.info"))
        self.assertFalse(metadata.is_sidecar_filename("arm.0001.xml"))
        self.assertFalse(metadata.is_sidecar_filename(".hidden"))


class TestSidecarIO(unittest.TestCase):

    def test_write_and_read(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.0001.xml")
            open(weight_path, "w").close()
            sidecar_path = metadata.write_export_sidecar(
                weight_path, "xml", comment="test comment"
            )
            self.assertTrue(os.path.isfile(sidecar_path))
            data = metadata.read_sidecar(weight_path)
            self.assertEqual(data["schema_version"], metadata.SCHEMA_VERSION)
            self.assertEqual(data["target"], "arm.0001.xml")
            self.assertEqual(data["comment"], "test comment")
            self.assertEqual(data["format"], "xml")
            self.assertEqual(data["tool"], "WipSkin")

    def test_reexport_preserves_created_and_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "body.dat")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(
                weight_path, "custom", comment="keep me"
            )
            first = metadata.read_sidecar(weight_path)
            created = first["created"]
            created_by = first["created_by"]
            metadata.write_export_sidecar(weight_path, "custom")
            second = metadata.read_sidecar(weight_path)
            self.assertEqual(second["created"], created)
            self.assertEqual(second["created_by"], created_by)
            self.assertEqual(second["comment"], "keep me")
            self.assertIn("exported", second)

    def test_update_sidecar_merges_and_preserves(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.0001.xml")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(
                weight_path, "xml", comment="keep"
            )
            metadata.update_sidecar(weight_path, {"viewer_stats": {"n": 3}})
            data = metadata.read_sidecar(weight_path)
            self.assertEqual(data["viewer_stats"], {"n": 3})
            self.assertEqual(data["comment"], "keep")
            self.assertEqual(data["format"], "xml")

    def test_update_sidecar_noop_without_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.0001.xml")
            open(weight_path, "w").close()
            result = metadata.update_sidecar(weight_path, {"viewer_stats": {"n": 1}})
            self.assertIsNone(result)
            self.assertIsNone(metadata.read_sidecar(weight_path))

    def test_new_version_export_uses_explicit_empty_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            v1_path = os.path.join(directory, "body.0001.xml")
            v2_path = os.path.join(directory, "body.0002.xml")
            open(v1_path, "w").close()
            open(v2_path, "w").close()
            metadata.write_export_sidecar(
                v1_path, "xml", comment="v1 note"
            )
            metadata.write_export_sidecar(
                v2_path, "xml", comment=""
            )
            data = metadata.read_sidecar(v2_path)
            self.assertEqual(data["comment"], "")
            self.assertNotEqual(
                metadata.read_sidecar(v1_path)["comment"],
                data["comment"],
            )

    def test_rename_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            src_weight = os.path.join(directory, "arm.xml")
            dst_weight = os.path.join(directory, "arm_R.xml")
            open(src_weight, "w").close()
            metadata.write_export_sidecar(src_weight, "xml")
            metadata.rename_sidecar(src_weight, dst_weight)
            open(dst_weight, "w").close()
            self.assertFalse(os.path.isfile(metadata.sidecar_path(src_weight)))
            data = metadata.read_sidecar(dst_weight)
            self.assertEqual(data["target"], "arm_R.xml")

    def test_rename_weight_with_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            src_weight = os.path.join(directory, "arm.0001.xml")
            dst_weight = os.path.join(directory, "arm.0002.xml")
            open(src_weight, "w").close()
            metadata.write_export_sidecar(
                src_weight, "xml", comment="keep"
            )
            had_sidecar = metadata.rename_weight_with_sidecar(src_weight, dst_weight)
            self.assertTrue(had_sidecar)
            self.assertTrue(os.path.isfile(dst_weight))
            self.assertFalse(os.path.isfile(src_weight))
            self.assertFalse(os.path.isfile(metadata.sidecar_path(src_weight)))
            self.assertTrue(os.path.isfile(metadata.sidecar_path(dst_weight)))
            data = metadata.read_sidecar(dst_weight)
            self.assertEqual(data["target"], "arm.0002.xml")
            self.assertEqual(data["comment"], "keep")

    def test_rename_weight_without_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            src_weight = os.path.join(directory, "arm.xml")
            dst_weight = os.path.join(directory, "arm_R.xml")
            open(src_weight, "w").close()
            had_sidecar = metadata.rename_weight_with_sidecar(src_weight, dst_weight)
            self.assertFalse(had_sidecar)
            self.assertFalse(os.path.isfile(metadata.sidecar_path(dst_weight)))

    def test_copy_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            src_weight = os.path.join(directory, "mesh_L.xml")
            dst_weight = os.path.join(directory, "mesh_R.xml")
            open(src_weight, "w").close()
            metadata.write_export_sidecar(src_weight, "xml", comment="copied")
            open(dst_weight, "w").close()
            metadata.copy_sidecar(src_weight, dst_weight)
            data = metadata.read_sidecar(dst_weight)
            self.assertEqual(data["target"], "mesh_R.xml")
            self.assertEqual(data["comment"], "copied")

    def test_delete_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.xml")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(weight_path, "xml")
            self.assertTrue(metadata.delete_sidecar(weight_path))
            self.assertIsNone(metadata.read_sidecar(weight_path))


class TestFormatViewerLines(unittest.TestCase):

    def test_format_viewer_lines_empty(self):
        self.assertEqual(metadata.format_viewer_lines(None), [])

    def test_format_viewer_lines_with_comment(self):
        lines = metadata.format_audit_lines({
            "comment": "hidden",
            "created": "2026-06-15T10:30:00+09:00",
            "created_by": "user",
            "exported": "2026-06-16T00:26:55+09:00",
            "exported_by": "user",
            "tool": "WipSkin",
            "tool_version": "0.1.0",
            "mgear_version": "5.3.4",
            "format": "xml",
        }, extra_fields=(("mGear version", "mgear_version"),))
        text = "\n".join(lines)
        self.assertIn("Created by: user", text)
        self.assertIn("Created:", text)
        self.assertIn("Tool version: 0.1.0", text)
        self.assertIn("mGear version: 5.3.4", text)
        self.assertNotIn("Comment:", text)
        self.assertNotIn("Tool: WipSkin", text)
        self.assertNotIn("Format:", text)
        self.assertNotIn("Sidecar", text)

    def test_extra_fields_follow_tool_version(self):
        lines = metadata.format_audit_lines(
            {"tool_version": "1.0", "source_scene": "a.ma", "x_ver": "2"},
            extra_fields=(("X version", "x_ver"),),
        )
        self.assertEqual(
            lines,
            ["Tool version: 1.0", "X version: 2", "Source scene: a.ma"],
        )

    def test_format_specific_keys_need_extra_fields(self):
        lines = metadata.format_audit_lines({"mgear_version": "5.3.4"})
        self.assertEqual(lines, [])

    def test_join_viewer_sections(self):
        text = metadata.join_viewer_sections(
            ["Mesh: geo", "Created by: user"],
            ["Influences: 3"],
        )
        self.assertEqual(
            text,
            "Mesh: geo\nCreated by: user\n\nInfluences: 3",
        )


class TestCommentSidecar(unittest.TestCase):

    def test_write_comment_sidecar_creates_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.xml")
            open(weight_path, "w").close()
            metadata.write_comment_sidecar(
                weight_path, "manual note", format_name="xml"
            )
            data = metadata.read_sidecar(weight_path)
            self.assertEqual(data["comment"], "manual note")
            self.assertEqual(data["format"], "xml")
            self.assertEqual(data["target"], "arm.xml")

    def test_write_comment_sidecar_needs_format_for_a_new_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.unknown")
            open(weight_path, "w").close()
            with self.assertRaises(ValueError):
                metadata.write_comment_sidecar(weight_path, "note")
            self.assertIsNone(metadata.read_sidecar(weight_path))

    def test_write_comment_sidecar_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "body.dat")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(
                weight_path, "custom", comment="original"
            )
            first = metadata.read_sidecar(weight_path)
            metadata.write_comment_sidecar(weight_path, "replaced")
            second = metadata.read_sidecar(weight_path)
            self.assertEqual(second["comment"], "replaced")
            self.assertEqual(second["created"], first["created"])
            self.assertEqual(second["created_by"], first["created_by"])

    def test_write_comment_sidecar_keeps_the_existing_format(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "body.dat")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(weight_path, "custom")
            metadata.write_comment_sidecar(
                weight_path, "note", format_name="other"
            )
            self.assertEqual(
                metadata.read_sidecar(weight_path)["format"], "custom"
            )


class TestSidecarHidden(unittest.TestCase):

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_sidecar_is_hidden_on_windows(self):
        import ctypes

        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.xml")
            open(weight_path, "w").close()
            sidecar_file = metadata.write_export_sidecar(
                weight_path, "xml"
            )
            attrs = ctypes.windll.kernel32.GetFileAttributesW(sidecar_file)
            self.assertNotEqual(attrs, -1)
            self.assertTrue(attrs & 0x02)


if __name__ == "__main__":
    unittest.main()
