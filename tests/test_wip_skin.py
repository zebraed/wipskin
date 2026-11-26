import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

# wip_skin.py keeps Maya (and formats.xml_skin, which needs Maya to import)
# as lazy, function-local imports, so the module itself -- and its manifest
# schema / naming / validation logic -- import and run fine without Maya.
from wipskin.formats.skin.xml import wip as wip_skin

try:
    import maya  # noqa: F401
    MAYA_AVAILABLE = True
except ImportError:
    MAYA_AVAILABLE = False

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_skin.xml")


class TestNaming(unittest.TestCase):

    def test_wip_dir_name(self):
        self.assertEqual(wip_skin.wip_dir_name("body"), "body_wip")

    def test_wip_dir_path(self):
        self.assertEqual(
            wip_skin.wip_dir_path("C:/proj/weights", "body"),
            "C:/proj/weights/body_wip",
        )

    def test_base_member_filename_unversioned(self):
        self.assertEqual(wip_skin.base_member_filename("body"), "body_base.xml")

    def test_base_member_filename_versioned(self):
        self.assertEqual(
            wip_skin.base_member_filename("body", 3), "body_base.0003.xml"
        )

    def test_group_member_filename_appends_layer_suffix(self):
        self.assertEqual(
            wip_skin.group_member_filename("body", "Face"),
            "body_Face_layer.xml",
        )

    def test_group_member_filename_does_not_duplicate_layer_word(self):
        self.assertEqual(
            wip_skin.group_member_filename("body", "Face Layer"),
            "body_Face_layer.xml",
        )
        self.assertEqual(
            wip_skin.group_member_filename("body", "twist_layer"),
            "body_twist_layer.xml",
        )

    def test_group_member_filename_versioned(self):
        self.assertEqual(
            wip_skin.group_member_filename("body", "Face", 7),
            "body_Face_layer.0007.xml",
        )

    def test_group_member_filename_rejects_empty_token(self):
        with self.assertRaises(ValueError):
            wip_skin.group_member_filename("body", "   ")

    def test_manifest_filename(self):
        self.assertEqual(wip_skin.manifest_filename("body"), "body.wip")
        self.assertEqual(wip_skin.manifest_filename("body", 2), "body.0002.wip")

    def test_sanitize_group_token_strips_illegal_chars_and_collapses(self):
        self.assertEqual(wip_skin.sanitize_group_token("Face Layer"), "Face")
        self.assertEqual(wip_skin.sanitize_group_token("  Face -- Layer!! "), "Face")
        self.assertEqual(wip_skin.sanitize_group_token(""), "")

    def test_is_valid_group_display_name(self):
        self.assertTrue(wip_skin.is_valid_group_display_name("Face"))
        self.assertFalse(wip_skin.is_valid_group_display_name("   "))

    def test_new_group_id_unique(self):
        ids = {wip_skin.new_group_id() for _ in range(50)}
        self.assertEqual(len(ids), 50)


class TestVersionResolution(unittest.TestCase):

    def test_next_export_version_no_auto_version(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                wip_skin.next_export_version(directory, "body", False), 0
            )

    def test_next_export_version_scans_wip_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            wip_dir = wip_skin.wip_dir_path(directory, "body")
            os.makedirs(wip_dir)
            for name in ("body.0001.wip", "body.0003.wip", "body.0002.wip"):
                open(os.path.join(wip_dir, name), "w").close()
            self.assertEqual(
                wip_skin.next_export_version(directory, "body", True), 4
            )

    def test_next_export_version_empty_dir_starts_at_one(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                wip_skin.next_export_version(directory, "body", True), 1
            )

    def test_find_latest_manifest_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            wip_dir = wip_skin.wip_dir_path(directory, "body")
            os.makedirs(wip_dir)
            for name in ("body.0001.wip", "body.0002.wip"):
                open(os.path.join(wip_dir, name), "w").close()
            self.assertEqual(
                wip_skin.find_latest_manifest_filename(directory, "body"),
                "body.0002.wip",
            )

    def test_find_latest_manifest_filename_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                wip_skin.find_latest_manifest_filename(directory, "body"), ""
            )


