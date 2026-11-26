import os
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

try:
    from wipskin.formats import scene
except ImportError:
    scene = None


class TestSkinnableShapes(unittest.TestCase):

    def test_skinnable_shape_types(self):
        if scene is None:
            self.skipTest("Maya not available")
        self.assertIn("mesh", scene.DEFORMABLE_SHAPE_TYPES)
        self.assertIn("nurbsCurve", scene.DEFORMABLE_SHAPE_TYPES)
        self.assertIn("nurbsSurface", scene.DEFORMABLE_SHAPE_TYPES)
        self.assertIn("lattice", scene.DEFORMABLE_SHAPE_TYPES)

    def test_bezier_curve_is_skinnable(self):
        if scene is None:
            self.skipTest("Maya not available")
        # bezierCurve is a nurbsCurve subtype; cmds.nodeType() returns the
        # concrete "bezierCurve" name rather than "nurbsCurve", so the check
        # must use objectType's inheritance-aware isa rather than an exact
        # nodeType() match.
        from maya import cmds
        shape = cmds.createNode("bezierCurve")
        try:
            self.assertTrue(scene.is_deformable_shape_type(shape))
        finally:
            cmds.delete(shape)

    def test_is_skinnable_component(self):
        if scene is None:
            self.skipTest("Maya not available")
        self.assertTrue(scene.is_skinnable_component("meshShape.vtx[0]"))
        self.assertTrue(scene.is_skinnable_component("curveShape.cv[1]"))
        self.assertTrue(scene.is_skinnable_component("surfaceShape.s[0][1]"))
        self.assertTrue(scene.is_skinnable_component("ffd1LatticeShape.pt[3]"))
        self.assertFalse(scene.is_skinnable_component("|group|mesh"))

    def test_get_node_leaf_name_strips_path_and_namespace(self):
        if scene is None:
            self.skipTest("Maya not available")
        self.assertEqual(scene.get_node_leaf_name("body_geoShape"), "body_geoShape")
        self.assertEqual(
            scene.get_node_leaf_name("|group|body_geo|body_geoShape"),
            "body_geoShape",
        )
        self.assertEqual(
            scene.get_node_leaf_name("char:body_geoShape"),
            "body_geoShape",
        )


if __name__ == "__main__":
    unittest.main()
