"""
Guards the plugin boundary (no Maya required).

Bundled plugins (wipskin/plugins/<name>/) are written exactly like external
ones: they reach WipSkin only through wipskin.api, so whatever they need is
proven to be public. The core, in turn, never imports a plugin; it only
names the bundled ones for the loader.
"""

import ast
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
PACKAGE_DIR = os.path.join(PARENT, "wipskin")
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

# Base-class state that only built-in adapters may touch; plugins use
# self.host instead.
_PRIVATE_ADAPTER_ATTRS = {"_controller", "_view", "_settings", "_comment"}


def _iter_python_files(directory):
    for dirpath, _dirnames, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith(".py"):
                yield os.path.join(dirpath, filename)


def _imported_wipskin_modules(path):
    """(lineno, module, names) for every wipskin import in path."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "wipskin" or node.module.startswith("wipskin."):
                yield node.lineno, node.module, [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "wipskin" or alias.name.startswith("wipskin."):
                    yield node.lineno, alias.name, []


_QT_PACKAGES = {"PySide2", "PySide6", "shiboken2", "shiboken6"}


def _imported_modules(path):
    """(lineno, module) for every import in path, wipskin or not.

    ``from wipskin.api import ui`` counts as importing wipskin.api.ui.
    """
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.lineno, node.module
            for alias in node.names:
                yield node.lineno, f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name


def _base_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_api(module):
    return module == "wipskin.api" or module.startswith("wipskin.api.")


class TestPluginsImportOnlyTheApi(unittest.TestCase):

    def test_plugin_modules_import_wipskin_only_through_the_api(self):
        for name in sorted(os.listdir(PLUGINS_DIR)):
            plugin_dir = os.path.join(PLUGINS_DIR, name)
            if not os.path.isdir(plugin_dir) or name.startswith("_"):
                continue

            own_package = f"wipskin.plugins.{name}"
            for path in _iter_python_files(plugin_dir):
                for lineno, module, names in _imported_wipskin_modules(path):
                    with self.subTest(file=os.path.relpath(path, PARENT),
                                      line=lineno):
                        allowed = (
                            _is_api(module)
                            or module == own_package
                            or module.startswith(own_package + ".")
                            or (module == "wipskin" and names == ["api"])
                        )
                        self.assertTrue(
                            allowed,
                            f"imports {module} {names}; use wipskin.api",
                        )

    def test_plugin_non_ui_modules_stay_free_of_qt(self):
        # Each plugin mirrors the app's layers: constants/format/weights
        # carry no Qt (testable outside Maya's UI), everything Qt lives in
        # <plugin>/ui/. plugin.py, the entry module, wires the two together.
        for name in sorted(os.listdir(PLUGINS_DIR)):
            plugin_dir = os.path.join(PLUGINS_DIR, name)
            if not os.path.isdir(plugin_dir) or name.startswith("_"):
                continue

            ui_dir = os.path.join(plugin_dir, "ui")
            own_ui = f"wipskin.plugins.{name}.ui"
            for path in _iter_python_files(plugin_dir):
                if path.startswith(ui_dir + os.sep):
                    continue

                if os.path.basename(path) == "plugin.py":
                    continue

                rel = os.path.relpath(path, PARENT)
                for lineno, module in _imported_modules(path):
                    with self.subTest(file=rel, line=lineno):
                        is_ui = (
                            module == "wipskin.api.ui"
                            or module == own_ui
                            or module.startswith(own_ui + ".")
                            or module.split(".")[0] in _QT_PACKAGES
                        )
                        self.assertFalse(
                            is_ui, f"imports {module}; move it under ui/"
                        )

    def test_plugin_adapters_reach_the_tab_only_through_host(self):
        for path in _iter_python_files(PLUGINS_DIR):
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for adapter in ast.walk(tree):
                if not (
                    isinstance(adapter, ast.ClassDef)
                    and any(_base_name(b) == "SkinFormatIO" for b in adapter.bases)
                ):
                    continue

                for node in ast.walk(adapter):
                    if (
                        isinstance(node, ast.Attribute)
                        and isinstance(node.value, ast.Name)
                        and node.value.id == "self"
                        and node.attr in _PRIVATE_ADAPTER_ATTRS
                    ):
                        with self.subTest(file=os.path.relpath(path, PARENT),
                                          line=node.lineno):
                            self.fail(f"self.{node.attr}: use self.host")


class TestExamplePluginsImportOnlyTheApi(unittest.TestCase):
    """The examples are what third-party authors copy: same rule."""

    def test_example_plugins_import_wipskin_only_through_the_api(self):
        examples_dir = os.path.join(REPO_ROOT, "examples", "plugins")
        for path in _iter_python_files(examples_dir):
            for lineno, module, names in _imported_wipskin_modules(path):
                with self.subTest(file=os.path.relpath(path, REPO_ROOT),
                                  line=lineno):
                    self.assertTrue(
                        _is_api(module)
                        or (module == "wipskin" and names == ["api"]),
                        f"imports {module} {names}; use wipskin.api",
                    )


class TestCoreDoesNotImportPlugins(unittest.TestCase):

    # The loader's list of module names is the core's only tie to plugins.
    _ALLOWED = {
        os.path.join("wipskin", "ui", "window.py"): {"wipskin.plugins"},
    }

    def test_core_modules_never_import_a_plugin(self):
        for path in _iter_python_files(PACKAGE_DIR):
            if path.startswith(PLUGINS_DIR + os.sep):
                continue

            rel = os.path.relpath(path, PARENT)
            for lineno, module, _names in _imported_wipskin_modules(path):
                if module != "wipskin.plugins" and not module.startswith(
                    "wipskin.plugins."
                ):
                    continue

                with self.subTest(file=rel, line=lineno):
                    self.assertIn(module, self._ALLOWED.get(rel, set()))


class TestPureImports(unittest.TestCase):
    """wipskin.api and a plugin's pure modules load without Maya or Qt and
    register nothing, so plugin format code stays testable outside Maya.
    """

    def _run(self, code):
        env = dict(os.environ)
        env["PYTHONPATH"] = PARENT + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_api_and_plugin_formats_import_without_maya_or_qt(self):
        self._run(
            "import sys\n"
            "import wipskin.api\n"
            "from wipskin.plugins.mgear import constants, format, weights\n"
            "from wipskin.plugins.ngskintools import constants, format\n"
            "from wipskin.plugins.ngskintools import layer_file, weights\n"
            "assert 'ngSkinTools2' not in sys.modules\n"
            "loaded = [m for m in ('maya', 'PySide2', 'PySide6') if m in sys.modules]\n"
            "assert not loaded, loaded\n"
            "assert 'wipskin.ui.controllers.skin_formats.registry' not in sys.modules\n"
            "assert 'wipskin.formats.skin.engine' not in sys.modules\n"
            "print('ok')\n"
        )

    def test_minimal_plugin_format_needs_three_fields(self):
        self._run(
            "from wipskin import api\n"
            "class Xxx(api.SkinFormat):\n"
            "    mode = 'xxx'\n"
            "    label = 'XXX'\n"
            "    extensions = ('xxx',)\n"
            "fmt = Xxx()\n"
            "assert fmt.viewer_title == 'XXX Viewer'\n"
            "assert fmt.get_metadata_format('a.xxx') == 'xxx'\n"
            "assert fmt.describe('a.xxx') == api.ViewerInfo()\n"
            "print('ok')\n"
        )


if __name__ == "__main__":
    unittest.main()
