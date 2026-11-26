"""scene.list_skinned_shapes against a fake maya.cmds (no Maya required).

The fake answers only the calls list_skinned_shapes makes; it does not stand
in for real skinCluster queries.
"""

import importlib
import os
import sys
import types
import unittest
from unittest import mock

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)


def _import_scene_with_fake_maya():
    """A private copy of scene, leaving sys.modules as other tests found it."""
    import wipskin.formats as formats_package

    saved_maya = sys.modules.get("maya")
    saved_scene = sys.modules.pop("wipskin.formats.scene", None)
    saved_attr = formats_package.__dict__.get("scene")
    maya_module = types.ModuleType("maya")
    maya_module.cmds = mock.Mock()
    sys.modules["maya"] = maya_module
    try:
        return importlib.import_module("wipskin.formats.scene")
    finally:
        if saved_maya is None:
            sys.modules.pop("maya", None)
        else:
            sys.modules["maya"] = saved_maya

        if saved_scene is None:
            sys.modules.pop("wipskin.formats.scene", None)
        else:
            sys.modules["wipskin.formats.scene"] = saved_scene

        if saved_attr is None:
            formats_package.__dict__.pop("scene", None)
        else:
            formats_package.scene = saved_attr


scene = _import_scene_with_fake_maya()


class TestListSkinnedShapes(unittest.TestCase):

    def setUp(self):
        self.cmds = mock.Mock()
        self.cmds.ls.return_value = ["skinCluster1", "skinCluster2"]
        self.geometry = {
            "skinCluster1": ["bodyShape", "propShape"],
            "skinCluster2": ["bodyShape", "curveShape"],
        }
        self.cmds.skinCluster.side_effect = (
            lambda skc, query, geometry: self.geometry[skc]
        )
        node_types = {
            "|body|bodyShape": "mesh",
            "|prop|propShape": "mesh",
            "|curve|curveShape": "nurbsCurve",
        }
        self.cmds.nodeType.side_effect = node_types.__getitem__
        patcher = mock.patch.object(scene, "cmds", self.cmds)
        patcher.start()
        self.addCleanup(patcher.stop)
        shape_patcher = mock.patch.object(
            scene,
            "get_skinnable_shape",
            side_effect=lambda name: {
                "bodyShape": "|body|bodyShape",
                "propShape": "|prop|propShape",
                "curveShape": "|curve|curveShape",
            }.get(name, ""),
        )
        shape_patcher.start()
        self.addCleanup(shape_patcher.stop)

    def test_every_deformed_shape_once_in_skin_cluster_order(self):
        self.assertEqual(
            scene.list_skinned_shapes(),
            ["|body|bodyShape", "|prop|propShape", "|curve|curveShape"],
        )
        self.cmds.ls.assert_called_once_with(type="skinCluster")

    def test_shape_types_keeps_only_those_types(self):
        self.assertEqual(
            scene.list_skinned_shapes(shape_types=("mesh",)),
            ["|body|bodyShape", "|prop|propShape"],
        )

    def test_unresolvable_geometry_is_left_out(self):
        self.geometry["skinCluster2"] = ["origShapeOnly"]
        self.assertEqual(
            scene.list_skinned_shapes(),
            ["|body|bodyShape", "|prop|propShape"],
        )

    def test_skin_cluster_without_geometry_is_skipped(self):
        self.geometry["skinCluster1"] = None
        self.assertEqual(
            scene.list_skinned_shapes(),
            ["|body|bodyShape", "|curve|curveShape"],
        )

    def test_no_skin_clusters(self):
        self.cmds.ls.return_value = []
        self.assertEqual(scene.list_skinned_shapes(), [])


if __name__ == "__main__":
    unittest.main()
