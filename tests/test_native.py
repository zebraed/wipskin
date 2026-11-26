"""
Tests for the native (Rust/PyO3) build_weight_matrix, compared against the
pure-Python reference logic in xml_skin._build_weight_matrix_from_xml.

`native` is a Rust extension module built separately (see native/, built with
`maturin develop` inside a dedicated venv -- it is not part of wipskin's
normal Python dependencies). These tests skip entirely when it isn't
importable, so a normal `pytest wipskin/tests` run (no native module built)
is unaffected.
"""

import os
import sys
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

try:
    import wipskin_native as native
except ImportError:
    native = None

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_skin_deformer_element(root):
    """Mirror of xml_skin._find_skin_deformer_element."""
    untyped = None
    for element in root:
        if element.tag != "deformer":
            continue
        deformer_type = element.attrib.get("type", "")
        if deformer_type == "skinCluster":
            return element
        if deformer_type == "" and untyped is None:
            untyped = element
    return untyped


def _list_other_deformer_names(root, skin_element):
    names = []
    for element in root:
        if element.tag != "deformer" or element is skin_element:
            continue
        name = element.attrib.get("name", "")
        if name:
            names.append(name)
    return names


def _list_skin_weights_elements(root, include_blend_weights=False):
    """Mirror of xml_skin._list_skin_weights_elements (the owner-aware
    filtering the native side does not yet replicate -- see module docstring
    in native/src/lib.rs)."""
    skin_element = _find_skin_deformer_element(root)
    other_names = _list_other_deformer_names(root, skin_element)
    result = []
    current = None
    for element in root:
        if element.tag == "deformer":
            current = element
            continue
        if element.tag != "weights":
            continue
        if current is not None and current is not skin_element:
            continue
        if not include_blend_weights:
            if element.attrib.get("source", "") == "baseLayer":
                continue
        deformer_name = element.attrib.get("deformer", "")
        if deformer_name and deformer_name in other_names:
            continue
        result.append(element)
    return result


def py_reference_weight_matrix(path, scene_influences, num_verts):
    """Owner-aware Python reference (same contract as xml_skin.py's
    _build_weight_matrix_from_xml, reimplemented here so this test file has
    no dependency on importing xml_skin, which requires Maya)."""
    root = ET.parse(path).getroot()
    num_inf = len(scene_influences)
    inf_column = {name: i for i, name in enumerate(scene_influences)}
    matrix = [0.0] * (num_verts * num_inf)
    for element in _list_skin_weights_elements(root):
        column = inf_column.get(element.attrib.get("source", ""))
        if column is None:
            continue
        for point in element:
            if point.tag != "point":
                continue
            row = _int_or_none(point.attrib.get("index"))
            if row is None or row < 0 or row >= num_verts:
                continue
            value = _float_or_none(point.attrib.get("value"))
            if value is None:
                continue
            matrix[row * num_inf + column] = value
    return matrix


