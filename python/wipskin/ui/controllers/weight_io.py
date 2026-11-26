"""Abstract base for the tab controllers."""

from __future__ import annotations

import abc
import contextlib
import os

from maya import cmds

from wipskin.core import feedback
from wipskin.core.path_utils import norm_path
from wipskin.core.i18n import tr


class WeightIOController(abc.ABC):
    """Base controller wiring a weight-file tab view to a weight format."""

    def __init__(self, settings, view):
        self._settings = settings
        self._view = view

    @property
    def settings(self):
        """SettingsModel, for collaborators outside this module."""
        return self._settings

    @property
    def view(self):
        """Tab view, for collaborators outside this module."""
        return self._view

    # ------------------
    # Contract

    @abc.abstractmethod
    def update_viewer(self):
        """Refresh the viewer panel for the current selection."""

    @abc.abstractmethod
    def resolve_import_paths(self, mode):
        """Resolve the weight file paths to import (empty/None aborts)."""

    @abc.abstractmethod
    def import_weights(self, mode="browser"):
        """Import the resolved weight file(s) onto the scene."""

    @abc.abstractmethod
    def export_weights(self, mode="browser"):
        """Export the current scene selection to weight file(s)."""

    # ------------------
    # Shared helpers

    @staticmethod
    @contextlib.contextmanager
    def undo_chunk(chunk_name):
        """Group the with-block into one undo chunk, closed even on raise."""
        cmds.undoInfo(openChunk=True, chunkName=chunk_name)
        try:
            yield
        finally:
            cmds.undoInfo(closeChunk=True, chunkName=chunk_name)

    @staticmethod
    def select_node_with_modifiers(node):
        """Select node in Maya honoring the held Shift/Ctrl modifiers."""
        key_mod = cmds.getModifiers()
        if key_mod == 1:
            cmds.select(node, toggle=True)
        elif key_mod == 4:
            cmds.select(node, deselect=True)
        elif key_mod == 5:
            cmds.select(node, add=True)
        else:
            cmds.select(node, r=True)

    @staticmethod
    def is_node_in_scene(name, node_types=None) -> bool:
        """True when name resolves to a scene node, optionally of node_types."""
        if node_types:
            return bool(cmds.ls(name, long=True, type=node_types))
        return bool(cmds.ls(name, long=True))

    def select_existing_nodes(self, nodes, empty_message, node_types=None):
        """Select the nodes that exist in the scene; warn and return False if none."""
        existing = [
            node for node in nodes if self.is_node_in_scene(node, node_types)
        ]
        if not existing:
            feedback.display_warning(empty_message)
            return False
        cmds.select(existing, r=True)
        return True

    def _selected_weight_file(self, on_unavailable):
        """Resolve (header, path) of the first selected weight file.

        on_unavailable(message_or_None) is called instead when unavailable.
        """
        selected = self._view.section.selected_names()
        if not selected:
            on_unavailable(None)
            return None

        dir_name = self._view.section.directory()
        if not dir_name:
            on_unavailable(tr("Set a weight directory first."))
            return None

        file_name = selected[0]
        file_path = norm_path(os.path.join(dir_name, file_name))
        if len(selected) > 1:
            header = tr(
                "{file_name}  ({count} files selected — showing first)",
                file_name=file_name,
                count=len(selected),
            )
        else:
            header = file_name

        if not os.path.isfile(file_path):
            on_unavailable(tr("File not found: {file_name}", file_name=file_name))
            return None
        return header, file_path
