"""The shipped catalogs match the texts the code asks to translate.

Scans the source for ``tr("literal", ...)`` calls (and the viewer wording a
format declares as class attributes) and compares with the catalogs, so a new
UI text without a translation, or a catalog entry nothing uses any more,
fails here. No Maya or Qt required.

Texts that reach tr() through data instead of a literal are listed in
INDIRECT_KEYS.
"""

import ast
import json
import os
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

from wipskin.core import i18n

PACKAGE_DIR = os.path.join(PARENT, "wipskin")
PLUGINS_DIR = os.path.join(PACKAGE_DIR, "plugins")

# SkinWeightFormat attributes holding English wording the tab passes to tr().
FORMAT_WORDING_ATTRS = {
    "viewer_title",
    "viewer_selector_label",
    "viewer_selector_tooltip",
    "viewer_print_tooltip",
    "viewer_meta_tooltip",
}

# (scope, text): reaches tr() as data, not as a literal tr("...") argument.
INDIRECT_KEYS = {
    # tr(self._file_kind) / tr(label) over tables and defaults
    ("core", "weight"),
    ("core", "deformer weight"),
    ("core", "XML Viewer"),
    ("core", "Influences:"),
    ("core", "Not in scene"),
    ("core", "Continue"),
    ("core", "Existing files:"),
    ("core", "e.g. character_skin"),
    ("core", "Enter a valid base name."),
    ("core", "Right-click for recent weight directories."),
    ("core", "Select a weight file to inspect it."),
    ("core", "Item:"),
    ("core", "Summary metadata for the selected weight file."),
    # metadata.COMMENT_PLACEHOLDER_* are passed through tr() where shown
    ("core", "No comment written"),
    ("core", "Select a weight file first"),
    # gskin_pack_editor_dialog tables, shown through tr()
    ("mgear", "Member"), ("mgear", "Recorded"), ("mgear", "Latest"),
    ("mgear", "Scene"), ("mgear", "Action"), ("mgear", "Keep"),
    ("mgear", "Re-export"),
    # AUDIT_FIELDS label, translated by metadata.format_audit_lines
    ("mgear", "mGear version"),
}

# Source texts the catalog deliberately leaves English: a translation equal to
# the source adds nothing, so the entry is omitted.
UNTRANSLATED_OK = {"OK", "mGear Viewer"}


def _scope_of(path):
    rel = os.path.relpath(path, PACKAGE_DIR).replace(os.sep, "/")
    parts = rel.split("/")
    if parts[0] == "plugins" and len(parts) > 2:
        return parts[1]

    return "core"


def _iter_sources():
    for dirpath, _dirs, files in os.walk(PACKAGE_DIR):
        if "_native" in dirpath or "__pycache__" in dirpath:
            continue

        for name in files:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def _collect_keys():
    """{scope: {text: set of relative paths}} from the source tree."""
    scopes = {}
    for path in _iter_sources():
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        scope = _scope_of(path)
        found = scopes.setdefault(scope, {})
        rel = os.path.relpath(path, PACKAGE_DIR).replace(os.sep, "/")
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.setdefault(node.args[0].value, set()).add(rel)
            elif isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.Assign)
                        and isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)
                        and stmt.value.value
                        and any(
                            isinstance(t, ast.Name)
                            and t.id in FORMAT_WORDING_ATTRS
                            for t in stmt.targets
                        )
                    ):
                        found.setdefault(stmt.value.value, set()).add(rel)
    for scope, text in INDIRECT_KEYS:
        scopes.setdefault(scope, {}).setdefault(text, set()).add("(indirect)")
    return scopes


def _read_catalog(scope, language):
    folder = (
        i18n.LOCALE_DIR if scope == "core"
        else os.path.join(PLUGINS_DIR, scope, "locales")
    )
    path = os.path.join(folder, f"{language}.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class TestCatalogsMatchTheSource(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.keys = _collect_keys()
        cls.languages = [
            code for code in i18n.LANGUAGES if code != i18n.DEFAULT_LANGUAGE
        ]

    def _merged(self, language, scopes):
        merged = {}
        for scope in scopes:
            merged.update(_read_catalog(scope, language))
        return merged

    def test_every_text_the_code_translates_has_a_translation(self):
        for language in self.languages:
            for scope, found in self.keys.items():
                # A plugin's texts may be covered by its own catalog or the
                # core one; the core's must stand on the core catalog alone.
                scopes = ["core"] if scope == "core" else ["core", scope]
                catalog = self._merged(language, scopes)
                for text, files in sorted(found.items()):
                    with self.subTest(language=language, scope=scope,
                                      text=text[:60]):
                        if text in UNTRANSLATED_OK:
                            continue

                        self.assertIn(
                            text, catalog,
                            f"no {language} translation (used in "
                            f"{sorted(files)[0]})",
                        )

    def test_no_catalog_entry_is_unused(self):
        for language in self.languages:
            for scope, found in self.keys.items():
                catalog = _read_catalog(scope, language)
                for text in sorted(catalog):
                    with self.subTest(language=language, scope=scope,
                                      text=text[:60]):
                        self.assertIn(
                            text, found,
                            f"{scope}/{language}.json has an entry that "
                            f"{scope}'s code never translates",
                        )

    def test_a_shared_text_lives_in_one_catalog(self):
        # The same English text in two catalogs can drift into two
        # different translations; the core one is the single home.
        for language in self.languages:
            core = _read_catalog("core", language)
            for scope in self.keys:
                if scope == "core":
                    continue

                for text in _read_catalog(scope, language):
                    with self.subTest(language=language, scope=scope,
                                      text=text[:60]):
                        self.assertNotIn(
                            text, core,
                            "also in the core catalog; keep it there only",
                        )


class TestTrAcceptsAnyFieldName(unittest.TestCase):
    """tr's first argument is positional only, so {source} is a legal field."""

    def test_a_field_named_source_does_not_clash(self):
        saved = dict(i18n._state)
        self.addCleanup(i18n._state.update, saved)
        i18n.set_language(i18n.DEFAULT_LANGUAGE)
        self.assertEqual(
            i18n.tr("from {source}", source="scene"), "from scene"
        )


if __name__ == "__main__":
    unittest.main()
