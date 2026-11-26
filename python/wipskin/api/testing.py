"""Contract checks a skin format plugin can run in its own test suite.

Mix SkinFormatContractTests into a unittest.TestCase and point it at your
format; no Maya needed::

    import unittest
    from wipskin import api
    from wipskin.api.testing import SkinFormatContractTests
    from my_plugin.format import MyFormat

    class TestMyFormatContract(SkinFormatContractTests, unittest.TestCase):
        format_class = MyFormat

        def make_sample_data(self):            # optional: enables round trip
            return api.SkinWeightData("body", ["hip", "knee"], [1, 0, 0.5, 0.5])

These are the checks wipskin.api.register_skin_format() and the SkinWeight
tab rely on; a format that passes them registers and lists its files.
"""

from __future__ import annotations

import os
import re
import tempfile

from wipskin.core.constants import REQUESTED_DEFAULTS
from wipskin.formats.skin.base import (
    SkinWeightData,
    SkinWeightFormat,
    ViewerInfo,
    check_can_register,
    get_declared_defaults,
)

# Modes end up in settings keys and sidecars: keep them identifier-like.
_MODE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class SkinFormatContractTests:
    """unittest mixin checking one SkinWeightFormat against the contract.

    Attributes:
        format_class (type): The SkinWeightFormat subclass under test.
    """

    format_class = None

    def make_sample_data(self):
        """SkinWeightData to write and read back; None skips the round trip.

        Returns:
            SkinWeightData | None: Sample weights for formats that implement
            write_weights and read_weights.
        """
        return None

    def _get_format(self):
        if self.format_class is None:
            self.skipTest("Set format_class to the format under test.")

        return self.format_class()

    def test_contract_is_a_skin_format(self):
        if self.format_class is None:
            self.skipTest("Set format_class to the format under test.")

        self.assertTrue(
            isinstance(self.format_class, type)
            and issubclass(self.format_class, SkinWeightFormat),
            "format_class must subclass wipskin.api.SkinFormat",
        )

    def test_contract_identity(self):
        fmt = self._get_format()
        self.assertRegex(fmt.mode, _MODE_PATTERN)
        self.assertTrue(fmt.label.strip(), "label must not be blank")
        self.assertTrue(fmt.viewer_title.strip())
        self.assertIsInstance(fmt.metadata_format, str)
        self.assertTrue(fmt.metadata_format)

    def test_contract_extensions(self):
        fmt = self._get_format()
        self.assertTrue(fmt.extensions, "declare at least one extension")
        for ext in (*fmt.extensions, *fmt.pack_extensions):
            with self.subTest(ext=ext):
                self.assertFalse(ext.startswith("."), "write extensions without a dot")
                self.assertTrue(ext.strip())

        lowered = [ext.lower() for ext in fmt.extensions]
        self.assertEqual(len(lowered), len(set(lowered)), "extensions repeat")
        self.assertIn(fmt.get_primary_extension(), fmt.extensions)
        for ext in fmt.pack_extensions:
            with self.subTest(pack=ext):
                self.assertIn(ext.lower(), lowered, "packs must be listed extensions")

    def test_contract_passes_registration_checks(self):
        check_can_register([], self._get_format(), REQUESTED_DEFAULTS)

    def test_contract_settings_defaults(self):
        fmt = self._get_format()
        defaults = get_declared_defaults(fmt)
        for key in defaults:
            with self.subTest(key=key):
                self.assertIsInstance(key, str)
                self.assertNotIn(key, REQUESTED_DEFAULTS)

        self.assertTrue(
            fmt.export_auto_naming_setting in defaults
            or fmt.export_auto_naming_setting in REQUESTED_DEFAULTS,
            "the Auto Naming key needs a default (see get_default_settings)",
        )

    def test_contract_availability(self):
        fmt = self._get_format()
        available = fmt.is_available()
        self.assertIsInstance(available, bool)
        reason = fmt.get_unavailable_reason()
        if available:
            self.assertEqual(reason, "")
        else:
            self.assertTrue(reason, "say why the format is unavailable")

    def test_contract_metadata_format_per_extension(self):
        fmt = self._get_format()
        for ext in fmt.extensions:
            with self.subTest(ext=ext):
                value = fmt.get_metadata_format(f"sample.{ext}")
                self.assertIsInstance(value, str)
                self.assertTrue(value)

    def test_contract_lists_its_files(self):
        fmt = self._get_format()
        if fmt.get_file_predicate() is not None:
            self.skipTest("list_files filters on file contents")

        with tempfile.TemporaryDirectory() as directory:
            expected = []
            for index, ext in enumerate(fmt.extensions):
                name = f"sample{index}.{ext}"
                open(os.path.join(directory, name), "w").close()
                expected.append(name)
            open(os.path.join(directory, "unrelated.notmine"), "w").close()
            listed = fmt.list_files(directory)

        self.assertEqual(sorted(listed), sorted(expected))

    def test_contract_weight_round_trip(self):
        fmt = self._get_format()
        if not (fmt.has_weight_writer() and fmt.has_weight_reader()):
            self.skipTest("format does not both read and write weights")

        data = self.make_sample_data()
        if data is None:
            self.skipTest("make_sample_data() returned None")

        self.assertIsInstance(data, SkinWeightData)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(
                directory, f"sample.{fmt.get_primary_extension()}"
            )
            fmt.write_weights(path, data)
            read_back = fmt.read_weights(path)
            info = fmt.describe(path)

        self.assertIsInstance(read_back, SkinWeightData)
        self.assertEqual(read_back.shape, data.shape)
        self.assertEqual(read_back.influences, data.influences)
        self.assertEqual(read_back.vertex_count, data.vertex_count)
        for got, want in zip(read_back.weights, data.weights):
            self.assertAlmostEqual(got, want, places=6)
        self.assertIsInstance(info, ViewerInfo)
