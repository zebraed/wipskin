"""Tests for mGear skin path helpers (no Maya required)."""

import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import metadata
from wipskin.plugins.mgear import weights as mgear_skin


class TestNormalizePaths(unittest.TestCase):

    def test_normalize_skin_path_json(self):
        self.assertEqual(
            mgear_skin._normalize_skin_path("/tmp/body.skin", True),
            "/tmp/body.jSkin",
        )
        self.assertEqual(
            mgear_skin._normalize_skin_path("/tmp/body.jSkin", True),
            "/tmp/body.jSkin",
        )

    def test_normalize_skin_path_binary(self):
        self.assertEqual(
            mgear_skin._normalize_skin_path("/tmp/body.skin", False),
            "/tmp/body.gSkin",
        )

    def test_normalize_pack_path_always_gskinpack(self):
        self.assertEqual(
            mgear_skin._normalize_pack_path("/tmp/rig.jSkinPack"),
            "/tmp/rig.gSkinPack",
        )
        self.assertEqual(
            mgear_skin._normalize_pack_path("/tmp/rig.gSkinPack"),
            "/tmp/rig.gSkinPack",
        )

    def test_is_pack_file(self):
        self.assertTrue(mgear_skin.is_pack_file("/tmp/rig.gSkinPack"))
        self.assertTrue(mgear_skin.is_pack_file("/tmp/rig.jSkinPack"))
        self.assertFalse(mgear_skin.is_pack_file("/tmp/body.jSkin"))


