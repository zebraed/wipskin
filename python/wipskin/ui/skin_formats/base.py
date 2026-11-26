"""Contract for one skin format's Import/Export option page."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SkinFormatContext:
    """Everything the tab hands one option page at construction.

    Attributes:
        settings (SettingsModel): Persisted prefs.
        registry (ResetRegistry): Reset-to-default registration.
        parent (QWidget): Owner of the pages (QButtonGroup parent).
        skin_format (SkinWeightFormat): The format this page belongs to.
        config (dict): Project-level config shared by every format (showUI's
            vc_exec_cmd / vc_depot_root, ...); read the keys this format
            understands and ignore the rest.
        request_viewer_refresh (callable): () -> None. Re-reads the viewer
            for the current file selection, for options that change what
            the viewer shows.
    """

    settings: object
    registry: object
    parent: object
    skin_format: object
    config: dict
    request_viewer_refresh: Callable[[], None]


class SkinFormatOptions(abc.ABC):
    """Owns a format's option widgets and exposes them as typed readers.

    The tab builds one of these per registered format and only ever asks it
    to fill a layout, so no format-specific widget or getter lives on the
    tab itself.
    """

    def __init__(self, context: SkinFormatContext):
        self._settings = context.settings
        self._registry = context.registry
        #: QWidget that owns the pages (QButtonGroup parent).
        self._parent = context.parent
        self._skin_format = context.skin_format
        self._config = context.config
        self._request_viewer_refresh = context.request_viewer_refresh

    def get_primary_extension(self) -> str:
        """Extension a new export gets when a name is typed without one.

        Override when the extension depends on this page's widgets.
        """
        return self._skin_format.get_primary_extension()

    @abc.abstractmethod
    def build_import_page(self, layout):
        """Fill layout with this format's Import options."""

    @abc.abstractmethod
    def build_export_page(self, layout):
        """Fill layout with this format's Export options."""


class NoOptions(SkinFormatOptions):
    """Option page of a format with no Import/Export options of its own."""

    def build_import_page(self, layout):
        layout.addStretch()

    def build_export_page(self, layout):
        layout.addStretch()
