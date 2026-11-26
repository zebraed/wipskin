"""Base adapter binding one skin format to the SkinWeight tab."""

from __future__ import annotations

import os

from maya import cmds

from wipskin.core import feedback
from wipskin.core import io
from wipskin.core import metadata
from wipskin.core import weight_files
from wipskin.core.constants import APP_TITLE, IMPORT_AS_SELECTED
from wipskin.formats import scene
from wipskin.formats.skin import engine
from wipskin.formats.skin import registry as skin_registry
from wipskin.ui.export_base_name_dialog import prompt_export_base_name
from wipskin.ui.controllers.skin_formats.host import SkinTabHost
from wipskin.ui.skin_formats.base import NoOptions
from wipskin.core.i18n import tr


def get_format_labels(predicate) -> str:
    """Labels of the registered formats that predicate accepts, for messages.

    Args:
        predicate (callable): ``predicate(skin_format) -> bool``.

    Returns:
        str: Comma-separated labels in Format-combo order, e.g. "mGear".
    """
    return ", ".join(
        skin_format.label
        for skin_format in skin_registry.list_skin_formats()
        if predicate(skin_format)
    )


class SkinFormatIO:
    """Adapts one SkinWeightFormat to the tab's widgets and IO flows.

    Every flow has a default, so a format registered on its own gets one of
    these built for it: the viewer shows SkinWeightFormat.describe(), and
    Import/Export run through the shared engine (formats.skin.engine) when
    the format implements read_weights / write_weights, else stay greyed
    out. Override import_weights / export_weights for flows of your own.
    Adapters reach the tab only through self.host.
    """

    #: SkinWeightFormat subclass this adapter drives.
    format_class = None
    #: SkinFormatOptions subclass holding this format's option widgets.
    options_class = NoOptions
    #: Whether the Import / Export buttons are enabled. Derived per subclass
    #: (see __init_subclass__) unless the subclass sets them itself.
    supports_import = False
    supports_export = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if getattr(cls, "format_class", None) is None:
            raise TypeError(f"{cls.__name__} must define 'format_class'")

        # Enabled when the subclass brings its own flow, or the format can
        # read / write weights for the default flow below.
        if "supports_import" not in vars(cls):
            cls.supports_import = (
                cls.import_weights is not SkinFormatIO.import_weights
                or cls.format_class.has_weight_reader()
            )

        if "supports_export" not in vars(cls):
            cls.supports_export = (
                cls.export_weights is not SkinFormatIO.export_weights
                or cls.format_class.has_weight_writer()
            )

    def __init__(self, controller):
        self.format = self.format_class()
        self.host = SkinTabHost(controller)
        # Built-in adapters only; plugins go through self.host.
        self._controller = controller
        self._settings = controller.settings
        self._view = controller.view
        self._comment = controller.comment

    @property
    def options(self):
        """This format's option page owner, for reading its widgets."""
        return self.host.get_format_options(self.format.mode)

    # Flows
    def update_viewer(self):
        """Refresh the viewer panel for the current file selection.

        The default shows SkinWeightFormat.describe() under the sidecar
        audit lines.
        """
        resolved = self.host.get_selected_viewer_file(
            tr("Select a weight file to inspect it.")
        )
        if resolved is None:
            return

        header, path = resolved
        try:
            info = self.format.describe(path)
        except Exception as exc:  # noqa: BLE001 - plugin code boundary
            self.host.clear_viewer(
                tr("Failed to read {label} file: {exc}", label=self.format.label, exc=exc)
            )
            return

        self.host.set_influence_list_chrome()
        viewer = self.host.viewer
        viewer.set_header(header)
        viewer.set_meta(metadata.join_viewer_sections(
            metadata.format_audit_lines(metadata.read_sidecar(path)),
            list(info.meta_lines),
        ))
        viewer.set_list_items(
            info.influences,
            missing_predicate=lambda name: self.host.is_node_in_scene(
                name, self.format.influence_node_types()
            ),
        )

    def import_weights(self, mode):
        """Import the selected weight file(s) onto the scene.

        The default reads each file with SkinWeightFormat.read_weights and
        applies it with the shared engine: onto its recorded shape, or onto
        the first selected shape when Import As is "selected shape".
        """
        if not self.format.has_weight_reader():
            feedback.display_warning(
                tr("Import is not available for {label}.", label=self.format.label)
            )
            return

        target = None
        if self.host.import_as_mode() == IMPORT_AS_SELECTED:
            selected = scene.list_skinnable_shapes()
            if not selected:
                feedback.display_error(
                    tr("No skinnable geometry selected to import skin weights on.")
                )
                return

            target = selected[0]

        paths = self.host.resolve_import_paths(mode)
        if not paths:
            return

        imported = 0
        with self.host.undo_chunk(f"importSkin{self.format.label}"):
            for path in paths:
                try:
                    data = self.format.read_weights(path)
                    shape = target
                    if shape is None:
                        shape = data.shape
                        if not cmds.objExists(shape):
                            raise ValueError(f"Shape not in the scene: {shape}")

                    engine.apply_skin_weights(shape, data)
                except Exception as exc:  # noqa: BLE001 - plugin code boundary
                    feedback.display_error(
                        f"{os.path.basename(path)}: {exc}"
                    )
                    continue

                imported += 1

        if imported:
            feedback.display_info(tr("Imported {imported} file(s)", imported=imported))
            self.host.refresh_files()

    def export_weights(self, mode):
        """Export the scene selection to weight file(s).

        The default collects each selected skinned mesh with the shared
        engine and writes it with SkinWeightFormat.write_weights, one file
        per shape, named like the XML export (shape name with Auto Naming,
        else the typed base name, numbered when several shapes).
        """
        if not self.format.has_weight_writer():
            feedback.display_warning(
                tr("Export is not available for {label}.", label=self.format.label)
            )
            return

        shapes = scene.list_skinnable_shapes()
        if not shapes:
            feedback.display_error(
                tr("No skinnable geometry selected to export skin weights from.")
            )
            return

        dir_name = self.host.get_directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return

        extension = self.format.get_primary_extension()
        auto_name = self.host.export_auto_naming()
        auto_version = self.host.export_version_number()
        base_name = None
        if not auto_name:
            base_name = prompt_export_base_name(
                self.host.parent_widget,
                dir_name,
                extension=extension,
                title=tr(
                    "{app_title}: Export {label}",
                    app_title=APP_TITLE,
                    label=self.format.label,
                ),
                hint=tr("Enter a base name for the {label} file.", label=self.format.label),
                strip_extensions=self.format.extensions,
            )
            if not base_name:
                return

        comment = self.host.get_export_comment(auto_version=auto_version)
        exported = []
        with self.host.undo_chunk(f"exportSkin{self.format.label}"):
            for index, shape in enumerate(shapes, start=1):
                try:
                    data = engine.collect_skin_weights(shape)
                    if auto_name:
                        stem = io.sanitize_export_base_name(
                            data.shape.rsplit("|", 1)[-1]
                        )
                    elif len(shapes) == 1:
                        stem = base_name
                    else:
                        stem = io.apply_multi_export_index(base_name, index)

                    path = io.resolve_export_path(
                        dir_name, stem, extension, auto_version=auto_version,
                    )
                    self._write_weights_file(path, data)
                    metadata.write_export_sidecar(
                        path, self.format.get_metadata_format(path),
                        comment=comment,
                    )
                except Exception as exc:  # noqa: BLE001 - plugin code boundary
                    feedback.display_error(f"{shape}: {exc}")
                    continue

                exported.append(path)

        if exported:
            feedback.display_info(tr("Exported {count} file(s)", count=len(exported)))
            self.host.refresh_files()
            self.host.select_files([os.path.basename(p) for p in exported])

    def list_scene_export_shapes(self) -> list:
        """Skinned shapes in the scene that this format can export.

        Returns:
            list: Shape long paths; the default takes every skinnable type.
        """
        return scene.list_skinned_shapes()

    def get_scene_export_note(self) -> str:
        """Extra text for the "Export All Skins in Scene" confirmation.

        Returns:
            str: How the current Export options change the scene export,
            or "" when there is nothing to add.
        """
        return ""

    def export_scene_weights(self, shapes):
        """Export shapes, chosen from the whole scene, with Auto Naming on.

        The default selects every shape at once and runs export_weights,
        which suits flows that write one file per selected shape. Override
        when the flow merges the selection into one file (see
        export_each_shape).

        Args:
            shapes (list): Shape long paths from list_scene_export_shapes().
        """
        with self.host.exporting_shapes(shapes):
            self.export_weights("browser")

    def export_each_shape(self, shapes):
        """Run export_weights once per shape, each selected on its own.

        Args:
            shapes (list): Shape long paths to export.
        """
        for shape in shapes:
            with self.host.exporting_shapes([shape]):
                self.export_weights("browser")

    def _write_weights_file(self, path, data):
        """write_weights into a temp file, then swap it in.

        A writer that fails midway must not leave a truncated file where a
        good one (or nothing) was.
        """
        temp_path = f"{path}.tmp"
        try:
            self.format.write_weights(temp_path, data)
            os.replace(temp_path, path)
        except BaseException:
            if os.path.exists(temp_path):
                os.remove(temp_path)

            raise

    # Overridable behavior
    def rename_influence(self, dir_name, file_name, old_name, new_name) -> str:
        """Write a new version of file_name with one influence renamed.

        The selected file is never edited: a joint rename that turns out to
        be wrong must not cost the user their existing weights.

        Args:
            dir_name (str): Weight directory holding file_name.
            file_name (str): Files-list name of the weight file.
            old_name (str): Influence name to replace.
            new_name (str): Replacement name.

        Returns:
            str: Files-list name of the new version.

        Raises:
            ValueError: When the rename cannot be applied.
        """
        raise ValueError(
            f"Renaming an influence is not supported for {self.format.label}."
        )

    def rename_file(self, dir_name, file_name):
        """Rename file_name when this format needs more than a file rename.

        Lets a format take over the Files list's rename for entries the
        generic single-file rename cannot handle.

        Args:
            dir_name (str): Weight directory holding file_name.
            file_name (str): Files-list name of the selected entry.

        Returns:
            None when not applicable (the generic rename prompt runs), or
            ``(True, new_display_name)`` once handled; new_display_name is
            None when nothing changed on disk.
        """
        return None

    def write_renamed_version(
        self, dir_name, file_name, old_name, new_name, rewrite,
    ) -> str:
        """Copy file_name to the next version, then rewrite names in the copy.

        Shared by the formats whose files are a single document; ``.wip``
        packs span several files and write their own version instead.

        Args:
            dir_name (str): Weight directory holding file_name.
            file_name (str): Files-list name of the source file.
            old_name (str): Influence name to replace.
            new_name (str): Replacement name.
            rewrite (callable): Called as ``rewrite(path, old_name,
                new_name)``; returns how many names it replaced.

        Returns:
            str: Files-list name of the new version.

        Raises:
            ValueError: When the file holds no influence named old_name.
        """
        new_file_name = weight_files.copy_to_next_version(dir_name, file_name)
        try:
            changed = rewrite(
                os.path.join(dir_name, new_file_name), old_name, new_name
            )
            if not changed:
                raise ValueError(f"Influence not in this file: {old_name}")

        except Exception:
            # Leave no half-written version behind for the user to clean up.
            weight_files.delete_weight_files(dir_name, [new_file_name])
            raise

        return new_file_name

    def list_file_actions(self, selected_names) -> list:
        """FileAction entries this format adds to the Files right-click menu."""
        return []

    def edit_selected_file(self):
        """Open this format's editor for the selected file; most have none."""

    def list_menu_actions(self) -> list:
        """FileAction entries this format adds to the Options menu.

        Offered whatever the Files selection, so a callback must cope with
        nothing being selected.
        """
        return []

    def reset_viewer_state(self):
        """Drop cached viewer state; called when the viewer is cleared."""

    def on_selector_changed(self, index):
        """Handle the viewer's selector combo changing (has_chunk_selector)."""

    def print_current_selection(self):
        """Print the viewer's current item (has_chunk_selector formats)."""
        modes = get_format_labels(
            lambda skin_format: skin_format.has_chunk_selector
        )
        feedback.display_warning(tr("Printing is only available in {modes} mode.", modes=modes))

    def on_viewer_item_clicked(self, item):
        """Single-click in the viewer list; influences ignore it."""

    def on_viewer_item_activated(self, item):
        """Double-click in the viewer list."""
        self.host.select_influence(item)

    def select_all_from_viewer(self):
        """Select every listed influence that exists in the scene."""
        self.host.select_existing_nodes(
            self.host.viewer.list_names(),
            tr("No influences from the list exist in the scene."),
            node_types=self.format.influence_node_types(),
        )
