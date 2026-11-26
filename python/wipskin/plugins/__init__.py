"""Skin format plugins bundled with WipSkin.

Each plugin talks to WipSkin only through wipskin.api and registers itself
when its entry module (``<name>.plugin``) is imported. showUI() imports
these, in this order (the Format combo's order after XML), before the ones
listed in WIPSKIN_PLUGINS.
"""

BUNDLED_PLUGINS = (
    "wipskin.plugins.mgear.plugin",
    "wipskin.plugins.ngskintools.plugin",
)
