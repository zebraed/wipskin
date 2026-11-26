"""
Guards for the import-time boundary of the public packages (no Maya required).

Importing wipskin and wipskin.api must NOT load Maya or Qt: showUI,
register_skin_format and Reload import their heavy dependencies when called,
so scripts and plugins can import the package outside Maya.
"""

import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")

HEAVY_PACKAGES = ("maya", "PySide2", "PySide6", "shiboken2", "shiboken6")


class TestPackageImportPurity(unittest.TestCase):

    def _assert_import_loads_no_heavy_package(self, statement):
        code = (
            "import sys\n"
            f"{statement}\n"
            f"heavy = {HEAVY_PACKAGES!r}\n"
            "loaded = sorted(\n"
            "    name for name in sys.modules\n"
            "    if name.split('.')[0] in heavy\n"
            ")\n"
            "assert not loaded, 'loaded at import: %s' % loaded\n"
            "print('ok')\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = PARENT + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_import_wipskin_does_not_load_maya_or_qt(self):
        self._assert_import_loads_no_heavy_package("import wipskin")

    def test_import_wipskin_api_does_not_load_maya_or_qt(self):
        self._assert_import_loads_no_heavy_package("import wipskin.api")


if __name__ == "__main__":
    unittest.main()
