"""The plugin template (wipskin/plugins/_template) stays valid but unloaded.

It is the folder authors copy, so it runs the same contract checks they
would. The boundary tests skip "_" folders; this file applies the same two
rules to it. No Maya required.
"""

import os
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin import api
from wipskin.api.testing import SkinFormatContractTests
from wipskin.plugins import BUNDLED_PLUGINS
from wipskin.plugins._template.format import TemplateSkinFormat

TEMPLATE_DIR = os.path.join(PARENT, "wipskin", "plugins", "_template")


class TestTemplateContract(SkinFormatContractTests, unittest.TestCase):

    format_class = TemplateSkinFormat

    def make_sample_data(self):
        return api.SkinWeightData(
            "body", ["hip", "knee"], [1.0, 0.0, 0.25, 0.75, 0.0, 1.0],
        )


class TestTemplateIsNotLoaded(unittest.TestCase):

    def test_it_is_not_a_bundled_plugin(self):
        for module in BUNDLED_PLUGINS:
            self.assertNotIn("_template", module)

    def test_importing_its_format_does_not_import_the_entry_module(self):
        # Only plugin.py registers; format.py alone must stay inert.
        self.assertNotIn("wipskin.plugins._template.plugin", sys.modules)

    def test_it_reaches_wipskin_only_through_the_api(self):
        import ast

        for name in ("format.py", "plugin.py", "constants.py"):
            with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] != "wipskin":
                        continue

                    with self.subTest(file=name, module=node.module):
                        self.assertTrue(
                            node.module == "wipskin"
                            or node.module.startswith("wipskin.api")
                            or node.module.startswith("wipskin.plugins._template"),
                            node.module,
                        )


if __name__ == "__main__":
    unittest.main()
