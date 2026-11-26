import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import metadata
from wipskin.core import weight_files
from wipskin.plugins.mgear import weights as mgear_skin
from wipskin.plugins.mgear.format import MgearSkinWeightFormat
from wipskin.formats.skin.xml import wip as wip_skin

# The XML weight reader pulls maya.cmds at import time.
try:
    from wipskin.formats.skin.xml import weights as xml_skin
except ImportError:
    xml_skin = None


JSKIN = {
    "objName": "body",
    "skinClsName": "skinCluster1",
    "weights": {
        "joint_1": {"0": 1.0},
        "joint_10": {"0": 0.5, "1": 0.5},
        "ns:joint_2": {"1": 1.0},
    },
}

SKIN_XML = """<?xml version="1.0" encoding="utf-8"?>
<deformerWeight>
  <weights deformer="skinCluster1" source="joint_1" shape="bodyShape" layer="0" defaultValue="0.000" size="2" max="2">
    <point index="0" value="1.000"/>
  </weights>
  <weights deformer="skinCluster1" source="joint_10" shape="bodyShape" layer="0" defaultValue="0.000" size="2" max="2">
    <point index="1" value="1.000"/>
  </weights>
  <bindPreMatrices>
    <bindPreMatrix deformer="skinCluster1" source="joint_1" matrix="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>
    <bindPreMatrix deformer="skinCluster1" source="joint_10" matrix="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>
  </bindPreMatrices>
</deformerWeight>
"""


class TempDirCase(unittest.TestCase):

    def setUp(self):
        self.dir_name = tempfile.mkdtemp(prefix="wipskin_rename_")
        self.addCleanup(shutil.rmtree, self.dir_name, True)

    def write(self, name, text):
        path = os.path.join(self.dir_name, name)
        with open(path, "w", encoding="utf-8") as file_id:
            file_id.write(text)
        return path


class TestFormatCapability(unittest.TestCase):
    """Only text formats whose names are stored as text qualify."""

    def test_mgear_allows_jskin_only(self):
        fmt = MgearSkinWeightFormat()
        self.assertTrue(fmt.can_rename_influence("body.jSkin"))
        self.assertTrue(fmt.can_rename_influence("body.0003.jskin"))
        self.assertFalse(fmt.can_rename_influence("body.gSkin"))
        self.assertFalse(fmt.can_rename_influence("rig.jSkinPack"))
        self.assertFalse(fmt.can_rename_influence("rig.gSkinPack"))


class TestMgearRename(TempDirCase):

    def write_jskin(self, name="body.0001.jSkin"):
        return self.write(name, json.dumps(JSKIN, indent=4, sort_keys=True))

    def read_weights(self, path):
        with open(path, encoding="utf-8") as file_id:
            return json.load(file_id)["weights"]

    def test_renames_only_the_exact_name(self):
        path = self.write_jskin()
        self.assertEqual(mgear_skin.rename_influence(path, "joint_1", "spine_1"), 1)

        weights = self.read_weights(path)
        self.assertIn("spine_1", weights)
        self.assertNotIn("joint_1", weights)
        self.assertIn("joint_10", weights)

    def test_weights_survive_the_rename(self):
        path = self.write_jskin()
        mgear_skin.rename_influence(path, "joint_10", "spine_10")
        self.assertEqual(
            self.read_weights(path)["spine_10"], {"0": 0.5, "1": 0.5}
        )

    def test_namespace_is_part_of_the_name(self):
        path = self.write_jskin()
        self.assertEqual(mgear_skin.rename_influence(path, "joint_2", "x"), 0)
        self.assertEqual(
            mgear_skin.rename_influence(path, "ns:joint_2", "ns2:joint_2"), 1
        )
        self.assertIn("ns2:joint_2", self.read_weights(path))

    def test_absent_influence_reports_no_change(self):
        path = self.write_jskin()
        self.assertEqual(mgear_skin.rename_influence(path, "nope", "x"), 0)

    def test_collision_is_refused(self):
        path = self.write_jskin()
        with self.assertRaises(ValueError):
            mgear_skin.rename_influence(path, "joint_1", "joint_10")
        self.assertIn("joint_1", self.read_weights(path))

    def test_list_influence_names_keeps_namespaces(self):
        path = self.write_jskin()
        self.assertEqual(
            mgear_skin.list_influence_names(path),
            ["joint_1", "joint_10", "ns:joint_2"],
        )


class TestMgearInfluenceListing(TempDirCase):
    """What the viewer lists has to be what the rename can find."""

    def write_sidecar(self, path, influences):
        with open(metadata.sidecar_path(path), "w", encoding="utf-8") as file_id:
            json.dump({"influences": influences}, file_id)

    def test_jskin_names_come_from_the_file_not_the_sidecar(self):
        # mGear strips the namespace on export while the sidecar keeps the
        # scene name, so only the file's keys can be renamed.
        path = self.write("body.0001.jSkin", json.dumps(JSKIN))
        self.write_sidecar(path, ["rig:joint_1", "rig:joint_10"])
        self.assertEqual(
            mgear_skin.list_influences(path),
            ["joint_1", "joint_10", "ns:joint_2"],
        )

    def test_gskin_falls_back_to_the_sidecar(self):
        path = self.write("body.0001.gSkin", "not json")
        self.write_sidecar(path, ["joint_1"])
        self.assertEqual(mgear_skin.list_influences(path), ["joint_1"])

    def test_unreadable_jskin_falls_back_to_the_sidecar(self):
        path = self.write("body.0001.jSkin", "{ broken")
        self.write_sidecar(path, ["joint_1"])
        self.assertEqual(mgear_skin.list_influences(path), ["joint_1"])

    def test_no_source_at_all_lists_nothing(self):
        path = self.write("body.0001.gSkin", "binary")
        self.assertEqual(mgear_skin.list_influences(path), [])


