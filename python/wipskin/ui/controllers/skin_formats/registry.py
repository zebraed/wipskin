"""The skin format adapters the SkinWeight tab drives.

XML is built in; every other format (the bundled mGear and ngSkinTools
plugins included) joins through register_format_io(), public as
wipskin.api.register_skin_format(). It also registers the adapter's
SkinWeightFormat in formats.skin.registry so both lists stay in step.
"""

from __future__ import annotations

from wipskin.formats.skin import registry as skin_registry
from wipskin.formats.skin.base import SkinWeightFormat
from wipskin.ui.controllers.skin_formats.base import SkinFormatIO
from wipskin.ui.controllers.skin_formats.xml import XmlFormatIO
from wipskin.ui.skin_formats.base import SkinFormatOptions

# Same order as formats.skin.registry, which sets the Format combo's order.
_FORMAT_IOS = [XmlFormatIO]
_BY_MODE = {io_class.format_class.mode: io_class for io_class in _FORMAT_IOS}
#: Modules that called register_format_io(), so wipskin.Reload() can
#: re-import them against the reloaded package.
_PLUGIN_MODULES = []

_registered_modes = [skin_format.mode for skin_format in skin_registry.list_skin_formats()]
if list(_BY_MODE) != _registered_modes:
    raise RuntimeError(
        "SkinFormatIO registry out of step with formats.skin.registry: "
        f"{list(_BY_MODE)} != {_registered_modes}"
    )


def build_default_io_class(format_class):
    """SkinFormatIO for a format registered without one.

    Args:
        format_class (type): SkinWeightFormat subclass.

    Returns:
        type: SkinFormatIO subclass with every flow left at its default.
    """
    return type(
        f"{format_class.__name__}IO",
        (SkinFormatIO,),
        {"format_class": format_class, "__module__": format_class.__module__},
    )


def register_format_io(format_or_io_class, source_module=None):
    """Add a skin format to the SkinWeight tab.

    Takes effect for windows opened afterwards (the next showUI()).

    Args:
        format_or_io_class (type): A SkinWeightFormat subclass, which gets
            the default adapter (viewer from describe(), no Import/Export),
            or a SkinFormatIO subclass naming its format_class and
            options_class.
        source_module (str, optional): Module that registers the format,
            re-imported by wipskin.Reload(); the class's own module when
            omitted.

    Raises:
        TypeError: When the class (or a class it names) has the wrong base.
        ValueError: When the format clashes with a registered one (mode,
            settings keys). Nothing is registered then.
    """
    if not isinstance(format_or_io_class, type):
        raise TypeError(
            "Expected a SkinWeightFormat or SkinFormatIO subclass, got "
            f"{format_or_io_class!r}."
        )

    if issubclass(format_or_io_class, SkinWeightFormat):
        io_class = build_default_io_class(format_or_io_class)
    elif issubclass(format_or_io_class, SkinFormatIO):
        io_class = format_or_io_class
    else:
        raise TypeError(
            "Expected a SkinWeightFormat or SkinFormatIO subclass, got "
            f"{format_or_io_class.__name__}."
        )

    if not issubclass(io_class.format_class, SkinWeightFormat):
        raise TypeError(
            f"{io_class.__name__}.format_class must subclass SkinWeightFormat."
        )

    if not issubclass(io_class.options_class, SkinFormatOptions):
        raise TypeError(
            f"{io_class.__name__}.options_class must subclass "
            "SkinFormatOptions."
        )

    # Validates the format against every registered one before adding it,
    # so a rejected format leaves neither list changed.
    skin_registry.register_skin_format(io_class.format_class())
    _FORMAT_IOS.append(io_class)
    _BY_MODE[io_class.format_class.mode] = io_class
    if source_module is None:
        source_module = format_or_io_class.__module__

    if source_module not in _PLUGIN_MODULES:
        _PLUGIN_MODULES.append(source_module)


def list_format_io_classes() -> tuple:
    """Every registered SkinFormatIO class, in Format-combo display order."""
    return tuple(_FORMAT_IOS)


def get_format_io_class(mode: str):
    """Return the SkinFormatIO class for a MODE_* id.

    Raises:
        KeyError: When mode has no registered adapter.
    """
    return _BY_MODE[mode]


def list_plugin_modules() -> list:
    """Names of the modules that registered formats via register_format_io."""
    return list(_PLUGIN_MODULES)