class TestPackBaseNameHelpers(unittest.TestCase):

    def test_list_gskin_pack_base_names(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            for name in ("zebra.gSkinPack", "Alpha.gSkinPack", "skip.jSkin"):
                with open(os.path.join(tmp_dir, name), "w", encoding="utf-8"):
                    pass
            names = mgear_skin.list_gskin_pack_base_names(tmp_dir)
            self.assertEqual(names, ["Alpha", "zebra"])

    def test_list_gskin_pack_base_names_missing_dir(self):
        self.assertEqual(
            mgear_skin.list_gskin_pack_base_names("/no/such/dir"),
            [],
        )

    def test_sanitize_pack_base_name(self):
        self.assertEqual(
            mgear_skin.sanitize_pack_base_name("  character_skin.gSkinPack  "),
            "character_skin",
        )
        self.assertEqual(
            mgear_skin.sanitize_pack_base_name("path/to/rig.jSkinPack"),
            "rig",
        )
        self.assertEqual(
            mgear_skin.sanitize_pack_base_name('bad<>:"|?*name'),
            "badname",
        )
        self.assertEqual(mgear_skin.sanitize_pack_base_name("   "), "")


class TestListExportTransforms(unittest.TestCase):

    def setUp(self):
        self._saved_maya = sys.modules.get("maya")
        maya_module = types.ModuleType("maya")
        maya_module.cmds = mock.Mock()
        sys.modules["maya"] = maya_module
        self.cmds = maya_module.cmds

    def tearDown(self):
        if self._saved_maya is None:
            sys.modules.pop("maya", None)
        else:
            sys.modules["maya"] = self._saved_maya

    def test_mesh_shape_to_parent_transform(self):
        self.cmds.listRelatives.return_value = ["|grp|head"]
        self.cmds.nodeType.return_value = "mesh"
        result = mgear_skin.list_export_transforms(["|grp|head|headShape"])
        self.assertEqual(result, ["|grp|head"])
        self.cmds.listRelatives.assert_called_once_with(
            "|grp|head|headShape", parent=True, fullPath=True
        )

    def test_transform_passthrough(self):
        self.cmds.nodeType.return_value = "transform"
        result = mgear_skin.list_export_transforms(["|grp|head"])
        self.assertEqual(result, ["|grp|head"])

    def test_nurbs_curve_shape_to_parent_transform(self):
        self.cmds.listRelatives.return_value = ["|curveGrp|curve1"]
        self.cmds.nodeType.return_value = "nurbsCurve"
        result = mgear_skin.list_export_transforms(["|curveGrp|curve1|curveShape1"])
        self.assertEqual(result, ["|curveGrp|curve1"])
        self.cmds.listRelatives.assert_called_once_with(
            "|curveGrp|curve1|curveShape1", parent=True, fullPath=True
        )

    def test_nurbs_surface_and_lattice_shape_to_parent_transform(self):
        for shape_type in ("nurbsSurface", "lattice"):
            self.cmds.listRelatives.return_value = ["|grp|geo"]
            self.cmds.nodeType.return_value = shape_type
            result = mgear_skin.list_export_transforms(["|grp|geo|geoShape"])
            self.assertEqual(result, ["|grp|geo"])

    def test_deduplicates_same_transform(self):
        self.cmds.listRelatives.return_value = ["|grp|head"]
        self.cmds.nodeType.return_value = "mesh"
        shapes = ["|grp|head|headShape", "|grp|head|headShape2"]
        result = mgear_skin.list_export_transforms(shapes)
        self.assertEqual(result, ["|grp|head"])


class TestParseFileInfo(unittest.TestCase):

    def test_parse_pack_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = os.path.join(tmp_dir, "rig.gSkinPack")
            with open(pack_path, "w", encoding="utf-8") as file_id:
                file_id.write(
                    '{"packFiles": ["a.jSkin", "b.jSkin"], '
                    '"mgearVersion": "5.3.4"}'
                )
            info = mgear_skin.parse_file_info(pack_path)
            self.assertEqual(info["type"], "pack")
            self.assertEqual(info["entries"], ["a.jSkin", "b.jSkin"])
            self.assertEqual(info["mgear_version"], "5.3.4")


class TestDescribePackMember(unittest.TestCase):

    def test_display_shows_arrow_to_newer_latest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            for name in ("body.0001.jSkin", "body.0005.jSkin"):
                open(os.path.join(tmp_dir, name), "w").close()
            desc = mgear_skin.describe_pack_member(tmp_dir, "body.0001.jSkin")
            self.assertEqual(desc["display"], "body.0001.jSkin -> 0005")
            self.assertEqual(desc["latest"], "body.0005.jSkin")
            self.assertTrue(desc["latest_exists"])

    def test_display_without_newer_latest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            open(os.path.join(tmp_dir, "body.0003.jSkin"), "w").close()
            desc = mgear_skin.describe_pack_member(tmp_dir, "body.0003.jSkin")
            self.assertEqual(desc["display"], "body.0003.jSkin")
            self.assertEqual(desc["latest"], "body.0003.jSkin")


class TestListPackMemberBaseNames(unittest.TestCase):

    def test_versioned_and_unversioned_members(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = os.path.join(tmp_dir, "rig.gSkinPack")
            with open(pack_path, "w", encoding="utf-8") as file_id:
                json.dump(
                    {
                        "packFiles": [
                            "body.0001.jSkin",
                            "head.gSkin",
                            "body.0003.jSkin",
                            "arm.0002.jSkin",
                        ]
                    },
                    file_id,
                )
            self.assertEqual(
                mgear_skin.list_pack_member_base_names(pack_path),
                ["body", "head", "arm"],
            )

    def test_empty_pack_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = os.path.join(tmp_dir, "empty.gSkinPack")
            with open(pack_path, "w", encoding="utf-8") as file_id:
                json.dump({"packFiles": []}, file_id)
            self.assertEqual(
                mgear_skin.list_pack_member_base_names(pack_path),
                [],
            )


class TestFindTransformsForBaseName(unittest.TestCase):

    def setUp(self):
        self._saved_maya = sys.modules.get("maya")
        maya_module = types.ModuleType("maya")
        maya_module.cmds = mock.Mock()
        sys.modules["maya"] = maya_module
        self.cmds = maya_module.cmds

    def tearDown(self):
        if self._saved_maya is None:
            sys.modules.pop("maya", None)
        else:
            sys.modules["maya"] = self._saved_maya

    def test_exact_transform_match(self):
        def _ls(pattern, long=True):
            if pattern == "body":
                return ["|grp|body"]
            return []

        self.cmds.ls.side_effect = _ls
        self.cmds.nodeType.return_value = "transform"
        result = mgear_skin._find_transforms_for_base_name("body")
        self.assertEqual(result, ["|grp|body"])

    def test_namespaced_transform_match(self):
        def _ls(pattern, long=True):
            if pattern == "*:body":
                return ["|grp|char:body"]
            return []

        self.cmds.ls.side_effect = _ls
        self.cmds.nodeType.return_value = "transform"
        result = mgear_skin._find_transforms_for_base_name("body")
        self.assertEqual(result, ["|grp|char:body"])

    def test_ambiguous_transforms(self):
        def _ls(pattern, long=True):
            if pattern == "body":
                return ["|a|body", "|b|body"]
            return []

        self.cmds.ls.side_effect = _ls
        self.cmds.nodeType.return_value = "transform"
        result = mgear_skin._find_transforms_for_base_name("body")
        self.assertEqual(result, ["|a|body", "|b|body"])


class TestExportSkinPackSkipUnskinned(unittest.TestCase):
    """export_skin_pack should warn+skip transforms without a skinCluster."""

    def _make_obj(self, name):
        obj = mock.Mock()
        obj.stripNamespace.return_value = name
        return obj

    def test_skips_unskinned_and_exports_skinned(self):
        skinned = self._make_obj("body")
        unskinned = self._make_obj("prop")
        mod = mock.Mock()
        mod.getSkinCluster.side_effect = lambda obj: (
            mock.Mock(name="skinCluster1") if obj is skinned else None
        )

        def _export_skin(filePath=None, objs=None):
            with open(filePath, "w", encoding="utf-8") as file_id:
                file_id.write("{}")
            return True

        mod.exportSkin.side_effect = _export_skin
        om2_mod = types.ModuleType("maya.api")
        om2_mod.OpenMaya = mock.Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = os.path.join(tmp_dir, "rig.gSkinPack")
            with mock.patch.object(mgear_skin, "is_available", return_value=True), \
                    mock.patch.object(mgear_skin, "_skin_module", return_value=mod), \
                    mock.patch.object(
                        mgear_skin, "_as_export_pynodes",
                        return_value=[skinned, unskinned],
                    ), \
                    mock.patch.object(
                        mgear_skin, "get_mgear_version", return_value=""
                    ), \
                    mock.patch.object(
                        mgear_skin.metadata, "write_export_sidecar"
                    ),                     mock.patch.object(
                        mgear_skin, "_get_bind_metadata", return_value={}
                    ),                     mock.patch.object(
                        mgear_skin, "_get_member_dag_paths", return_value={}
                    ), \
                    mock.patch.dict(
                        sys.modules,
                        {
                            "maya": types.ModuleType("maya"),
                            "maya.api": om2_mod,
                        },
                    ):
                result = mgear_skin.export_skin_pack(
                    ["bodyShape", "propShape"], pack_path, use_json=True
                )

            self.assertEqual(result, pack_path)
            self.assertTrue(os.path.isfile(pack_path))
            with open(pack_path, encoding="utf-8") as file_id:
                pack_data = json.load(file_id)
            self.assertEqual(pack_data["packFiles"], ["body.jSkin"])
            mod.exportSkin.assert_called_once()
            om2_mod.OpenMaya.MGlobal.displayWarning.assert_called_once()
            warning_msg = om2_mod.OpenMaya.MGlobal.displayWarning.call_args[0][0]
            self.assertIn("No skinCluster on: prop", warning_msg)

    def test_all_unskinned_raises(self):
        unskinned = self._make_obj("prop")
        mod = mock.Mock()
        mod.getSkinCluster.return_value = None
        om2_mod = types.ModuleType("maya.api")
        om2_mod.OpenMaya = mock.Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = os.path.join(tmp_dir, "rig.gSkinPack")
            with mock.patch.object(mgear_skin, "is_available", return_value=True), \
                    mock.patch.object(mgear_skin, "_skin_module", return_value=mod), \
                    mock.patch.object(
                        mgear_skin, "_as_export_pynodes",
                        return_value=[unskinned],
                    ), \
                    mock.patch.dict(
                        sys.modules,
                        {
                            "maya": types.ModuleType("maya"),
                            "maya.api": om2_mod,
                        },
                    ):
                with self.assertRaises(RuntimeError) as ctx:
                    mgear_skin.export_skin_pack(
                        ["propShape"], pack_path, use_json=True
                    )
            self.assertIn("produced no skin files", str(ctx.exception))
            mod.exportSkin.assert_not_called()


class TestSidecarInfluences(unittest.TestCase):
    """Bind info is read back from the sidecar, since .gSkin is binary."""

    def _write_weight_file(self, directory, name="body.gSkin"):
        path = os.path.join(directory, name)
        with open(path, "wb") as file_id:
            file_id.write(b"pickle-stand-in")
        return path

    def test_returns_recorded_influences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_weight_file(directory)
            metadata.write_export_sidecar(
                path, mgear_skin.METADATA_FORMAT,
                extra={"shape": "body_geoShape",
                       "influences": ["joint_1", "joint_2"]},
            )
            self.assertEqual(
                mgear_skin.list_sidecar_influences(path),
                ["joint_1", "joint_2"],
            )

    def test_returns_empty_without_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_weight_file(directory)
            self.assertEqual(mgear_skin.list_sidecar_influences(path), [])

    def test_returns_empty_when_sidecar_predates_the_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_weight_file(directory)
            metadata.write_export_sidecar(path, mgear_skin.METADATA_FORMAT)
            self.assertEqual(mgear_skin.list_sidecar_influences(path), [])

    def test_shape_is_recorded_for_the_viewer_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_weight_file(directory)
            metadata.write_export_sidecar(
                path, mgear_skin.METADATA_FORMAT,
                extra={"shape": "body_geoShape", "influences": []},
            )
            self.assertEqual(
                metadata.read_sidecar(path)["shape"], "body_geoShape"
            )


class TestGetSidecarMemberRecords(unittest.TestCase):

    def _write_pack(self, directory, sidecar_extra=None):
        pack_path = os.path.join(directory, "rig.gSkinPack")
        with open(pack_path, "w", encoding="utf-8") as file_id:
            json.dump({"packFiles": ["body.0001.jSkin"]}, file_id)
        if sidecar_extra is not None:
            metadata.write_export_sidecar(
                pack_path, mgear_skin.METADATA_FORMAT, extra=sidecar_extra
            )
        return pack_path

    def test_records_keyed_by_member_base_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, {
                "members": [
                    {
                        "file": "body.0003.jSkin",
                        "transform": "|char|geo|body",
                        "shape": "|char|geo|body|bodyShape",
                    },
                    {"file": "head.gSkin", "transform": "|char|geo|head"},
                ],
            })
            records = mgear_skin.get_sidecar_member_records(pack_path)
            self.assertEqual(sorted(records), ["body", "head"])
            self.assertEqual(records["body"]["transform"], "|char|geo|body")

    def test_empty_without_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir)
            self.assertEqual(mgear_skin.get_sidecar_member_records(pack_path), {})

    def test_empty_when_sidecar_predates_the_field(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, {"mgear_version": "4.2.0"})
            self.assertEqual(mgear_skin.get_sidecar_member_records(pack_path), {})

    def test_skips_malformed_entries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, {
                "members": [
                    "body.0001.jSkin",
                    {"transform": "|char|geo|body"},
                    {"file": "  ", "transform": "|x"},
                    {"file": "arm.0002.jSkin", "transform": "|char|geo|arm"},
                ],
            })
            records = mgear_skin.get_sidecar_member_records(pack_path)
            self.assertEqual(list(records), ["arm"])