class TestXmlRename(TempDirCase):

    def setUp(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        super().setUp()

    def read(self, path):
        with open(path, encoding="utf-8") as file_id:
            return file_id.read()

    def test_weights_and_bind_pre_matrix_both_follow(self):
        path = self.write("body.0001.xml", SKIN_XML)
        self.assertEqual(xml_skin.rename_influence(path, "joint_1", "spine_1"), 2)

        text = self.read(path)
        self.assertIn('source="spine_1"', text)
        self.assertIn('source="joint_10"', text)
        self.assertNotIn('source="joint_1"', text)

    def test_absent_influence_reports_no_change(self):
        path = self.write("body.0001.xml", SKIN_XML)
        self.assertEqual(xml_skin.rename_influence(path, "nope", "x"), 0)

    def test_collision_is_refused(self):
        path = self.write("body.0001.xml", SKIN_XML)
        with self.assertRaises(ValueError):
            xml_skin.rename_influence(path, "joint_1", "joint_10")


class TestWipPackRename(TempDirCase):
    """A pack rename rewrites the manifest and every member it lists."""

    def setUp(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        super().setUp()
        self.pack_dir = os.path.join(self.dir_name, wip_skin.wip_dir_name("body"))
        os.makedirs(self.pack_dir)
        base_member = wip_skin.base_member_filename("body", 1)
        group_member = wip_skin.group_member_filename("body", "arm", 1)
        for member in (base_member, group_member):
            self.write(os.path.join(os.path.basename(self.pack_dir), member), SKIN_XML)

        manifest = wip_skin.build_manifest(
            shape="bodyShape",
            skin_cluster="skinCluster1",
            vertex_count=2,
            base_name="body",
            version=1,
            base_member=base_member,
            base_influences=["joint_1", "joint_10"],
            base_source=wip_skin.BASE_SOURCE_SCENE,
            base_source_file="",
            groups=[{
                "id": wip_skin.new_group_id(),
                "name": "arm",
                "member": group_member,
                "influences": ["joint_1"],
            }],
        )
        self.display_name = (
            f"{os.path.basename(self.pack_dir)}/"
            f"{wip_skin.manifest_filename('body', 1)}"
        )
        wip_skin.write_manifest(
            os.path.join(self.dir_name, self.display_name), manifest
        )

    def rename(self, old_name, new_name):
        return wip_skin.rename_influence(
            self.dir_name, self.display_name, old_name, new_name
        )

    def test_new_version_carries_the_renamed_influence(self):
        new_display = self.rename("joint_1", "spine_1")
        self.assertTrue(new_display.endswith("body.0002.wip"))

        manifest = wip_skin.read_manifest(
            os.path.join(self.dir_name, new_display)
        )
        self.assertEqual(
            manifest["base"]["influences"], ["spine_1", "joint_10"]
        )
        self.assertEqual(manifest["groups"][0]["influences"], ["spine_1"])
        for entry in [manifest["base"]] + manifest["groups"]:
            path = os.path.join(self.pack_dir, entry["member"])
            with open(path, encoding="utf-8") as file_id:
                self.assertIn('source="spine_1"', file_id.read())

    def test_source_version_is_left_intact(self):
        self.rename("joint_1", "spine_1")
        manifest = wip_skin.read_manifest(
            os.path.join(self.dir_name, self.display_name)
        )
        self.assertEqual(
            manifest["base"]["influences"], ["joint_1", "joint_10"]
        )

    def test_absent_influence_is_refused(self):
        with self.assertRaises(ValueError):
            self.rename("nope", "x")

    def test_collision_is_refused(self):
        with self.assertRaises(ValueError):
            self.rename("joint_1", "joint_10")


class TestCopyToNextVersion(TempDirCase):
    """The selected file is never edited; the rename lands on a new version."""

    def test_copy_lands_on_the_next_version(self):
        self.write("body.0001.xml", SKIN_XML)
        new_name = weight_files.copy_to_next_version(self.dir_name, "body.0001.xml")
        self.assertEqual(new_name, "body.0002.xml")
        self.assertTrue(os.path.isfile(os.path.join(self.dir_name, "body.0001.xml")))

    def test_copy_keeps_the_subdirectory_prefix(self):
        os.makedirs(os.path.join(self.dir_name, "body_wip"))
        self.write(os.path.join("body_wip", "body.0001.xml"), SKIN_XML)
        new_name = weight_files.copy_to_next_version(
            self.dir_name, "body_wip/body.0001.xml"
        )
        self.assertEqual(new_name, "body_wip/body.0002.xml")

    def test_missing_source_raises(self):
        with self.assertRaises(OSError):
            weight_files.copy_to_next_version(self.dir_name, "nope.xml")


if __name__ == "__main__":
    unittest.main()
