"""The example plugin (examples/plugins/wipskin_jsonskin) keeps working.

It doubles as the template third-party authors copy, so it runs the same
contract checks they would (wipskin.api.testing). No Maya required.
"""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
EXAMPLES = os.path.join(REPO_ROOT, "examples", "plugins")
for path in (PARENT, EXAMPLES):
    if path not in sys.path:
        sys.path.insert(0, path)

from wipskin import api
from wipskin.api.testing import SkinFormatContractTests
from wipskin_jsonskin.format import JsonSkinFormat


class TestJsonSkinContract(SkinFormatContractTests, unittest.TestCase):

    format_class = JsonSkinFormat

    def make_sample_data(self):
        return api.SkinWeightData(
            "body", ["hip", "knee"], [1.0, 0.0, 0.25, 0.75, 0.0, 1.0],
        )


class TestJsonSkinFile(unittest.TestCase):

    def test_file_stores_sparse_vertex_rows(self):
        data = api.SkinWeightData("body", ["hip", "knee"], [1.0, 0.0, 0.25, 0.75])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.jsonskin")
            JsonSkinFormat().write_weights(path, data)
            with open(path, encoding="utf-8") as handle:
                document = json.load(handle)

        self.assertEqual(document["version"], 1)
        self.assertEqual(
            document["vertices"], [{"hip": 1.0}, {"hip": 0.25, "knee": 0.75}]
        )

    def test_rejects_an_unknown_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "body.jsonskin")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"version": 99}, handle)
            with self.assertRaises(ValueError):
                JsonSkinFormat().read_weights(path)

    def test_gets_import_export_from_the_shared_engine(self):
        self.assertTrue(JsonSkinFormat.has_weight_reader())
        self.assertTrue(JsonSkinFormat.has_weight_writer())


if __name__ == "__main__":
    unittest.main()
