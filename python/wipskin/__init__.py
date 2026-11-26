"""WipSkin — Maya skin weight (XML / mGear / ngSkinTools) and deformer weight (XML) IO."""

import sys

from wipskin.core.constants import (
    APP_TITLE,
    __author__,
    __copyright__,
    __email__,
    __license__,
    __status__,
    __version__,
)


def showUI(
    vc_exec_cmd=None,
    vc_depot_root=None,
    docs_override=None,
    dockable=True,
):
    """Open window in Maya."""
    from wipskin.ui import show_window
    show_window(
        vc_exec_cmd=vc_exec_cmd,
        vc_depot_root=vc_depot_root,
        docs_override=docs_override,
        dockable=dockable,
    )


def register_skin_format(format_or_io_class):
    """Add a skin weight format to the SkinWeight tab.

    Same as wipskin.api.register_skin_format(); kept here for scripts that
    already call it.

    Args:
        format_or_io_class (type): SkinWeightFormat or SkinFormatIO subclass.

    Raises:
        TypeError: When the class has the wrong base class.
        ValueError: When the format clashes with a registered one; nothing
            is registered then.
    """
    from wipskin.ui.controllers.skin_formats import registry
    registry.register_format_io(
        format_or_io_class,
        source_module=sys._getframe(1).f_globals.get("__name__"),
    )


def Reload():
    """Reload wipskin submodules (development).

    Plugin modules that registered formats are dropped too and imported
    again afterwards, so they register against the reloaded package.
    """
    from wipskin.core import plugin_loader

    try:
        from wipskin.ui.window import close_existing_window
        close_existing_window()
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup, never block reload
        print(f"{APP_TITLE}: Reload() couldn't close the existing window: {exc}")

    format_registry = sys.modules.get(
        "wipskin.ui.controllers.skin_formats.registry"
    )
    plugin_modules = []
    if format_registry is not None:
        plugin_modules = format_registry.list_plugin_modules()
    plugin_loader.drop_modules(plugin_modules)

    prefix = __name__ + "."
    to_remove = []
    for module_name in list(sys.modules):
        if module_name == __name__ or module_name.startswith(prefix):
            to_remove.append(module_name)
    for module_name in to_remove:
        del sys.modules[module_name]

    def report_failure(name, exc):
        print(f"{APP_TITLE}: Reload() couldn't re-import plugin {name}: {exc}")

    plugin_loader.import_plugin_modules(plugin_modules, report_failure)
    print(f"{APP_TITLE} {__version__} Reloaded.")


__all__ = [
    "APP_TITLE",
    "__author__",
    "__copyright__",
    "__email__",
    "__license__",
    "__status__",
    "__version__",
    "showUI",
    "register_skin_format",
    "Reload",
    "io",
]

from wipskin.core import io