class TestBuildWeightMatrix(unittest.TestCase):

    def setUp(self):
        if native is None:
            self.skipTest("native extension module not built (see native/README or run maturin develop)")

    def test_matches_python_reference_on_real_maya_sample(self):
        path = os.path.join(FIXTURES, "sample_skin_plane_two_joints.xml")
        for influences in (["joint2", "joint1"], ["joint1", "joint2"]):
            with self.subTest(influences=influences):
                expected = py_reference_weight_matrix(path, influences, 4)
                actual = native.build_weight_matrix(path, influences, 4)
                self.assertEqual(actual, expected)

    def test_column_order_follows_scene_influences(self):
        path = os.path.join(
            FIXTURES, "sample_skin_plane_two_joints_asymmetric.xml"
        )
        for influences in (["joint2", "joint1"], ["joint1", "joint2"]):
            with self.subTest(influences=influences):
                expected = py_reference_weight_matrix(path, influences, 4)
                actual = native.build_weight_matrix(path, influences, 4)
                self.assertEqual(actual, expected)

    def test_matches_on_basic_skin_fixture(self):
        path = os.path.join(FIXTURES, "sample_skin.xml")
        influences = ["joint_1", "joint_2"]
        expected = py_reference_weight_matrix(path, influences, 3)
        actual = native.build_weight_matrix(path, influences, 3)
        self.assertEqual(actual, expected)

    def test_mixed_deformers_file_no_name_collision(self):
        """
        native.build_weight_matrix doesn't replicate the Python side's
        deformer-ownership filtering (_list_skin_weights_elements). This is
        safe as long as no non-skinCluster deformer's <weights source="...">
        happens to share a name with a skinCluster influence -- which this
        fixture (blendShape targets mouthOpenH/mouthOpenV vs joints
        joint_1/joint_2) demonstrates is the common case. If this test starts
        failing on a new fixture, the native ownership gap has become a real
        bug and needs the same filtering added to native/src/lib.rs.
        """
        path = os.path.join(FIXTURES, "sample_skin_mixed_deformers.xml")
        influences = ["joint_1", "joint_2"]
        expected = py_reference_weight_matrix(path, influences, 3)
        actual = native.build_weight_matrix(path, influences, 3)
        self.assertEqual(actual, expected)

    def test_influence_missing_from_scene_is_skipped(self):
        path = os.path.join(FIXTURES, "sample_skin_plane_two_joints.xml")
        actual = native.build_weight_matrix(path, ["joint1"], 4)
        self.assertEqual(actual, [0.5, 0.5, 0.5, 0.5])

    def test_out_of_range_point_index_is_skipped(self):
        with_extra_xml = os.path.join(FIXTURES, "sample_skin.xml")
        # sample_skin.xml has 3 verts; asking for num_verts=3 with real data
        # already covers in-range parsing (see test_matches_on_basic_skin_fixture).
        # This just confirms an intentionally undersized num_verts doesn't
        # crash or write out of bounds.
        actual = native.build_weight_matrix(
            with_extra_xml, ["joint_1", "joint_2"], 1
        )
        self.assertEqual(len(actual), 2)


def _parse_write_inputs(path):
    """
    Extract the arguments native.write_skin_xml needs from a real Maya skin
    XML fixture, so tests can round-trip: parse a real sample -> feed its
    data back through write_skin_xml -> compare against the same sample.
    """
    root = ET.parse(path).getroot()
    header = root.find("headerInfo")
    deformer = root.find("deformer")
    shape = root.find("shape")

    positions = []
    polygon_counts = []
    polygon_connects = []
    for element in shape:
        if element.tag == "point":
            positions.extend(float(v) for v in element.attrib["value"].split())
        elif element.tag == "polygonCounts":
            polygon_counts = [
                int(v) for v in element.attrib["polygonCounts"].split()
            ]
        elif element.tag == "polygonConnects":
            polygon_connects = [
                int(v) for v in element.attrib["polygonConnects"].split()
            ]
    num_verts = len(positions) // 3

    weight_blocks = _list_skin_weights_elements(root)
    influence_names = [el.attrib["source"] for el in weight_blocks]
    num_inf = len(influence_names)
    weight_matrix = [0.0] * (num_verts * num_inf)
    default_value = 0.0
    for column, element in enumerate(weight_blocks):
        default_value = _float_or_none(element.attrib.get("defaultValue")) or 0.0
        for point in element:
            row = _int_or_none(point.attrib.get("index"))
            value = _float_or_none(point.attrib.get("value"))
            if row is not None and value is not None:
                weight_matrix[row * num_inf + column] = value

    attributes = [
        (a.attrib["name"], a.attrib["type"], a.attrib["value"])
        for a in deformer
    ]

    return {
        "file_name": os.path.basename(header.attrib["fileName"]),
        "world_matrix": [float(v) for v in header.attrib["worldMatrix"].split()],
        "deformer_name": deformer.attrib["name"],
        "deformer_type": deformer.attrib["type"],
        "attributes": attributes,
        "shape_name": shape.attrib["name"],
        "group": int(shape.attrib["group"]),
        "positions": positions,
        "influence_names": influence_names,
        "weight_matrix": weight_matrix,
        "default_value": default_value,
        "polygon_counts": polygon_counts,
        "polygon_connects": polygon_connects,
        "num_verts": num_verts,
    }