class TestFindMemberTransforms(unittest.TestCase):

    def setUp(self):
        self._saved_maya = sys.modules.get("maya")
        maya_module = types.ModuleType("maya")
        maya_module.cmds = mock.Mock()
        sys.modules["maya"] = maya_module
        self.cmds = maya_module.cmds

    def tearDown(self):
        if self._saved_maya is None:
            sys.modules.pop("maya", None)
        else:
            sys.modules["maya"] = self._saved_maya

    def test_recorded_transform_wins_over_name_matching(self):
        def _ls(pattern, long=True):
            if pattern == "|char|geo|body":
                return ["|char|geo|body"]
            return ["|wrong|body"]

        self.cmds.ls.side_effect = _ls
        self.cmds.nodeType.return_value = "transform"
        result = mgear_skin._find_member_transforms(
            "body", {"transform": "|char|geo|body"}
        )
        self.assertEqual(result, ["|char|geo|body"])

    def test_recorded_shape_resolves_to_its_parent(self):
        def _ls(pattern, long=True):
            if pattern == "|char|geo|body|bodyShape":
                return ["|char|geo|body|bodyShape"]
            return []

        self.cmds.ls.side_effect = _ls
        self.cmds.nodeType.return_value = "mesh"
        self.cmds.listRelatives.return_value = ["|char|geo|body"]
        result = mgear_skin._find_member_transforms(
            "body", {"shape": "|char|geo|body|bodyShape"}
        )
        self.assertEqual(result, ["|char|geo|body"])

    def test_falls_back_to_name_matching_when_recorded_node_is_gone(self):
        def _ls(pattern, long=True):
            if pattern == "body":
                return ["|new|body"]
            return []

        self.cmds.ls.side_effect = _ls
        self.cmds.nodeType.return_value = "transform"
        result = mgear_skin._find_member_transforms(
            "body", {"transform": "|old|body"}
        )
        self.assertEqual(result, ["|new|body"])

    def test_falls_back_to_name_matching_without_a_record(self):
        def _ls(pattern, long=True):
            if pattern == "body":
                return ["|grp|body"]
            return []

        self.cmds.ls.side_effect = _ls
        self.cmds.nodeType.return_value = "transform"
        self.assertEqual(
            mgear_skin._find_member_transforms("body", {}),
            ["|grp|body"],
        )


