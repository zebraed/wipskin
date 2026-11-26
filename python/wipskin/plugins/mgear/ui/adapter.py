"""mGear IO flow for the SkinWeight tab."""

from __future__ import annotations

import os

from wipskin.api.maya import feedback
from wipskin.api import metadata
from wipskin.api import io
from wipskin.api import APP_TITLE
from wipskin.plugins.mgear.constants import (
    MGEAR_PACK_VERSION_LATEST,
    SETTING_MGEAR_PACK_BASE_NAME,
)
from wipskin.api import norm_path
from wipskin.api.maya import scene
from wipskin.plugins.mgear import weights as mgear_skin
from wipskin.plugins.mgear.format import MgearSkinWeightFormat
from wipskin.api.ui import confirm_with_items
from wipskin.api.ui import FileAction
from wipskin.plugins.mgear.ui.gskin_pack_choice_dialog import choose_gskin_pack
from wipskin.plugins.mgear.ui.gskin_pack_editor_dialog import edit_gskin_pack
from wipskin.api.ui import QtCore
from wipskin.api.ui import ICON_EXPORT_SVG, ICON_IMPORT_SVG, ICON_RENAME_SVG
from wipskin.api.ui import SkinFormatIO
from wipskin.plugins.mgear.ui.options import MgearSkinFormatOptions
from wipskin.api import tr


def _update_sidecar_influences(path, old_name, new_name):
    """Keep the recorded influence list in step with the renamed file."""
    sidecar = metadata.read_sidecar(path)
    if not sidecar or "influences" not in sidecar:
        return

    metadata.update_sidecar(path, {"influences": [
        new_name if influence == old_name else influence
        for influence in sidecar["influences"]
    ]})