class TestManifestBuildReadWrite(unittest.TestCase):

    def _build(self):
        return wip_skin.build_manifest(
            shape="body_geoShape",
            skin_cluster="body_skinCluster",
            vertex_count=3,
            base_name="body",
            version=1,
            base_member="body_base.0001.xml",
            base_influences=["joint_1"],
            base_source=wip_skin.BASE_SOURCE_SCENE,
            base_source_file="",
            groups=[
                {
                    "id": "abc123",
                    "name": "Face",
                    "member": "body_Face_layer.0001.xml",
                    "influences": ["joint_2"],
                    "ratio": 100.0,
                },
            ],
        )

    def test_build_manifest_shape(self):
        manifest = self._build()
        self.assertEqual(manifest["schema_version"], wip_skin.SCHEMA_VERSION)
        self.assertEqual(manifest["base"]["compose"], wip_skin.COMPOSE_REPLACE)
        self.assertEqual(manifest["groups"][0]["compose"], wip_skin.COMPOSE_RAW_ADD)
        self.assertEqual(manifest["groups"][0]["ratio"], 100.0)

    def test_build_manifest_rejects_bad_base_source(self):
        with self.assertRaises(ValueError):
            wip_skin.build_manifest(
                shape="s", skin_cluster="skc", vertex_count=1, base_name="b",
                version=0, base_member="b_base.xml", base_influences=["j"],
                base_source="bogus", base_source_file="", groups=[],
            )

    def test_write_then_read_manifest_round_trip(self):
        manifest = self._build()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.0001.wip")
            wip_skin.write_manifest(path, manifest)
            loaded = wip_skin.read_manifest(path)
            self.assertEqual(loaded, manifest)

    def test_read_manifest_rejects_invalid_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bad.wip")
            with open(path, "w", encoding="utf-8") as file_id:
                json.dump({"schema_version": 999}, file_id)
            with self.assertRaises(ValueError):
                wip_skin.read_manifest(path)

    def test_is_wip_manifest_file_true_for_valid_manifest(self):
        manifest = self._build()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.0001.wip")
            wip_skin.write_manifest(path, manifest)
            self.assertTrue(wip_skin.is_wip_manifest_file(path))

    def test_is_wip_manifest_file_false_for_non_wip_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.xml")
            open(path, "w").close()
            self.assertFalse(wip_skin.is_wip_manifest_file(path))

    def test_is_wip_manifest_file_false_for_garbage_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.wip")
            with open(path, "w", encoding="utf-8") as file_id:
                file_id.write("not json")
            self.assertFalse(wip_skin.is_wip_manifest_file(path))

    def test_write_manifest_leaves_no_temp_file_on_disk(self):
        manifest = self._build()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nested_wip", "body.0001.wip")
            wip_skin.write_manifest(path, manifest)
            self.assertTrue(os.path.isfile(path))
            self.assertFalse(os.path.isfile(path + ".tegtmp"))


def _write_test_pack(directory, base_name, version, group_name="Face"):
    """
    Write a minimal-but-real WIP pack (manifest + empty member XML stand-ins)
    directly to disk, for rename_wip_pack tests -- no Maya needed since only
    the file layout/manifest content matters here, not real weight data.
    """
    wip_dir = wip_skin.wip_dir_path(directory, base_name)
    os.makedirs(wip_dir, exist_ok=True)
    base_member = wip_skin.base_member_filename(base_name, version)
    group_member = wip_skin.group_member_filename(base_name, group_name, version)
    open(os.path.join(wip_dir, base_member), "w").close()
    open(os.path.join(wip_dir, group_member), "w").close()
    manifest = wip_skin.build_manifest(
        shape="body_geoShape", skin_cluster="body_skinCluster", vertex_count=3,
        base_name=base_name, version=version, base_member=base_member,
        base_influences=["joint_1"], base_source=wip_skin.BASE_SOURCE_SCENE,
        base_source_file="",
        groups=[{
            "id": "g1", "name": group_name, "member": group_member,
            "influences": ["joint_2"], "ratio": 100.0,
        }],
    )
    manifest_path = os.path.join(
        wip_dir, wip_skin.manifest_filename(base_name, version)
    )
    wip_skin.write_manifest(manifest_path, manifest)
    return manifest_path