class TestExportSkinPackRecordsMembers(unittest.TestCase):
    """export_skin_pack should record member DAG paths in the pack sidecar."""

    def test_pack_sidecar_records_member_paths(self):
        obj = mock.Mock()
        obj.stripNamespace.return_value = "body"
        obj.__str__ = mock.Mock(return_value="|char|geo|body")
        mod = mock.Mock()
        mod.getSkinCluster.return_value = mock.Mock()

        def _export_skin(filePath=None, objs=None):
            with open(filePath, "w", encoding="utf-8") as file_id:
                file_id.write("{}")
            return True

        mod.exportSkin.side_effect = _export_skin
        om2_mod = types.ModuleType("maya.api")
        om2_mod.OpenMaya = mock.Mock()

        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = os.path.join(tmp_dir, "rig.gSkinPack")
            with mock.patch.object(mgear_skin, "is_available", return_value=True),                     mock.patch.object(mgear_skin, "_skin_module", return_value=mod),                     mock.patch.object(
                        mgear_skin, "_as_export_pynodes", return_value=[obj]
                    ),                     mock.patch.object(
                        mgear_skin, "get_mgear_version", return_value=""
                    ),                     mock.patch.object(
                        mgear_skin, "_get_bind_metadata", return_value={}
                    ),                     mock.patch.object(
                        mgear_skin, "_get_member_dag_paths",
                        return_value={
                            "shape": "|char|geo|body|bodyShape",
                            "transform": "|char|geo|body",
                        },
                    ),                     mock.patch.dict(
                        sys.modules,
                        {
                            "maya": types.ModuleType("maya"),
                            "maya.api": om2_mod,
                        },
                    ):
                mgear_skin.export_skin_pack(
                    ["bodyShape"], pack_path, use_json=True
                )

            records = mgear_skin.get_sidecar_member_records(pack_path)
            self.assertEqual(list(records), ["body"])
            self.assertEqual(records["body"], {
                "file": "body.jSkin",
                "shape": "|char|geo|body|bodyShape",
                "transform": "|char|geo|body",
            })


