import os
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from unittest import mock

from wipskin.core.constants import REQUESTED_DEFAULTS
from wipskin.plugins.mgear import constants as mgear_constants
from wipskin.plugins.mgear.constants import MODE_MGEAR
from wipskin.plugins.ngskintools import constants as ngskintools_constants
from wipskin.plugins.ngskintools.constants import MODE_NGSKINTOOLS
from wipskin.formats.skin.xml import constants as xml_constants
from wipskin.formats.skin.xml.constants import MODE_XML
from wipskin.formats.skin.base import (
    Availability,
    SkinWeightFormat,
    ViewerInfo,
    check_can_register,
    get_declared_defaults,
    merge_default_settings,
    select_available_format,
)
from wipskin.plugins.mgear import weights as mgear_weights
from wipskin.plugins.mgear.format import MgearSkinWeightFormat
from wipskin.plugins.ngskintools.format import NgSkinToolsSkinWeightFormat

# XmlSkinWeightFormat pulls formats.xml.skin, which needs Maya.
try:
    from wipskin.formats.skin.xml.format import XmlSkinWeightFormat
except ImportError:
    XmlSkinWeightFormat = None


def _maya_free_formats():
    return [MgearSkinWeightFormat, NgSkinToolsSkinWeightFormat]


class TestSkinWeightFormatContract(unittest.TestCase):

    REQUIRED = {
        "mode": "m",
        "label": "L",
        "extensions": ("x",),
    }

    def test_subclass_must_define_identity_fields(self):
        for missing in self.REQUIRED:
            with self.subTest(missing=missing):
                attrs = {k: v for k, v in self.REQUIRED.items() if k != missing}
                with self.assertRaises(TypeError) as ctx:
                    type("Broken", (SkinWeightFormat,), attrs)
                self.assertIn(missing, str(ctx.exception))

    def test_fully_defined_subclass_is_accepted(self):
        cls = type("Complete", (SkinWeightFormat,), dict(self.REQUIRED))
        self.assertEqual(cls().get_primary_extension(), "x")

    def test_minimal_format_gets_defaults_for_the_rest(self):
        cls = type("Minimal", (SkinWeightFormat,), dict(self.REQUIRED))
        self.assertEqual(cls.viewer_title, "L Viewer")
        self.assertEqual(cls.metadata_format, "m")
        self.assertEqual(
            cls.export_auto_naming_setting, "setting_wipskin_m_exportAutoNaming"
        )
        self.assertTrue(cls.generated_auto_naming_setting)
        self.assertEqual(
            get_declared_defaults(cls()),
            {"setting_wipskin_m_exportAutoNaming": False},
        )
        self.assertEqual(cls().describe("any.x"), ViewerInfo())

    def test_explicit_values_win_over_defaults(self):
        attrs = dict(
            self.REQUIRED, viewer_title="V", metadata_format="f",
            export_auto_naming_setting="s",
        )
        cls = type("Explicit", (SkinWeightFormat,), attrs)
        self.assertEqual(
            (cls.viewer_title, cls.metadata_format, cls.export_auto_naming_setting),
            ("V", "f", "s"),
        )
        self.assertFalse(cls.generated_auto_naming_setting)
        self.assertEqual(get_declared_defaults(cls()), {})

    def test_minimal_format_passes_registration_checks(self):
        cls = type("Minimal", (SkinWeightFormat,), dict(self.REQUIRED))
        check_can_register([], cls(), set())

    def test_builtin_formats_keep_their_explicit_names(self):
        self.assertEqual(MgearSkinWeightFormat.viewer_title, "mGear Viewer")
        self.assertFalse(MgearSkinWeightFormat.generated_auto_naming_setting)
        self.assertEqual(
            NgSkinToolsSkinWeightFormat.viewer_title, "ngSkinTools Viewer"
        )

    def test_modes_are_known_and_unique(self):
        modes = [cls.mode for cls in _maya_free_formats()]
        for mode in modes:
            self.assertIn(mode, (MODE_MGEAR, MODE_NGSKINTOOLS, MODE_XML))
        self.assertEqual(len(modes), len(set(modes)))

    def test_primary_extension_is_first_extension(self):
        fmt = MgearSkinWeightFormat()
        self.assertEqual(fmt.get_primary_extension(), fmt.extensions[0])

    def test_bundled_formats_do_not_support_temp_file(self):
        for cls in _maya_free_formats():
            with self.subTest(cls=cls.__name__):
                self.assertFalse(cls.supports_temp_file)

    def test_temp_file_path_exists_exactly_when_temp_is_supported(self):
        for cls in _maya_free_formats():
            with self.subTest(cls=cls.__name__):
                self.assertEqual(
                    cls().get_temp_file_path() is not None,
                    cls.supports_temp_file,
                )

    def test_bundled_formats_are_text(self):
        for cls in _maya_free_formats():
            with self.subTest(cls=cls.__name__):
                self.assertTrue(cls.is_text_format)

    def test_opposite_side_is_narrower_than_text_format(self):
        # mGear files are text too, but the entry is deliberately XML-only.
        self.assertTrue(MgearSkinWeightFormat.is_text_format)
        self.assertFalse(MgearSkinWeightFormat.supports_opposite_side)
        self.assertFalse(NgSkinToolsSkinWeightFormat.supports_opposite_side)

    def test_ngskintools_influences_are_joints(self):
        self.assertEqual(
            NgSkinToolsSkinWeightFormat().influence_node_types(), ("joint",)
        )
        self.assertIsNone(MgearSkinWeightFormat().influence_node_types())

    def test_extensions_are_non_empty_dotless(self):
        for cls in _maya_free_formats():
            with self.subTest(cls=cls.__name__):
                self.assertTrue(cls.extensions)
                for ext in cls.extensions:
                    self.assertFalse(ext.startswith("."))


