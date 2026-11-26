"""Import the modules that add formats to WipSkin.

A plugin is a plain Python module on sys.path that registers its formats
when imported. Modules listed in the WIPSKIN_PLUGINS environment variable
(separated like PATH entries) are imported before the window opens.
"""

from __future__ import annotations

import importlib
import os
import sys

ENV_VAR = "WIPSKIN_PLUGINS"


def list_plugin_module_names(value=None) -> list:
    """Module names listed in WIPSKIN_PLUGINS, in order and without repeats.

    Args:
        value (str, optional): Raw variable value; read from the environment
            when omitted.

    Returns:
        list: Module names; empty when the variable is unset or blank.
    """
    if value is None:
        value = os.environ.get(ENV_VAR, "")

    names = []
    for entry in value.split(os.pathsep):
        name = entry.strip()
        if name and name not in names:
            names.append(name)
    return names


def import_plugin_modules(names, on_error) -> list:
    """Import each plugin module, carrying on past the ones that fail.

    A broken plugin must not stop WipSkin or the other plugins from loading,
    so any exception its import raises goes to on_error instead.

    Args:
        names (iterable): Module names to import.
        on_error (callable): Called as ``on_error(name, exc)`` for each
            module whose import raised.

    Returns:
        list: Names of the modules that imported.
    """
    imported = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - plugin boundary
            on_error(name, exc)
            continue

        imported.append(name)
    return imported


def drop_modules(names) -> list:
    """Remove modules (and their submodules) from sys.modules.

    The next import runs them again, so a plugin re-registers against a
    freshly imported wipskin instead of keeping classes from the old one.

    Args:
        names (iterable): Top module names to drop.

    Returns:
        list: Every module name removed.
    """
    names = list(names)
    dropped = []
    for module_name in list(sys.modules):
        for name in names:
            if module_name == name or module_name.startswith(name + "."):
                del sys.modules[module_name]
                dropped.append(module_name)
                break
    return dropped
