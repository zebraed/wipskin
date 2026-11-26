"""Modal dialog for the file list's "Generate Opposite Side..." entry."""

from __future__ import annotations

from wipskin.ui.qt_compat import QtCore, QtWidgets

from wipskin.core.constants import APP_TITLE
from wipskin.core.i18n import tr


class GenerateOppositeSideDialog(QtWidgets.QDialog):
    """Source-side / destination-side LineEdit pair + Ok/Cancel."""

    def __init__(self, initial_source="", initial_destination="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("{app_title}: Generate Opposite Side", app_title=APP_TITLE))
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        hint = QtWidgets.QLabel(
            tr("Copy the selected file(s), replacing the source side string "
               "with the destination side string in the filename and file "
               "content.")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(QtWidgets.QLabel(tr("Source side:")))
        self._source_edit = QtWidgets.QLineEdit(initial_source)
        layout.addWidget(self._source_edit)

        layout.addWidget(QtWidgets.QLabel(tr("Destination side:")))
        self._destination_edit = QtWidgets.QLineEdit(initial_destination)
        layout.addWidget(self._destination_edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._source_edit.setFocus(QtCore.Qt.OtherFocusReason)
        self._source_edit.selectAll()
        self.resize(360, self.sizeHint().height())

    def source_side(self) -> str:
        return self._source_edit.text().strip()

    def destination_side(self) -> str:
        return self._destination_edit.text().strip()

    def accept(self):
        if not self.source_side():
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(), tr("Enter a source side string to replace.")
            )
            self._source_edit.setFocus(QtCore.Qt.OtherFocusReason)
            return
        if self.source_side() == self.destination_side():
            QtWidgets.QMessageBox.warning(
                self,
                self.windowTitle(),
                tr("Source side and destination side must be different."),
            )
            self._destination_edit.setFocus(QtCore.Qt.OtherFocusReason)
            return
        super().accept()


def prompt_opposite_side(parent, initial_source="", initial_destination=""):
    """Show the dialog; returns (source, destination) or None if cancelled."""
    dialog = GenerateOppositeSideDialog(
        initial_source=initial_source,
        initial_destination=initial_destination,
        parent=parent,
    )
    if hasattr(dialog, "exec"):
        result = dialog.exec()
    else:
        result = dialog.exec_()
    if result != QtWidgets.QDialog.Accepted:
        return None
    return dialog.source_side(), dialog.destination_side()