class TestRenameWipPack(unittest.TestCase):

    def test_renames_directory_manifest_and_members(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_test_pack(directory, "body", 1)

            display_name = wip_skin.rename_wip_pack(directory, "body", "torso")

            self.assertEqual(display_name, "torso_wip/torso.0001.wip")
            self.assertFalse(os.path.isdir(os.path.join(directory, "body_wip")))
            new_wip_dir = os.path.join(directory, "torso_wip")
            self.assertTrue(os.path.isdir(new_wip_dir))
            self.assertTrue(os.path.isfile(os.path.join(new_wip_dir, "torso.0001.wip")))
            self.assertTrue(
                os.path.isfile(os.path.join(new_wip_dir, "torso_base.0001.xml"))
            )
            self.assertTrue(
                os.path.isfile(os.path.join(new_wip_dir, "torso_Face_layer.0001.xml"))
            )

    def test_manifest_content_member_fields_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_test_pack(directory, "body", 1)
            wip_skin.rename_wip_pack(directory, "body", "torso")

            manifest_path = os.path.join(
                directory, "torso_wip", "torso.0001.wip"
            )
            manifest = wip_skin.read_manifest(manifest_path)
            self.assertEqual(manifest["base_name"], "torso")
            self.assertEqual(manifest["base"]["member"], "torso_base.0001.xml")
            self.assertEqual(manifest["groups"][0]["member"], "torso_Face_layer.0001.xml")

    def test_sidecars_move_with_their_files(self):
        from wipskin.core import metadata

        with tempfile.TemporaryDirectory() as directory:
            manifest_path = _write_test_pack(directory, "body", 1)
            wip_dir = os.path.dirname(manifest_path)
            metadata.write_export_sidecar(
                os.path.join(wip_dir, "body_base.0001.xml"), wip_skin.MEMBER_METADATA_FORMAT
            )
            metadata.write_export_sidecar(manifest_path, wip_skin.METADATA_FORMAT)

            wip_skin.rename_wip_pack(directory, "body", "torso")

            new_wip_dir = os.path.join(directory, "torso_wip")
            self.assertTrue(os.path.isfile(
                metadata.sidecar_path(os.path.join(new_wip_dir, "torso_base.0001.xml"))
            ))
            self.assertTrue(os.path.isfile(
                metadata.sidecar_path(os.path.join(new_wip_dir, "torso.0001.wip"))
            ))

    def test_renames_all_versions_in_the_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_test_pack(directory, "body", 1)
            _write_test_pack(directory, "body", 2)

            display_name = wip_skin.rename_wip_pack(directory, "body", "torso")

            self.assertEqual(display_name, "torso_wip/torso.0002.wip")
            new_wip_dir = os.path.join(directory, "torso_wip")
            self.assertTrue(os.path.isfile(os.path.join(new_wip_dir, "torso.0001.wip")))
            self.assertTrue(os.path.isfile(os.path.join(new_wip_dir, "torso.0002.wip")))
            self.assertTrue(
                os.path.isfile(os.path.join(new_wip_dir, "torso_base.0001.xml"))
            )
            self.assertTrue(
                os.path.isfile(os.path.join(new_wip_dir, "torso_base.0002.xml"))
            )

    def test_empty_new_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_test_pack(directory, "body", 1)
            with self.assertRaises(ValueError):
                wip_skin.rename_wip_pack(directory, "body", "   ")

    def test_unchanged_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_test_pack(directory, "body", 1)
            with self.assertRaises(ValueError):
                wip_skin.rename_wip_pack(directory, "body", "body")

    def test_missing_pack_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                wip_skin.rename_wip_pack(directory, "body", "torso")

    def test_existing_target_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_test_pack(directory, "body", 1)
            os.makedirs(os.path.join(directory, "torso_wip"))
            with self.assertRaises(ValueError):
                wip_skin.rename_wip_pack(directory, "body", "torso")

    def test_missing_member_file_raises_oserror(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = _write_test_pack(directory, "body", 1)
            os.remove(os.path.join(os.path.dirname(manifest_path), "body_base.0001.xml"))
            with self.assertRaises(OSError):
                wip_skin.rename_wip_pack(directory, "body", "torso")


class TestFormatManifestViewerText(unittest.TestCase):

    def test_includes_shape_groups_and_ratio(self):
        manifest = wip_skin.build_manifest(
            shape="body_geoShape", skin_cluster="body_skinCluster",
            vertex_count=3, base_name="body", version=1,
            base_member="body_base.0001.xml", base_influences=["joint_1"],
            base_source=wip_skin.BASE_SOURCE_SCENE, base_source_file="",
            groups=[{
                "id": "g1", "name": "Face", "member": "body_Face_layer.0001.xml",
                "influences": ["joint_2"], "ratio": 50.0,
            }],
        )
        text = wip_skin.format_manifest_viewer_text(manifest)
        self.assertIn("Shape: body_geoShape", text)
        self.assertIn("Groups: 1", text)
        self.assertIn("Face: 1 influence(s), default ratio 50%", text)


class TestValidateGroupAssignment(unittest.TestCase):

    def test_valid_full_assignment(self):
        errors = wip_skin.validate_group_assignment(
            base_influences=["joint_1"],
            groups=[("Face", ["joint_2"])],
            scene_influences=["joint_1", "joint_2"],
        )
        self.assertEqual(errors, [])

    def test_empty_base_is_rejected(self):
        errors = wip_skin.validate_group_assignment(
            base_influences=[],
            groups=[("Face", ["joint_1", "joint_2"])],
            scene_influences=["joint_1", "joint_2"],
        )
        self.assertTrue(any("Base group is empty" in err for err in errors))

    def test_unassigned_influence_is_rejected(self):
        errors = wip_skin.validate_group_assignment(
            base_influences=["joint_1"],
            groups=[],
            scene_influences=["joint_1", "joint_2"],
        )
        self.assertTrue(any("Unassigned" in err and "joint_2" in err for err in errors))

    def test_duplicate_assignment_is_rejected(self):
        errors = wip_skin.validate_group_assignment(
            base_influences=["joint_1"],
            groups=[("Face", ["joint_1", "joint_2"])],
            scene_influences=["joint_1", "joint_2"],
        )
        self.assertTrue(any("multiple groups" in err for err in errors))

    def test_duplicate_group_names_rejected(self):
        errors = wip_skin.validate_group_assignment(
            base_influences=["joint_1"],
            groups=[("Face", ["joint_2"]), ("face", ["joint_3"])],
            scene_influences=["joint_1", "joint_2", "joint_3"],
        )
        self.assertTrue(any("Duplicate group name" in err for err in errors))

    def test_empty_group_name_rejected(self):
        errors = wip_skin.validate_group_assignment(
            base_influences=["joint_1"],
            groups=[("  ", ["joint_2"])],
            scene_influences=["joint_1", "joint_2"],
        )
        self.assertTrue(any("empty" in err for err in errors))

    def test_base_locked_ignores_base_influences_for_assignment(self):
        # Existing-XML base: base_influences come from the XML and are not
        # re-validated against scene_influences here (diff_existing_base_influences
        # handles that separately); only the remaining scene influences must
        # be assigned to exactly one Layer group.
        errors = wip_skin.validate_group_assignment(
            base_influences=["joint_1"],
            groups=[("Twist", ["joint_2"])],
            scene_influences=["joint_1", "joint_2"],
            base_locked=True,
        )
        self.assertEqual(errors, [])

    def test_base_locked_still_rejects_duplicate_with_base(self):
        # joint_1 belongs to the (locked) Base XML; assigning it to a Layer
        # group too must still be rejected as a duplicate assignment.
        errors = wip_skin.validate_group_assignment(
            base_influences=["joint_1"],
            groups=[("Twist", ["joint_1"])],
            scene_influences=["joint_1"],
            base_locked=True,
        )
        self.assertTrue(any("multiple groups" in err for err in errors))


class TestDiffExistingBaseInfluences(unittest.TestCase):

    def test_no_difference(self):
        missing, new = wip_skin.diff_existing_base_influences(
            ["joint_1"], ["joint_1", "joint_2"]
        )
        self.assertEqual(missing, [])
        self.assertEqual(new, ["joint_2"])

    def test_missing_in_scene(self):
        missing, new = wip_skin.diff_existing_base_influences(
            ["joint_1", "joint_removed"], ["joint_1"]
        )
        self.assertEqual(missing, ["joint_removed"])
        self.assertEqual(new, [])


class TestWriteFilteredSkinXml(unittest.TestCase):

    def test_keeps_only_selected_influence(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = os.path.join(directory, "body_base.xml")
            kept = wip_skin.write_filtered_skin_xml(FIXTURE, dest, ["joint_1"])
            self.assertEqual(kept, 1)
            root = ET.parse(dest).getroot()
            sources = [el.attrib.get("source") for el in root.findall("weights")]
            self.assertEqual(sources, ["joint_1"])

    def test_keeps_multiple_selected_influences(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = os.path.join(directory, "body_all.xml")
            kept = wip_skin.write_filtered_skin_xml(
                FIXTURE, dest, ["joint_1", "joint_2"]
            )
            self.assertEqual(kept, 2)

    def test_keeps_none_when_no_match(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = os.path.join(directory, "body_none.xml")
            kept = wip_skin.write_filtered_skin_xml(FIXTURE, dest, ["joint_missing"])
            self.assertEqual(kept, 0)
            root = ET.parse(dest).getroot()
            self.assertEqual(root.findall("weights"), [])

    def test_preserves_non_weights_elements(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = os.path.join(directory, "body_face.xml")
            wip_skin.write_filtered_skin_xml(FIXTURE, dest, ["joint_2"])
            root = ET.parse(dest).getroot()
            self.assertIsNotNone(root.find("shape"))
            self.assertIsNotNone(root.find("deformer"))

    def test_creates_missing_destination_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = os.path.join(directory, "nested", "body_base.xml")
            wip_skin.write_filtered_skin_xml(FIXTURE, dest, ["joint_1"])
            self.assertTrue(os.path.isfile(dest))

    def _fixture_with_bind_pre_matrices(self, directory):
        """Copy FIXTURE and add a bindPreMatrices block covering both joints.

        Mirrors xml_skin's <bindPreMatrices><bindPreMatrix source=.../></...>
        shape without importing xml_skin (Maya-only), matching how
        write_filtered_skin_xml itself stays Maya-free.
        """
        source = os.path.join(directory, "source.xml")
        tree = ET.parse(FIXTURE)
        root = tree.getroot()
        container = ET.SubElement(root, "bindPreMatrices")
        for name in ("joint_1", "joint_2"):
            ET.SubElement(container, "bindPreMatrix", {
                "source": name,
                "value": " ".join(str(float(i)) for i in range(16)),
            })
        tree.write(source, encoding="utf-8", xml_declaration=True)
        return source

    def test_filters_bind_pre_matrices_to_kept_influences(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._fixture_with_bind_pre_matrices(directory)
            dest = os.path.join(directory, "body_base.xml")
            wip_skin.write_filtered_skin_xml(source, dest, ["joint_1"])
            root = ET.parse(dest).getroot()
            container = root.find("bindPreMatrices")
            self.assertIsNotNone(container)
            sources = [el.attrib.get("source") for el in container.findall("bindPreMatrix")]
            self.assertEqual(sources, ["joint_1"])

    def test_drops_bind_pre_matrices_block_when_no_influence_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._fixture_with_bind_pre_matrices(directory)
            dest = os.path.join(directory, "body_none.xml")
            wip_skin.write_filtered_skin_xml(source, dest, ["joint_missing"])
            root = ET.parse(dest).getroot()
            self.assertIsNone(root.find("bindPreMatrices"))

    def test_no_bind_pre_matrices_block_when_source_has_none(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = os.path.join(directory, "body_base.xml")
            wip_skin.write_filtered_skin_xml(FIXTURE, dest, ["joint_1"])
            root = ET.parse(dest).getroot()
            self.assertIsNone(root.find("bindPreMatrices"))


@unittest.skipUnless(MAYA_AVAILABLE, "Maya not available")
class TestComposeRequiresMaya(unittest.TestCase):
    def test_placeholder(self):
        self.skipTest("Compose/export integration is verified in Maya only.")


if __name__ == "__main__":
    unittest.main()
