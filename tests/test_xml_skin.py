import os
import sys
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

try:
    from wipskin.formats.skin.xml import weights as xml_skin
except ImportError:
    xml_skin = None


FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_skin.xml")
STALE_MAX_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_skin_stale_max_influences.xml"
)
DEFORMER_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_deformer.xml")
WEIGHT_BLENDED_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_skin_weight_blended.xml"
)
MIXED_DEFORMERS_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_skin_mixed_deformers.xml"
)
CORRUPTED_DEFORMER_ATTR_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_skin_corrupted_deformer_attr.xml"
)
# Real Maya deformerWeights output (cmds.deformerWeights(export=True) on a
# 4-vert plane bound to joint1/joint2), captured to nail the bulk-API import
# format: <weights> layer/defaultValue/size/max attrs, leading-space point
# values, headerInfo worldMatrix, and per-attribute type="..." attrs.
PLANE_TWO_JOINTS_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_skin_plane_two_joints.xml"
)
PLANE_TWO_JOINTS_ASYMMETRIC_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures",
    "sample_skin_plane_two_joints_asymmetric.xml",
)


class TestXmlFixtures(unittest.TestCase):

    def test_skin_and_deformer_fixtures_use_distinct_root_tags(self):
        skin_root = ET.parse(FIXTURE).getroot().tag
        deformer_root = ET.parse(DEFORMER_FIXTURE).getroot().tag
        self.assertEqual(skin_root, "deformerWeight")
        self.assertEqual(deformer_root, "customDeformerWeight")
        self.assertNotEqual(skin_root, deformer_root)


    def test_fixture_includes_skin_attributes(self):
        deformer = ET.parse(FIXTURE).find("deformer")
        self.assertIsNotNone(deformer)
        attributes = deformer.findall("attribute")
        names = [element.attrib.get("name", "") for element in attributes]
        self.assertIn("skinningMethod", names)
        self.assertIn("normalizeWeights", names)
        self.assertIn("maxInfluences", names)


