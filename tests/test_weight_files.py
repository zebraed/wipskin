"""
Unit tests for wipskin.core.weight_files (no Maya/Qt required).
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import metadata
from wipskin.core import weight_files
from wipskin.formats.skin.xml import wip as wip_skin


class TestScanWeightFiles(unittest.TestCase):

    def test_missing_directory_returns_empty(self):
        self.assertEqual(weight_files.scan_weight_files("", ["dat"]), [])
        self.assertEqual(
            weight_files.scan_weight_files("/no/such/dir", ["dat"]), []
        )

    def test_filters_by_extension_and_skips_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("arm.dat", "leg.xml", ".arm.dat.info"):
                open(os.path.join(directory, name), "w").close()
            names = weight_files.scan_weight_files(directory, ["dat"])
            self.assertEqual(names, ["arm.dat"])

    def test_predicate_filters_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("keep.xml", "skip.xml"):
                open(os.path.join(directory, name), "w").close()
            names = weight_files.scan_weight_files(
                directory, ["xml"],
                predicate=lambda path: "keep" in path,
            )
            self.assertEqual(names, ["keep.xml"])

    def test_sorted_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("c.dat", "a.dat", "b.dat"):
                open(os.path.join(directory, name), "w").close()
            names = weight_files.scan_weight_files(directory, ["dat"])
            self.assertEqual(names, ["a.dat", "b.dat", "c.dat"])


class TestScanSubdirWeightFiles(unittest.TestCase):

    def test_missing_directory_returns_empty(self):
        self.assertEqual(
            weight_files.scan_subdir_weight_files("/no/such/dir", "_wip", ["wip"]),
            [],
        )

    def test_finds_files_one_level_into_matching_subdirs(self):
        with tempfile.TemporaryDirectory() as directory:
            wip_dir = os.path.join(directory, "body_wip")
            os.makedirs(wip_dir)
            open(os.path.join(wip_dir, "body.0001.wip"), "w").close()
            open(os.path.join(wip_dir, "body_base.0001.xml"), "w").close()
            names = weight_files.scan_subdir_weight_files(directory, "_wip", ["wip"])
            self.assertEqual(names, ["body_wip/body.0001.wip"])

    def test_ignores_subdirs_not_matching_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            other_dir = os.path.join(directory, "backup")
            os.makedirs(other_dir)
            open(os.path.join(other_dir, "body.0001.wip"), "w").close()
            names = weight_files.scan_subdir_weight_files(directory, "_wip", ["wip"])
            self.assertEqual(names, [])

    def test_skips_sidecar_files(self):
        with tempfile.TemporaryDirectory() as directory:
            wip_dir = os.path.join(directory, "body_wip")
            os.makedirs(wip_dir)
            open(os.path.join(wip_dir, "body.0001.wip"), "w").close()
            open(os.path.join(wip_dir, ".body.0001.wip.info"), "w").close()
            names = weight_files.scan_subdir_weight_files(directory, "_wip", ["wip"])
            self.assertEqual(names, ["body_wip/body.0001.wip"])

    def test_does_not_descend_more_than_one_level(self):
        with tempfile.TemporaryDirectory() as directory:
            nested = os.path.join(directory, "body_wip", "deeper")
            os.makedirs(nested)
            open(os.path.join(nested, "body.0001.wip"), "w").close()
            names = weight_files.scan_subdir_weight_files(directory, "_wip", ["wip"])
            self.assertEqual(names, [])


class TestUniquePath(unittest.TestCase):

    def test_no_collision_returns_same_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "arm.dat")
            self.assertEqual(
                weight_files.unique_path(path),
                weight_files.unique_path(path),
            )
            self.assertTrue(weight_files.unique_path(path).endswith("arm.dat"))

    def test_collision_appends_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            existing = os.path.join(directory, "arm.dat")
            open(existing, "w").close()
            result = weight_files.unique_path(existing)
            self.assertTrue(os.path.basename(result).startswith("armCopy"))
            self.assertFalse(os.path.exists(result))

    def test_repeated_collision_appends_copy_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "arm.dat"), "w").close()
            open(os.path.join(directory, "armCopy.dat"), "w").close()
            result = weight_files.unique_path(
                os.path.join(directory, "arm.dat")
            )
            self.assertEqual(os.path.basename(result), "armCopyCopy.dat")


class TestDeleteWeightFiles(unittest.TestCase):

    def test_deletes_file_and_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.xml")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(weight_path, "xml")
            self.assertTrue(os.path.isfile(metadata.sidecar_path(weight_path)))

            weight_files.delete_weight_files(directory, ["arm.xml"])
            self.assertFalse(os.path.isfile(weight_path))
            self.assertFalse(os.path.isfile(metadata.sidecar_path(weight_path)))

    def test_missing_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_files.delete_weight_files(directory, ["missing.xml"])


class TestRenameWeightFile(unittest.TestCase):

    def test_rename_moves_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            src = os.path.join(directory, "arm.xml")
            open(src, "w").close()
            metadata.write_export_sidecar(src, "xml", comment="hi")

            new_name, had_sidecar = weight_files.rename_weight_file(
                directory, "arm.xml", "shoulder.xml"
            )
            self.assertEqual(new_name, "shoulder.xml")
            self.assertTrue(had_sidecar)
            dst = os.path.join(directory, "shoulder.xml")
            self.assertTrue(os.path.isfile(dst))
            self.assertTrue(os.path.isfile(metadata.sidecar_path(dst)))
            self.assertFalse(os.path.isfile(src))

    def test_rename_without_extension_appends_default(self):
        with tempfile.TemporaryDirectory() as directory:
            src = os.path.join(directory, "arm.xml")
            open(src, "w").close()
            new_name, _ = weight_files.rename_weight_file(
                directory, "arm.xml", "shoulder", default_ext="xml"
            )
            self.assertEqual(new_name, "shoulder.xml")

    def test_rename_collision_appends_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "arm.xml"), "w").close()
            open(os.path.join(directory, "shoulder.xml"), "w").close()
            new_name, _ = weight_files.rename_weight_file(
                directory, "arm.xml", "shoulder.xml"
            )
            self.assertEqual(new_name, "shoulderCopy.xml")


class TestArchiveWeightFiles(unittest.TestCase):

    def test_moves_file_and_sidecar_into_backup_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.xml")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(weight_path, "xml")

            archived = weight_files.archive_weight_files(directory, ["arm.xml"])

            self.assertEqual(archived, ["arm.xml"])
            self.assertFalse(os.path.isfile(weight_path))
            self.assertFalse(os.path.isfile(metadata.sidecar_path(weight_path)))
            backup_path = os.path.join(
                directory, weight_files.BACKUP_DIR_NAME, "arm.xml"
            )
            self.assertTrue(os.path.isfile(backup_path))
            self.assertTrue(os.path.isfile(metadata.sidecar_path(backup_path)))

    def test_missing_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            archived = weight_files.archive_weight_files(directory, ["missing.xml"])
            self.assertEqual(archived, [])

    def test_collision_with_existing_archive_appends_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            backup_dir = os.path.join(directory, weight_files.BACKUP_DIR_NAME)
            os.makedirs(backup_dir)
            open(os.path.join(backup_dir, "arm.xml"), "w").close()
            open(os.path.join(directory, "arm.xml"), "w").close()

            archived = weight_files.archive_weight_files(directory, ["arm.xml"])

            self.assertEqual(archived, ["armCopy.xml"])
            self.assertFalse(os.path.isfile(os.path.join(directory, "arm.xml")))

    def test_backup_dir_is_reused_across_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("arm.xml", "leg.xml"):
                open(os.path.join(directory, name), "w").close()
            weight_files.archive_weight_files(directory, ["arm.xml"])
            weight_files.archive_weight_files(directory, ["leg.xml"])

            backup_dir = os.path.join(directory, weight_files.BACKUP_DIR_NAME)
            self.assertTrue(os.path.isfile(os.path.join(backup_dir, "arm.xml")))
            self.assertTrue(os.path.isfile(os.path.join(backup_dir, "leg.xml")))


class TestGetBackupDir(unittest.TestCase):

    def test_points_at_the_backup_subfolder(self):
        self.assertEqual(
            os.path.basename(weight_files.get_backup_dir("/tmp/weights")),
            weight_files.BACKUP_DIR_NAME,
        )


class TestUnarchiveWeightFiles(unittest.TestCase):
    """Unarchive is the inverse of Archive, including sidecars and subdirs."""

    def test_round_trip_restores_file_and_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            weight_path = os.path.join(directory, "arm.xml")
            open(weight_path, "w").close()
            metadata.write_export_sidecar(weight_path, "xml")
            weight_files.archive_weight_files(directory, ["arm.xml"])

            restored = weight_files.unarchive_weight_files(
                directory, ["arm.xml"]
            )

            self.assertEqual(restored, ["arm.xml"])
            self.assertTrue(os.path.isfile(weight_path))
            self.assertTrue(
                os.path.isfile(metadata.sidecar_path(weight_path))
            )
            backup_path = os.path.join(
                directory, weight_files.BACKUP_DIR_NAME, "arm.xml"
            )
            self.assertFalse(os.path.isfile(backup_path))
            self.assertFalse(
                os.path.isfile(metadata.sidecar_path(backup_path))
            )

    def test_missing_archive_entry_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                weight_files.unarchive_weight_files(directory, ["missing.xml"]),
                [],
            )

    def test_collision_with_a_live_file_appends_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "arm.xml"), "w").close()
            weight_files.archive_weight_files(directory, ["arm.xml"])
            open(os.path.join(directory, "arm.xml"), "w").close()

            restored = weight_files.unarchive_weight_files(
                directory, ["arm.xml"]
            )

            self.assertEqual(restored, ["armCopy.xml"])
            self.assertTrue(
                os.path.isfile(os.path.join(directory, "arm.xml")),
                "the live file must not be overwritten",
            )
            self.assertTrue(
                os.path.isfile(os.path.join(directory, "armCopy.xml"))
            )

    def test_restores_a_subdirectory_entry_and_recreates_the_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            wip_dir = os.path.join(directory, "body_wip")
            os.makedirs(wip_dir)
            member = "body_wip/body.0001.wip"
            open(os.path.join(directory, member), "w").close()
            weight_files.archive_weight_files(directory, [member])
            self.assertFalse(os.path.isdir(wip_dir), "emptied subdir removed")

            restored = weight_files.unarchive_weight_files(directory, [member])

            self.assertEqual(restored, [member])
            self.assertTrue(os.path.isfile(os.path.join(directory, member)))
            backup_subdir = os.path.join(
                directory, weight_files.BACKUP_DIR_NAME, "body_wip"
            )
            self.assertFalse(
                os.path.isdir(backup_subdir),
                "the emptied archive subdir is cleaned up",
            )

    def test_restores_several_files_at_once(self):
        with tempfile.TemporaryDirectory() as directory:
            names = ["arm.xml", "leg.xml", "spine.xml"]
            for name in names:
                open(os.path.join(directory, name), "w").close()
            weight_files.archive_weight_files(directory, names)

            restored = weight_files.unarchive_weight_files(directory, names)

            self.assertEqual(sorted(restored), sorted(names))
            for name in names:
                self.assertTrue(os.path.isfile(os.path.join(directory, name)))


class TestWipPackArchiveAndDelete(unittest.TestCase):
    """A WIP pack entry is "<base>_wip/name.wip", so Archive/Delete have to
    cope with a subdirectory in the name (they used to fail or orphan members).
    """

    def _make_pack(self, directory, base="body", version=1):
        import json

        wip_dir = os.path.join(directory, f"{base}_wip")
        os.makedirs(wip_dir, exist_ok=True)
        base_member = f"{base}_base.{version:04d}.xml"
        group_member = f"{base}_arm_layer.{version:04d}.xml"
        for member in (base_member, group_member):
            with open(os.path.join(wip_dir, member), "w") as file_id:
                file_id.write("<deformerWeight/>")
        manifest = {
            "schema_version": 1,
            "version": version,
            "base_name": base,
            "shape": "bodyShape",
            "skin_cluster": "skinCluster1",
            "vertex_count": 3,
            "base": {
                "member": base_member,
                "influences": ["j1"],
                "source": "scene",
                "source_file": "",
            },
            "groups": [{
                "id": "g1",
                "name": "arm",
                "member": group_member,
                "influences": ["j2"],
                "ratio": 100.0,
            }],
        }
        manifest_name = f"{base}.{version:04d}.wip"
        with open(os.path.join(wip_dir, manifest_name), "w") as file_id:
            json.dump(manifest, file_id)
        return f"{base}_wip/{manifest_name}", wip_dir

    def test_archive_keeps_the_pack_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            entry, wip_dir = self._make_pack(directory)
            names = wip_skin.list_pack_version_names(directory, entry)
            weight_files.archive_weight_files(directory, names)

            self.assertFalse(os.path.isdir(wip_dir))
            archived = os.path.join(
                directory, weight_files.BACKUP_DIR_NAME, "body_wip"
            )
            self.assertEqual(
                sorted(os.listdir(archived)),
                ["body.0001.wip", "body_arm_layer.0001.xml",
                 "body_base.0001.xml"],
            )

    def test_delete_removes_members_and_the_emptied_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            entry, wip_dir = self._make_pack(directory)
            names = wip_skin.list_pack_version_names(directory, entry)
            weight_files.delete_weight_files(directory, names)

            self.assertFalse(os.path.isdir(wip_dir))

    def test_delete_keeps_other_versions_in_the_same_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            first, wip_dir = self._make_pack(directory, version=1)
            self._make_pack(directory, version=2)
            names = wip_skin.list_pack_version_names(directory, first)
            weight_files.delete_weight_files(directory, names)

            self.assertTrue(os.path.isdir(wip_dir))
            self.assertEqual(
                sorted(os.listdir(wip_dir)),
                ["body.0002.wip", "body_arm_layer.0002.xml",
                 "body_base.0002.xml"],
            )

    def test_list_pack_version_names_puts_the_manifest_last(self):
        with tempfile.TemporaryDirectory() as directory:
            entry, _ = self._make_pack(directory)
            names = wip_skin.list_pack_version_names(directory, entry)
            self.assertEqual(names[-1], entry)
            self.assertEqual(len(names), 3)

    def test_list_pack_version_names_is_empty_for_a_missing_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                wip_skin.list_pack_version_names(directory, "gone_wip/gone.wip"),
                [],
            )

    def test_plain_files_keep_the_flat_archive_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.xml")
            with open(path, "w") as file_id:
                file_id.write("<deformerWeight/>")
            weight_files.archive_weight_files(directory, ["body.xml"])

            archived = os.path.join(directory, weight_files.BACKUP_DIR_NAME)
            self.assertEqual(os.listdir(archived), ["body.xml"])


if __name__ == "__main__":
    unittest.main()
