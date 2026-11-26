"""ngSkinTools layer IO flow for the SkinWeight tab."""

from __future__ import annotations

import os

from maya import cmds

from wipskin.api import (
    APP_TITLE,
    IMPORT_AS_SELECTED,
    io,
    metadata,
    tr,
)
from wipskin.api.maya import feedback, scene
from wipskin.api.ui import SkinFormatIO, prompt_export_base_name
from wipskin.plugins.ngskintools import layer_file, weights
from wipskin.plugins.ngskintools.constants import FILE_NAME_SUFFIX
from wipskin.plugins.ngskintools.format import NgSkinToolsSkinWeightFormat
from wipskin.plugins.ngskintools.ui.layer_picker import pick_layers
from wipskin.plugins.ngskintools.ui.options import NgSkinToolsOptions


class NgSkinToolsFormatIO(SkinFormatIO):
    """ngSkinTools layer JSON through ngSkinTools2's export_json / import_json."""

    format_class = NgSkinToolsSkinWeightFormat
    options_class = NgSkinToolsOptions

    # ------------------
    # Import

    def import_weights(self, mode):
        if not self._check_available():
            return

        selected_target = None
        if self.host.import_as_mode() == IMPORT_AS_SELECTED:
            selected = scene.list_skinnable_shapes()
            if not selected:
                feedback.display_error(
                    tr("No skinnable geometry selected to import layers on.")
                )
                return

            selected_target = selected[0]

        paths = self.host.resolve_import_paths(mode)
        if not paths:
            return

        transfer_mode = self.options.transfer_mode()
        add_missing = self.options.add_missing_influences()
        replace_existing = self.options.replace_existing_layers()
        choose_layers = self.options.choose_layers()
        imported = 0
        with self.host.undo_chunk("importSkinNgSkinTools"):
            for path in paths:
                name = os.path.basename(path)
                try:
                    target = selected_target
                    if target is None:
                        target = self._find_saved_target(path)

                    skin_cluster = weights.get_skin_cluster(target)
                    if skin_cluster is None:
                        raise ValueError(
                            tr("{node} has no skinCluster. Bind it first.",
                               node=target)
                        )

                    summary = layer_file.read_layer_file(path)
                    keep_layer_ids = None
                    if choose_layers:
                        picked = pick_layers(
                            self.host.parent_widget, name, summary.layers,
                        )
                        if picked is None:
                            break

                        if not picked:
                            feedback.display_warning(
                                tr("No layers chosen, skipped: {name}", name=name)
                            )
                            continue

                        if len(picked) < len(summary.layers):
                            keep_layer_ids = picked

                    influence_paths = []
                    if add_missing:
                        influence_paths = summary.influences

                    weights.import_layers(
                        skin_cluster, path, transfer_mode, influence_paths,
                        replace_existing=replace_existing and not choose_layers,
                        keep_layer_ids=keep_layer_ids,
                        replace_same_names=replace_existing and choose_layers,
                    )
                except Exception as exc:  # noqa: BLE001 - ngSkinTools2 raises plain Exception
                    feedback.display_error(f"{name}: {exc}")
                    continue

                imported += 1

        try:
            weights.notify_layers_changed()
        except Exception as exc:  # noqa: BLE001 - ngSkinTools2 raises plain Exception
            feedback.display_warning(
                tr("Could not refresh the ngSkinTools window: {error}", error=exc)
            )

        if imported:
            feedback.display_info(tr("Imported {imported} file(s)", imported=imported))

    def _find_saved_target(self, path) -> str:
        """Long path of the scene node a layer file was exported from.

        Tries the shape recorded in the sidecar, then the file's base name.

        Args:
            path (str): Layer file path.

        Returns:
            str: Node long path.

        Raises:
            ValueError: Nothing matches, or a name matches several nodes.
        """
        sidecar = metadata.read_sidecar(path)
        candidates = []
        if sidecar is not None and sidecar.get("shape"):
            candidates.append(sidecar["shape"])

        base_name = io.parse_versioned_filename(os.path.basename(path))[0]
        if base_name.endswith(FILE_NAME_SUFFIX):
            base_name = base_name[:-len(FILE_NAME_SUFFIX)]

        candidates.append(base_name)
        for candidate in candidates:
            found = cmds.ls(candidate, long=True)
            if len(found) == 1:
                return found[0]

            if len(found) > 1:
                raise ValueError(
                    tr("{node} matches several nodes in the scene.", node=candidate)
                )

        raise ValueError(
            tr("No node named {node} in the scene. Use Import As: selected shape.",
               node=candidates[-1])
        )

    # ------------------
    # Export

    def list_scene_export_shapes(self):
        if not self.format.is_available():
            return []

        shapes = []
        for shape in scene.list_skinned_shapes():
            skin_cluster = weights.get_skin_cluster(shape)
            if skin_cluster is not None and weights.has_layers(skin_cluster):
                shapes.append(shape)

        return shapes

    def export_weights(self, mode):
        if not self._check_available():
            return

        shapes = scene.list_skinnable_shapes()
        if not shapes:
            feedback.display_error(
                tr("No skinnable geometry selected to export layers from.")
            )
            return

        dir_name = self.host.get_directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return

        extension = weights.EXT
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
        with self.host.undo_chunk("exportSkinNgSkinTools"):
            for index, shape in enumerate(shapes, start=1):
                try:
                    skin_cluster = weights.get_skin_cluster(shape)
                    if skin_cluster is None:
                        feedback.display_warning(
                            tr("Skipped, not skinned: {node}", node=shape)
                        )
                        continue

                    if not weights.has_layers(skin_cluster):
                        feedback.display_warning(
                            tr("Skipped, no ngSkinTools layers: {node}", node=shape)
                        )
                        continue

                    if auto_name:
                        transform = scene.get_shape_transform(shape)
                        stem = io.sanitize_export_base_name(transform.rsplit("|", 1)[-1])
                    elif len(shapes) == 1:
                        stem = base_name
                    else:
                        stem = io.apply_multi_export_index(base_name, index)

                    if not stem.endswith(FILE_NAME_SUFFIX):
                        stem += FILE_NAME_SUFFIX

                    path = io.resolve_export_path(
                        dir_name, stem, extension, auto_version=auto_version,
                    )
                    weights.export_layers(skin_cluster, path)
                    metadata.write_export_sidecar(
                        path, self.format.get_metadata_format(path),
                        comment=comment, extra={"shape": shape},
                    )
                except Exception as exc:  # noqa: BLE001 - ngSkinTools2 raises plain Exception
                    feedback.display_error(f"{shape}: {exc}")
                    continue

                exported.append(path)

        if exported:
            feedback.display_info(tr("Exported {count} file(s)", count=len(exported)))
            self.host.refresh_files()
            self.host.select_files([os.path.basename(path) for path in exported])

    def _check_available(self) -> bool:
        if self.format.is_available():
            return True

        feedback.display_error(self.format.get_unavailable_reason())
        return False
