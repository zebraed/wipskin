"""UI language catalog: looks up a translation by the English source text.

The English text in the code is the key, so an untranslated text simply
shows in English. The core catalog lives in ``wipskin/locales/<code>.json``;
a plugin ships its own ``locales/<code>.json`` beside its code and registers
the folder with register_locales(). Loading a language merges every
registered folder's catalog, the later-registered one winning on a clash.
No Qt or Maya import: usable from any layer, including plugin format code.
"""

from __future__ import annotations

import json
import os

LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales"
)
DEFAULT_LANGUAGE = "en"

LANGUAGES = {
    "en": "English",
    "ja": "日本語",
}

_state = {"language": DEFAULT_LANGUAGE, "catalog": {}}
_locale_dirs = [LOCALE_DIR]


def get_language() -> str:
    """Return the current language code.

    Returns:
        str: A key of LANGUAGES.
    """
    return _state["language"]


def _read_catalog(path) -> dict:
    with open(path, encoding="utf-8") as stream:
        catalog = json.load(stream)

    if not isinstance(catalog, dict):
        raise ValueError(f"{path}: a catalog is a JSON object of text pairs")

    return catalog


def _build_catalog(language):
    """Merge every registered folder's catalog for language.

    Returns:
        tuple: ``(catalog, problems)``; problems lists the plugin catalogs
        that were skipped, as ``"<path>: <reason>"`` strings.

    Raises:
        OSError: When the core catalog cannot be read.
        ValueError: When the core catalog is not a JSON object.
    """
    catalog = {}
    problems = []
    if language == DEFAULT_LANGUAGE:
        return catalog, problems

    for directory in _locale_dirs:
        path = os.path.join(directory, f"{language}.json")
        if directory == LOCALE_DIR:
            catalog.update(_read_catalog(path))
            continue

        # A plugin may not offer this language; a broken file must not take
        # the whole UI down with it.
        if not os.path.isfile(path):
            continue

        try:
            catalog.update(_read_catalog(path))
        except (OSError, ValueError) as exc:
            problems.append(f"{path}: {exc}")
    return catalog, problems


def set_language(language) -> list:
    """Switch the language, loading its catalogs.

    Args:
        language (str): A key of LANGUAGES.

    Returns:
        list: Messages for plugin catalogs that were skipped because they
        could not be read; empty normally.

    Raises:
        ValueError: When language is unknown, or the core catalog is invalid.
        OSError: When the core catalog cannot be read. The current language
            stays as it was in both cases.
    """
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language}")

    catalog, problems = _build_catalog(language)
    _state["language"] = language
    _state["catalog"] = catalog
    return problems


def register_locales(directory) -> list:
    """Add a folder of ``<code>.json`` catalogs, e.g. a plugin's ``locales``.

    Safe to call again with the same folder. Takes effect at once when a
    language other than English is active.

    Args:
        directory (str): Folder holding the plugin's catalogs.

    Returns:
        list: Messages for catalogs skipped while reloading the active
        language; empty normally.
    """
    directory = os.path.normpath(os.path.abspath(directory))
    if directory in _locale_dirs:
        return []

    _locale_dirs.append(directory)
    if _state["language"] == DEFAULT_LANGUAGE:
        return []

    return set_language(_state["language"])


def list_locale_dirs() -> list:
    """Folders whose catalogs are merged, core first."""
    return list(_locale_dirs)


def tr(source, /, **fields) -> str:
    """Translate an English text into the current language.

    Args:
        source (str): The English text. May hold ``{name}`` fields when
            fields are passed. Positional only, so a field may be named
            ``source``.
        **fields: Values for the fields. Without them braces in source are
            left alone.

    Returns:
        str: The translation, or source when the catalog has none.
    """
    text = _state["catalog"].get(source, source)
    if fields:
        return text.format(**fields)

    return text
