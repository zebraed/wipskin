"""WIP Skin Export dialog: Base source + influence-to-group assignment.

Opened by controllers.skin_io when "WIP Skin" is checked in the XML Export
Options. Owns only the assignment UI; formats.wip_skin owns manifest schema,
naming, validation, and the actual filtered-XML export.
"""

from __future__ import annotations

import os

from maya import cmds

from wipskin.ui.qt_compat import QtCore, QtWidgets

from wipskin.core import feedback
from wipskin.core.constants import APP_TITLE
from wipskin.formats import scene
from wipskin.formats.skin.xml import wip as wip_skin
from wipskin.formats.skin.xml import weights as xml_skin
from wipskin.ui.widgets import ICON_LAYER_EDITOR_MAYA, make_maya_builtin_icon
from wipskin.core.i18n import tr


class _InfluenceListWidget(QtWidgets.QListWidget):
    """QListWidget that supports dragging its items into another
    _InfluenceListWidget (moving, not copying) -- used for the Unassigned
    pool and each group's influence list.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)

    def names(self) -> list:
        return [self.item(index).text() for index in range(self.count())]

    def add_names(self, names):
        existing = set(self.names())
        for name in names:
            if name not in existing:
                self.addItem(name)
                existing.add(name)

    def remove_names(self, names):
        remove_set = set(names)
        for index in reversed(range(self.count())):
            if self.item(index).text() in remove_set:
                self.takeItem(index)

    def dropEvent(self, event):
        source = event.source()
        if source is None or source is self or not isinstance(source, _InfluenceListWidget):
            super().dropEvent(event)
            return
        moved = [item.text() for item in source.selectedItems()]
        if not moved:
            event.ignore()
            return
        self.add_names(moved)
        source.remove_names(moved)
        event.setDropAction(QtCore.Qt.MoveAction)
        event.accept()


class _GroupBox(QtWidgets.QGroupBox):
    """One Layer group: rename field, member-filename preview, influence list."""

    changed = QtCore.Signal()
    remove_requested = QtCore.Signal(object)
    move_up_requested = QtCore.Signal(object)
    move_down_requested = QtCore.Signal(object)

    def __init__(self, base_name_getter, group_id=None, name="Layer", influences=None, ratio=100.0, parent=None):
        super().__init__(parent)
        self.group_id = group_id or wip_skin.new_group_id()
        self.ratio = ratio
        self._base_name_getter = base_name_getter
        self.setFlat(True)

        layout = QtWidgets.QVBoxLayout(self)
        header_row = QtWidgets.QHBoxLayout()
        layout.addLayout(header_row)
        layer_icon = make_maya_builtin_icon(ICON_LAYER_EDITOR_MAYA)
        if not layer_icon.isNull():
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(layer_icon.pixmap(16, 16))
            icon_label.setToolTip(tr("Layer group"))
            header_row.addWidget(icon_label)
        self.name_edit = QtWidgets.QLineEdit(name)
        self.name_edit.setToolTip(tr("Group display name (used to build the member XML filename)."))
        self.name_edit.textChanged.connect(self._on_name_changed)
        header_row.addWidget(self.name_edit)
        up_button = QtWidgets.QPushButton("▲")
        up_button.setFixedWidth(24)
        up_button.setToolTip(tr("Move group up."))
        up_button.clicked.connect(lambda *_: self.move_up_requested.emit(self))
        header_row.addWidget(up_button)
        down_button = QtWidgets.QPushButton("▼")
        down_button.setFixedWidth(24)
        down_button.setToolTip(tr("Move group down."))
        down_button.clicked.connect(lambda *_: self.move_down_requested.emit(self))
        header_row.addWidget(down_button)
        remove_button = QtWidgets.QPushButton("✕")
        remove_button.setFixedWidth(24)
        remove_button.setToolTip(tr("Remove this group (influences return to Unassigned)."))
        remove_button.clicked.connect(lambda *_: self.remove_requested.emit(self))
        header_row.addWidget(remove_button)

        self.filename_label = QtWidgets.QLabel()
        self.filename_label.setStyleSheet("color: gray;")
        layout.addWidget(self.filename_label)

        self.list_widget = _InfluenceListWidget()
        self.list_widget.setMinimumHeight(70)
        layout.addWidget(self.list_widget)
        if influences:
            self.list_widget.add_names(influences)

        self._update_filename_preview()

    def _on_name_changed(self, *_):
        self._update_filename_preview()
        self.changed.emit()

    def _update_filename_preview(self):
        base_name = self._base_name_getter() or "<base>"
        try:
            preview = wip_skin.group_member_filename(base_name, self.name_edit.text())
        except ValueError:
            preview = "(invalid group name)"
        self.filename_label.setText(preview)

    def display_name(self) -> str:
        return self.name_edit.text().strip()

    def influences(self) -> list:
        return self.list_widget.names()


class WipSkinExportDialog(QtWidgets.QDialog):
    """Configure a WIP Skin export: Base source + ordered Layer groups.
    """

    def __init__(self, shape, weight_dir, base_name, parent=None):
        super().__init__(parent)
        self._shape = shape
        self._weight_dir = weight_dir
        self._base_name = base_name
        self._skc = scene.get_skin_cluster(shape)
        self._existing_base_xml_path = ""
        self._groups = []  # list of _GroupBox, in export order
        self._result = None

        self.setWindowTitle(tr(
            "{app_title}: WIP Skin Export -- {base_name}",
            app_title=APP_TITLE,
            base_name=base_name,
        ))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(760, 560)
        self._build_ui()
        self._load_previous_manifest()
        self._populate_from_scene(keep_assignment=True)

    # ------------------
    # Build

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        source_row = QtWidgets.QHBoxLayout()
        layout.addLayout(source_row)
        source_row.addWidget(QtWidgets.QLabel(tr("Base source:")))
        self.source_scene_radio = QtWidgets.QRadioButton(tr("From Scene"))
        self.source_existing_radio = QtWidgets.QRadioButton(tr("From Existing XML"))
        group = QtWidgets.QButtonGroup(self)
        group.addButton(self.source_scene_radio)
        group.addButton(self.source_existing_radio)
        source_row.addWidget(self.source_scene_radio)
        source_row.addWidget(self.source_existing_radio)
        self.source_scene_radio.setChecked(True)
        self.existing_xml_edit = QtWidgets.QLineEdit()
        self.existing_xml_edit.setReadOnly(True)
        self.existing_xml_edit.setPlaceholderText(tr("(choose a previously exported skin XML)"))
        source_row.addWidget(self.existing_xml_edit, 1)
        self.browse_existing_button = QtWidgets.QPushButton(tr("Browse..."))
        self.browse_existing_button.clicked.connect(self._browse_existing_xml)
        source_row.addWidget(self.browse_existing_button)
        self.source_scene_radio.toggled.connect(self._on_source_toggled)
        self.source_existing_radio.toggled.connect(self._on_source_toggled)

        columns = QtWidgets.QHBoxLayout()
        layout.addLayout(columns, 1)

        left_box = QtWidgets.QGroupBox(tr("Unassigned / All Influences"))
        left_layout = QtWidgets.QVBoxLayout(left_box)
        self.pool_list = _InfluenceListWidget()
        left_layout.addWidget(self.pool_list)
        columns.addWidget(left_box, 1)

        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        base_box = QtWidgets.QGroupBox(wip_skin.BASE_GROUP_LABEL)
        base_layout = QtWidgets.QVBoxLayout(base_box)
        self.base_filename_label = QtWidgets.QLabel()
        self.base_filename_label.setStyleSheet("color: gray;")
        base_layout.addWidget(self.base_filename_label)
        self.base_list = _InfluenceListWidget()
        self.base_list.setMinimumHeight(70)
        base_layout.addWidget(self.base_list)
        right_layout.addWidget(base_box)

        self.groups_area = QtWidgets.QScrollArea()
        self.groups_area.setWidgetResizable(True)
        self.groups_container = QtWidgets.QWidget()
        self.groups_layout = QtWidgets.QVBoxLayout(self.groups_container)
        self.groups_layout.addStretch()
        self.groups_area.setWidget(self.groups_container)
        right_layout.addWidget(self.groups_area, 1)

        add_group_button = QtWidgets.QPushButton(tr("+ Add Layer"))
        add_group_button.clicked.connect(lambda *_: self._add_group())
        right_layout.addWidget(add_group_button)

        columns.addWidget(right_widget, 2)

        action_row = QtWidgets.QHBoxLayout()
        layout.addLayout(action_row)
        action_row.addWidget(QtWidgets.QLabel(tr("Target:")))
        self.target_combo = QtWidgets.QComboBox()
        action_row.addWidget(self.target_combo)
        add_selection_button = QtWidgets.QPushButton(tr("Add Maya Selection"))
        add_selection_button.setToolTip(
            tr("Assign the scene selection's influences (intersected with the "
               "skinCluster) to the Target group above.")
        )
        add_selection_button.clicked.connect(self._add_maya_selection)
        action_row.addWidget(add_selection_button)
        refresh_button = QtWidgets.QPushButton(tr("Refresh"))
        refresh_button.setToolTip(tr("Re-read influences from the skinCluster."))
        refresh_button.clicked.connect(lambda *_: self._populate_from_scene(keep_assignment=True))
        action_row.addWidget(refresh_button)
        action_row.addStretch()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.base_list.model().rowsInserted.connect(lambda *_: self._update_base_filename_preview())
        self._update_base_filename_preview()
        self._on_source_toggled(True)

    # ------------------
    # Scene / previous-manifest population

    def _all_scene_influences(self) -> list:
        if not self._skc:
            return []
        influences = cmds.skinCluster(self._skc, query=True, influence=True)
        if influences is None:
            return []
        return list(influences)

    def _load_previous_manifest(self):
        latest_name = wip_skin.find_latest_manifest_filename(self._weight_dir, self._base_name)
        if not latest_name:
            return
        wip_dir = wip_skin.wip_dir_path(self._weight_dir, self._base_name)
        path = os.path.join(wip_dir, latest_name)
        try:
            manifest = wip_skin.read_manifest(path)
        except (OSError, ValueError):
            return

        if manifest["base"]["source"] == wip_skin.BASE_SOURCE_EXISTING_XML:
            self.source_existing_radio.setChecked(True)
            source_file = manifest["base"].get("source_file", "")
            candidate = os.path.join(self._weight_dir, source_file) if source_file else ""
            if candidate and os.path.isfile(candidate):
                self._existing_base_xml_path = candidate
                self.existing_xml_edit.setText(source_file)
                self._apply_existing_xml_base()
            else:
                feedback.display_warning(
                    tr(
                        "WIP Export: previous Base XML source is no longer found ({file}); "
                        "choose it again via Browse.",
                        file=source_file or tr("(unknown)"),
                    )
                )
                self.base_list.add_names(manifest["base"]["influences"])
        else:
            self.source_scene_radio.setChecked(True)
            self.base_list.add_names(manifest["base"]["influences"])

        for group in manifest.get("groups", []):
            self._add_group(
                group_id=group["id"],
                name=group["name"],
                influences=group["influences"],
                ratio=group.get("ratio", wip_skin.DEFAULT_RATIO),
            )

    def _populate_from_scene(self, keep_assignment=True):
        scene_influences = self._all_scene_influences()
        assigned = set(self.base_list.names())
        for group_box in self._groups:
            assigned.update(group_box.influences())
        if not keep_assignment:
            self.base_list.clear()
            for group_box in self._groups:
                group_box.list_widget.clear()
            assigned = set()

        stale = assigned - set(scene_influences)
        if stale:
            feedback.display_warning(
                "WIP Export: influence(s) no longer on the skinCluster: "
                + ", ".join(sorted(stale))
                + " -- please reassign or remove before exporting."
            )

        self.pool_list.clear()
        new_names = [name for name in scene_influences if name not in assigned]
        self.pool_list.add_names(new_names)
        self._refresh_target_combo()

    def _refresh_target_combo(self):
        current = self.target_combo.currentText()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItem(wip_skin.BASE_GROUP_LABEL)
        for group_box in self._groups:
            self.target_combo.addItem(group_box.display_name())
        index = self.target_combo.findText(current)
        self.target_combo.setCurrentIndex(index if index >= 0 else 0)
        self.target_combo.blockSignals(False)

    # ------------------
    # Base source

    def _on_source_toggled(self, _checked):
        is_existing = self.source_existing_radio.isChecked()
        self.existing_xml_edit.setEnabled(is_existing)
        self.browse_existing_button.setEnabled(is_existing)
        self.base_list.setEnabled(not is_existing)
        self.base_list.setAcceptDrops(not is_existing)
        if is_existing:
            self._apply_existing_xml_base()

    def _browse_existing_xml(self):
        paths = cmds.fileDialog2(
            caption=tr("{app_title}: Choose Base Skin XML", app_title=APP_TITLE),
            fileMode=1,
            okCaption=tr("Choose"),
            fileFilter=f"{APP_TITLE} XML Files (*.{xml_skin.EXT})",
            startingDirectory=self._weight_dir,
        )
        if not paths:
            return
        path = paths[0]
        if not xml_skin.is_skin_weight_file(path):
            feedback.display_error(tr("Not a skin weight XML: {path}", path=path))
            return
        self._existing_base_xml_path = path
        self.existing_xml_edit.setText(os.path.relpath(path, self._weight_dir))
        self._apply_existing_xml_base()

    def _apply_existing_xml_base(self):
        if not self._existing_base_xml_path or not os.path.isfile(self._existing_base_xml_path):
            return
        info = xml_skin.parse_file_info(self._existing_base_xml_path)
        vertex_count = None
        if self._shape and cmds.nodeType(self._shape) == "mesh":
            vertex_count = cmds.polyEvaluate(self._shape, vertex=True)
        errors = wip_skin.validate_existing_base_xml(
            self._existing_base_xml_path, info.get("shape", ""), vertex_count
        )
        if errors:
            feedback.display_warning("WIP Export Base XML: " + "; ".join(errors))
        self.base_list.clear()
        self.base_list.setEnabled(False)
        self.base_list.add_names(info["influences"])
        self._update_base_filename_preview()
        # _populate_from_scene() below warns about any assigned-but-not-
        # in-scene influence, which also covers a stale Base XML influence.
        self._populate_from_scene(keep_assignment=True)

    def _update_base_filename_preview(self):
        try:
            preview = wip_skin.base_member_filename(self._base_name or "<base>")
        except Exception:
            preview = ""
        self.base_filename_label.setText(preview)

    # ------------------
    # Groups

    def _add_group(self, group_id=None, name=None, influences=None, ratio=100.0):
        if name is None:
            name = f"Layer{len(self._groups) + 1}"
        group_box = _GroupBox(
            base_name_getter=lambda: self._base_name,
            group_id=group_id,
            name=name,
            influences=influences,
            ratio=ratio,
        )
        group_box.remove_requested.connect(self._remove_group)
        group_box.move_up_requested.connect(lambda box: self._move_group(box, -1))
        group_box.move_down_requested.connect(lambda box: self._move_group(box, 1))
        group_box.changed.connect(self._refresh_target_combo)
        self._groups.append(group_box)
        self.groups_layout.insertWidget(self.groups_layout.count() - 1, group_box)
        self._refresh_target_combo()
        return group_box

    def _remove_group(self, group_box):
        if group_box not in self._groups:
            return
        orphaned = group_box.influences()
        self._groups.remove(group_box)
        self.groups_layout.removeWidget(group_box)
        group_box.setParent(None)
        group_box.deleteLater()
        self.pool_list.add_names(orphaned)
        self._refresh_target_combo()

    def _move_group(self, group_box, direction):
        if group_box not in self._groups:
            return
        index = self._groups.index(group_box)
        new_index = index + direction
        if new_index < 0 or new_index >= len(self._groups):
            return
        self._groups[index], self._groups[new_index] = (
            self._groups[new_index],
            self._groups[index],
        )
        self.groups_layout.removeWidget(group_box)
        self.groups_layout.insertWidget(new_index, group_box)
        self._refresh_target_combo()

    # ------------------
    # Add Maya Selection

    def _target_list(self):
        text = self.target_combo.currentText()
        if text == wip_skin.BASE_GROUP_LABEL:
            return self.base_list
        for group_box in self._groups:
            if group_box.display_name() == text:
                return group_box.list_widget
        return None

    def _add_maya_selection(self):
        target = self._target_list()
        if target is None or not target.isEnabled():
            feedback.display_warning(tr("Choose a valid, editable Target group first."))
            return
        selection = cmds.ls(sl=True, long=True)
        if not selection:
            feedback.display_warning(tr("Nothing selected in Maya."))
            return
        scene_influences = set(self._all_scene_influences())
        matched = []
        for item in selection:
            short = item.rsplit("|", 1)[-1]
            for candidate in (item, short):
                if candidate in scene_influences and candidate not in matched:
                    matched.append(candidate)
                    break
        if not matched:
            feedback.display_warning(tr("Selection has no skinCluster influences."))
            return
        # Only move influences currently sitting in the Unassigned pool --
        # avoid silently stealing an influence from another group.
        pool_names = set(self.pool_list.names())
        moved = [name for name in matched if name in pool_names]
        if not moved:
            feedback.display_warning(
                tr("Selected influence(s) are already assigned to a group.")
            )
            return
        target.add_names(moved)
        self.pool_list.remove_names(moved)

    # ------------------
    # Accept / result

    def _current_group_pairs(self):
        return [(box.display_name(), box.influences()) for box in self._groups]

    def accept(self):
        base_source = (
            wip_skin.BASE_SOURCE_EXISTING_XML
            if self.source_existing_radio.isChecked()
            else wip_skin.BASE_SOURCE_SCENE
        )
        scene_influences = self._all_scene_influences()
        group_pairs = self._current_group_pairs()

        if base_source == wip_skin.BASE_SOURCE_EXISTING_XML:
            if not self._existing_base_xml_path:
                feedback.display_error(tr("Choose a Base XML file first."))
                return
            base_influences = self.base_list.names()
            errors = wip_skin.validate_group_assignment(
                base_influences, group_pairs, scene_influences, base_locked=True
            )
        else:
            base_influences = self.base_list.names()
            errors = wip_skin.validate_group_assignment(
                base_influences, group_pairs, scene_influences, base_locked=False
            )

        if self.pool_list.count() > 0 and not errors:
            errors.append(
                "Unassigned influence(s): " + ", ".join(self.pool_list.names())
            )

        if errors:
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(), "\n".join(errors)
            )
            return

        self._result = {
            "base_source": base_source,
            "base_influences": base_influences,
            "existing_base_xml_path": self._existing_base_xml_path,
            "groups": [
                {
                    "id": box.group_id,
                    "name": box.display_name(),
                    "influences": box.influences(),
                    "ratio": box.ratio,
                }
                for box in self._groups
            ],
        }
        super().accept()

    def result_config(self) -> dict:
        """Resolved export configuration; only valid after accept()."""
        return self._result
