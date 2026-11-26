"""Maya deformerWeights XML (and .wip packs) IO flow for the SkinWeight tab."""

from __future__ import annotations

import os

from maya import cmds

from wipskin.core import feedback
from wipskin.core import io
from wipskin.core.constants import (
    APP_TITLE,
    IMPORT_AS_SELECTED,
)
from wipskin.formats.skin.xml.constants import (
    SETTING_XML_EXPORT_BASE_NAME,
    XML_MODE_ADD,
    XML_MODE_REPLACE,
)
from wipskin.core.path_utils import norm_path
from wipskin.formats import scene
from wipskin.formats.skin.xml import weights as xml_skin
from wipskin.formats.skin.xml import wip as wip_skin
from wipskin.formats.skin.xml.format import XmlSkinWeightFormat
from wipskin.ui.qt_compat import QtCore, QtWidgets
from wipskin.ui.controllers.skin_formats.base import SkinFormatIO
from wipskin.ui.skin_formats.xml import XmlSkinFormatOptions
from wipskin.core.i18n import tr


class XmlFormatIO(SkinFormatIO):
    """Maya deformerWeights XML, including the .wip pack sub-format."""

    format_class = XmlSkinWeightFormat
    options_class = XmlSkinFormatOptions

    def __init__(self, controller):
        super().__init__(controller)
        self._wip_export_dialog = None
        self._wip_import_dialog = None
        # Meshes still waiting for their WIP Skin dialog in a scene export.
        self._wip_export_queue = []

    # ------------------
    # Viewer

    def update_viewer(self):
        resolved = self._controller.get_selected_viewer_file(None)
        if resolved is None:
            return
        header, file_path = resolved
        viewer = self._view.viewer
        self._controller.set_influence_list_chrome()
        viewer.set_header(header)
        if file_path.lower().endswith(f".{wip_skin.EXT}"):
            self._update_wip_viewer(file_path)
            return
        try:
            info = xml_skin.parse_file_info(file_path)
        except Exception as exc:
            self._controller.clear_viewer(tr("Failed to read XML: {exc}", exc=exc))
            return
        viewer.set_meta(xml_skin.format_viewer_text(info))
        viewer.set_list_items(
            info["influences"],
            missing_predicate=self._controller.is_node_in_scene,
        )

    def rename_influence(self, dir_name, file_name, old_name, new_name) -> str:
        if file_name.lower().endswith(f".{wip_skin.EXT}"):
            return wip_skin.rename_influence(
                dir_name, file_name, old_name, new_name
            )

        return self.write_renamed_version(
            dir_name, file_name, old_name, new_name,
            xml_skin.rename_influence,
        )

    def rename_file(self, dir_name, file_name):
        """Rename a whole .wip pack (subdirectory + Base/Layer member XMLs).

        The generic single-file rename would either orphan the members left
        behind in the old <base>_wip/ folder or leave a stale folder name.
        """
        if not file_name.lower().endswith(f".{wip_skin.EXT}"):
            return None

        manifest_path = os.path.join(dir_name, file_name)
        try:
            manifest = wip_skin.read_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            feedback.display_error(tr("Failed to read WIP manifest: {exc}", exc=exc))
            return True, None

        old_base_name = manifest.get("base_name", "")
        text, ok = QtWidgets.QInputDialog.getText(
            self._view,
            tr("Rename WIP pack"),
            tr("New base name (renames the pack, its <base>_wip folder, and "
               "all Base/Layer member XMLs):"),
            text=old_base_name,
        )
        if not ok:
            return True, None
        new_base_name = io.sanitize_export_base_name(
            text, strip_extensions=(wip_skin.EXT,)
        )
        if not new_base_name or new_base_name == old_base_name:
            return True, None

        try:
            new_display_name = wip_skin.rename_wip_pack(
                dir_name, old_base_name, new_base_name
            )
        except OSError as exc:
            feedback.display_error(tr("Failed to rename WIP pack: {exc}", exc=exc))
            return True, None
        except ValueError as exc:
            feedback.display_warning(str(exc))
            return True, None

        feedback.display_info(
            tr(
                "Renamed WIP pack '{old_base_name}' to '{new_base_name}'",
                old_base_name=old_base_name,
                new_base_name=new_base_name,
            )
        )
        return True, new_display_name

    def _update_wip_viewer(self, file_path):
        viewer = self._view.viewer
        try:
            manifest = wip_skin.read_manifest(file_path)
        except (OSError, ValueError) as exc:
            self._controller.clear_viewer(tr("Failed to read WIP manifest: {exc}", exc=exc))
            return
        viewer.set_meta(wip_skin.format_manifest_viewer_text(manifest))
        viewer.set_list_items(
            wip_skin.list_manifest_influences(manifest),
            missing_predicate=self._controller.is_node_in_scene,
        )

    # ------------------
    # Import

    def import_weights(self, mode):
        import_as = self._view.import_as_mode()
        shape = ""
        if import_as == IMPORT_AS_SELECTED:
            selected_shapes = scene.list_skinnable_shapes()
            if not selected_shapes:
                feedback.display_error(
                    tr("No skinnable geometry selected to import skin weights on.")
                )
                return
            shape = selected_shapes[0]
        paths = self._controller.resolve_import_paths(mode)
        if not paths:
            return
        dir_name = self._view.section.directory()

        wip_suffix = f".{wip_skin.EXT}"
        wip_paths = [path for path in paths if path.lower().endswith(wip_suffix)]
        xml_paths = [path for path in paths if not path.lower().endswith(wip_suffix)]

        if wip_paths:
            if import_as == IMPORT_AS_SELECTED:
                feedback.display_warning(
                    tr("WIP Skin import always targets its recorded shape; "
                       "'selected shape' is ignored for .wip file(s).")
                )
            filenames = [
                norm_path(os.path.relpath(path, dir_name)) for path in wip_paths
            ]
            self._start_next_wip_import(dir_name, filenames)

        had_error = False
        if xml_paths:
            method = self.options.import_method()
            xml_mode = (
                XML_MODE_REPLACE
                if self.options.import_mode() == XML_MODE_REPLACE
                else XML_MODE_ADD
            )
            ignore_names = self.options.import_ignore_names()
            normalize = self.options.import_normalize()
            restore_bind_pre_matrix = self.options.import_bind_pre_matrix()
            with self._controller.undo_chunk("importSkinXml"):
                for path in xml_paths:
                    try:
                        xml_skin.import_skin(
                            dir_name,
                            os.path.basename(path),
                            method=method,
                            mode=xml_mode,
                            import_as=import_as,
                            shape=shape,
                            ignore_names=ignore_names,
                            normalize=normalize,
                            restore_bind_pre_matrix=restore_bind_pre_matrix,
                        )
                    except Exception as exc:
                        had_error = True
                        feedback.display_error(str(exc))

            if not had_error:
                self._view.section.refresh()

    def _start_next_wip_import(self, dir_name, remaining_filenames):
        """Open a modeless WIP Import dialog for the next queued .wip pack."""
        if not remaining_filenames:
            return
        filename = remaining_filenames[0]
        rest = remaining_filenames[1:]

        while self._wip_import_dialog is not None:
            self._wip_import_dialog.close()

        from wipskin.ui.wip_skin_import_dialog import WipSkinImportDialog

        try:
            dialog = WipSkinImportDialog(
                dir_name, filename, self._settings, parent=self._view
            )
        except (OSError, ValueError) as exc:
            feedback.display_error(tr("Failed to read WIP manifest: {exc}", exc=exc))
            self._start_next_wip_import(dir_name, rest)
            return
        dialog.finished.connect(
            lambda result: self._on_wip_import_dialog_finished(
                dialog, result, dir_name, filename, rest
            )
        )
        self._wip_import_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_wip_import_dialog_finished(self, dialog, result, dir_name, filename, rest):
        if self._wip_import_dialog is dialog:
            self._wip_import_dialog = None
        if result == QtWidgets.QDialog.Accepted:
            self._compose_wip_import(dialog, dir_name, filename)
        self._start_next_wip_import(dir_name, rest)

    def _compose_wip_import(self, dialog, dir_name, filename):
        config = dialog.result_config()
        if config.get("already_applied"):
            # Realtime session already validated/composed/finalized this.
            self._view.section.refresh()
            return

        errors = wip_skin.validate_import(
            dir_name, filename,
            config["enabled_group_ids"], config["group_ratios"],
        )
        if errors:
            feedback.display_error(
                tr("WIP Import blocked: {reasons}", reasons="; ".join(errors))
            )
            return

        with self._controller.undo_chunk("importSkinWip"):
            try:
                wip_skin.compose_wip(
                    dir_name, filename,
                    config["enabled_group_ids"], config["group_ratios"],
                    normalize_interactive=config["normalize_interactive"],
                )
            except Exception as exc:
                feedback.display_error(str(exc))
                return
        self._view.section.refresh()

    # ------------------
    # Export

    def export_weights(self, mode):
        if self.options.export_wip():
            self._export_wip(mode)
            return
        shape_names = scene.list_skinnable_shapes()
        if not shape_names:
            feedback.display_error(
                tr("No skinnable geometry selected to export skin weights on.")
            )
            return
        dir_name = self._view.section.directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return
        auto_name = self._controller.export_auto_naming()
        auto_version = self._view.export_version_number()
        filename = None
        if not auto_name:
            base_name = self._prompt_export_base_name(dir_name)
            if not base_name:
                return
            filename = f"{base_name}.{xml_skin.EXT}"
        with self._controller.undo_chunk("exportSkinXml"):
            try:
                exported = xml_skin.export_skin(
                    shape_names,
                    dir_name,
                    filename=filename,
                    auto_name=auto_name,
                    auto_version=auto_version,
                    optimize=self.options.export_optimize(),
                    save_bind_pre_matrix=self.options.export_bind_pre_matrix(),
                    comment=self._comment(auto_version=auto_version),
                )
            except Exception as exc:
                feedback.display_error(str(exc))
                exported = []
        if exported:
            feedback.display_info(tr("Exported {count} file(s)", count=len(exported)))
            self._view.section.refresh()
            self._view.section.select_files(
                [os.path.basename(path) for path in exported]
            )

    def list_scene_export_shapes(self):
        if self.options.export_wip():
            return scene.list_skinned_shapes(shape_types=("mesh",))

        return super().list_scene_export_shapes()

    def get_scene_export_note(self):
        if self.options.export_wip():
            return tr(
                "WIP Skin is on: the WIP Skin dialog opens for each mesh in "
                "turn. Canceling a dialog stops the remaining meshes."
            )

        return ""

    def export_scene_weights(self, shapes):
        if not self.options.export_wip():
            super().export_scene_weights(shapes)
            return

        self._wip_export_queue = list(shapes)
        self._export_next_wip()

    def _export_next_wip(self):
        """Open the WIP Skin dialog for the next queued mesh, if any."""
        while self._wip_export_queue:
            shape = self._wip_export_queue.pop(0)
            if not cmds.objExists(shape):
                feedback.display_warning(
                    tr("Skipped, no longer in the scene: {shape}", shape=shape)
                )
                continue

            with self.host.exporting_shapes([shape]):
                dialog = self._export_wip("browser")
            if dialog is None:
                continue

            # Queued so the accepted dialog finishes its export first.
            dialog.accepted.connect(
                lambda: QtCore.QTimer.singleShot(0, self._export_next_wip)
            )
            dialog.rejected.connect(self._stop_wip_export_queue)
            return

    def _stop_wip_export_queue(self):
        if self._wip_export_queue:
            feedback.display_warning(
                tr(
                    "WIP Skin export stopped: {count} mesh(es) were not "
                    "exported.",
                    count=len(self._wip_export_queue),
                )
            )

        self._wip_export_queue = []

    def _export_wip(self, mode):
        """Open the WIP Skin dialog for the one selected mesh.

        Args:
            mode (str): "browser"; WIP packs have no temp file.

        Returns:
            WipSkinExportDialog | None: The opened dialog, or None when the
            selection or settings stopped the export.
        """
        shape_names = scene.list_skinnable_shapes()
        mesh_shapes = [name for name in shape_names if cmds.nodeType(name) == "mesh"]
        if len(mesh_shapes) != 1:
            feedback.display_error(
                tr("WIP Skin export requires selecting exactly one skinned "
                   "polygon mesh.")
            )
            return None
        shape = mesh_shapes[0]
        dir_name = self._view.section.directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return None
        if self._controller.export_auto_naming():
            base_name = scene.get_shape_transform(shape).rsplit("|", 1)[-1]
        else:
            base_name = self._prompt_export_base_name(dir_name)
            if not base_name:
                return None

        from wipskin.ui.wip_skin_export_dialog import WipSkinExportDialog

        if self._wip_export_dialog is not None:
            self._wip_export_dialog.close()

        dialog = WipSkinExportDialog(shape, dir_name, base_name, parent=self._view)
        dialog.accepted.connect(
            lambda: self._finish_wip_export(dialog, shape, dir_name, base_name)
        )
        dialog.finished.connect(lambda *_: self._clear_wip_export_dialog(dialog))
        self._wip_export_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _clear_wip_export_dialog(self, dialog):
        if self._wip_export_dialog is dialog:
            self._wip_export_dialog = None

    def _finish_wip_export(self, dialog, shape, dir_name, base_name):
        config = dialog.result_config()
        auto_version = self._view.export_version_number()
        outcome = None
        with self._controller.undo_chunk("exportSkinWip"):
            try:
                outcome = wip_skin.export_wip(
                    shape,
                    dir_name,
                    base_name,
                    config["base_source"],
                    config["groups"],
                    base_influences=config["base_influences"],
                    existing_base_xml_path=config["existing_base_xml_path"],
                    auto_version=auto_version,
                    comment=self._comment(auto_version=auto_version),
                )
            except Exception as exc:
                feedback.display_error(str(exc))
        if outcome:
            feedback.display_info(tr(
                "Exported WIP pack: {manifest_path}",
                manifest_path=outcome['manifest_path'],
            ))
            self._view.section.refresh()
            wip_dir_name = os.path.basename(os.path.dirname(outcome["manifest_path"]))
            manifest_name = os.path.basename(outcome["manifest_path"])
            self._view.section.select_files([f"{wip_dir_name}/{manifest_name}"])

    def _prompt_export_base_name(self, directory) -> str | None:
        """Ask for an XML export base name when Auto Naming is off.

        Remembers the last accepted name for the next export.
        """
        from wipskin.ui.export_base_name_dialog import prompt_export_base_name

        initial = self._settings.raw_text(SETTING_XML_EXPORT_BASE_NAME, "")
        base_name = prompt_export_base_name(
            self._view,
            directory,
            extension=xml_skin.EXT,
            initial_name=initial,
            title=tr("{app_title}: Export XML", app_title=APP_TITLE),
            hint=tr("Enter a base name for the deformerWeights XML file."),
            existing_label=tr("Existing XML files:"),
            placeholder=tr("e.g. character_skin"),
            empty_error=tr("Enter a valid base name for the XML file."),
            strip_extensions=(xml_skin.EXT,),
        )
        if not base_name:
            return None
        self._settings.set(SETTING_XML_EXPORT_BASE_NAME, base_name)
        return base_name
