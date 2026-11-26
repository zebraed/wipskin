"""The skin weight formats the SkinWeight tab offers."""

from __future__ import annotations

from wipskin.core.constants import REQUESTED_DEFAULTS
from wipskin.formats.skin import base
from wipskin.formats.skin.xml.format import XmlSkinWeightFormat

# Display order of the tab's Format combo: the built-in XML first, then
# plugin formats (bundled mGear and ngSkinTools included), in registration order.
_FORMATS = []
_BY_MODE = {}


def register_skin_format(skin_format):
    """Add a format to the SkinWeight tab's list.

    Only the format facts are registered here; the tab also needs the
    format's SkinFormatIO, so plugins register through
    wipskin.api.register_skin_format() instead of calling this directly.

    Args:
        skin_format (SkinWeightFormat): Instance of the format to add.

    Raises:
        TypeError: When skin_format is not a SkinWeightFormat.
        ValueError: When it clashes with a registered format; nothing is
            registered then.
    """
    base.check_can_register(_FORMATS, skin_format, REQUESTED_DEFAULTS)
    _FORMATS.append(skin_format)
    _BY_MODE[skin_format.mode] = skin_format


def list_skin_formats() -> tuple:
    """Every registered format, in Format-combo display order."""
    return tuple(_FORMATS)


def get_skin_format(mode: str):
    """Return the format for a MODE_* id; KeyError when unregistered."""
    return _BY_MODE[mode]


def pick_available_format(saved_mode: str):
    """Return the format the tab should start on.

    Args:
        saved_mode (str): Mode stored in the user's settings; may be empty
            or no longer registered.

    Returns:
        SkinWeightFormat: The saved format when it can run, else the
        available one with the lowest fallback_rank.
    """
    return base.select_available_format(_FORMATS, saved_mode)


def get_default_settings() -> dict:
    """Settings key -> default value, merged from every registered format.

    Raises:
        ValueError: When two formats declare the same key.
    """
    return base.merge_default_settings(_FORMATS)


register_skin_format(XmlSkinWeightFormat())
