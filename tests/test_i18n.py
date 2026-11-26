"""The i18n catalog (no Maya or Qt required)."""

import json
import os
import string
import sys
import tempfile
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import i18n


def _write_catalog(directory, language, entries):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, f"{language}.json"), "w",
              encoding="utf-8") as stream:
        json.dump(entries, stream, ensure_ascii=False)


def _list_fields(text):
    return sorted(
        name for _lit, name, _spec, _conv in string.Formatter().parse(text)
        if name
    )


class _I18nTestCase(unittest.TestCase):
    """Leaves the module-level language state as it found it."""

    def setUp(self):
        self._saved = (
            dict(i18n._state), list(i18n._locale_dirs),
        )
        i18n._locale_dirs[:] = [i18n.LOCALE_DIR]
        i18n.set_language(i18n.DEFAULT_LANGUAGE)
        self.addCleanup(self._restore)

    def _restore(self):
        i18n._state.update(self._saved[0])
        i18n._locale_dirs[:] = self._saved[1]


class TestLanguage(_I18nTestCase):

    def test_default_language_returns_the_source(self):
        self.assertEqual(i18n.get_language(), "en")
        self.assertEqual(i18n.tr("Anything at all"), "Anything at all")

    def test_unknown_language_is_rejected_and_state_kept(self):
        i18n.set_language("ja")
        with self.assertRaises(ValueError):
            i18n.set_language("xx")
        self.assertEqual(i18n.get_language(), "ja")

    def test_every_language_has_a_core_catalog(self):
        for code in i18n.LANGUAGES:
            if code == i18n.DEFAULT_LANGUAGE:
                continue

            with self.subTest(code=code):
                path = os.path.join(i18n.LOCALE_DIR, f"{code}.json")
                self.assertTrue(os.path.isfile(path), path)


class TestTranslate(_I18nTestCase):

    def setUp(self):
        super().setUp()
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.plugin_dir = os.path.join(self._dir.name, "locales")
        _write_catalog(self.plugin_dir, "ja", {
            "Plugin only": "プラグインだけ",
            "Selected {name}": "{name}を選択",
        })

    def test_registered_catalog_translates_after_set_language(self):
        i18n.register_locales(self.plugin_dir)
        i18n.set_language("ja")
        self.assertEqual(i18n.tr("Plugin only"), "プラグインだけ")

    def test_registering_while_japanese_applies_at_once(self):
        i18n.set_language("ja")
        self.assertEqual(i18n.tr("Plugin only"), "Plugin only")
        i18n.register_locales(self.plugin_dir)
        self.assertEqual(i18n.tr("Plugin only"), "プラグインだけ")

    def test_registering_twice_is_harmless(self):
        i18n.register_locales(self.plugin_dir)
        i18n.register_locales(self.plugin_dir + os.sep)
        self.assertEqual(i18n.list_locale_dirs().count(
            os.path.normpath(os.path.abspath(self.plugin_dir))), 1)

    def test_untranslated_text_falls_back_to_the_source(self):
        i18n.register_locales(self.plugin_dir)
        i18n.set_language("ja")
        self.assertEqual(i18n.tr("Nobody translated this"),
                         "Nobody translated this")

    def test_fields_are_filled_in_translated_and_untranslated_text(self):
        i18n.register_locales(self.plugin_dir)
        i18n.set_language("ja")
        self.assertEqual(i18n.tr("Selected {name}", name="pCube1"),
                         "pCube1を選択")
        self.assertEqual(i18n.tr("Not there {name}", name="x"),
                         "Not there x")

    def test_braces_stay_when_no_fields_are_passed(self):
        self.assertEqual(i18n.tr("{literal}"), "{literal}")

    def test_later_registered_catalog_wins_a_clash(self):
        i18n.register_locales(self.plugin_dir)
        other = os.path.join(self._dir.name, "other")
        _write_catalog(other, "ja", {"Plugin only": "別の訳"})
        i18n.register_locales(other)
        i18n.set_language("ja")
        self.assertEqual(i18n.tr("Plugin only"), "別の訳")

    def test_plugin_without_the_language_is_skipped(self):
        empty = os.path.join(self._dir.name, "empty")
        os.makedirs(empty)
        i18n.register_locales(empty)
        self.assertEqual(i18n.set_language("ja"), [])

    def test_broken_plugin_catalog_is_reported_not_fatal(self):
        broken = os.path.join(self._dir.name, "broken")
        os.makedirs(broken)
        with open(os.path.join(broken, "ja.json"), "w") as stream:
            stream.write("{not json")
        i18n.register_locales(self.plugin_dir)
        i18n.register_locales(broken)
        problems = i18n.set_language("ja")
        self.assertEqual(len(problems), 1)
        self.assertIn("broken", problems[0])
        self.assertEqual(i18n.get_language(), "ja")
        self.assertEqual(i18n.tr("Plugin only"), "プラグインだけ")

    def test_non_object_plugin_catalog_is_reported(self):
        listy = os.path.join(self._dir.name, "listy")
        _write_catalog(listy, "ja", ["not", "an", "object"])
        i18n.register_locales(listy)
        self.assertEqual(len(i18n.set_language("ja")), 1)


class TestShippedCatalogs(_I18nTestCase):
    """The catalogs in the repository are well formed."""

    def _list_catalogs(self):
        plugins_dir = os.path.join(PARENT, "wipskin", "plugins")
        directories = [i18n.LOCALE_DIR]
        for name in sorted(os.listdir(plugins_dir)):
            locales = os.path.join(plugins_dir, name, "locales")
            if os.path.isdir(locales):
                directories.append(locales)
        for directory in directories:
            for filename in sorted(os.listdir(directory)):
                if filename.endswith(".json"):
                    yield os.path.join(directory, filename)

    def test_catalogs_are_json_objects_of_text_pairs(self):
        for path in self._list_catalogs():
            with self.subTest(path=os.path.relpath(path, PARENT)):
                catalog = i18n._read_catalog(path)
                for source, text in catalog.items():
                    self.assertIsInstance(source, str)
                    self.assertIsInstance(text, str)
                    self.assertTrue(text.strip(), f"empty translation: {source}")

    def test_every_entry_keeps_the_fields_of_its_source(self):
        for path in self._list_catalogs():
            with self.subTest(path=os.path.relpath(path, PARENT)):
                for source, text in i18n._read_catalog(path).items():
                    self.assertEqual(
                        _list_fields(text), _list_fields(source), source
                    )


if __name__ == "__main__":
    unittest.main()
