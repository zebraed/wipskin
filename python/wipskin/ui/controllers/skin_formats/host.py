"""What a skin format adapter may ask of the SkinWeight tab.

Plugins reach the tab only through SkinTabHost (wipskin.api.ui.Host), so the
tab's widgets and controller can change without breaking them.
"""

from __future__ import annotations


class ViewerPort:
    """The viewer panel operations a format adapter uses."""

    def __init__(self, viewer_panel):
        self._viewer = viewer_panel

    def set_header(self, text):
        """Show text (usually the file name line) above the metadata box."""
        self._viewer.set_header(text)

    def set_meta(self, text):
        """Replace the metadata box text."""
        self._viewer.set_meta(text)

    def set_selector_items(self, labels):
        """Fill the selector combo (has_chunk_selector) without signalling."""
        self._viewer.set_selector_items(labels)

    def get_selector_index(self) -> int:
        """Index of the selector combo's current entry; -1 when none."""
        return self._viewer.selector_index()

    def set_selector_index(self, index):
        """Select a selector combo entry, signalling as a user pick would."""
        if self._viewer.selector_combo is not None:
            self._viewer.selector_combo.setCurrentIndex(index)

    def set_list_items(self, names, missing_predicate=None, sort=True):
        """Fill the name list.

        Args:
            names (iterable): Names to list.
            missing_predicate (callable, optional): ``(name) -> bool``;
                False dims the entry and makes it unselectable.
            sort (bool): Sort the names alphabetically.
        """
        self._viewer.set_list_items(
            names, sort=sort, missing_predicate=missing_predicate,
        )

    def set_list_entries(self, entries, sort=False,
                         missing_tooltip="Not in scene"):
        """Fill the name list from dicts (display / recorded / latest / missing).

        Args:
            entries (iterable): Entry dicts; see ViewerPanel.set_list_entries.
            sort (bool): Sort by display text.
            missing_tooltip (str): Tooltip of entries flagged missing.
        """
        self._viewer.set_list_entries(
            entries, sort=sort, missing_tooltip=missing_tooltip,
        )

    def list_names(self, selectable_only=False) -> list:
        """Names currently in the list, optionally skipping dimmed rows."""
        return self._viewer.list_names(selectable_only=selectable_only)

    def list_member_targets(self, prefer_latest=True, selectable_only=True):
        """File names that listed pack members point at."""
        return self._viewer.list_member_targets(
            prefer_latest=prefer_latest, selectable_only=selectable_only,
        )


class SkinTabHost:
    """The SkinWeight tab, as seen by one format adapter."""

    def __init__(self, controller):
        self._controller = controller
        self._view = controller.view
        self._viewer = ViewerPort(controller.view.viewer)

    # ------------------
    # Session

    @property
    def settings(self):
        """SettingsModel for the format's own settings keys."""
        return self._controller.settings

    @property
    def parent_widget(self):
        """Widget to parent the format's dialogs to."""
        return self._view

    @property
    def viewer(self) -> ViewerPort:
        """The viewer panel."""
        return self._viewer

    def get_format_options(self, mode):
        """SkinFormatOptions the tab built for mode."""
        return self._view.get_format_options(mode)

    # ------------------
    # Files list

    def get_directory(self) -> str:
        """Current weight directory; empty when none is set."""
        return self._view.section.directory()

    def refresh_files(self):
        """Rescan the weight directory."""
        self._view.section.refresh()

    def select_files(self, names, emit_changed=True):
        """Select Files-list entries by name.

        Args:
            names (list): Files-list names to select.
            emit_changed (bool): Refresh the viewer for the new selection.
        """
        self._view.section.select_files(names, emit_changed=emit_changed)

    def list_selected_names(self) -> list:
        """Files-list names of the selected entries."""
        return self._view.section.selected_names()

    def list_selected_paths(self) -> list:
        """Paths of the selected entries."""
        return self._view.section.selected_paths()

    # ------------------
    # Tab options shared by every format

    def import_as_mode(self) -> str:
        """IMPORT_AS_SAVED or IMPORT_AS_SELECTED."""
        return self._view.import_as_mode()

    def export_auto_naming(self) -> bool:
        """Export "auto naming" state; always True inside exporting_shapes()."""
        return self._controller.export_auto_naming()

    def export_version_number(self) -> bool:
        """Export "version number" checkbox state."""
        return self._view.export_version_number()

    def get_export_comment(self, auto_version=False) -> str:
        """Sidecar comment for an export (see App.export_comment)."""
        return self._controller.comment(auto_version=auto_version)

    def get_export_base_name(self, names) -> str:
        """Auto naming base name for the shapes being exported."""
        return self._controller.get_export_base_name(names)

    # ------------------
    # Viewer helpers

    def get_selected_viewer_file(self, no_selection_message):
        """(header, path) of the first selected file, else None.

        The viewer is cleared (showing no_selection_message, or the default
        prompt when None) whenever None is returned.
        """
        return self._controller.get_selected_viewer_file(no_selection_message)

    def clear_viewer(self, message=None):
        """Empty the viewer, showing message (or the default prompt)."""
        self._controller.clear_viewer(message)

    def set_influence_list_chrome(self):
        """Label the viewer list as influences."""
        self._controller.set_influence_list_chrome()

    def set_member_list_chrome(self):
        """Label the viewer list as pack members."""
        self._controller.set_member_list_chrome()

    # ------------------
    # Import / export plumbing

    def resolve_import_paths(self, mode):
        """Weight paths to import for "browser" or "temp"; None to stop."""
        return self._controller.resolve_import_paths(mode)

    def undo_chunk(self, name):
        """Context manager grouping the block into one undo step."""
        return self._controller.undo_chunk(name)

    def exporting_shapes(self, shapes):
        """Context manager selecting shapes with Auto Naming forced on.

        Lets export_scene_weights run the selection-driven export_weights
        for shapes it did not get from the user's selection. The previous
        Maya selection comes back when the block ends.

        Args:
            shapes (list): Shape long paths to select.
        """
        return self._controller.exporting_shapes(shapes)

    def is_node_in_scene(self, name, node_types=None) -> bool:
        """True when name exists (and is one of node_types, if given)."""
        return self._controller.is_node_in_scene(name, node_types)

    def select_existing_nodes(self, names, empty_message, node_types=None):
        """Select the listed nodes that exist; warn with empty_message if none."""
        self._controller.select_existing_nodes(
            names, empty_message, node_types=node_types,
        )

    def select_influence(self, item):
        """Select a viewer list item's influence, honoring Shift/Ctrl."""
        self._controller.select_influence(item)