class TestPackFilenames(unittest.TestCase):
    """Pack manifests are the files the tab tints green."""

    def test_mgear_packs_are_recognized_case_insensitively(self):
        fmt = MgearSkinWeightFormat()
        for name in ("rig.gSkinPack", "rig.0002.gskinpack", "rig.jSkinPack"):
            with self.subTest(name=name):
                self.assertTrue(fmt.is_pack_filename(name))

    def test_mgear_member_files_are_not_packs(self):
        fmt = MgearSkinWeightFormat()
        for name in ("body.jSkin", "body.0003.gSkin", "body"):
            with self.subTest(name=name):
                self.assertFalse(fmt.is_pack_filename(name))

    def test_ngskintools_declares_no_packs(self):
        fmt = NgSkinToolsSkinWeightFormat()
        self.assertEqual(fmt.pack_extensions, ())
        self.assertFalse(fmt.is_pack_filename("body.json"))

    def test_xml_wip_is_a_pack_including_its_subdir_prefix(self):
        if XmlSkinWeightFormat is None:
            self.skipTest("Maya not available")

        fmt = XmlSkinWeightFormat()
        self.assertTrue(fmt.is_pack_filename("rig_wip/rig.0001.wip"))
        self.assertFalse(fmt.is_pack_filename("rig.xml"))


def _fake_format(mode, rank=100, availability=Availability.AVAILABLE,
                 defaults=None):
    attrs = {
        "mode": mode,
        "label": mode,
        "viewer_title": mode,
        "extensions": (mode,),
        "export_auto_naming_setting": f"auto_{mode}",
        "metadata_format": mode,
        "fallback_rank": rank,
        "get_availability": classmethod(lambda cls: availability),
    }
    if defaults is not None:
        attrs["get_default_settings"] = lambda self: defaults
    return type(f"Fake_{mode}", (SkinWeightFormat,), attrs)()


class TestAvailability(unittest.TestCase):

    def test_mgear_is_not_installed_when_its_package_is_absent(self):
        with mock.patch.object(mgear_weights, "is_available",
                               return_value=False):
            self.assertIs(
                MgearSkinWeightFormat.get_availability(),
                Availability.NOT_INSTALLED,
            )
        with mock.patch.object(mgear_weights, "is_available",
                               return_value=True):
            self.assertIs(
                MgearSkinWeightFormat.get_availability(),
                Availability.AVAILABLE,
            )

    def test_unavailable_reason_is_empty_only_when_available(self):
        with mock.patch.object(mgear_weights, "is_available", return_value=False):
            self.assertIn("mGear", MgearSkinWeightFormat.get_unavailable_reason())

        with mock.patch.object(mgear_weights, "is_available", return_value=True):
            self.assertEqual(MgearSkinWeightFormat.get_unavailable_reason(), "")


