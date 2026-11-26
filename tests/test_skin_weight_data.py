"""SkinWeightData and the read/write (codec) hooks of SkinWeightFormat.

The shared engine that moves SkinWeightData in and out of a skinCluster
needs Maya; everything it relies on that does not is checked here.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin import api
from wipskin.formats.skin.base import SkinWeightData, ViewerInfo


def _data():
    # 3 vertices x 2 influences, vertex-major.
    return SkinWeightData(
        shape="body",
        influences=["hip", "knee"],
        weights=[1.0, 0.0, 0.25, 0.75, 0.0, 1.0],
    )


class TestSkinWeightData(unittest.TestCase):

    def test_vertex_count_follows_the_rows(self):
        self.assertEqual(_data().vertex_count, 3)

    def test_rejects_rows_that_do_not_fill(self):
        with self.assertRaises(ValueError):
            SkinWeightData(shape="s", influences=["a", "b"], weights=[1.0])

    def test_rejects_no_influence(self):
        with self.assertRaises(ValueError):
            SkinWeightData(shape="s", influences=[], weights=[])

    def test_rejects_repeated_influences(self):
        with self.assertRaises(ValueError):
            SkinWeightData(shape="s", influences=["a", "a"], weights=[1, 0])

    def test_weights_become_floats(self):
        data = SkinWeightData(shape="s", influences=["a"], weights=[1, 0])
        self.assertEqual(data.weights, [1.0, 0.0])
        self.assertIsInstance(data.weights[0], float)

    def test_from_vertex_weights_fills_missing_with_zero(self):
        data = SkinWeightData.from_vertex_weights(
            "body", [{"hip": 1.0}, {"hip": 0.25, "knee": 0.75}, {"knee": 1.0}],
        )
        self.assertEqual(data.influences, ["hip", "knee"])
        self.assertEqual(data.weights, _data().weights)

    def test_from_vertex_weights_keeps_a_given_column_order(self):
        data = SkinWeightData.from_vertex_weights(
            "body", [{"hip": 1.0}], influences=["knee", "hip"],
        )
        self.assertEqual(data.weights, [0.0, 1.0])

    def test_list_vertex_weights_round_trips_without_zeros(self):
        rows = _data().list_vertex_weights()
        self.assertEqual(rows, [
            {"hip": 1.0}, {"hip": 0.25, "knee": 0.75}, {"knee": 1.0},
        ])
        rebuilt = SkinWeightData.from_vertex_weights(
            "body", rows, influences=["hip", "knee"],
        )
        self.assertEqual(rebuilt.weights, _data().weights)


class TestBuildColumnMatrix(unittest.TestCase):
    """The remap apply_skin_weights does onto the skinCluster's columns."""

    def test_places_each_influence_in_its_column(self):
        # skinCluster order: [knee, extra, hip]
        matrix = _data().build_column_matrix([2, 0], 3)
        self.assertEqual(matrix, [
            0.0, 0.0, 1.0,
            0.75, 0.0, 0.25,
            1.0, 0.0, 0.0,
        ])

    def test_identity_order_is_a_copy(self):
        data = _data()
        self.assertEqual(data.build_column_matrix([0, 1], 2), data.weights)

    def test_rejects_wrong_or_clashing_columns(self):
        for columns, count in (([0], 2), ([0, 0], 2), ([0, 2], 2), ([-1, 0], 2)):
            with self.subTest(columns=columns):
                with self.assertRaises(ValueError):
                    _data().build_column_matrix(columns, count)


class _TextFormat(api.SkinFormat):
    """A tiny codec plugin: one line per vertex, "name=weight" pairs."""

    mode = "txtskin"
    label = "TxtSkin"
    extensions = ("txtskin",)

    def read_weights(self, path):
        with open(path, encoding="utf-8") as handle:
            shape = handle.readline().strip()
            rows = []
            for line in handle:
                pairs = (item.split("=") for item in line.split())
                rows.append({name: float(value) for name, value in pairs})
        return api.SkinWeightData.from_vertex_weights(shape, rows)

    def write_weights(self, path, data):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(data.shape + "\n")
            for row in data.list_vertex_weights():
                handle.write(
                    " ".join(f"{k}={v!r}" for k, v in row.items()) + "\n"
                )


class TestCodecHooks(unittest.TestCase):

    def test_plain_format_has_no_codec(self):
        class Plain(api.SkinFormat):
            mode = "plain"
            label = "Plain"
            extensions = ("plain",)

        self.assertFalse(Plain.has_weight_reader())
        self.assertFalse(Plain.has_weight_writer())
        self.assertEqual(Plain().describe("x.plain"), ViewerInfo())
        with self.assertRaises(NotImplementedError):
            Plain().read_weights("x.plain")

    def test_codec_format_is_detected(self):
        self.assertTrue(_TextFormat.has_weight_reader())
        self.assertTrue(_TextFormat.has_weight_writer())

    def test_codec_round_trip_and_default_viewer(self):
        fmt = _TextFormat()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.txtskin")
            fmt.write_weights(path, _data())
            data = fmt.read_weights(path)
            info = fmt.describe(path)

        self.assertEqual(data.shape, "body")
        self.assertEqual(data.influences, ["hip", "knee"])
        self.assertEqual(data.weights, _data().weights)
        self.assertEqual(
            info.meta_lines,
            ["Shape: body", "Vertices: 3", "Influences: 2"],
        )
        self.assertEqual(info.influences, ["hip", "knee"])


if __name__ == "__main__":
    unittest.main()
