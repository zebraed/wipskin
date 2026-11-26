"""Public API for WipSkin skin format plugins.

A plugin imports wipskin only through this package (enforced by
tests/test_plugin_boundary.py):

- ``wipskin.api``       format contract and file helpers; no Maya or Qt, so a
                        plugin's format/constants modules test outside Maya.
- ``wipskin.api.maya``  Maya-side helpers (scene queries, feedback).
- ``wipskin.api.ui``    adapter / option page bases, the tab Host, Qt.
- ``wipskin.api.testing``  contract checks for a plugin's own unit tests.

See docs/PLUGINS.md for the guide; API_VERSION says how stable this is.

The smallest plugin is a SkinWeightFormat with mode, label and extensions,
passed to register_skin_format(); its files then list, version, rename and
carry comments, and describe() fills the viewer. Implementing
read_weights() / write_weights() (SkinWeightData in and out) also enables
Import / Export through the shared engine.
"""

from __future__ import annotations

import sys

from wipskin.core import file_cache
from wipskin.core import i18n
from wipskin.core import io
from wipskin.core import metadata
from wipskin.core import weight_files
from wipskin.core.constants import (
    APP_TITLE,
    IMPORT_AS_SAVED,
    IMPORT_AS_SELECTED,
    SETTING_LAST_SAVE_PATH,
)
from wipskin.core.path_utils import norm_path
from wipskin.formats.skin.base import (
    Availability,
    SkinWeightData,
    SkinWeightFormat,
    ViewerInfo,
)

#: Version of this plugin API as (major, minor). 0.x is provisional: names
#: may still change between minor versions until a third-party format has
#: been built on it. Plugins can check it before relying on newer names.
API_VERSION = (0, 1)

#: Short name for plugin authors; the same class as SkinWeightFormat.
SkinFormat = SkinWeightFormat

#: Translates an English UI text into the current language (see
#: register_locales); falls back to the text itself.
tr = i18n.tr
get_language = i18n.get_language


def register_locales(directory):
    """Add a folder of ``<code>.json`` translation catalogs for a plugin.

    Each catalog maps the English text used with ``tr()`` to its translation,
    e.g. ``<plugin>/locales/ja.json``. Call it from the plugin's entry
    module. Languages the plugin has no file for stay English.

    Args:
        directory (str): Folder holding the catalogs.

    Returns:
        list: Messages for catalogs that could not be read; empty normally.
    """
    return i18n.register_locales(directory)


def register_skin_format(format_or_io_class):
    """Add a skin weight format to the SkinWeight tab.

    Call it at import time of your plugin's entry module (listed in the
    WIPSKIN_PLUGINS environment variable); takes effect from the next
    showUI(). Needs Maya and Qt, which are imported only here.

    Args:
        format_or_io_class (type): A SkinWeightFormat subclass, which gets
            the default adapter (viewer from describe(), no Import/Export),
            or a wipskin.api.ui.SkinFormatIO subclass for full control.

    Raises:
        TypeError: When the class has the wrong base class.
        ValueError: When the format clashes with a registered one (mode,
            settings keys); nothing is registered then.
    """
    from wipskin.ui.controllers.skin_formats import registry

    registry.register_format_io(
        format_or_io_class,
        # Re-imported by wipskin.Reload() so the plugin registers again.
        source_module=sys._getframe(1).f_globals.get("__name__"),
    )


__all__ = [
    "API_VERSION",
    "APP_TITLE",
    "Availability",
    "IMPORT_AS_SAVED",
    "IMPORT_AS_SELECTED",
    "SETTING_LAST_SAVE_PATH",
    "SkinFormat",
    "SkinWeightData",
    "SkinWeightFormat",
    "ViewerInfo",
    "file_cache",
    "get_language",
    "io",
    "metadata",
    "norm_path",
    "register_locales",
    "register_skin_format",
    "tr",
    "weight_files",
]
