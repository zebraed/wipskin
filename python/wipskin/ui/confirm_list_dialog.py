"""Modal confirm dialog whose item list scrolls instead of growing the dialog.

cmds.confirmDialog lays every message line out at once, so a few hundred file
names push its buttons past the bottom of the screen. Use this whenever the
prompt carries a list the user should be able to read in full.
"""

from __future__ import annotations

from wipskin.ui.qt_compat import QtCore, QtWidgets
from wipskin.core.i18n import tr


class ConfirmListDialog(QtWidgets.QDialog):
    """Message, a scrollable read-only listing, then Cancel / confirm."""

    def __init__(
        self,
        message,
        items,
        confirm_label="Continue",
        title="",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        message_label = QtWidgets.QLabel(message)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        # Read-only text rather than a list widget: it scrolls both ways for
        # long paths, stays copyable, and shows nothing that looks clickable.
        self._items_view = QtWidgets.QPlainTextEdit()
        self._items_view.setPlainText("\n".join(str(item) for item in items))
        self._items_view.setReadOnly(True)
        self._items_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        layout.addWidget(self._items_view)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        buttons.addButton(
            tr(confirm_label), QtWidgets.QDialogButtonBox.AcceptRole
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # These prompts are destructive, so Enter cancels like confirmDialog's
        # defaultButton="Cancel" did.
        cancel_button = buttons.button(QtWidgets.QDialogButtonBox.Cancel)
        cancel_button.setDefault(True)
        cancel_button.setFocus(QtCore.Qt.OtherFocusReason)

        self.resize(460, 420)


def confirm_with_items(
    parent,
    title,
    message,
    items,
    confirm_label="Continue",
) -> bool:
    """Show the dialog.

    Returns:
        bool: True when the user picks confirm_label.
    """
    dialog = ConfirmListDialog(
        message,
        items,
        confirm_label=confirm_label,
        title=title,
        parent=parent,
    )
    if hasattr(dialog, "exec"):
        result = dialog.exec()
    else:
        result = dialog.exec_()

    return result == QtWidgets.QDialog.Accepted