class TestWriteSkinXml(unittest.TestCase):
    """
    native.write_skin_xml is the Rust counterpart of Maya's own
    cmds.deformerWeights(export=True) for a single mesh skinCluster (see
    Phase 3 in the optimization plan). Verified against real Maya exports
    the user captured directly (not a hand-written approximation of the
    format) -- see the fixtures referenced below and
    docs/OPTIMIZATION_TECHNIQUES.md for the samples' provenance.
    """

    def setUp(self):
        if native is None:
            self.skipTest("native extension module not built (see native/README or run maturin develop)")
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

    def _write_and_reload(self, data):
        out_path = os.path.join(self._tmpdir.name, "out.xml")
        native.write_skin_xml(
            out_path,
            data["file_name"],
            data["world_matrix"],
            data["deformer_name"],
            data["deformer_type"],
            data["attributes"],
            data["shape_name"],
            data["group"],
            data["positions"],
            data["influence_names"],
            data["weight_matrix"],
            data["default_value"],
            1e-6,
            data["polygon_counts"],
            data["polygon_connects"],
        )
        return out_path

    def _assert_header_and_shape_match(self, generated_path, reference_path):
        gen_root = ET.parse(generated_path).getroot()
        ref_root = ET.parse(reference_path).getroot()
        gen_header = gen_root.find("headerInfo")
        ref_header = ref_root.find("headerInfo")
        self.assertEqual(
            gen_header.attrib["worldMatrix"], ref_header.attrib["worldMatrix"]
        )
        gen_deformer = gen_root.find("deformer")
        ref_deformer = ref_root.find("deformer")
        self.assertEqual(gen_deformer.attrib, ref_deformer.attrib)
        self.assertEqual(
            [(a.attrib["name"], a.attrib["type"], a.attrib["value"]) for a in gen_deformer],
            [(a.attrib["name"], a.attrib["type"], a.attrib["value"]) for a in ref_deformer],
        )
        gen_shape = gen_root.find("shape")
        ref_shape = ref_root.find("shape")
        self.assertEqual(gen_shape.attrib, ref_shape.attrib)
        self.assertEqual(
            [(p.attrib["index"], p.attrib["value"]) for p in gen_shape if p.tag == "point"],
            [(p.attrib["index"], p.attrib["value"]) for p in ref_shape if p.tag == "point"],
        )
        gen_counts = gen_shape.find("polygonCounts")
        ref_counts = ref_shape.find("polygonCounts")
        self.assertEqual(
            gen_counts.attrib if gen_counts is not None else None,
            ref_counts.attrib if ref_counts is not None else None,
        )
        gen_connects = gen_shape.find("polygonConnects")
        ref_connects = ref_shape.find("polygonConnects")
        self.assertEqual(
            gen_connects.attrib if gen_connects is not None else None,
            ref_connects.attrib if ref_connects is not None else None,
        )

    def _assert_weights_semantically_equal(
        self,
        generated_path,
        reference_path,
        influence_names,
        num_verts,
    ):
        """
        Compares effective weight values (via build_weight_matrix), not raw
        XML structure: a real Maya export sometimes writes explicit
        value="0.000000" points that write_skin_xml's tolerance-based sparse
        writer omits. Both are 0.0 on read-back, so this is the correct
        equivalence to test, not byte-identical <point> lists.
        """
        gen_matrix = native.build_weight_matrix(
            generated_path, influence_names, num_verts
        )
        ref_matrix = py_reference_weight_matrix(
            reference_path, influence_names, num_verts
        )
        self.assertEqual(gen_matrix, ref_matrix)

    def test_matches_real_maya_sample_sparse_no_vertex_connections(self):
        """
        sample_skin_sparse_three_joints.xml: real Maya export (3 joints,
        sparse weights, no vertexConnections). Covers layer ordering and the
        sparse write path.
        """
        reference = os.path.join(FIXTURES, "sample_skin_sparse_three_joints.xml")
        data = _parse_write_inputs(reference)
        generated = self._write_and_reload(data)
        self._assert_header_and_shape_match(generated, reference)
        self._assert_weights_semantically_equal(
            generated, reference, data["influence_names"], data["num_verts"]
        )

    def test_matches_real_maya_sample_with_vertex_connections(self):
        """
        sample_skin_vertex_connections.xml: real Maya export with
        vertexConnections=True (polygonCounts/polygonConnects present).
        Covers the mesh-topology output path used for interop with Maya's
        stock importer and spatial import methods.
        """
        reference = os.path.join(FIXTURES, "sample_skin_vertex_connections.xml")
        data = _parse_write_inputs(reference)
        generated = self._write_and_reload(data)
        self._assert_header_and_shape_match(generated, reference)
        self._assert_weights_semantically_equal(
            generated, reference, data["influence_names"], data["num_verts"]
        )

    def test_matches_real_maya_sample_simple_two_joints(self):
        """sample_skin_plane_two_joints.xml: the original small real-Maya sample."""
        reference = os.path.join(FIXTURES, "sample_skin_plane_two_joints.xml")
        data = _parse_write_inputs(reference)
        generated = self._write_and_reload(data)
        self._assert_header_and_shape_match(generated, reference)
        self._assert_weights_semantically_equal(
            generated, reference, data["influence_names"], data["num_verts"]
        )

    def test_column_order_follows_influence_names_order(self):
        """
        Weight columns must follow the caller-supplied influence_names order
        (e.g. MFnSkinCluster.influenceObjects() in production), not any
        implicit ordering -- verified with an intentionally reordered
        influence list against the asymmetric-weight fixture.
        """
        reference = os.path.join(
            FIXTURES, "sample_skin_plane_two_joints_asymmetric.xml"
        )
        data = _parse_write_inputs(reference)
        reordered = dict(data)
        reordered["influence_names"] = list(reversed(data["influence_names"]))
        num_inf = len(reordered["influence_names"])
        num_verts = data["num_verts"]
        reordered_matrix = [0.0] * (num_verts * num_inf)
        for row in range(num_verts):
            for old_col in range(num_inf):
                new_col = num_inf - 1 - old_col
                reordered_matrix[row * num_inf + new_col] = data["weight_matrix"][
                    row * num_inf + old_col
                ]
        reordered["weight_matrix"] = reordered_matrix

        generated = self._write_and_reload(reordered)
        gen_matrix = native.build_weight_matrix(
            generated, reordered["influence_names"], num_verts
        )
        self.assertEqual(gen_matrix, reordered_matrix)

    def test_zero_weight_below_tolerance_is_omitted(self):
        data = {
            "file_name": "t.xml", "world_matrix": [1.0] * 16,
            "deformer_name": "skc", "deformer_type": "skinCluster",
            "attributes": [], "shape_name": "shp", "group": 0,
            "positions": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            "influence_names": ["j0", "j1"],
            "weight_matrix": [1.0, 0.0, 0.0000001, 0.9999999],
            "default_value": 0.0, "polygon_counts": [], "polygon_connects": [],
        }
        out_path = self._write_and_reload(data)
        root = ET.parse(out_path).getroot()
        j0_block = next(w for w in root if w.tag == "weights" and w.attrib["source"] == "j0")
        j1_block = next(w for w in root if w.tag == "weights" and w.attrib["source"] == "j1")
        j0_indices = {p.attrib["index"] for p in j0_block}
        j1_indices = {p.attrib["index"] for p in j1_block}
        self.assertEqual(j0_indices, {"0"})
        self.assertEqual(j1_indices, {"1"})


