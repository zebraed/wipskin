"""QSettings-backed preferences model for WipSkin.

Centralizes the value-coercion patterns (checkbox 1/0 flags, int lists for
splitters, recent-dir history) that were previously duplicated per widget
callback in the UI.
"""

from __future__ import annotations

from wipskin.ui.qt_compat import QtCore

from wipskin.core.constants import (
    APP_WINDOW_NAME,
    MAX_RECENT_DIRS,
    REQUESTED_DEFAULTS,
    SETTINGS_ORG,
    SETTING_RECENT_DIRS,
)
from wipskin.core.path_utils import norm_path

_FALSE_STRINGS = ("", "0", "false", "no", "none")


def to_bool(value) -> bool:
    """Coerce a QSettings value to bool.

    QSettings may return the stored value as str after a restart, where
    bool("0") would be wrongly truthy.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _FALSE_STRINGS
    return bool(value)


class SettingsModel:
    """Typed access to WipSkin user preferences.

    Keys tracked in constants.REQUESTED_DEFAULTS, or declared through
    extra_defaults, fall back to their canonical default; other keys use the
    explicit fallback of the raw accessors.
    """

    def __init__(self, qsettings=None, extra_defaults=None):
        """Args:
            qsettings (QSettings, optional): Backing store; the WipSkin
                organisation/app store when omitted.
            extra_defaults (dict, optional): Defaults beyond
                REQUESTED_DEFAULTS, e.g. the ones skin formats declare.

        Raises:
            ValueError: When extra_defaults redeclares a built-in key.
        """
        if qsettings is None:
            qsettings = QtCore.QSettings(SETTINGS_ORG, APP_WINDOW_NAME)
        self._qsettings = qsettings
        self._defaults = dict(REQUESTED_DEFAULTS)
        if extra_defaults is not None:
            clashing = sorted(set(extra_defaults) & set(self._defaults))
            if clashing:
                raise ValueError(
                    f"Settings defaults already declared: {clashing}"
                )

            self._defaults.update(extra_defaults)

    @property
    def qsettings(self):
        """The underlying QSettings (geometry save/restore, clear, ...)."""
        return self._qsettings

    def clear(self):
        """Remove all stored preferences."""
        self._qsettings.clear()

    def default(self, key: str):
        """Canonical default for a tracked UI setting."""
        return self._defaults[key]

    def value(self, key: str):
        """Stored value for a tracked key, falling back to its canonical default."""
        return self._qsettings.value(key, self._defaults[key])

    def flag(self, key: str) -> bool:
        return to_bool(self.value(key))

    def text(self, key: str) -> str:
        return str(self.value(key))

    def int_value(self, key: str) -> int:
        return int(self.value(key))

    def float_value(self, key: str) -> float:
        return float(self.value(key))

    def raw(self, key: str, fallback=None):
        """Stored value for a key with no tracked default."""
        return self._qsettings.value(key, fallback)

    def raw_text(self, key: str, fallback: str = "") -> str:
        value = self._qsettings.value(key, fallback)
        if value is None:
            return ""
        return str(value)

    def raw_int(self, key: str, fallback: int = 0) -> int:
        try:
            return int(self._qsettings.value(key, fallback))
        except (TypeError, ValueError):
            return fallback

    def set(self, key: str, value):
        self._qsettings.setValue(key, value)

    def set_flag(self, key: str, checked: bool):
        """Store a checkbox state in the 1/0 format the legacy UI used."""
        self._qsettings.setValue(key, 1 if checked else 0)

    def recent_dirs(self) -> list:
        recent = self._qsettings.value(SETTING_RECENT_DIRS, [])
        if not isinstance(recent, list):
            recent = [recent] if recent else []
        return [norm_path(str(path)) for path in recent if path]

    def add_recent_dir(self, dir_name: str):
        dir_name = norm_path(dir_name)
        if not dir_name:
            return
        recent = self.recent_dirs()
        if dir_name in recent:
            recent.remove(dir_name)
        recent.insert(0, dir_name)
        self._qsettings.setValue(SETTING_RECENT_DIRS, recent[:MAX_RECENT_DIRS])

    def splitter_sizes(
        self,
        key: str,
        default_sizes,
        migrate_two_pane: bool = False,
        migrate_three_pane: bool = False,
    ) -> list:
        """Saved splitter sizes validated against len(default_sizes)
        """
        default_sizes = list(default_sizes)
        saved = self._qsettings.value(key)
        if not saved:
            return default_sizes
        try:
            sizes = [int(value) for value in saved]
        except (TypeError, ValueError):
            return default_sizes
        if migrate_two_pane and len(sizes) == 2:
            return [sizes[0], max(sizes[0] * 3, default_sizes[1]), sizes[1]]
        if migrate_three_pane and len(sizes) == 3:
            return [sizes[0], sizes[1] + sizes[2]]
        if len(sizes) != len(default_sizes):
            return default_sizes
        return sizes

    def save_splitter_sizes(self, key: str, sizes):
        self._qsettings.setValue(key, list(sizes))
