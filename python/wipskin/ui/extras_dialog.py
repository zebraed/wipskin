"""Modeless Extras dialog for WipSkin (app-wide utilities).

Actions are surfaced as signals wired by the App. Format-specific extras
belong to their format plugin.
"""

from __future__ import annotations

import os

from wipskin.ui.qt_compat import QtCore, QtWidgets

from wipskin.core.constants import APP_TITLE
from wipskin.core.i18n import tr


class ExtrasDialog(QtWidgets.QDialog):
    """Modeless dialog for the Extras menu."""

    reset_preferences_requested = QtCore.Signal()
    reset_all_defaults_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("{app_title} Extras", app_title=APP_TITLE))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
        self._build_ui()

    def _build_ui(self):
        layout_extras = QtWidgets.QVBoxLayout(self)
        grid = QtWidgets.QGridLayout()
        layout_extras.addLayout(grid)

        reset_button = QtWidgets.QPushButton(tr("Reset Preferences"))
        reset_button.setToolTip(tr("Reset all user changed values back to defaults."))
        reset_button.clicked.connect(
            lambda *_: self.reset_preferences_requested.emit()
        )
        grid.addWidget(reset_button, 0, 0)

        package_dir = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        tt_package_path = tr("The location where the WipSkin Python package is saved.")
        package_path_label = QtWidgets.QLabel(tr("Package Path:"))
        package_path_label.setToolTip(tt_package_path)
        grid.addWidget(package_path_label, 1, 0, QtCore.Qt.AlignRight)
        package_path_edit = QtWidgets.QLineEdit(package_dir)
        package_path_edit.setReadOnly(True)
        package_path_edit.setToolTip(tt_package_path)
        grid.addWidget(package_path_edit, 1, 1)

        layout_utils = QtWidgets.QHBoxLayout()
        layout_extras.addLayout(layout_utils)
        reset_all_button = QtWidgets.QPushButton(tr("Reset All To Defaults"))
        reset_all_button.setToolTip(
            tr("Reset the requested Import/Export/Extras options back to their "
               "startup defaults.")
        )
        reset_all_button.clicked.connect(
            lambda *_: self.reset_all_defaults_requested.emit()
        )
        layout_utils.addWidget(reset_all_button)
        layout_utils.addStretch()
        layout_extras.addStretch()

    def closeEvent(self, event):
        """Hide instead of destroying so widget state persists per session."""
        event.accept()
        self.hide()