DEFORMER_MULTI_SHAPE_FIXTURE = os.path.join(
    FIXTURES, "sample_deformer_multi_shape.xml"
)


class TestReadDeformerWeights(unittest.TestCase):
    """
    native.read_deformer_weights is wipskin's own deformer-weight XML
    reader (customDeformerWeight root; weightList-based deformers --
    cluster/softMod/wrap/etc, NOT blendShape). Verified against the existing
    hand-written multi-shape fixture used by tests/test_deformer.py, so both
    the Python parser (deformer.parse_file_info) and this Rust reader are
    checked against the same on-disk contract.
    """

    def setUp(self):
        if native is None:
            self.skipTest("native extension module not built (see native/README or run maturin develop)")

    def test_reads_correct_shape_block_by_shape_attribute(self):
        sphere = native.read_deformer_weights(
            DEFORMER_MULTI_SHAPE_FIXTURE, "pSphereShape1", 2
        )
        cube = native.read_deformer_weights(
            DEFORMER_MULTI_SHAPE_FIXTURE, "pCubeShape1", 2
        )
        self.assertEqual(sphere, [1.0, 0.25])
        self.assertEqual(cube, [0.5, 0.75])

    def test_unknown_shape_returns_all_defaults(self):
        # No <weights shape="..."> block matches -> every vertex keeps the
        # default (1.0), mirroring deformer._read_deformer_weights' own
        # default=1.0 for an unreadable/missing attribute.
        result = native.read_deformer_weights(
            DEFORMER_MULTI_SHAPE_FIXTURE, "noSuchShape", 3
        )
        self.assertEqual(result, [1.0, 1.0, 1.0])


