import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import plugin_loader


class TestListPluginModuleNames(unittest.TestCase):

    def test_splits_like_path_entries_and_drops_blanks_and_repeats(self):
        value = os.pathsep.join([" studio.fmt ", "", "other", "studio.fmt"])
        self.assertEqual(
            plugin_loader.list_plugin_module_names(value),
            ["studio.fmt", "other"],
        )

    def test_unset_variable_means_no_plugins(self):
        environ = dict(os.environ)
        environ.pop(plugin_loader.ENV_VAR, None)
        original = os.environ
        try:
            os.environ = environ
            self.assertEqual(plugin_loader.list_plugin_module_names(), [])
        finally:
            os.environ = original


class _TempModules(unittest.TestCase):
    """Writes throwaway modules to a temp dir on sys.path."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        sys.path.insert(0, self._dir.name)
        self.addCleanup(sys.path.remove, self._dir.name)
        self._names = []
        self.addCleanup(self._forget_modules)

    def write_module(self, name, source):
        with open(os.path.join(self._dir.name, f"{name}.py"), "w") as handle:
            handle.write(source)
        self._names.append(name)

    def _forget_modules(self):
        for name in self._names:
            sys.modules.pop(name, None)


class TestImportPluginModules(_TempModules):

    def test_a_failing_plugin_does_not_stop_the_others(self):
        self.write_module("_wipskin_test_ok", "LOADED = True\n")
        self.write_module("_wipskin_test_bad", "raise RuntimeError('boom')\n")
        errors = []
        imported = plugin_loader.import_plugin_modules(
            ["_wipskin_test_bad", "_wipskin_test_missing", "_wipskin_test_ok"],
            on_error=lambda name, exc: errors.append((name, type(exc))),
        )
        self.assertEqual(imported, ["_wipskin_test_ok"])
        self.assertEqual(
            errors,
            [
                ("_wipskin_test_bad", RuntimeError),
                ("_wipskin_test_missing", ModuleNotFoundError),
            ],
        )
        self.assertTrue(sys.modules["_wipskin_test_ok"].LOADED)


class TestDropModules(unittest.TestCase):

    def setUp(self):
        self._saved = {
            name: sys.modules.get(name)
            for name in ("_wsk_pkg", "_wsk_pkg.sub", "_wsk_pkg2")
        }
        for name in self._saved:
            sys.modules[name] = object()
        self.addCleanup(self._restore)

    def _restore(self):
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_drops_the_module_and_its_submodules_only(self):
        dropped = plugin_loader.drop_modules(["_wsk_pkg"])
        self.assertEqual(sorted(dropped), ["_wsk_pkg", "_wsk_pkg.sub"])
        self.assertNotIn("_wsk_pkg", sys.modules)
        self.assertNotIn("_wsk_pkg.sub", sys.modules)
        self.assertIn("_wsk_pkg2", sys.modules)


if __name__ == "__main__":
    unittest.main()