class TestParseFileInfo(unittest.TestCase):

    def test_parse_sample_xml(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        info = xml_skin.parse_file_info(FIXTURE)
        self.assertEqual(info["deformer"], "body_skinCluster")
        self.assertEqual(info["shape"], "body_geoShape")
        self.assertEqual(info["influences"], ["joint_1", "joint_2"])
        self.assertEqual(
            info["attributes"],
            [
                {"name": "skinningMethod", "value": "0"},
                {"name": "normalizeWeights", "value": "1"},
                {"name": "maxInfluences", "value": "4"},
            ],
        )
        self.assertEqual(info["mesh_vert_count"], 3)
        self.assertEqual(info["saved_vert_count"], 3)
        text = xml_skin.format_viewer_text(info)
        self.assertIn("Mesh: body_geoShape", text)
        self.assertIn("Saved verts: 3 / 3", text)
        self.assertIn("Influences: 2", text)
        self.assertIn("Skin method: classic linear", text)
        self.assertIn("Normalize weights: interactive", text)
        self.assertIn("Max influences: 4", text)
        self.assertNotIn("Attributes:", text)

    def test_blend_weights_block_excluded_from_influences(self):
        """
        A skinCluster set to 'weight blended' gets an extra <weights
        source="baseLayer"> block for its blendWeights list (not a real
        joint influence) — it must not appear in influences or inflate
        max-influences-per-vertex.
        """
        if xml_skin is None:
            self.skipTest("Maya not available")
        info = xml_skin.parse_file_info(WEIGHT_BLENDED_FIXTURE)
        self.assertEqual(info["influences"], ["joint_1", "joint_2"])
        self.assertNotIn("baseLayer", info["influences"])
        # vert 1 has joint_1 + joint_2 = 2 real influences; the baseLayer
        # block (present on every vert) must not push this to 3.
        self.assertEqual(info["weight_max_influences"], 2)
        self.assertEqual(info["effective_max_influences"], 2)

    def test_mixed_deformers_only_reports_skin_cluster(self):
        """
        Mixed deformer XML must report only the skinCluster (no blendShape
        targets in the influence list).
        """
        if xml_skin is None:
            self.skipTest("Maya not available")
        info = xml_skin.parse_file_info(MIXED_DEFORMERS_FIXTURE)
        self.assertEqual(info["deformer"], "body_skinCluster")
        self.assertEqual(info["influences"], ["joint_1", "joint_2"])
        self.assertNotIn("mouthOpenH", info["influences"])
        self.assertNotIn("mouthOpenV", info["influences"])
        attr_names = [entry["name"] for entry in info["attributes"]]
        self.assertIn("skinningMethod", attr_names)
        self.assertNotIn("envelope", attr_names)
        # index 1 has joint_1 + joint_2 only (blendShape must not make this 3)
        self.assertEqual(info["weight_max_influences"], 2)
        self.assertEqual(info["effective_max_influences"], 2)

    def test_corrupted_deformer_attr_uses_document_order(self):
        """
        Even when every weights deformer= attr claims the skinCluster name,
        weights after non-skin deformer stubs must not enter the influence list
        (Maya writes each deformer's weights immediately after its stub).
        """
        if xml_skin is None:
            self.skipTest("Maya not available")
        info = xml_skin.parse_file_info(CORRUPTED_DEFORMER_ATTR_FIXTURE)
        self.assertEqual(info["deformer"], "body_skinCluster")
        self.assertEqual(info["influences"], ["joint_1"])
        self.assertNotIn("headSquash_setup", info["influences"])
        self.assertNotIn("mouthOpenH", info["influences"])
        # All-1.0 blendShape blocks must not inflate max influences to 3
        self.assertEqual(info["weight_max_influences"], 1)
        self.assertEqual(info["effective_max_influences"], 1)


class TestFormatViewerText(unittest.TestCase):

    def test_format_viewer_text_from_fixture(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        info = xml_skin.parse_file_info(FIXTURE)
        text = xml_skin.format_viewer_text(info)
        self.assertIn("Saved verts: 3 / 3", text)
        self.assertIn("Skin method: classic linear", text)
        self.assertIn("Max influences: 4", text)

    def test_format_viewer_text_matrix_value(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        info = {
            "deformer": "sk",
            "shape": "sh",
            "influences": [],
            "saved_vert_count": None,
            "mesh_vert_count": None,
            "attributes": [
                {
                    "name": "relativeSpaceMatrix",
                    "value": "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1",
                },
            ],
        }
        text = xml_skin.format_viewer_text(info)
        self.assertIn("Relative space matrix:", text)
        self.assertIn("1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1", text)


class TestIsSkinWeightFile(unittest.TestCase):

    def test_is_skin_weight_file_true_for_skin_xml(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        self.assertTrue(xml_skin.is_skin_weight_file(FIXTURE))

    def test_is_skin_weight_file_false_for_deformer_xml(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        self.assertFalse(xml_skin.is_skin_weight_file(DEFORMER_FIXTURE))


class TestMaxInfluences(unittest.TestCase):

    def test_effective_max_influences_from_stale_attribute(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.parse(STALE_MAX_FIXTURE).getroot()
        self.assertEqual(xml_skin._get_max_influences_from_weights(root), 3)
        self.assertEqual(xml_skin._get_effective_max_influences(root), 3)

    def test_effective_max_influences_keeps_higher_attribute(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.parse(FIXTURE).getroot()
        self.assertEqual(xml_skin._get_max_influences_from_weights(root), 2)
        self.assertEqual(xml_skin._get_effective_max_influences(root), 4)

    def test_parse_stale_max_influences_fixture(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        info = xml_skin.parse_file_info(STALE_MAX_FIXTURE)
        self.assertEqual(info["effective_max_influences"], 3)
        text = xml_skin.format_viewer_text(info)
        self.assertIn("Max influences: 3", text)
        self.assertNotIn("Max influences: 1", text)

    def test_patch_max_influences_in_file(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "stale.xml")
            shutil.copy2(STALE_MAX_FIXTURE, path)
            effective = xml_skin._patch_max_influences_in_file(path)
            self.assertEqual(effective, 3)
            root = ET.parse(path).getroot()
            value = xml_skin._get_xml_attribute_value(root, "maxInfluences")
            self.assertEqual(value, "3")


class TestDeformerName(unittest.TestCase):

    def test_set_deformer_name_in_xml(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.fromstring(
            "<deformerWeight>"
            "<deformer name=\"wrong_skinCluster\" type=\"skinCluster\"/>"
            "<weights deformer=\"wrong_skinCluster\" source=\"joint_1\"/>"
            "</deformerWeight>"
        )
        changed = xml_skin._set_deformer_name_in_xml(root, "body_skinCluster")
        self.assertTrue(changed)
        deformer = root.find("deformer")
        weights = root.find("weights")
        self.assertEqual(deformer.attrib.get("name"), "body_skinCluster")
        self.assertEqual(weights.attrib.get("deformer"), "body_skinCluster")

    def test_set_deformer_name_in_xml_skips_other_deformer_stubs(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.fromstring(
            "<deformerWeight>"
            "<deformer name=\"wrong_skinCluster\" type=\"skinCluster\"/>"
            "<weights deformer=\"wrong_skinCluster\" source=\"joint_1\"/>"
            "<deformer name=\"body_deltaMush1\" type=\"deltaMush\"/>"
            "<deformer name=\"body_ffd1\" type=\"ffd\"/>"
            "</deformerWeight>"
        )
        changed = xml_skin._set_deformer_name_in_xml(root, "body_skinCluster")
        self.assertTrue(changed)
        stub_deformers = [
            element for element in root.findall("deformer")
            if element.attrib.get("type") != "skinCluster"
        ]
        self.assertEqual(len(stub_deformers), 2)
        self.assertEqual(stub_deformers[0].attrib.get("name"), "body_deltaMush1")
        self.assertEqual(stub_deformers[1].attrib.get("name"), "body_ffd1")

    def test_set_deformer_name_keeps_other_deformer_weights(self):
        """
        Do not rewrite deformer= on <weights> that belong to non-skin
        deformers (e.g. blendShape).
        """
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.parse(MIXED_DEFORMERS_FIXTURE).getroot()
        changed = xml_skin._set_deformer_name_in_xml(root, "renamed_skinCluster")
        self.assertTrue(changed)
        weights_by_source = {
            element.attrib.get("source"): element.attrib.get("deformer")
            for element in root.findall("weights")
        }
        self.assertEqual(weights_by_source["mouthOpenH"], "body_blendShape")
        self.assertEqual(weights_by_source["mouthOpenV"], "body_blendShape")
        self.assertEqual(weights_by_source["joint_1"], "renamed_skinCluster")
        self.assertEqual(weights_by_source["joint_2"], "renamed_skinCluster")
        deformer_names = [
            element.attrib.get("name") for element in root.findall("deformer")
        ]
        self.assertIn("body_blendShape", deformer_names)
        self.assertIn("renamed_skinCluster", deformer_names)
        self.assertNotIn("body_skinCluster", deformer_names)

    def test_set_header_filename_strips_absolute_path(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.fromstring(
            "<deformerWeight>"
            "<headerInfo fileName=\"D:/old/project/body.0007.xml\"/>"
            "</deformerWeight>"
        )
        changed = xml_skin._set_header_filename(root, "D:/new/project/body.0007.xml")
        self.assertTrue(changed)
        header = root.find("headerInfo")
        self.assertEqual(header.attrib.get("fileName"), "body.0007.xml")

    def test_set_header_filename_no_header_element(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.fromstring("<deformerWeight></deformerWeight>")
        changed = xml_skin._set_header_filename(root, "D:/new/project/body.0007.xml")
        self.assertFalse(changed)

    def test_parse_deformer_from_weights_element(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "sample_skin_weights_deformer.xml"
        )
        info = xml_skin.parse_file_info(fixture_path)
        self.assertEqual(info["deformer"], "body_skinCluster")


class TestSkinnableShapes(unittest.TestCase):
    # Shape/selection queries moved to formats.scene -- see tests/test_scene.py.

    def test_vertex_connections_mesh_only(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        self.assertTrue(xml_skin._uses_vertex_connections("mesh"))
        self.assertFalse(xml_skin._uses_vertex_connections("nurbsCurve"))
        self.assertFalse(xml_skin._uses_vertex_connections("nurbsSurface"))
        self.assertFalse(xml_skin._uses_vertex_connections("lattice"))


class TestResolveExportFilename(unittest.TestCase):

    def test_auto_version_strips_existing_version_from_filename(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            open(os.path.join(directory, "body_geo.0002.xml"), "w").close()
            result = xml_skin._resolve_export_filename(
                "body_geo",
                directory,
                "body_geo.0002.xml",
                auto_name=False,
                auto_version=True,
            )
            self.assertEqual(result, "body_geo.0003.xml")


class TestSavedAttributes(unittest.TestCase):

    def test_saved_attributes_include_extended_skin_attrs(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        for name in (
            "deformUserNormals",
            "relativeSpaceMode",
            "relativeSpaceMatrix",
            "dqsSupportNonRigid",
            "weightDistribution",
        ):
            self.assertIn(name, xml_skin.SAVED_ATTRIBUTES)


class TestMgearAvailable(unittest.TestCase):

    def test_is_available_without_crash(self):
        mgear_skin = __import__(
            "wipskin.plugins.mgear.weights", fromlist=["is_available"]
        )
        self.assertIn(mgear_skin.is_available(), (True, False))


class TestBuildWeightMatrixFromXml(unittest.TestCase):
    """
    _build_weight_matrix_from_xml backs the Phase 3 bulk-API "index" import
    path (xml_skin.import_skin). Verified against a real Maya
    deformerWeights export (see PLANE_TWO_JOINTS_FIXTURE), not a
    hand-written approximation of the format.
    """

    def test_matches_real_maya_sample(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.parse(PLANE_TWO_JOINTS_FIXTURE).getroot()
        matrix = xml_skin._build_weight_matrix_from_xml(
            root, ["joint2", "joint1"], 4
        )
        self.assertEqual(matrix, [0.5, 0.5] * 4)

    def test_column_order_follows_scene_influences_not_xml_order(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        # Real Maya sample where joint2 (0.9/0.7) and joint1 (0.1/0.3) are
        # NOT equal, so column mixups are numerically detectable. The XML
        # lists joint2's <weights> block before joint1's (layer 0 vs 1), but
        # the matrix must follow whatever order the caller passes as
        # scene_influences (MFnSkinCluster.influenceObjects() order in
        # production), not the XML's block order.
        root = ET.parse(PLANE_TWO_JOINTS_ASYMMETRIC_FIXTURE).getroot()
        matrix_joint2_first = xml_skin._build_weight_matrix_from_xml(
            root, ["joint2", "joint1"], 4
        )
        matrix_joint1_first = xml_skin._build_weight_matrix_from_xml(
            root, ["joint1", "joint2"], 4
        )
        self.assertEqual(matrix_joint2_first[0:2], [0.9, 0.1])
        self.assertEqual(matrix_joint1_first[0:2], [0.1, 0.9])
        self.assertEqual(matrix_joint2_first[2:4], [0.7, 0.3])
        self.assertEqual(matrix_joint1_first[2:4], [0.3, 0.7])

    def test_influence_missing_from_scene_is_skipped_not_crashed(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.parse(PLANE_TWO_JOINTS_FIXTURE).getroot()
        # joint2 is not part of "the scene" in this call -- its <weights>
        # block must be silently ignored, not raise or corrupt joint1's column.
        matrix = xml_skin._build_weight_matrix_from_xml(root, ["joint1"], 4)
        self.assertEqual(matrix, [0.5] * 4)

    def test_out_of_range_point_index_is_skipped(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.fromstring(
            '<deformerWeight><deformer name="skc" type="skinCluster"/>'
            '<weights deformer="skc" source="j0"><point index="0" value="1.0"/>'
            '<point index="99" value="1.0"/></weights></deformerWeight>'
        )
        matrix = xml_skin._build_weight_matrix_from_xml(root, ["j0"], 2)
        self.assertEqual(matrix, [1.0, 0.0])


class TestMergeAddWeightMatrix(unittest.TestCase):

    def test_vertex_absent_from_file_is_untouched(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        current = [0.6, 0.4]
        imported = [0.0, 0.0]
        result = xml_skin._merge_add_weight_matrix(current, imported, 1, 2)
        self.assertEqual(result, [0.6, 0.4])

    def test_listed_influence_is_added_then_row_renormalized(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        current = [0.6, 0.4]
        imported = [0.3, 0.0]
        result = xml_skin._merge_add_weight_matrix(current, imported, 1, 2)
        self.assertAlmostEqual(result[0], 0.9 / 1.3)
        self.assertAlmostEqual(result[1], 0.4 / 1.3)

    def test_new_influence_added_and_renormalized(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        current = [1.0, 0.0]
        imported = [0.0, 0.5]
        result = xml_skin._merge_add_weight_matrix(current, imported, 1, 2)
        self.assertAlmostEqual(result[0], 1.0 / 1.5)
        self.assertAlmostEqual(result[1], 0.5 / 1.5)

    def test_zero_total_does_not_crash(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        current = [0.0, 0.0]
        imported = [0.0, 0.0]
        result = xml_skin._merge_add_weight_matrix(current, imported, 1, 2)
        self.assertEqual(result, [0.0, 0.0])

    def test_multiple_verts_are_independent(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        current = [0.6, 0.4, 1.0, 0.0]
        imported = [0.3, 0.0, 0.0, 0.5]
        result = xml_skin._merge_add_weight_matrix(current, imported, 2, 2)
        self.assertAlmostEqual(result[0], 0.9 / 1.3)
        self.assertAlmostEqual(result[1], 0.4 / 1.3)
        self.assertAlmostEqual(result[2], 1.0 / 1.5)
        self.assertAlmostEqual(result[3], 0.5 / 1.5)


class TestBindPreMatrixXmlHelpers(unittest.TestCase):
    """
    _read_bind_pre_matrices / _write_bind_pre_matrices_block are pure XML
    manipulation (no Maya calls), unlike the capture/apply pair
    (_collect_bind_pre_matrices / _apply_bind_pre_matrices) which need a
    live skinCluster and are Maya-only.
    """

    def test_read_returns_empty_when_block_absent(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.parse(FIXTURE).getroot()
        self.assertEqual(xml_skin._read_bind_pre_matrices(root), {})

    def test_write_then_read_round_trip(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "sample.xml")
            shutil.copy2(FIXTURE, path)
            matrices = {
                "joint_1": [float(i) for i in range(16)],
                "joint_2": [1.0, 0.0, 0.0, 0.0] * 4,
            }
            xml_skin._write_bind_pre_matrices_block(path, matrices)
            root = ET.parse(path).getroot()
            result = xml_skin._read_bind_pre_matrices(root)
            self.assertEqual(result, matrices)

    def test_write_with_empty_dict_is_noop(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "sample.xml")
            shutil.copy2(FIXTURE, path)
            xml_skin._write_bind_pre_matrices_block(path, {})
            root = ET.parse(path).getroot()
            self.assertIsNone(root.find(xml_skin.BIND_PRE_MATRIX_CONTAINER_TAG))

    def test_write_replaces_existing_block(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "sample.xml")
            shutil.copy2(FIXTURE, path)
            xml_skin._write_bind_pre_matrices_block(path, {"joint_1": [1.0] * 16})
            xml_skin._write_bind_pre_matrices_block(path, {"joint_2": [2.0] * 16})
            root = ET.parse(path).getroot()
            result = xml_skin._read_bind_pre_matrices(root)
            self.assertEqual(result, {"joint_2": [2.0] * 16})

    def test_read_skips_malformed_entries(self):
        if xml_skin is None:
            self.skipTest("Maya not available")
        root = ET.fromstring(
            "<deformerWeight><bindPreMatrices>"
            '<bindPreMatrix source="joint_1" value="1 2 3"/>'
            '<bindPreMatrix source="joint_2" value="a b c d e f g h i j k l m n o p"/>'
            f'<bindPreMatrix source="joint_3" value="{" ".join(str(f) for f in range(16))}"/>'
            "</bindPreMatrices></deformerWeight>"
        )
        result = xml_skin._read_bind_pre_matrices(root)
        self.assertEqual(list(result.keys()), ["joint_3"])