class TestWriteDeformerWeightXml(unittest.TestCase):
    """
    native.write_deformer_weight_xml is the Rust counterpart of
    deformer.py's ElementTree-based _export_deformer_weight_xml (wipskin's
    own customDeformerWeight format, not a Maya-native one -- see
    docs/OPTIMIZATION_TECHNIQUES.md). Multi-shape safe: every *_list
    argument must have one entry per shape.
    """

    def setUp(self):
        if native is None:
            self.skipTest("native extension module not built (see native/README or run maturin develop)")
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)

    def test_round_trip_two_shapes(self):
        out_path = os.path.join(self._tmpdir.name, "cluster1.xml")
        shape_names = ["pSphereShape1", "pCubeShape1"]
        identity_matrix = [
            1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0,
        ]
        world_matrices = [identity_matrix, identity_matrix]
        positions_list = [
            [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 1.0, 1.0, 0.0],
        ]
        polygon_counts_list = [[3], [3]]
        polygon_connects_list = [[0, 1, 0], [0, 1, 0]]
        weights_list = [
            [0.774758, 0.111132],
            [0.5, 1.0],
        ]

        native.write_deformer_weight_xml(
            out_path, "cluster1.xml", "cluster1",
            shape_names, world_matrices, positions_list,
            polygon_counts_list, polygon_connects_list, weights_list,
        )

        root = ET.parse(out_path).getroot()
        self.assertEqual(root.tag, "customDeformerWeight")
        shapes = [el for el in root if el.tag == "shape"]
        weights_blocks = [el for el in root if el.tag == "weights"]
        # All <shape> blocks come before all <weights> blocks, matching
        # deformer.py's own two-phase layout.
        self.assertEqual([s.attrib["name"] for s in shapes], shape_names)
        self.assertEqual(
            [w.attrib["shape"] for w in weights_blocks], shape_names
        )
        self.assertTrue(
            all(w.attrib["source"] == "baseLayer" for w in weights_blocks)
        )

        for i, name in enumerate(shape_names):
            got = native.read_deformer_weights(out_path, name, len(weights_list[i]))
            self.assertEqual(got, weights_list[i])

    def test_matches_existing_multi_shape_fixture_shape_and_weights(self):
        """
        Reconstructs the hand-written sample_deformer_multi_shape.xml fixture
        (positions/topology invented since that fixture omits them for
        brevity) and checks the parts that fixture DOES specify -- shape
        names, weights-per-shape association, and weight values -- match.
        """
        out_path = os.path.join(self._tmpdir.name, "cluster1.xml")
        shape_names = ["pSphereShape1", "pCubeShape1"]
        identity_matrix = [1.0] * 16
        positions_list = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0]] * 2
        polygon_counts_list = [[3]] * 2
        polygon_connects_list = [[0, 1, 0]] * 2
        weights_list = [[1.0, 0.25], [0.5, 0.75]]

        native.write_deformer_weight_xml(
            out_path, "cluster_multi.xml", "cluster1",
            shape_names, [identity_matrix] * 2, positions_list,
            polygon_counts_list, polygon_connects_list, weights_list,
        )

        for i, name in enumerate(shape_names):
            got = native.read_deformer_weights(out_path, name, 2)
            expected = native.read_deformer_weights(
                DEFORMER_MULTI_SHAPE_FIXTURE, name, 2
            )
            self.assertEqual(got, expected, weights_list[i])


if __name__ == "__main__":
    unittest.main()
