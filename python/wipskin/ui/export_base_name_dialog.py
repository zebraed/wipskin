"""Modal dialog for choosing an export base name when Auto Naming is off."""

from __future__ import annotations

from wipskin.ui.qt_compat import QtCore, QtWidgets

from wipskin.core import io
from wipskin.core.constants import APP_TITLE
from wipskin.core.i18n import tr


class ExportBaseNameDialog(QtWidgets.QDialog):
    """Optional combobox of existing base names + LineEdit for input."""

    def __init__(
        self,
        existing_names,
        initial_name="",
        title="",
        hint="",
        existing_label="Existing files:",
        placeholder="e.g. character_skin",
        empty_error="Enter a valid base name.",
        strip_extensions=(),
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            title or tr("{app_title}: Export", app_title=APP_TITLE)
        )
        self.setModal(True)
        self._existing_names = list(existing_names or [])
        self._strip_extensions = tuple(strip_extensions or ())
        self._empty_error = tr(empty_error)

        layout = QtWidgets.QVBoxLayout(self)

        if hint:
            hint_label = QtWidgets.QLabel(tr(hint))
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)

        if self._existing_names:
            layout.addWidget(QtWidgets.QLabel(tr(existing_label)))
            self._combo = QtWidgets.QComboBox()
            self._combo.addItem("")
            self._combo.addItems(self._existing_names)
            self._combo.setToolTip(tr("Select an existing base name to reuse."))
            self._combo.currentTextChanged.connect(self._on_combo_changed)
            layout.addWidget(self._combo)
        else:
            self._combo = None

        layout.addWidget(QtWidgets.QLabel(tr("Base name:")))
        self._line_edit = QtWidgets.QLineEdit()
        self._line_edit.setPlaceholderText(tr(placeholder))
        self._line_edit.setText(initial_name or "")
        self._line_edit.selectAll()
        layout.addWidget(self._line_edit)

        if self._combo is not None and initial_name in self._existing_names:
            self._combo.setCurrentText(initial_name)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._line_edit.setFocus(QtCore.Qt.OtherFocusReason)
        self.resize(360, self.sizeHint().height())

    def _on_combo_changed(self, text):
        if text:
            self._line_edit.setText(text)
            self._line_edit.selectAll()

    def base_name(self) -> str:
        return io.sanitize_export_base_name(
            self._line_edit.text(),
            strip_extensions=self._strip_extensions,
        )

    def accept(self):
        if not self.base_name():
            QtWidgets.QMessageBox.warning(
                self,
                self.windowTitle(),
                self._empty_error,
            )
            self._line_edit.setFocus(QtCore.Qt.OtherFocusReason)
            return
        super().accept()


def prompt_export_base_name(
    parent,
    directory,
    extension,
    initial_name="",
    title="",
    hint="",
    existing_label="Existing files:",
    placeholder="e.g. character_skin",
    empty_error="Enter a valid base name.",
    strip_extensions=None,
) -> str | None:
    """Show the base-name dialog.

    Returns:
        str: The sanitized name, or None if cancelled.
    """
    if strip_extensions is None:
        strip_extensions = (extension,)
    existing_names = io.list_base_names_for_extension(directory, extension)
    dialog = ExportBaseNameDialog(
        existing_names,
        initial_name=initial_name,
        title=title,
        hint=hint,
        existing_label=existing_label,
        placeholder=placeholder,
        empty_error=empty_error,
        strip_extensions=strip_extensions,
        parent=parent,
    )
    if hasattr(dialog, "exec"):
        result = dialog.exec()
    else:
        result = dialog.exec_()
    if result != QtWidgets.QDialog.Accepted:
        return None
    return dialog.base_name()
