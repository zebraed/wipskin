"""
Unit tests for wipskin.xml_accel (no Maya/Qt required).

xml_accel is the dispatch point for the optional wipskin_native (Rust)
accelerator; every native_* function must degrade to None/False rather than
raising when the accelerator isn't loaded, since xml_skin.py/deformer.py rely
on that to fall back to their pure-Python paths.

Split out of the former tests/test_xml_probe.py alongside xml_probe.py's own
split into xml_sniff.py (see test_xml_sniff.py) and xml_accel.py (this).
"""

import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.formats import xml_accel


class TestNativeAvailable(unittest.TestCase):

    def test_native_available_returns_a_bool(self):
        # True/False depending on whether this checkout has a built .pyd --
        # either way it must be a plain bool, never None/raise.
        self.assertIsInstance(xml_accel.native_available(), bool)


class TestKillSwitchDegradesEveryEntryPoint(unittest.TestCase):
    """
    WIPSKIN_NO_NATIVE=1 forces _load_native() to return None regardless of
    whether a real wipskin_native.pyd is present, giving a deterministic way
    to exercise the "native unavailable" branch of every dispatch function
    without depending on this checkout's build state.
    """

    def _run(self, code):
        env = dict(os.environ)
        env["PYTHONPATH"] = PARENT + os.pathsep + env.get("PYTHONPATH", "")
        env["WIPSKIN_NO_NATIVE"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_native_available_is_false(self):
        code = (
            "from wipskin.formats import xml_accel\n"
            "assert xml_accel.native_available() is False\n"
            "print('ok')\n"
        )
        self.assertIn("ok", self._run(code))

    def test_read_paths_return_none_without_raising(self):
        code = (
            "from wipskin.formats import xml_accel\n"
            "assert xml_accel.native_build_weight_matrix('nope.xml', [], 0) is None\n"
            "assert xml_accel.native_read_deformer_weights('nope.xml', 's', 0) is None\n"
            "print('ok')\n"
        )
        self.assertIn("ok", self._run(code))

    def test_write_paths_return_false_without_touching_the_filesystem(self):
        code = (
            "from wipskin.formats import xml_accel\n"
            "assert xml_accel.native_write_skin_xml(\n"
            "    'nope.xml', 'nope.xml', [], 'skc', 'skinCluster', [],\n"
            "    'shape', 0, [], [], [], 0.0, 1e-6,\n"
            ") is False\n"
            "assert xml_accel.native_write_deformer_weight_xml(\n"
            "    'nope.xml', 'nope.xml', 'cluster1', [], [], [], [], [], [],\n"
            ") is False\n"
            "import os\n"
            "assert not os.path.exists('nope.xml')\n"
            "print('ok')\n"
        )
        self.assertIn("ok", self._run(code))


if __name__ == "__main__":
    unittest.main()
