"""SkinWeight tab controller: shared plumbing and Qt signal endpoints."""

from __future__ import annotations

import contextlib
import dataclasses
import os

from maya import cmds

from wipskin.core import feedback
from wipskin.core.constants import (
    APP_TITLE,
    SETTING_LAST_SAVE_PATH,
)
from wipskin.core.path_utils import norm_path
from wipskin.formats import scene
from wipskin.core import weight_files
from wipskin.ui.qt_compat import QtWidgets
from wipskin.ui.confirm_list_dialog import confirm_with_items
from wipskin.ui.controllers.skin_formats import registry as skin_format_registry
from wipskin.ui.controllers.skin_formats.base import (
    SkinFormatIO,
    get_format_labels,
)
from wipskin.ui.controllers.weight_io import WeightIOController
from wipskin.ui.file_action import FileAction
from wipskin.ui.widgets import ICON_EXPORT_SVG
from wipskin.core.i18n import tr


def _temp_file_modes() -> str:
    """Labels of the formats with Import/Export Temp, for warnings."""
    return get_format_labels(
        lambda skin_format: skin_format.supports_temp_file
    )


class SkinIOController(WeightIOController):
    """Controller for the SkinWeight tab.

    Delegates to the SkinFormatIO for the current Format combo entry, so the Qt
    signal endpoints stay bound to this one object across mode switches.
    """

    def __init__(self, settings, view, comment_provider):
        super().__init__(settings, view)
        self._comment = comment_provider
        # Paths picked through the file browser, used as import/export
        # candidates when the list has no selection.
        self.weight_paths = []
        # Set by exporting_shapes(): scene-wide exports always name each
        # file after its shape, whatever the Auto Naming checkbox says.
        self._force_export_auto_naming = False
        self._formats = {
            io_class.format_class.mode: io_class(self)
            for io_class in skin_format_registry.list_format_io_classes()
        }

    @property
    def comment(self):
        """Export-comment provider, for the format adapters."""
        return self._comment

    def _current_format(self) -> SkinFormatIO:
        """Return the SkinFormatIO for the tab's current Format combo entry."""
        return self._formats[self._view.skin_weight_mode()]

    # ------------------
    # Viewer

    def update_viewer(self):
        """Refresh the file viewer panel for the current mode/selection."""
        self._current_format().update_viewer()

    def clear_viewer(self, message=None):
        for skin_format in self._formats.values():
            skin_format.reset_viewer_state()
        self._view.viewer.set_list_label(
            tr("Influences:"),
            select_all_tooltip=tr("Select all influences in Maya."),
        )
        self._view.viewer.clear(message)

    def set_influence_list_chrome(self):
        self._view.viewer.set_list_label(
            tr("Influences:"),
            select_all_tooltip=tr("Select all influences in Maya."),
        )
        self._view.viewer.set_list_tooltip(
            tr("Double-click an influence to select it in Maya "
               "(Shift/Ctrl modifiers supported).\n"
               "Dimmed entries are not in the scene.")
        )

    def set_member_list_chrome(self):
        self._view.viewer.set_list_label(
            tr("Members:"),
            select_all_tooltip=(
                tr("Select all existing pack member files in the Files list.")
            ),
        )
        self._view.viewer.set_list_tooltip(
            tr("Click a member to select its file in Files.\n"
               "Display is recorded -> latest when a newer version exists.\n"
               "Dimmed entries are missing on disk.")
        )

    def get_selected_viewer_file(self, no_selection_message):
        """Resolve (header, path) of the first selected file, else None."""
        def clear_viewer(message):
            if message is None:
                message = no_selection_message
            self.clear_viewer(message)

        return self._selected_weight_file(clear_viewer)

    def list_file_actions(self, selected_names) -> list:
        """Files right-click entries: the format's own, then the scene export."""
        skin_format = self._current_format()
        actions = list(skin_format.list_file_actions(selected_names))
        actions.append(self._build_scene_export_action(skin_format))
        return actions

    def _build_scene_export_action(self, skin_format) -> FileAction:
        enabled = (
            skin_format.supports_export and skin_format.format.is_available()
        )
        if enabled:
            tooltip = tr(
                "Export the skin weights of every skinned shape in the scene, "
                "one file per shape named after it, with the current Format "
                "and its Export options."
            )
        else:
            tooltip = tr(
                "Export is not available for {label}.",
                label=skin_format.format.label,
            )

        return FileAction(
            tr("Export All Skins in Scene..."),
            self.export_scene_weights,
            enabled=enabled,
            tooltip=tooltip,
            icon=ICON_EXPORT_SVG,
        )

    def rename_file(self, dir_name, file_name):
        """Files list rename hook: the current format's own rename, if any."""
        return self._current_format().rename_file(dir_name, file_name)

    def list_menu_actions(self) -> list:
        """Options menu entries, one set per format.

        Entries of formats other than the current one come back disabled
        with a tooltip naming the format that offers them.
        """
        current = self._current_format()
        actions = []
        for skin_format in self._formats.values():
            for action in skin_format.list_menu_actions():
                if skin_format is not current:
                    action = dataclasses.replace(
                        action,
                        enabled=False,
                        tooltip=(
                            tr(
                                "Available in {label} mode on the SkinWeight tab.",
                                label=skin_format.format.label,
                            )
                        ),
                    )

                actions.append(action)
        return actions

    def edit_selected_file(self):
        """Files list double-click / "Edit Pack...": open the format's editor."""
        self._current_format().edit_selected_file()

    def on_chunk_selected(self, index):
        self._current_format().on_selector_changed(index)

    # ------------------
    # Influence / member list selection

    def on_viewer_item_clicked(self, item):
        """Single-click: Member View selects Files; influences ignore click."""
        self._current_format().on_viewer_item_clicked(item)

    def on_viewer_item_activated(self, item):
        """Double-click: Member View selects Files; otherwise select Maya influence."""
        self._current_format().on_viewer_item_activated(item)

    def select_influence(self, item):
        """Select an influence in Maya honoring Shift/Ctrl modifiers."""
        influence = item.text()
        node_types = self._current_format().format.influence_node_types()
        if not self.is_node_in_scene(influence, node_types):
            feedback.display_warning(tr(
                "Influence not in scene: {influence}",
                influence=influence,
            ))
            return
        self.select_node_with_modifiers(influence)

    def select_all_influences(self):
        self._current_format().select_all_from_viewer()

    # ------------------
    # Influence rename

    def rename_influence(self, old_name):
        """Save a new version of the selected file with old_name replaced.

        Args:
            old_name (str): Influence name right-clicked in the viewer list.
        """
        section = self._view.section
        selected = section.selected_names()
        if len(selected) != 1:
            feedback.display_warning(tr("Select a single weight file first."))
            return

        dir_name = section.directory()
        file_name = selected[0]
        text, ok = QtWidgets.QInputDialog.getText(
            self._view,
            tr("Rename influence"),
            tr(
                "New influence name (saved as a new version of {basename}):",
                basename=os.path.basename(file_name),
            ),
            text=old_name,
        )
        if not ok or not text.strip() or text.strip() == old_name:
            return

        new_name = text.strip()

        try:
            renamed = self._current_format().rename_influence(
                dir_name, file_name, old_name, new_name
            )
        except (OSError, ValueError) as exc:
            feedback.display_error(str(exc))
            return

        section.refresh()
        section.select_files([renamed])
        feedback.display_info(
            tr(
                "Renamed influence in {renamed}: {old_name} -> {new_name}",
                renamed=renamed,
                old_name=old_name,
                new_name=new_name,
            )
        )

    # ------------------
    # Printing

    def print_current_chunk(self):
        self._current_format().print_current_selection()

    # ------------------
    # Path resolution

    def browse_files(self, mode: str):
        """Browse ("import"/"export") and sync the weight dir / file list."""
        if mode == "export":
            file_mode, ok = 0, tr("Export")
            caption = tr("Choose {app_title} File", app_title=APP_TITLE)
        elif mode == "import":
            file_mode, ok = 4, tr("Import")
            caption = tr("Choose {app_title} File(s)", app_title=APP_TITLE)
        else:
            raise Exception(f"mode '{mode}' is invalid")

        start_dir = self._view.section.directory()
        if not start_dir:
            start_dir = self._settings.raw_text(SETTING_LAST_SAVE_PATH)
        filter_parts = [f"*.{ext}" for ext in self._view.mode_extensions()]
        weight_paths = cmds.fileDialog2(
            caption=caption,
            fileMode=file_mode,
            okCaption=ok,
            fileFilter=f"{APP_TITLE} Files ({' '.join(filter_parts)})",
            startingDirectory=start_dir,
        )
        if not weight_paths:
            self.weight_paths = []
            return

        weight_paths = [norm_path(path) for path in weight_paths]
        self.weight_paths = weight_paths
        self._view.section.set_directory(
            os.path.dirname(weight_paths[0]), add_recent=True
        )
        self._view.section.select_files(
            [os.path.basename(path) for path in weight_paths]
        )

        if mode == "export" and len(weight_paths) == 1:
            file_path = weight_paths[0]
            if os.path.isfile(file_path) and not os.access(file_path, os.W_OK):
                err_str = tr(
                    "The provided weight file is read-only: "
                    "Please make it writable before exporting:"
                )
                feedback.display_error(f"{err_str} {file_path}")
                feedback.show_error_dialog(
                    tr("{app_title} Error", app_title=APP_TITLE),
                    f"{err_str}\n{file_path}",
                )

    def resolve_import_paths(self, mode):
        if mode == "browser":
            paths = self._view.section.selected_paths()
            if not paths and self.weight_paths:
                paths = list(self.weight_paths)
            if not paths:
                feedback.display_warning(tr("Select weight file(s) in the list."))
                self.browse_files("import")
                paths = self._view.section.selected_paths()
                if not paths and self.weight_paths:
                    paths = list(self.weight_paths)
                if not paths:
                    feedback.display_info(tr("No import path chosen."))
                    return None
        elif mode == "temp":
            temp_path = self._current_format().format.get_temp_file_path()
            if temp_path is not None and os.path.isfile(temp_path):
                paths = [temp_path]
            else:
                feedback.display_error(
                    tr(
                        "No 'temp {label} file' on disk:  Please 'Export -> Export Temp' first.",
                        label=self._current_format().format.label,
                    )
                )
                return None

        missing = [path for path in paths if not os.path.isfile(path)]
        if missing:
            print("Missing weight files:")
            for mis in missing:
                print(f"    {mis}")
            feedback.display_error(
                tr("Missing the above {count} weight files for import ^^", count=len(missing))
            )
            return None
        return paths

    def get_export_base_name(self, names) -> str:
        """Auto-naming base name: the sole shape's transform, else the scene.

        Args:
            names (list): Shapes the format would export, as the format
                itself resolved them from the selection.

        Returns:
            str: The short name of the shape's transform when there is
            exactly one (as XML export names its files), else the scene
            name, else "export".
        """
        if len(names) == 1:
            node = names[0]
            if scene.is_deformable_shape_type(node):
                node = scene.get_shape_transform(node)

            short_name = node.rsplit("|", 1)[-1]
            return os.path.splitext(short_name)[0]
        scene_name = cmds.file(query=True, sceneName=True, shortName=True)
        if scene_name:
            return os.path.splitext(scene_name)[0]
        return "export"

    # ------------------
    # Import / export

    def import_weights(self, mode="browser"):
        """When the 'Import' button is pressed ("browser" or "temp")."""
        if mode not in ("browser", "temp"):
            raise Exception(f"Invalid 'mode' arg provided: {mode}")
        skin_format = self._current_format()
        if mode == "temp" and not skin_format.format.supports_temp_file:
            feedback.display_warning(
                tr(
                    "Import Temp is only available in {temp_file_modes} mode.",
                    temp_file_modes=_temp_file_modes(),
                )
            )
            return
        skin_format.import_weights(mode)

    def export_weights(self, mode="browser"):
        """When the 'Export' button is pressed ("browser" or "temp")."""
        skin_format = self._current_format()
        if mode == "temp" and not skin_format.format.supports_temp_file:
            feedback.display_warning(
                tr(
                    "Export Temp is only available in {temp_file_modes} mode.",
                    temp_file_modes=_temp_file_modes(),
                )
            )
            return
        skin_format.export_weights(mode)

    def export_scene_weights(self):
        """Export every skinned shape in the scene after a confirmation.

        The current format decides which shapes it can export and how its
        Export options apply (see SkinFormatIO.export_scene_weights).
        """
        skin_format = self._current_format()
        dir_name = self._view.section.directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return

        shapes = skin_format.list_scene_export_shapes()
        if not shapes:
            feedback.display_warning(
                tr(
                    "No skinned shapes in the scene that {label} can export.",
                    label=skin_format.format.label,
                )
            )
            return

        message = tr(
            "Export the skin weights of {count} skinned shape(s) in the scene "
            "as {label} into:\n{dir_name}\n\nEach file is named after its "
            "shape. The {label} Export options apply.",
            count=len(shapes),
            label=skin_format.format.label,
            dir_name=dir_name,
        )
        note = skin_format.get_scene_export_note()
        if note:
            message = f"{message}\n\n{note}"

        confirmed = confirm_with_items(
            self._view,
            tr("{app_title}: Export All Skins in Scene", app_title=APP_TITLE),
            message,
            shapes,
            confirm_label="Export",
        )
        if not confirmed:
            return

        with self.undo_chunk("exportSceneSkin"):
            skin_format.export_scene_weights(shapes)

    def export_auto_naming(self) -> bool:
        """Export "auto naming" state, forced on inside exporting_shapes()."""
        if self._force_export_auto_naming:
            return True

        return self._view.export_auto_naming()

    @contextlib.contextmanager
    def exporting_shapes(self, shapes):
        """Select shapes and force Auto Naming on for the with-block.

        Lets a scene-wide export reuse the selection-driven Export flows.
        The previous Maya selection is restored even on raise.

        Args:
            shapes (list): Shape long paths to select.
        """
        previous = cmds.ls(sl=True, long=True)
        cmds.select(shapes, r=True)
        self._force_export_auto_naming = True
        try:
            yield
        finally:
            self._force_export_auto_naming = False
            if previous:
                cmds.select(previous, r=True)
            else:
                cmds.select(cl=True)

    # ------------------
    # Convert

    def convert_selected(self):
        """Copy selected files with source/destination replaced."""
        dir_name = self._view.section.directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return
        file_names = self._view.section.selected_names()
        if not file_names:
            feedback.display_warning(tr("Select weight file(s) to convert."))
            return
        source, destination = self._view.convert_fields()
        if not source:
            feedback.display_warning(tr("Enter a source string to replace."))
            return
        created = weight_files.convert_weight_files(
            dir_name,
            file_names,
            source,
            destination,
            replace_content=self._current_format().format.is_text_format,
        )
        if not created:
            feedback.display_warning(tr("No files were converted."))
            return
        for src_name, dst_name in created:
            print(f"// {APP_TITLE} convert: {src_name} --> {dst_name}")
        self._view.section.refresh()
        self._view.section.select_files([pair[1] for pair in created])
