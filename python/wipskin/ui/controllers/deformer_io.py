"""Deformer tab controller: deformer listing, XML weight import/export, viewer."""

from __future__ import annotations

import os

from maya import cmds

from wipskin.formats.deformer import xml as deformer_io
from wipskin.formats import scene
from wipskin.core import feedback
from wipskin.core import metadata
from wipskin.core.constants import (
    APP_TITLE,
    IMPORT_AS_SELECTED,
)
from wipskin.core.path_utils import norm_path
from wipskin.ui.qt_compat import QtWidgets
from wipskin.ui.controllers.weight_io import WeightIOController
from wipskin.core.i18n import tr


class DeformerIOController(WeightIOController):
    """Controller for the Deformer tab.
    """

    # ------------------
    # Deformer list

    def refresh_deformer_list(self):
        """List deformers on the selected mesh into the deformer list widget."""
        self._view.deformer_list.clear()
        self._view.shape_list.clear()
        deformers = deformer_io.list_deformers_from_selection()
        if not deformers:
            feedback.display_warning(tr("Select deformed geo to list deformers."))
            return
        for deformer_name, node_type in deformers:
            shape_count = deformer_io.deformer_shape_count(deformer_name)
            self._view.add_deformer_item(
                deformer_name,
                node_type,
                shape_count,
            )

    def refresh_deformer_shape_list(self):
        """List shapes affected by the currently selected deformer(s) into
        the shape list widget, so the user can export a subset individually.
        """
        self._view.shape_list.clear()
        for deformer_name in self._view.selected_deformer_names():
            for shape_long, node_type in deformer_io.list_deformer_shapes(
                deformer_name
            ):
                self._view.add_deformer_shape_item(
                    deformer_name, shape_long, node_type,
                )

    # ------------------
    # Viewer

    def _find_scene_shape(self, recorded_name):
        """Resolve a recorded shape name to one unambiguous scene shape."""
        matches = cmds.ls(recorded_name, long=True)
        if matches:
            shape_matches = [
                node for node in matches
                if scene.is_deformable_shape_type(node)
            ]
            if len(shape_matches) == 1:
                return shape_matches[0]

        target_leaf = scene.get_node_leaf_name(recorded_name)
        candidates = []
        for shape_type in scene.DEFORMABLE_SHAPE_TYPES:
            for candidate in cmds.ls(type=shape_type, long=True):
                if scene.get_node_leaf_name(candidate) == target_leaf:
                    candidates.append(candidate)
        if len(candidates) == 1:
            return candidates[0]
        return ""

    def _scene_shape_exists(self, recorded_name):
        return bool(self._find_scene_shape(recorded_name))

    def update_viewer(self):
        """Refresh the deformer viewer panel for the current selection."""
        resolved = self._selected_weight_file(self._view.viewer.clear)
        if resolved is None:
            return
        header, file_path = resolved
        self._view.viewer.set_header(header)
        try:
            info = deformer_io.parse_file_info(file_path)
        except Exception as exc:
            self._view.viewer.clear(tr("Failed to read XML: {exc}", exc=exc))
            return
        header_lines = [tr("Deformer: {name}", name=info["deformer"])]
        if len(info["shapes"]) > 1:
            header_lines.append(
                tr("Shapes: {count}", count=len(info["shapes"]))
            )
        else:
            header_lines.append(tr("Shape: {name}", name=info["shape"]))

        header_lines.extend(
            metadata.format_audit_lines(metadata.read_sidecar(file_path))
        )
        body_lines = []
        if len(info["shapes"]) > 1:
            for shape_info in info["shapes"]:
                count = shape_info["vertex_count"]
                if count is not None:
                    body_lines.append(tr(
                        "Vertices ({name}): {count}",
                        name=shape_info["name"],
                        count=count,
                    ))
        elif info["vertex_count"]:
            body_lines.append(
                tr("Vertices: {count}", count=info["vertex_count"])
            )
        self._view.viewer.set_meta(
            metadata.join_viewer_sections(header_lines, body_lines)
        )
        shape_names = [
            entry["name"]
            for entry in info["shapes"]
            if entry.get("name")
        ]
        self._view.viewer.set_list_items(
            shape_names,
            sort=False,
            missing_predicate=self._scene_shape_exists,
            missing_tooltip=tr("Shape not found in scene"),
        )

    def select_shape(self, item):
        recorded_name = str(item.text()).strip()
        shape = self._find_scene_shape(recorded_name)
        if not shape:
            feedback.display_warning(
                tr(
                    "Shape not found or ambiguous in scene: {recorded_name}",
                    recorded_name=recorded_name,
                )
            )
            return
        self.select_node_with_modifiers(shape)

    def select_all_shapes(self):
        shapes = []
        seen = set()
        for recorded_name in self._view.viewer.list_names(
            selectable_only=True
        ):
            shape = self._find_scene_shape(recorded_name)
            if not shape or shape in seen:
                continue
            seen.add(shape)
            shapes.append(shape)
        self.select_existing_nodes(
            shapes, tr("No listed shapes exist unambiguously in the scene.")
        )

    # ------------------
    # Import / export

    def resolve_import_paths(self, mode="browser") -> list:
        if mode != "browser":
            raise ValueError(f"Invalid mode: {mode}")
        dir_name = self._view.section.directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return []
        paths = self._view.section.selected_paths()
        if paths:
            return paths
        file_paths = cmds.fileDialog2(
            caption=tr("Choose {app_title} File(s)", app_title=APP_TITLE),
            fileMode=4,
            okCaption=tr("Import"),
            fileFilter="Deformer XML (*.xml)",
            startingDirectory=dir_name,
        )
        if not file_paths:
            return []
        file_paths = [norm_path(path) for path in file_paths]
        self._view.section.set_directory(
            os.path.dirname(file_paths[0]), add_recent=True
        )
        return file_paths

    def _resolve_selected_shape_deformer(self, shape):
        """Find which deformer on shape to import onto, for "selected shape"
        import when the Deformer List doesn't already pin one down.

        Returns:
            str: The deformer name (possibly "" when none was found on
                shape, so the caller falls back to prior behavior), or None
                if the user cancelled a multi-candidate picker.
        """
        candidates = deformer_io.list_deformers_from_selection(shape)
        if not candidates:
            return ""
        if len(candidates) == 1:
            return candidates[0][0]
        labels = [f"{name} <{node_type}>" for name, node_type in candidates]
        label, ok = QtWidgets.QInputDialog.getItem(
            self._view,
            tr("Import Deformer Weight"),
            tr("Selected shape has multiple deformers. Import onto:"),
            labels,
            editable=False,
        )
        if not ok:
            return None
        return candidates[labels.index(label)][0]

    def import_weights(self, mode="browser"):
        """Import deformer weight XML file(s) onto the scene."""
        paths = self.resolve_import_paths(mode)
        if not paths:
            return
        import_as = self._view.import_as_mode()
        method = self._view.import_method()
        ignore_names = self._view.import_ignore_names()
        shape = ""
        if import_as == IMPORT_AS_SELECTED:
            selection = cmds.ls(sl=True, long=True)
            if selection:
                shape = selection[0]
        deformer_names = self._view.selected_deformer_names()
        deformer_name = deformer_names[0] if len(deformer_names) == 1 else ""
        if not deformer_name and import_as == IMPORT_AS_SELECTED and shape:
            deformer_name = self._resolve_selected_shape_deformer(shape)
            if deformer_name is None:
                return
        dir_name = self._view.section.directory()
        had_error = False
        with self.undo_chunk("importDeformerWeight"):
            for path in paths:
                try:
                    deformer_io.import_deformer_weight(
                        dir_name,
                        os.path.basename(path),
                        method=method,
                        import_as=import_as,
                        shape=shape,
                        deformer=deformer_name,
                        ignore_names=ignore_names,
                    )
                except Exception as exc:
                    had_error = True
                    feedback.display_error(str(exc))
        if not had_error:
            self._view.section.refresh()

    def export_weights(self, mode="browser"):
        """Export the selected deformer(s)/shape(s) to weight XML file
        """
        dir_name = self._view.section.directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return

        jobs = self._view.selected_deformer_shape_pairs()
        if not jobs:
            deformer_names = self._view.selected_deformer_names()
            if not deformer_names:
                feedback.display_warning(
                    tr("Select deformer(s) or shape(s) in the list for export.")
                )
                return
            for deformer_name in deformer_names:
                for shape_long, _node_type in deformer_io.list_deformer_shapes(
                    deformer_name
                ):
                    jobs.append((deformer_name, shape_long))
            if not jobs:
                feedback.display_warning(
                    tr("Selected deformer(s) have no affected geometry to export.")
                )
                return

        auto_name = self._view.export_auto_naming()
        if not auto_name and len(jobs) != 1:
            feedback.display_warning(
                tr("Select one deformer/shape or enable auto naming for "
                   "multi-export.")
            )
            return

        filename = None
        if mode == "browser" and not auto_name:
            selected_paths = self._view.section.selected_paths()
            if len(selected_paths) == 1:
                filename = os.path.basename(selected_paths[0])
            else:
                file_paths = cmds.fileDialog2(
                    caption=tr("Save Deformer Weight"),
                    fileMode=0,
                    okCaption=tr("Export"),
                    fileFilter="Deformer XML (*.xml)",
                    startingDirectory=dir_name,
                )
                if not file_paths:
                    return
                save_path = norm_path(file_paths[0])
                dir_name = os.path.dirname(save_path)
                filename = os.path.basename(save_path)
                if not filename.lower().endswith(".xml"):
                    filename = f"{filename}.xml"
                self._view.section.set_directory(dir_name)
        exported = []
        had_error = False
        with self.undo_chunk("exportDeformerWeight"):
            for deformer_name, shape_long in jobs:
                try:
                    path = deformer_io.export_deformer_weight_for_shape(
                        deformer_name,
                        shape_long,
                        dir_name,
                        filename=filename,
                        auto_name=auto_name,
                        auto_version=self._view.export_version_number(),
                    )
                    exported.append(path)
                except Exception as exc:
                    had_error = True
                    feedback.display_error(str(exc))

        if exported and not had_error:
            feedback.display_info(tr("Exported {count} file(s)", count=len(exported)))
            self._view.section.refresh()
            self._view.section.select_files(
                [os.path.basename(path) for path in exported]
            )