class MgearFormatIO(SkinFormatIO):
    """mGear .jSkin / .gSkin and their .gSkinPack packs."""

    format_class = MgearSkinWeightFormat
    options_class = MgearSkinFormatOptions

    def __init__(self, controller):
        super().__init__(controller)
        # Pack files list their member files instead of influences, and
        # clicking a member selects its file rather than a Maya node.
        self._member_view = False
        self._viewer_file_path = ""

    def reset_viewer_state(self):
        self._member_view = False
        self._viewer_file_path = ""

    # ------------------
    # Viewer

    def update_viewer(self):
        resolved = self.host.get_selected_viewer_file(None)
        if resolved is None:
            return
        header, file_path = resolved
        viewer = self.host.viewer
        viewer.set_header(header)
        try:
            info = mgear_skin.parse_file_info(file_path)
        except Exception as exc:
            self.host.clear_viewer(tr("Failed to read mGear file: {exc}", exc=exc))
            return
        viewer.set_meta(mgear_skin.format_viewer_text(info))
        if info["type"] == "pack":
            self._viewer_file_path = file_path
            self._member_view = True
            self.host.set_member_list_chrome()
            pack_dir = os.path.dirname(file_path)
            prefer_latest = (
                self.options.pack_import_version()
                == MGEAR_PACK_VERSION_LATEST
            )
            entries = []
            for recorded_name in info["entries"]:
                desc = mgear_skin.describe_pack_member(pack_dir, recorded_name)
                if prefer_latest:
                    missing = not desc["latest_exists"]
                else:
                    missing = not desc["recorded_exists"]
                entries.append({
                    "display": desc["display"],
                    "recorded": desc["recorded"],
                    "latest": desc["latest"],
                    "missing": missing,
                })
            viewer.set_list_entries(
                entries,
                sort=False,
                missing_tooltip=tr("Not on disk"),
            )
        else:
            self._member_view = False
            self.host.set_influence_list_chrome()
            viewer.set_list_items(
                mgear_skin.list_influences(file_path),
                missing_predicate=self.host.is_node_in_scene,
            )

    def rename_influence(self, dir_name, file_name, old_name, new_name) -> str:
        if not self.format.can_rename_influence(file_name):
            raise ValueError(
                "Only .jSkin stores influence names as text; "
                f"cannot rename inside {file_name}."
            )

        new_file_name = self.write_renamed_version(
            dir_name, file_name, old_name, new_name,
            mgear_skin.rename_influence,
        )
        _update_sidecar_influences(
            os.path.join(dir_name, new_file_name), old_name, new_name
        )
        return new_file_name

    def on_viewer_item_clicked(self, item):
        if self._member_view:
            self._select_pack_member_from_item(item)

    def on_viewer_item_activated(self, item):
        if self._member_view:
            self._select_pack_member_from_item(item)
            return
        super().on_viewer_item_activated(item)

    def select_all_from_viewer(self):
        if not self._member_view:
            super().select_all_from_viewer()
            return
        prefer_latest = (
            self.options.pack_import_version()
            == MGEAR_PACK_VERSION_LATEST
        )
        self._select_pack_member_files(
            self.host.viewer.list_member_targets(
                prefer_latest=prefer_latest,
                selectable_only=True,
            )
        )

    def _select_pack_member_from_item(self, item):
        prefer_latest = (
            self.options.pack_import_version() == MGEAR_PACK_VERSION_LATEST
        )
        recorded = str(item.data(QtCore.Qt.UserRole) or "").strip()
        latest = str(item.data(QtCore.Qt.UserRole + 1) or "").strip()
        if prefer_latest and latest:
            target = latest
        else:
            target = recorded
        self._select_pack_member_files([target] if target else [])

    def _select_pack_member_files(self, member_names):
        """Highlight pack member files in the Files list without leaving Member View."""
        names = [name for name in member_names if name]
        if not names:
            feedback.display_warning(tr("No pack member files found on disk."))
            return
        pack_dir = ""
        if self._viewer_file_path:
            pack_dir = os.path.dirname(self._viewer_file_path)
        existing = []
        for name in names:
            if pack_dir and not os.path.isfile(os.path.join(pack_dir, name)):
                continue
            existing.append(name)
        if not existing:
            feedback.display_warning(tr("No pack member files found on disk."))
            return
        self.host.select_files(existing, emit_changed=False)

    # ------------------
    # Import / export

    def import_weights(self, mode):
        if not self.format.is_available():
            feedback.display_error(
                tr("mGear is not available. Install mGear 4.x to use this format.")
            )
            return

        paths = self.host.resolve_import_paths(mode)
        if not paths:
            return

        had_error = False
        with self.host.undo_chunk("importSkinMgear"):
            for path in paths:
                try:
                    if mgear_skin.is_pack_file(path):
                        mgear_skin.import_skin_pack(
                            path,
                            version_mode=self.options.pack_import_version(),
                        )
                    else:
                        mgear_skin.import_skin(path)
                except Exception as exc:
                    had_error = True
                    feedback.display_error(str(exc))
        if not had_error:
            self.host.refresh_files()

    def export_weights(self, mode):
        if not self.format.is_available():
            feedback.display_error(
                tr("mGear is not available. Install mGear 4.x to use this format.")
            )
            return

        shape_names = scene.list_skinnable_shapes()
        if not shape_names:
            pack_path = self._selected_gskin_pack_path()
            if pack_path:
                self._reexport_pack_members(pack_path)
                return

            feedback.display_error(
                tr("No skinnable geometry selected to export skin weights on.")
            )
            return

        if len(shape_names) > 1 and not self.options.export_pack():
            # A single file holds one shape: write one file per shape.
            self.export_each_shape(shape_names)
            return

        export_transforms = mgear_skin.list_export_transforms(shape_names)
        if not export_transforms:
            feedback.display_error(
                tr("No exportable transform found for mGear export.")
            )
            return

        dir_name = self.host.get_directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
            return

        use_json = self.options.use_json()
        auto_version = self.host.export_version_number()
        export_comment = self.host.get_export_comment(auto_version=auto_version)

        export_pack = self.options.export_pack()
        if export_pack:
            ext = mgear_skin.EXT_GSKIN_PACK
        elif use_json:
            ext = mgear_skin.EXT_JSKIN
        else:
            ext = mgear_skin.EXT_GSKIN

        if export_pack and not self.host.export_auto_naming():
            base_name = self._prompt_export_base_name(dir_name)
            if not base_name:
                return
        elif self.host.export_auto_naming():
            base_name = self.host.get_export_base_name(shape_names)
        else:
            base_name = export_transforms[0].rsplit("|", 1)[-1]

        path = io.resolve_export_path(
            dir_name, base_name, ext,
            auto_version=auto_version,
        )
        with self.host.undo_chunk("exportSkinMgear"):
            try:
                if export_pack:
                    mgear_skin.export_skin_pack(
                        shape_names, path, use_json=use_json,
                        comment=export_comment,
                        auto_version=auto_version,
                    )
                else:
                    mgear_skin.export_skin(
                        shape_names, path, use_json=use_json,
                        comment=export_comment,
                    )
            except Exception as exc:
                feedback.display_error(str(exc))
                path = None

        self._finish_export(path)

    def get_scene_export_note(self):
        if self.options.export_pack():
            return tr(
                "Export as .gSkinPack is on: every shape goes into one pack "
                "named after the scene."
            )

        return ""

    def export_scene_weights(self, shapes):
        # A single-file mGear export keeps only the first selected shape,
        # so without a pack each shape needs its own run.
        if self.options.export_pack():
            super().export_scene_weights(shapes)
            return

        self.export_each_shape(shapes)

    def _reexport_pack_members(self, pack_path):
        """Export with only a .gSkinPack selected: re-export all its members.

        Writes the next pack version. A member with no skinned scene mesh is
        warned about and keeps its newest file on disk.
        """
        try:
            states = mgear_skin.list_pack_member_states(pack_path)
        except (OSError, ValueError) as exc:
            feedback.display_error(tr("Failed to read pack: {exc}", exc=exc))
            return

        actions = mgear_skin.build_reexport_all_actions(states)
        if not any(
            action["action"] == mgear_skin.PACK_ACTION_REEXPORT
            for action in actions
        ):
            feedback.display_error(
                tr("No scene geometry matched the selected .gSkinPack members.")
            )
            return

        for state in states:
            if not state["has_skin_cluster"]:
                feedback.display_warning(
                    tr(
                        "Not re-exported, no skinned mesh in the scene: {base_name}",
                        base_name=state['base_name'],
                    )
                )

        with self.host.undo_chunk("exportSkinMgear"):
            try:
                path = mgear_skin.apply_pack_edit(pack_path, actions)
            except Exception as exc:
                feedback.display_error(str(exc))
                path = None

        self._finish_export(path)

    def _finish_export(self, path):
        """Report a written weight file and reselect it in the Files list."""
        if not path:
            return

        feedback.display_info(tr("Exported {path}", path=path))
        self.host.refresh_files()
        self.host.select_files([os.path.basename(path)])

    # ------------------
    # Pack editing

    def list_file_actions(self, selected_names) -> list:
        """Pack entries for a pack selection, member entries for member files."""
        if len(selected_names) == 1 and self.format.is_pack_filename(
            selected_names[0]
        ):
            return self._list_pack_actions()

        if selected_names and all(
            self._is_member_filename(name) for name in selected_names
        ):
            return [FileAction(
                tr("Add Member to .gSkinPack..."),
                self.add_selected_files_to_pack,
                tooltip=(
                    tr("Add the selected member file(s) to a .gSkinPack in this "
                       "directory and save it as a new version.")
                ),
                icon=ICON_IMPORT_SVG,
            )]

        return []

    def _list_pack_actions(self) -> list:
        can_export = self.format.is_available()
        has_selection = bool(scene.list_skinnable_shapes())
        if not can_export:
            export_tooltip = tr("mGear is not available.")
        elif not has_selection:
            export_tooltip = tr("Select skinned meshes in the scene first.")
        else:
            export_tooltip = tr(
                "Export the selected meshes and add them to this pack. A mesh "
                "already in the pack is re-exported over its member. The "
                "other members stay as they are. Saved as a new version."
            )
        return [
            FileAction(
                tr("Edit Pack..."),
                self.edit_selected_file,
                tooltip=(
                    tr("Choose what each pack member should point at, then save "
                       "the pack as a new version.")
                ),
                icon=ICON_RENAME_SVG,
            ),
            FileAction(
                tr("Add and Export Skin..."),
                self.add_and_export_selection,
                enabled=can_export and has_selection,
                tooltip=export_tooltip,
                icon=ICON_EXPORT_SVG,
            ),
        ]

    def _is_member_filename(self, name) -> bool:
        ext = os.path.splitext(name)[1].lstrip(".").lower()
        return ext in (
            mgear_skin.EXT_JSKIN.lower(), mgear_skin.EXT_GSKIN.lower()
        )

    def _confirm_pack_write(self, pack_path, plan) -> bool:
        """Show what the next pack version will do; True when confirmed."""
        items = (
            [tr("add: {name}", name=name) for name in plan["added"]]
            + [tr("update: {name}", name=name) for name in plan["updated"]]
            + [tr("keep: {name}", name=name) for name in plan["kept"]]
        )
        return confirm_with_items(
            self.host.parent_widget,
            tr("{app_title}: Update Pack", app_title=APP_TITLE),
            tr(
                "Write {next_pack_version_name}?",
                next_pack_version_name=mgear_skin.get_next_pack_version_name(pack_path),
            ),
            items,
            confirm_label=tr("Write"),
        )

    def add_and_export_selection(self):
        """Export the selected meshes into the selected .gSkinPack."""
        pack_path = self._selected_gskin_pack_path()
        if not pack_path:
            return

        shape_names = scene.list_skinnable_shapes()
        if not shape_names:
            feedback.display_error(tr("Select skinned meshes in the scene first."))
            return

        try:
            plan = mgear_skin.build_selection_actions(
                mgear_skin.list_pack_member_states(pack_path),
                mgear_skin.list_scene_export_candidates(shape_names),
            )
        except (OSError, ValueError) as exc:
            feedback.display_error(str(exc))
            return

        for base_name in plan["skipped"]:
            feedback.display_warning(
                tr("Not exported, no skinCluster: {base_name}", base_name=base_name)
            )

        if not plan["added"] and not plan["updated"]:
            feedback.display_error(
                tr("None of the selected meshes has a skinCluster to export.")
            )
            return

        if not self._confirm_pack_write(pack_path, plan):
            return

        with self.host.undo_chunk("exportSkinMgear"):
            try:
                path = mgear_skin.apply_pack_edit(pack_path, plan["actions"])
            except Exception as exc:
                feedback.display_error(str(exc))
                path = None

        self._finish_export(path)

    def add_selected_files_to_pack(self):
        """Add the selected member files to a .gSkinPack chosen in a dialog."""
        dir_name = self.host.get_directory()
        file_names = [
            name for name in self.host.list_selected_names()
            if self._is_member_filename(name)
        ]
        if not dir_name or not file_names:
            feedback.display_warning(tr("Select .jSkin / .gSkin file(s) to add."))
            return

        extensions = {
            os.path.splitext(name)[1].lstrip(".").lower()
            for name in file_names
        }
        if len(extensions) != 1:
            feedback.display_warning(
                tr("Select either .jSkin or .gSkin files, not both.")
            )
            return

        member_ext = extensions.pop()
        pack_names = io.filter_files_for_view(
            [
                name for name in self.format.list_files(dir_name)
                if self.format.is_pack_filename(name)
            ],
            "latest",
        )
        if not pack_names:
            feedback.display_warning(
                tr("No .gSkinPack found in the weight directory.")
            )
            return

        choices = []
        for pack_name in pack_names:
            pack_path = norm_path(os.path.join(dir_name, pack_name))
            try:
                pack_ext = mgear_skin.get_pack_member_extension(pack_path)
            except (OSError, ValueError):
                choices.append((
                    pack_name, False, tr("Could not read this pack."),
                ))
                continue

            if pack_ext == member_ext:
                choices.append((pack_name, True, ""))
            else:
                choices.append((
                    pack_name,
                    False,
                    tr("This pack uses .{ext} members.", ext=pack_ext),
                ))

        chosen = choose_gskin_pack(
            self.host.parent_widget,
            choices,
            tr(
                "Add {count} file(s) to which pack?\n"
                "Packs with a different member format are disabled.",
                count=len(file_names),
            ),
        )
        if not chosen:
            return

        pack_path = norm_path(os.path.join(dir_name, chosen))
        try:
            plan = mgear_skin.build_add_files_actions(
                mgear_skin.list_pack_member_states(pack_path), file_names
            )
        except (OSError, ValueError) as exc:
            feedback.display_error(str(exc))
            return

        if not self._confirm_pack_write(pack_path, plan):
            return

        try:
            path = mgear_skin.apply_pack_edit(pack_path, plan["actions"])
        except Exception as exc:
            feedback.display_error(str(exc))
            return

        self._finish_export(path)

    def edit_selected_file(self):
        """Open the pack editor for the selected .gSkinPack."""
        pack_path = self._selected_gskin_pack_path()
        if not pack_path:
            return

        self._edit_pack(pack_path)

    def _edit_pack(self, pack_path):
        """Run the pack editor and reselect the version it saved."""
        saved_path = edit_gskin_pack(self.host.parent_widget, pack_path)
        if not saved_path:
            return

        if norm_path(os.path.dirname(saved_path)) != self.host.get_directory():
            return

        self.host.refresh_files()
        self.host.select_files([os.path.basename(saved_path)])

    def _selected_gskin_pack_path(self):
        """Return the first selected on-disk .gSkinPack / .jSkinPack path."""
        for path in self.host.list_selected_paths():
            if mgear_skin.is_pack_file(path) and os.path.isfile(path):
                return path
        return None

    def _prompt_export_base_name(self, directory) -> str | None:
        """Ask for a .gSkinPack base name when Auto Naming is off.

        Remembers the last accepted name for the next export.
        """
        from wipskin.plugins.mgear.ui.gskin_pack_name_dialog import (
            prompt_gskin_pack_base_name,
        )

        initial = self.host.settings.raw_text(SETTING_MGEAR_PACK_BASE_NAME, "")
        base_name = prompt_gskin_pack_base_name(
            self.host.parent_widget, directory, initial_name=initial
        )
        if not base_name:
            return None

        self.host.settings.set(SETTING_MGEAR_PACK_BASE_NAME, base_name)
        return base_name
