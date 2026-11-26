"""ngSkinTools plugin: contract checks and the layer file reader (no Maya, no ngSkinTools2)."""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.api.testing import SkinFormatContractTests
from wipskin.plugins.ngskintools import layer_file
from wipskin.plugins.ngskintools.format import NgSkinToolsSkinWeightFormat

# Shape of an export_json file written by the ngSkinTools2 bundled with Maya 2027.
SAMPLE = {
    "mesh": {"triangles": [0, 1, 2], "vertPositions": [0.0] * 24},
    "layers": [
        {"id": 1, "name": "Base Weights", "parentId": None},
        {"id": 2, "name": "Cleanup", "parentId": None},
    ],
    "influences": [
        {"index": 0, "path": "|root|hip", "labelText": "", "labelSide": 0},
        {"index": 1, "path": "|knee", "labelText": "", "labelSide": 0},
    ],
}


def _write_json(directory, name, data):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)

    return path


class TestNgSkinToolsContract(SkinFormatContractTests, unittest.TestCase):

    format_class = NgSkinToolsSkinWeightFormat


class TestLayerFile(unittest.TestCase):

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory = self._directory.name

    def test_reads_layers_influences_and_vertex_count(self):
        path = _write_json(self.directory, "body.0001.json", SAMPLE)
        summary = layer_file.read_layer_file(path)
        self.assertEqual(summary.vertex_count, 8)
        self.assertEqual(summary.layer_names, ["Base Weights", "Cleanup"])
        self.assertEqual(summary.influences, ["|root|hip", "|knee"])

    def test_unnamed_layer_gets_a_numbered_name(self):
        data = dict(SAMPLE, layers=[{}])
        path = _write_json(self.directory, "body.json", data)
        self.assertEqual(layer_file.read_layer_file(path).layer_names, ["Layer 1"])

    def test_other_json_is_not_a_layer_file(self):
        other = _write_json(self.directory, "settings.json", {"layers": 3})
        listed = _write_json(self.directory, "list.json", [1, 2])
        broken = os.path.join(self.directory, "broken.json")
        with open(broken, "w", encoding="utf-8") as handle:
            handle.write("{")

        for path in (other, listed, broken):
            with self.subTest(path=os.path.basename(path)):
                self.assertFalse(layer_file.is_layer_file(path))
                with self.assertRaises(ValueError):
                    layer_file.read_layer_file(path)

    def test_missing_file_raises_oserror(self):
        with self.assertRaises(OSError):
            layer_file.read_layer_file(os.path.join(self.directory, "none.json"))

    def test_format_lists_only_layer_files(self):
        _write_json(self.directory, "body.0001.json", SAMPLE)
        _write_json(self.directory, "settings.json", {"a": 1})
        self.assertEqual(
            NgSkinToolsSkinWeightFormat().list_files(self.directory),
            ["body.0001.json"],
        )

    def test_describe_fills_the_viewer(self):
        path = _write_json(self.directory, "body.json", SAMPLE)
        info = NgSkinToolsSkinWeightFormat().describe(path)
        self.assertEqual(info.influences, ["hip", "knee"])
        self.assertEqual(
            info.meta_lines[:2], ["Layers: 2", "Vertices: 8"],
        )
        self.assertEqual(len(info.meta_lines), 4)

    def test_summary_keeps_the_layer_tree(self):
        data = dict(SAMPLE, layers=[
            {"id": 1, "name": "Top", "index": 0, "parentId": None},
            {"id": 2, "name": "Grp", "index": 1, "parentId": None},
            {"id": 3, "name": "A", "index": 0, "parentId": 2},
        ])
        path = _write_json(self.directory, "tree.json", data)
        self.assertEqual(
            layer_file.read_layer_file(path).layers,
            [
                layer_file.LayerEntry(1, "Top", None, 0),
                layer_file.LayerEntry(2, "Grp", None, 1),
                layer_file.LayerEntry(3, "A", 2, 0),
            ],
        )

    def test_full_path_only_where_short_names_collide(self):
        names = layer_file.list_display_names(
            ["|L|arm|hand", "|R|arm|hand", "|root|hip", "ns:knee"]
        )
        self.assertEqual(names, ["|L|arm|hand", "|R|arm|hand", "hip", "ns:knee"])


class _Imported:
    def __init__(self, id, name, parent_id, index):
        self.id = id
        self.name = name
        self.parent_id = parent_id
        self.index = index


class TestMatchImportedLayers(unittest.TestCase):

    FILE = [
        layer_file.LayerEntry(1, "Top", None, 0),
        layer_file.LayerEntry(2, "Grp", None, 1),
        layer_file.LayerEntry(3, "A", 2, 0),
        layer_file.LayerEntry(4, "B", 2, 1),
        layer_file.LayerEntry(5, "Last", None, 2),
    ]

    def test_pairs_by_tree_position_not_by_id(self):
        # Imported next to an existing layer: new ids, shifted indices.
        imported = [
            _Imported(6, "Last", None, 3),
            _Imported(3, "Grp", None, 2),
            _Imported(5, "B", 3, 1),
            _Imported(4, "A", 3, 0),
            _Imported(2, "Top", None, 1),
        ]
        matched = layer_file.match_imported_layers(self.FILE, imported)
        self.assertEqual(
            {file_id: layer.id for file_id, layer in matched.items()},
            {1: 2, 2: 3, 3: 4, 4: 5, 5: 6},
        )

    def test_a_different_shape_is_an_error(self):
        imported = [_Imported(2, "Top", None, 0)]
        with self.assertRaises(ValueError):
            layer_file.match_imported_layers(self.FILE, imported)

    def test_a_different_name_is_an_error(self):
        imported = [
            _Imported(1, "Top", None, 0),
            _Imported(2, "Other", None, 1),
            _Imported(3, "A", 2, 0),
            _Imported(4, "B", 2, 1),
            _Imported(5, "Last", None, 2),
        ]
        with self.assertRaises(ValueError):
            layer_file.match_imported_layers(self.FILE, imported)


if __name__ == "__main__":
    unittest.main()
