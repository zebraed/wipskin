"""Modal editor for one mGear .gSkinPack: what each member should point at.

Replaces guessing an outcome from checkboxes plus scene selection. The pack's
members are on screen with what is available for each, and the row's choice is
the whole instruction.
"""

from __future__ import annotations

import os

from maya import cmds

from wipskin.api.ui import QtCore, QtWidgets

from wipskin.api.maya import feedback
from wipskin.api import APP_TITLE
from wipskin.plugins.mgear import weights as mgear_skin
from wipskin.api import tr

_COLUMNS = ("Member", "Recorded", "Latest", "Scene", "Action")

_ACTION_LABELS = (
    (mgear_skin.PACK_ACTION_KEEP, "Keep"),
    (mgear_skin.PACK_ACTION_LATEST, "Latest"),
    (mgear_skin.PACK_ACTION_REEXPORT, "Re-export"),
)


def _version_text(version: int) -> str:
    return f"{int(version):04d}" if version else "-"


class GskinPackEditorDialog(QtWidgets.QDialog):
    """One row per pack member, each choosing Keep / Latest / Re-export."""

    def __init__(self, pack_path, parent=None):
        super().__init__(parent)
        self._pack_path = pack_path
        self._states = []
        #: base_name -> QButtonGroup, read back when saving.
        self._action_groups = {}
        self._saved_path = ""

        self.setWindowTitle(tr("{app_title}: Edit Pack", app_title=APP_TITLE))
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        name_label = QtWidgets.QLabel(os.path.basename(pack_path))
        name_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(name_label)

        self.table = QtWidgets.QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(name) for name in _COLUMNS])
        header = self.table.horizontalHeader()
        # Content columns size themselves to their widest entry and keep doing
        # so as rows reload; Action takes whatever width is left.
        for column in range(len(_COLUMNS) - 1):
            header.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeToContents
            )
        header.setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._select_row_mesh)
        self.table.setToolTip(
            tr("Keep: leave this entry as the pack already records it.\n"
               "Latest: point it at the newest file already on disk.\n"
               "Re-export: write a new member file from the scene mesh.\n"
               "Double-click a row to select its mesh in Maya.")
        )
        layout.addWidget(self.table)

        self._summary_label = QtWidgets.QLabel()
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        self._save_button = buttons.addButton(
            tr("Save as New Version"), QtWidgets.QDialogButtonBox.AcceptRole
        )
        self._save_button.clicked.connect(lambda *_: self.save())
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()
        self.resize(620, 400)

    # ---- state

    def saved_path(self) -> str:
        """Manifest written by Save, or empty when nothing was written."""
        return self._saved_path

    # ---- table

    def _load(self):
        try:
            self._states = mgear_skin.list_pack_member_states(self._pack_path)
        except (OSError, ValueError) as exc:
            feedback.display_error(tr("Failed to read pack: {exc}", exc=exc))
            self._states = []

        self.table.setRowCount(len(self._states))
        self._action_groups = {}
        for row, state in enumerate(self._states):
            self._build_row(row, state)
        self._update_summary()

    def _build_row(self, row, state):
        for column, text in enumerate((
            state["base_name"],
            _version_text(state["recorded_version"]),
            _version_text(state["latest_version"]),
            self._scene_text(state),
        )):
            item = QtWidgets.QTableWidgetItem(text)
            self.table.setItem(row, column, item)

        if not state["recorded_exists"]:
            self.table.item(row, 1).setToolTip(tr("Recorded file is not on disk."))

        self.table.setCellWidget(row, 4, self._build_action_cell(state))

    def _scene_text(self, state) -> str:
        if not state["transform"]:
            return tr("not found")

        short_name = state["transform"].rsplit("|", 1)[-1]
        if not state["has_skin_cluster"]:
            return tr("{name} (no skinCluster)", name=short_name)

        return short_name

    def _build_action_cell(self, state) -> QtWidgets.QWidget:
        """Three radios per row; unavailable choices are disabled, not hidden.

        Seeing why a choice is unavailable is the point of this dialog.
        """
        cell = QtWidgets.QWidget()
        cell_layout = QtWidgets.QHBoxLayout(cell)
        cell_layout.setContentsMargins(4, 0, 4, 0)
        group = QtWidgets.QButtonGroup(cell)
        enabled_by_action = {
            mgear_skin.PACK_ACTION_KEEP: True,
            mgear_skin.PACK_ACTION_LATEST: state["has_newer"],
            mgear_skin.PACK_ACTION_REEXPORT: state["has_skin_cluster"],
        }
        for action, label in _ACTION_LABELS:
            radio = QtWidgets.QRadioButton(tr(label))
            radio.setEnabled(enabled_by_action[action])
            radio.setProperty("pack_action", action)
            group.addButton(radio)
            cell_layout.addWidget(radio)
            # Newer file on disk is what the user almost always wants; a
            # re-export is never automatic because it writes to the scene's
            # weights, not just the manifest.
            if action == mgear_skin.PACK_ACTION_LATEST and state["has_newer"]:
                radio.setChecked(True)
            elif action == mgear_skin.PACK_ACTION_KEEP and not state["has_newer"]:
                radio.setChecked(True)
        cell_layout.addStretch()
        self._action_groups[state["base_name"]] = group
        # Connected only now: the default checks above would otherwise
        # summarize while later rows have no group yet (_load summarizes
        # once every row exists).
        for radio in group.buttons():
            radio.toggled.connect(lambda *_: self._update_summary())
        return cell

    def _selected_action(self, base_name) -> str:
        group = self._action_groups[base_name]
        checked = group.checkedButton()
        if checked is None:
            return mgear_skin.PACK_ACTION_KEEP

        return str(checked.property("pack_action"))

    def list_actions(self) -> list:
        """One apply_pack_edit action per member, in packFiles order."""
        actions = []
        for state in self._states:
            actions.append({
                "base_name": state["base_name"],
                "action": self._selected_action(state["base_name"]),
                "transform": state["transform"],
            })
        return actions

    # ---- summary

    def _update_summary(self):
        if not self._states:
            self._summary_label.setText(tr("This pack lists no members."))
            self._save_button.setEnabled(False)
            return

        counts = {action: 0 for action, _label in _ACTION_LABELS}
        for action in self.list_actions():
            counts[action["action"]] += 1
        breakdown = ", ".join(
            f"{counts[action]} {tr(label).lower()}"
            for action, label in _ACTION_LABELS
            if counts[action]
        )
        target = mgear_skin.get_next_pack_version_name(self._pack_path)
        self._summary_label.setText(tr(
            "Save -> {target}   ({breakdown})",
            target=target,
            breakdown=breakdown,
        ))
        self._save_button.setEnabled(True)

    # ---- actions

    def _select_row_mesh(self, item):
        """Double-click: select this member's mesh in Maya."""
        state = self._states[item.row()]
        transform = state["transform"]
        if not transform or not cmds.objExists(transform):
            feedback.display_warning(
                tr("No scene mesh for pack member: {base_name}", base_name=state['base_name'])
            )
            return

        cmds.select(transform, replace=True)

    def save(self):
        """Write the next pack version from the rows' choices."""
        try:
            self._saved_path = mgear_skin.apply_pack_edit(
                self._pack_path, self.list_actions()
            )
        except Exception as exc:
            feedback.display_error(str(exc))
            self._load()
            return

        feedback.display_info(tr("Saved {saved_path}", saved_path=self._saved_path))
        self.accept()


def edit_gskin_pack(parent, pack_path) -> str:
    """Show the pack editor.

    Returns:
        str: Manifest written by Save, or empty when cancelled.
    """
    dialog = GskinPackEditorDialog(pack_path, parent=parent)
    if hasattr(dialog, "exec"):
        dialog.exec()
    else:
        dialog.exec_()

    return dialog.saved_path()