class TestSelectAvailableFormat(unittest.TestCase):

    def setUp(self):
        self.xml = _fake_format("xml", rank=1)
        self.mgear = _fake_format("mgear", rank=2)
        self.other = _fake_format("other", rank=0)
        self.formats = (self.xml, self.mgear, self.other)

    def test_saved_format_wins_when_it_can_run(self):
        picked = select_available_format(self.formats, "mgear")
        self.assertIs(picked, self.mgear)

    def test_lowest_rank_wins_without_a_saved_format(self):
        for saved in ("", "gone"):
            with self.subTest(saved=saved):
                picked = select_available_format(self.formats, saved)
                self.assertIs(picked, self.other)

    def test_unavailable_saved_format_falls_back_by_rank(self):
        other = _fake_format(
            "other", rank=0, availability=Availability.NOT_INSTALLED
        )
        formats = (self.xml, self.mgear, other)
        self.assertIs(select_available_format(formats, "other"), self.xml)

    def test_registration_order_does_not_decide_the_fallback(self):
        picked = select_available_format(
            (self.mgear, self.xml), "missing"
        )
        self.assertIs(picked, self.xml)

    def test_raises_when_nothing_can_run(self):
        none = _fake_format("x", availability=Availability.NOT_INSTALLED)
        with self.assertRaises(ValueError):
            select_available_format((none,), "x")

    def test_shipped_formats_keep_the_fallback_order(self):
        self.assertLess(
            MgearSkinWeightFormat.fallback_rank,
            NgSkinToolsSkinWeightFormat.fallback_rank,
        )
        if XmlSkinWeightFormat is not None:
            self.assertLess(
                XmlSkinWeightFormat.fallback_rank,
                MgearSkinWeightFormat.fallback_rank,
            )


class TestCheckCanRegister(unittest.TestCase):

    RESERVED = {"builtin_key", "auto_xml"}

    def setUp(self):
        self.registered = [_fake_format("xml")]

    def test_accepts_a_format_that_declares_its_auto_naming_default(self):
        new = _fake_format("studio", defaults={"auto_studio": False})
        check_can_register(self.registered, new, self.RESERVED)

    def test_accepts_an_auto_naming_key_with_a_built_in_default(self):
        new = _fake_format("studio")
        new.export_auto_naming_setting = "builtin_key"
        check_can_register(self.registered, new, self.RESERVED)

    def test_rejects_a_taken_mode(self):
        new = _fake_format("xml", defaults={"auto_xml2": False})
        with self.assertRaises(ValueError) as ctx:
            check_can_register(self.registered, new, self.RESERVED)
        self.assertIn("'xml'", str(ctx.exception))

    def test_rejects_a_missing_auto_naming_default(self):
        new = _fake_format("studio")
        with self.assertRaises(ValueError) as ctx:
            check_can_register(self.registered, new, self.RESERVED)
        self.assertIn("auto_studio", str(ctx.exception))

    def test_rejects_redeclaring_a_built_in_key(self):
        new = _fake_format(
            "studio", defaults={"auto_studio": False, "builtin_key": 1}
        )
        with self.assertRaises(ValueError) as ctx:
            check_can_register(self.registered, new, self.RESERVED)
        self.assertIn("builtin_key", str(ctx.exception))

    def test_rejects_a_key_another_format_declares(self):
        registered = [_fake_format("a", defaults={"shared": 1, "auto_a": 0})]
        new = _fake_format("b", defaults={"shared": 2, "auto_b": 0})
        with self.assertRaises(ValueError):
            check_can_register(registered, new, set())

    def test_rejects_something_that_is_not_a_format(self):
        with self.assertRaises(TypeError):
            check_can_register(self.registered, object(), self.RESERVED)

    def test_leaves_the_registered_list_untouched(self):
        new = _fake_format("studio", defaults={"auto_studio": False})
        check_can_register(self.registered, new, self.RESERVED)
        self.assertEqual([f.mode for f in self.registered], ["xml"])


class TestMergeDefaultSettings(unittest.TestCase):

    def test_builtin_formats_declare_their_constants_defaults(self):
        for cls, constants in (
            (MgearSkinWeightFormat, mgear_constants),
            (NgSkinToolsSkinWeightFormat, ngskintools_constants),
        ):
            with self.subTest(cls=cls.__name__):
                self.assertEqual(
                    cls().get_default_settings(), constants.DEFAULT_SETTINGS
                )

    def test_builtin_defaults_are_a_copy(self):
        defaults = MgearSkinWeightFormat().get_default_settings()
        defaults["mutated"] = True
        self.assertNotIn("mutated", mgear_constants.DEFAULT_SETTINGS)

    def test_builtin_defaults_never_overlap(self):
        tables = {
            "core": REQUESTED_DEFAULTS,
            "xml": xml_constants.DEFAULT_SETTINGS,
            "mgear": mgear_constants.DEFAULT_SETTINGS,
            "ngskintools": ngskintools_constants.DEFAULT_SETTINGS,
        }
        seen = {}
        for owner, table in tables.items():
            for key in table:
                with self.subTest(key=key):
                    self.assertNotIn(key, seen, f"{owner} and {seen.get(key)}")
                seen[key] = owner

    def test_builtin_formats_pass_registration_checks(self):
        registered = []
        for cls in _maya_free_formats():
            with self.subTest(cls=cls.__name__):
                check_can_register(registered, cls(), REQUESTED_DEFAULTS)
                registered.append(cls())

    def test_xml_constants_need_no_maya(self):
        # formats/skin/xml/weights.py needs Maya; its constants must not.
        self.assertEqual(xml_constants.MODE_XML, "xml")
        self.assertIn(
            xml_constants.SETTING_EXPORT_AUTO_NAMING_XML,
            xml_constants.DEFAULT_SETTINGS,
        )

    def test_merges_every_formats_keys(self):
        merged = merge_default_settings([
            _fake_format("a", defaults={"k_a": 1}),
            _fake_format("b", defaults={"k_b": "x"}),
        ])
        self.assertEqual(merged, {"k_a": 1, "k_b": "x"})

    def test_same_key_in_two_formats_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            merge_default_settings([
                _fake_format("a", defaults={"shared": 1}),
                _fake_format("b", defaults={"shared": 2}),
            ])
        self.assertIn("shared", str(ctx.exception))


