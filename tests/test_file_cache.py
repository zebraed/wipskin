"""Unit tests for wipskin.core.file_cache (no Maya/Qt required)."""

import os
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import file_cache

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SKIN_FIXTURE = os.path.join(FIXTURES, "sample_skin.xml")


class TestMemoizeByStat(unittest.TestCase):

    def setUp(self):
        file_cache.clear_cache()

    def _counting_compute(self):
        calls = {"n": 0}

        def compute(path):
            calls["n"] += 1
            return {"path": path, "n": calls["n"]}

        return compute, calls

    def test_runs_compute_once_while_file_is_unchanged(self):
        compute, calls = self._counting_compute()
        first = file_cache.memoize_by_stat(SKIN_FIXTURE, compute)
        second = file_cache.memoize_by_stat(SKIN_FIXTURE, compute)
        self.assertIs(first, second)
        self.assertEqual(calls["n"], 1)

    def test_changed_file_recomputes(self):
        compute, calls = self._counting_compute()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "w.txt")
            with open(path, "w") as handle:
                handle.write("one")
            file_cache.memoize_by_stat(path, compute)
            self.assertEqual(calls["n"], 1)

            time.sleep(0.01)
            with open(path, "w") as handle:
                handle.write("two different")
            os.utime(path, None)
            file_cache.memoize_by_stat(path, compute)
            self.assertEqual(calls["n"], 2)

    def test_unstattable_path_bypasses_cache(self):
        compute, calls = self._counting_compute()
        missing = os.path.join(FIXTURES, "does_not_exist.xml")
        file_cache.memoize_by_stat(missing, compute)
        file_cache.memoize_by_stat(missing, compute)
        self.assertEqual(calls["n"], 2)

    def test_clear_cache_forces_recompute(self):
        compute, calls = self._counting_compute()
        file_cache.memoize_by_stat(SKIN_FIXTURE, compute)
        file_cache.clear_cache()
        file_cache.memoize_by_stat(SKIN_FIXTURE, compute)
        self.assertEqual(calls["n"], 2)


class TestGetStatStamp(unittest.TestCase):

    def test_missing_path_returns_none(self):
        self.assertIsNone(
            file_cache.get_stat_stamp(os.path.join(FIXTURES, "nope.xml"))
        )

    def test_existing_path_returns_mtime_and_size(self):
        stamp = file_cache.get_stat_stamp(SKIN_FIXTURE)
        self.assertEqual(len(stamp), 2)
        self.assertEqual(stamp[1], os.path.getsize(SKIN_FIXTURE))


if __name__ == "__main__":
    unittest.main()