class PackUpdateTestCase(unittest.TestCase):
    """Shared fixture: a pack manifest plus member files on disk."""

    def _write_pack(self, directory, pack_files, name="rig.gSkinPack",
                    mgear_version=None, members=None):
        pack_path = os.path.join(directory, name)
        pack_data = {"packFiles": list(pack_files), "rootPath": directory}
        if mgear_version:
            pack_data["mgearVersion"] = mgear_version
        with open(pack_path, "w", encoding="utf-8") as file_id:
            json.dump(pack_data, file_id)
        if members is not None:
            metadata.write_export_sidecar(
                pack_path, mgear_skin.METADATA_FORMAT, extra={"members": members}
            )
        return pack_path

    def _touch(self, directory, *names):
        for name in names:
            with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
                f.write("{}")


class TestBuildPackUpdatePlan(PackUpdateTestCase):

    def test_resolves_members_to_the_newest_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(
                tmp_dir,
                "body.0001.jSkin", "body.0003.jSkin",
                "head.0002.jSkin",
            )
            pack_path = self._write_pack(
                tmp_dir, ["body.0001.jSkin", "head.0002.jSkin"]
            )
            plan = mgear_skin.build_pack_update_plan(pack_path)
            self.assertEqual(
                plan["pack_files"], ["body.0003.jSkin", "head.0002.jSkin"]
            )
            self.assertEqual(
                plan["changes"], [("body.0001.jSkin", "body.0003.jSkin")]
            )
            self.assertEqual(plan["missing"], [])

    def test_no_changes_when_already_latest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0003.jSkin")
            pack_path = self._write_pack(tmp_dir, ["body.0003.jSkin"])
            plan = mgear_skin.build_pack_update_plan(pack_path)
            self.assertEqual(plan["changes"], [])
            self.assertEqual(plan["pack_files"], ["body.0003.jSkin"])

    def test_reports_missing_members(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin")
            pack_path = self._write_pack(
                tmp_dir, ["body.0001.jSkin", "gone.0001.jSkin"]
            )
            plan = mgear_skin.build_pack_update_plan(pack_path)
            self.assertEqual(plan["missing"], ["gone.0001.jSkin"])
            self.assertEqual(plan["pack_files"], ["body.0001.jSkin"])


class TestApplyPackEdit(PackUpdateTestCase):
    """One action per member decides what the next pack version points at."""

    def _actions(self, *pairs):
        return [
            {"base_name": base, "action": action, "transform": transform}
            for base, action, transform in pairs
        ]

    def test_keep_writes_the_recorded_filenames(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin", "body.0004.jSkin")
            pack_path = self._write_pack(tmp_dir, ["body.0001.jSkin"])

            target = mgear_skin.apply_pack_edit(
                pack_path,
                self._actions(("body", mgear_skin.PACK_ACTION_KEEP, "")),
            )

            self.assertEqual(os.path.basename(target), "rig.0001.gSkinPack")
            with open(target, encoding="utf-8") as file_id:
                self.assertEqual(
                    json.load(file_id)["packFiles"], ["body.0001.jSkin"]
                )

    def test_latest_moves_the_entry_to_the_newest_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin", "body.0004.jSkin")
            pack_path = self._write_pack(
                tmp_dir, ["body.0001.jSkin"], name="rig.0001.gSkinPack",
                mgear_version="4.2.0",
            )

            target = mgear_skin.apply_pack_edit(
                pack_path,
                self._actions(("body", mgear_skin.PACK_ACTION_LATEST, "")),
            )

            self.assertEqual(os.path.basename(target), "rig.0002.gSkinPack")
            self.assertTrue(os.path.isfile(pack_path), "source pack kept")
            with open(target, encoding="utf-8") as file_id:
                pack_data = json.load(file_id)
            self.assertEqual(pack_data["packFiles"], ["body.0004.jSkin"])
            self.assertEqual(pack_data["mgearVersion"], "4.2.0")

    def test_mixed_actions_keep_pack_files_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(
                tmp_dir,
                "zeta.0001.jSkin", "alpha.0001.jSkin", "alpha.0003.jSkin",
                "mid.0001.jSkin",
            )
            pack_path = self._write_pack(
                tmp_dir,
                ["zeta.0001.jSkin", "alpha.0001.jSkin", "mid.0001.jSkin"],
            )

            target = mgear_skin.apply_pack_edit(
                pack_path,
                self._actions(
                    ("zeta", mgear_skin.PACK_ACTION_KEEP, ""),
                    ("alpha", mgear_skin.PACK_ACTION_LATEST, ""),
                    ("mid", mgear_skin.PACK_ACTION_KEEP, ""),
                ),
            )

            with open(target, encoding="utf-8") as file_id:
                self.assertEqual(
                    json.load(file_id)["packFiles"],
                    ["zeta.0001.jSkin", "alpha.0003.jSkin", "mid.0001.jSkin"],
                )

    def test_carries_member_records_onto_new_filenames(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin", "body.0004.jSkin")
            pack_path = self._write_pack(
                tmp_dir, ["body.0001.jSkin"],
                members=[{
                    "file": "body.0001.jSkin",
                    "shape": "|char|geo|body|bodyShape",
                    "transform": "|char|geo|body",
                }],
            )

            target = mgear_skin.apply_pack_edit(
                pack_path,
                self._actions(("body", mgear_skin.PACK_ACTION_LATEST, "")),
            )

            self.assertEqual(
                mgear_skin.get_sidecar_member_records(target)["body"],
                {
                    "file": "body.0004.jSkin",
                    "shape": "|char|geo|body|bodyShape",
                    "transform": "|char|geo|body",
                },
            )

    def test_latest_without_a_file_on_disk_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, ["gone.0001.jSkin"])
            with self.assertRaises(RuntimeError) as ctx:
                mgear_skin.apply_pack_edit(
                    pack_path,
                    self._actions(("gone", mgear_skin.PACK_ACTION_LATEST, "")),
                )
            self.assertIn("gone", str(ctx.exception))

    def test_unknown_member_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin")
            pack_path = self._write_pack(tmp_dir, ["body.0001.jSkin"])
            with self.assertRaises(ValueError) as ctx:
                mgear_skin.apply_pack_edit(
                    pack_path,
                    self._actions(("nope", mgear_skin.PACK_ACTION_KEEP, "")),
                )
            self.assertIn("nope", str(ctx.exception))

    def test_unknown_action_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin")
            pack_path = self._write_pack(tmp_dir, ["body.0001.jSkin"])
            with self.assertRaises(ValueError):
                mgear_skin.apply_pack_edit(
                    pack_path, self._actions(("body", "explode", ""))
                )

    def test_empty_pack_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, [])
            with self.assertRaises(RuntimeError):
                mgear_skin.apply_pack_edit(pack_path, [])


class TestReexportThroughPackEdit(PackUpdateTestCase):
    """A re-export action writes a new member file and points the pack at it."""

    def _run(self, tmp_dir, pack_files, actions, members=None):
        pack_path = self._write_pack(tmp_dir, pack_files, members=members)
        objs = []
        for action in actions:
            if action["action"] != mgear_skin.PACK_ACTION_REEXPORT:
                continue
            obj = mock.Mock()
            obj.stripNamespace.return_value = action["base_name"]
            obj.__str__ = mock.Mock(return_value=action["transform"])
            objs.append(obj)

        mod = mock.Mock()
        mod.getSkinCluster.return_value = mock.Mock()

        def _export_skin(filePath=None, objs=None):
            with open(filePath, "w", encoding="utf-8") as file_id:
                file_id.write("{}")
            return True

        mod.exportSkin.side_effect = _export_skin
        om2_mod = types.ModuleType("maya.api")
        om2_mod.OpenMaya = mock.Mock()

        def _dag_paths(node):
            leaf = str(node).rsplit("|", 1)[-1]
            return {
                "shape": f"|char|geo|{leaf}|{leaf}Shape",
                "transform": f"|char|geo|{leaf}",
            }

        with mock.patch.object(mgear_skin, "is_available", return_value=True), \
                mock.patch.object(mgear_skin, "_skin_module", return_value=mod), \
                mock.patch.object(
                    mgear_skin, "_as_export_pynodes", return_value=objs
                ), \
                mock.patch.object(
                    mgear_skin, "get_mgear_version", return_value="4.2.0"
                ), \
                mock.patch.object(
                    mgear_skin, "_get_bind_metadata", return_value={}
                ), \
                mock.patch.object(
                    mgear_skin, "_get_member_dag_paths", side_effect=_dag_paths
                ), \
                mock.patch.dict(
                    sys.modules,
                    {"maya": types.ModuleType("maya"), "maya.api": om2_mod},
                ):
            return mgear_skin.apply_pack_edit(pack_path, actions)

    def test_only_the_reexported_member_gets_a_new_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin", "head.0001.jSkin")
            target = self._run(
                tmp_dir,
                ["body.0001.jSkin", "head.0001.jSkin"],
                [
                    {
                        "base_name": "body",
                        "action": mgear_skin.PACK_ACTION_REEXPORT,
                        "transform": "|char|geo|body",
                    },
                    {
                        "base_name": "head",
                        "action": mgear_skin.PACK_ACTION_KEEP,
                        "transform": "",
                    },
                ],
                members=[
                    {"file": "body.0001.jSkin", "transform": "|old|body"},
                    {"file": "head.0001.jSkin", "transform": "|char|geo|head"},
                ],
            )

            with open(target, encoding="utf-8") as file_id:
                self.assertEqual(
                    json.load(file_id)["packFiles"],
                    ["body.0002.jSkin", "head.0001.jSkin"],
                )
            self.assertFalse(
                os.path.isfile(os.path.join(tmp_dir, "head.0002.jSkin")),
                "a kept member is never re-exported",
            )
            records = mgear_skin.get_sidecar_member_records(target)
            self.assertEqual(records["body"]["transform"], "|char|geo|body")
            self.assertEqual(records["head"]["transform"], "|char|geo|head")

    def test_reexport_of_a_new_mesh_appends_a_member(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin")
            target = self._run(
                tmp_dir,
                ["body.0001.jSkin"],
                [
                    {
                        "base_name": "body",
                        "action": mgear_skin.PACK_ACTION_KEEP,
                        "transform": "",
                    },
                    {
                        "base_name": "arm",
                        "action": mgear_skin.PACK_ACTION_REEXPORT,
                        "transform": "|char|geo|arm",
                    },
                ],
            )

            with open(target, encoding="utf-8") as file_id:
                self.assertEqual(
                    json.load(file_id)["packFiles"],
                    ["body.0001.jSkin", "arm.0001.jSkin"],
                )
            self.assertEqual(
                mgear_skin.get_sidecar_member_records(target)["arm"]["transform"],
                "|char|geo|arm",
            )

    def test_reexport_that_produces_no_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin")
            actions = [{
                "base_name": "body",
                "action": mgear_skin.PACK_ACTION_REEXPORT,
                "transform": "",
            }]
            with self.assertRaises(RuntimeError) as ctx:
                self._run(tmp_dir, ["body.0001.jSkin"], actions)
            self.assertIn("body", str(ctx.exception))


def _state(base_name):
    return {"base_name": base_name}


def _candidate(base_name, has_skin_cluster=True):
    return {
        "base_name": base_name,
        "transform": f"|char|{base_name}",
        "has_skin_cluster": has_skin_cluster,
    }


class TestBuildSelectionActions(unittest.TestCase):
    """Add and Export Skin: selected meshes join or replace pack members."""

    def test_new_mesh_is_appended_and_the_rest_are_kept(self):
        plan = mgear_skin.build_selection_actions(
            [_state("body"), _state("head")], [_candidate("arm")]
        )
        self.assertEqual(plan["added"], ["arm"])
        self.assertEqual(plan["updated"], [])
        self.assertEqual(plan["kept"], ["body", "head"])
        self.assertEqual(
            [(a["base_name"], a["action"]) for a in plan["actions"]],
            [
                ("body", mgear_skin.PACK_ACTION_KEEP),
                ("head", mgear_skin.PACK_ACTION_KEEP),
                ("arm", mgear_skin.PACK_ACTION_REEXPORT),
            ],
        )
        self.assertEqual(plan["actions"][-1]["transform"], "|char|arm")

    def test_selected_member_is_reexported_in_place(self):
        plan = mgear_skin.build_selection_actions(
            [_state("body"), _state("head"), _state("arm")],
            [_candidate("head")],
        )
        self.assertEqual(plan["updated"], ["head"])
        self.assertEqual(plan["added"], [])
        self.assertEqual(
            [a["base_name"] for a in plan["actions"]],
            ["body", "head", "arm"],
        )
        self.assertEqual(
            plan["actions"][1]["action"], mgear_skin.PACK_ACTION_REEXPORT
        )

    def test_adds_and_updates_together(self):
        plan = mgear_skin.build_selection_actions(
            [_state("body")], [_candidate("body"), _candidate("arm")]
        )
        self.assertEqual(plan["updated"], ["body"])
        self.assertEqual(plan["added"], ["arm"])

    def test_mesh_without_skin_cluster_is_skipped(self):
        plan = mgear_skin.build_selection_actions(
            [_state("body")],
            [_candidate("prop", has_skin_cluster=False), _candidate("arm")],
        )
        self.assertEqual(plan["skipped"], ["prop"])
        self.assertEqual(plan["added"], ["arm"])
        self.assertNotIn("prop", [a["base_name"] for a in plan["actions"]])

    def test_two_meshes_with_one_member_name_raise(self):
        with self.assertRaises(ValueError) as ctx:
            mgear_skin.build_selection_actions(
                [], [_candidate("body"), _candidate("body")]
            )
        self.assertIn("body", str(ctx.exception))


class TestBuildAddFilesActions(unittest.TestCase):
    """Add Member to .gSkinPack: exported files join or replace members."""

    def test_new_file_is_appended_with_its_version(self):
        plan = mgear_skin.build_add_files_actions(
            [_state("body")], ["arm.0003.jSkin"]
        )
        self.assertEqual(plan["added"], ["arm"])
        self.assertEqual(plan["kept"], ["body"])
        self.assertEqual(plan["actions"][-1], {
            "base_name": "arm",
            "action": mgear_skin.PACK_ACTION_FILE,
            "file": "arm.0003.jSkin",
        })

    def test_file_named_like_a_member_replaces_it_in_place(self):
        plan = mgear_skin.build_add_files_actions(
            [_state("body"), _state("head")], ["body.0005.jSkin"]
        )
        self.assertEqual(plan["updated"], ["body"])
        self.assertEqual(plan["added"], [])
        self.assertEqual(
            [a["base_name"] for a in plan["actions"]], ["body", "head"]
        )
        self.assertEqual(plan["actions"][0]["file"], "body.0005.jSkin")

    def test_two_versions_of_one_member_raise(self):
        with self.assertRaises(ValueError):
            mgear_skin.build_add_files_actions(
                [], ["body.0001.jSkin", "body.0002.jSkin"]
            )


class TestGetPackMemberExtension(PackUpdateTestCase):

    def test_jskin_members(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, ["body.0001.jSkin"])
            self.assertEqual(
                mgear_skin.get_pack_member_extension(pack_path), "jskin"
            )

    def test_gskin_members(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, ["body.0001.gSkin"])
            self.assertEqual(
                mgear_skin.get_pack_member_extension(pack_path), "gskin"
            )


class TestApplyPackEditAddFiles(PackUpdateTestCase):

    def _apply(self, pack_path, *actions):
        return mgear_skin.apply_pack_edit(pack_path, list(actions))

    def _keep(self, base_name):
        return {"base_name": base_name, "action": mgear_skin.PACK_ACTION_KEEP}

    def _file(self, base_name, file_name):
        return {
            "base_name": base_name,
            "action": mgear_skin.PACK_ACTION_FILE,
            "file": file_name,
        }

    def _packed_files(self, target):
        with open(target, encoding="utf-8") as file_id:
            return json.load(file_id)["packFiles"]

    def test_file_is_appended_to_the_pack(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin", "arm.0002.jSkin")
            pack_path = self._write_pack(tmp_dir, ["body.0001.jSkin"])

            target = self._apply(
                pack_path, self._keep("body"),
                self._file("arm", "arm.0002.jSkin"),
            )

            self.assertEqual(
                self._packed_files(target),
                ["body.0001.jSkin", "arm.0002.jSkin"],
            )
            self.assertTrue(os.path.isfile(pack_path), "source pack kept")

    def test_file_replaces_a_member_and_keeps_its_scene_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin", "body.0006.jSkin")
            pack_path = self._write_pack(
                tmp_dir, ["body.0001.jSkin"],
                members=[{
                    "file": "body.0001.jSkin",
                    "transform": "|char|geo|body",
                }],
            )

            target = self._apply(
                pack_path, self._file("body", "body.0006.jSkin")
            )

            self.assertEqual(self._packed_files(target), ["body.0006.jSkin"])
            self.assertEqual(
                mgear_skin.get_sidecar_member_records(target)["body"],
                {"file": "body.0006.jSkin", "transform": "|char|geo|body"},
            )

    def test_file_in_the_other_format_is_refused_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin", "arm.0001.gSkin")
            pack_path = self._write_pack(
                tmp_dir, ["body.0001.jSkin"], name="rig.0001.gSkinPack"
            )

            with self.assertRaises(ValueError) as ctx:
                self._apply(
                    pack_path, self._keep("body"),
                    self._file("arm", "arm.0001.gSkin"),
                )

            self.assertIn("arm.0001.gSkin", str(ctx.exception))
            self.assertFalse(
                os.path.isfile(os.path.join(tmp_dir, "rig.0002.gSkinPack"))
            )

    def test_file_missing_on_disk_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin")
            pack_path = self._write_pack(tmp_dir, ["body.0001.jSkin"])

            with self.assertRaises(RuntimeError) as ctx:
                self._apply(
                    pack_path, self._keep("body"),
                    self._file("arm", "arm.0002.jSkin"),
                )

            self.assertIn("arm.0002.jSkin", str(ctx.exception))

    def test_member_named_twice_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._touch(tmp_dir, "body.0001.jSkin")
            pack_path = self._write_pack(tmp_dir, ["body.0001.jSkin"])

            with self.assertRaises(ValueError):
                self._apply(pack_path, self._keep("body"), self._keep("body"))


class TestBuildReexportAllActions(unittest.TestCase):
    """Export with only a pack selected re-exports every exportable member."""

    def _state(self, base_name, transform="", has_skin_cluster=False):
        return {
            "base_name": base_name,
            "transform": transform,
            "has_skin_cluster": has_skin_cluster,
        }

    def test_skinned_members_are_reexported(self):
        actions = mgear_skin.build_reexport_all_actions([
            self._state("body", "|char|body", True),
            self._state("head", "|char|head", True),
        ])
        self.assertEqual(
            [action["action"] for action in actions],
            [mgear_skin.PACK_ACTION_REEXPORT] * 2,
        )
        self.assertEqual(actions[0]["transform"], "|char|body")

    def test_members_without_a_skinned_mesh_stay_at_latest(self):
        actions = mgear_skin.build_reexport_all_actions([
            self._state("body", "|char|body", True),
            self._state("gone"),
            self._state("prop", "|char|prop", False),
        ])
        self.assertEqual(
            [action["action"] for action in actions],
            [
                mgear_skin.PACK_ACTION_REEXPORT,
                mgear_skin.PACK_ACTION_LATEST,
                mgear_skin.PACK_ACTION_LATEST,
            ],
        )

    def test_keeps_member_order(self):
        actions = mgear_skin.build_reexport_all_actions([
            self._state("zeta", "|zeta", True),
            self._state("alpha", "|alpha", True),
        ])
        self.assertEqual(
            [action["base_name"] for action in actions], ["zeta", "alpha"]
        )


class TestGetNextPackVersionName(PackUpdateTestCase):

    def test_next_version_of_a_versioned_pack(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(
                tmp_dir, [], name="rig.0003.gSkinPack"
            )
            self.assertEqual(
                mgear_skin.get_next_pack_version_name(pack_path),
                "rig.0004.gSkinPack",
            )

    def test_first_version_of_an_unversioned_pack(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_path = self._write_pack(tmp_dir, [], name="rig.gSkinPack")
            self.assertEqual(
                mgear_skin.get_next_pack_version_name(pack_path),
                "rig.0001.gSkinPack",
            )


if __name__ == "__main__":
    unittest.main()