class TestMetadataFormat(unittest.TestCase):
    """Sidecar "format" values must stay what existing sidecars hold."""

    def test_ngskintools_files_record_ngskintools(self):
        fmt = NgSkinToolsSkinWeightFormat()
        self.assertEqual(fmt.get_metadata_format("body.json"), "ngskintools")

    def test_mgear_files_and_packs_record_mgear(self):
        fmt = MgearSkinWeightFormat()
        for name in ("body.jSkin", "body.0002.gSkin", "rig.gSkinPack"):
            with self.subTest(name=name):
                self.assertEqual(fmt.get_metadata_format(name), "mgear")

    def test_xml_manifests_record_wip_and_xmls_record_xml(self):
        if XmlSkinWeightFormat is None:
            self.skipTest("Maya not available")

        fmt = XmlSkinWeightFormat()
        self.assertEqual(fmt.get_metadata_format("arm.0001.xml"), "xml")
        self.assertEqual(
            fmt.get_metadata_format("rig_wip/rig.0001.wip"), "wip"
        )

    def test_wip_member_value_matches_xml_skin(self):
        from wipskin.formats.skin.xml import wip

        self.assertEqual(wip.MEMBER_METADATA_FORMAT, "xml")
        if XmlSkinWeightFormat is not None:
            from wipskin.formats.skin.xml import weights as xml_skin

            self.assertEqual(
                wip.MEMBER_METADATA_FORMAT, xml_skin.METADATA_FORMAT
            )


class TestExpandFileNames(unittest.TestCase):
    """Archive and Delete act on what expand_file_names returns."""

    def test_default_acts_on_the_selection_as_is(self):
        names = ["rig.gSkinPack", "body.0001.jSkin"]
        for cls in _maya_free_formats():
            with self.subTest(cls=cls.__name__):
                expanded = cls().expand_file_names("any_dir", names)
                self.assertEqual(expanded, names)

    def test_default_returns_a_new_list(self):
        names = ["body.jSkin"]
        expanded = MgearSkinWeightFormat().expand_file_names("d", names)
        self.assertIsNot(expanded, names)

    def test_xml_expands_wip_entries_only(self):
        if XmlSkinWeightFormat is None:
            self.skipTest("Maya not available")

        from wipskin.formats.skin.xml import wip

        members = ["rig_wip/rig.0001.wip", "rig_wip/rig.Base.0001.xml"]
        with mock.patch.object(
            wip, "list_pack_version_names", return_value=members
        ) as list_members:
            expanded = XmlSkinWeightFormat().expand_file_names(
                "d", ["body.xml", "rig_wip/rig.0001.wip"]
            )

        list_members.assert_called_once_with("d", "rig_wip/rig.0001.wip")
        self.assertEqual(expanded, ["body.xml"] + members)


class TestXmlSkinWeightFormat(unittest.TestCase):

    def test_owns_xml_and_wip(self):
        if XmlSkinWeightFormat is None:
            self.skipTest("Maya not available")
        self.assertEqual(set(XmlSkinWeightFormat.extensions), {"xml", "wip"})



from wipskin.api.testing import SkinFormatContractTests  # noqa: E402


class TestMgearContract(SkinFormatContractTests, unittest.TestCase):
    """The bundled plugins pass the same checks third-party ones run."""

    format_class = MgearSkinWeightFormat


class TestNgSkinToolsContract(SkinFormatContractTests, unittest.TestCase):

    format_class = NgSkinToolsSkinWeightFormat


class TestXmlContract(SkinFormatContractTests, unittest.TestCase):

    # None outside Maya, which skips every check.
    format_class = XmlSkinWeightFormat


if __name__ == "__main__":
    unittest.main()
