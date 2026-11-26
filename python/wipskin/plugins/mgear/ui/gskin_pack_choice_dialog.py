"""Modal picker for which .gSkinPack a member file should be added to."""

from __future__ import annotations

from wipskin.api.ui import QtCore, QtWidgets

from wipskin.api import APP_TITLE
from wipskin.api import tr


class GskinPackChoiceDialog(QtWidgets.QDialog):
    """Single-choice list of packs; unusable ones stay visible but disabled."""

    def __init__(self, choices, message, parent=None):
        """Args:
            choices (list): (pack file name, enabled, tooltip) triples.
            message (str): Prompt shown above the list.
        """
        super().__init__(parent)
        self.setWindowTitle(tr("{app_title}: Add Member to .gSkinPack", app_title=APP_TITLE))
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        message_label = QtWidgets.QLabel(message)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        self._list = QtWidgets.QListWidget()
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        first_enabled = None
        for name, enabled, tooltip in choices:
            item = QtWidgets.QListWidgetItem(name)
            if tooltip:
                item.setToolTip(tooltip)

            if not enabled:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            elif first_enabled is None:
                first_enabled = item

            self._list.addItem(item)
        layout.addWidget(self._list)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self._ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._list.itemSelectionChanged.connect(self._update_ok_button)
        self._list.itemDoubleClicked.connect(lambda *_: self.accept())
        if first_enabled is not None:
            first_enabled.setSelected(True)

        self._update_ok_button()
        self.resize(380, 320)

    def _update_ok_button(self):
        self._ok_button.setEnabled(bool(self._list.selectedItems()))

    def chosen_name(self) -> str:
        """File name of the selected pack, or empty when none is."""
        items = self._list.selectedItems()
        if not items:
            return ""

        return items[0].text()

    def accept(self):
        if not self.chosen_name():
            return

        super().accept()


def choose_gskin_pack(parent, choices, message) -> str:
    """Show the picker.

    Args:
        parent (QWidget): Dialog parent.
        choices (list): (pack file name, enabled, tooltip) triples.
        message (str): Prompt shown above the list.

    Returns:
        str: The chosen pack file name, or empty when cancelled.
    """
    dialog = GskinPackChoiceDialog(choices, message, parent=parent)
    if hasattr(dialog, "exec"):
        accepted = dialog.exec()
    else:
        accepted = dialog.exec_()

    if accepted != QtWidgets.QDialog.Accepted:
        return ""

    return dialog.chosen_name()
