"""Modal browser for a weight directory's `.backup` archive folder.

Archived files are deliberately out of the way of the Files list, so restoring
or purging one needs its own view rather than a mode on the main list.
"""

from __future__ import annotations

from wipskin.ui.qt_compat import QtCore, QtGui, QtWidgets

from wipskin.core import feedback
from wipskin.core import io
from wipskin.core import weight_files
from wipskin.core.constants import APP_TITLE
from wipskin.ui.confirm_list_dialog import confirm_with_items
from wipskin.ui.widgets import (
    CONTEXT_MENU_ICON_SIZE,
    ICON_ARCHIVE_SVG,
    ICON_DELETE_SVG,
    ICON_OPEN_SVG,
    ICON_REFRESH_SVG,
    exec_menu,
    make_colored_svg_icon,
    svg_icon_path,
)
from wipskin.core.i18n import tr


class ArchiveDialog(QtWidgets.QDialog):
    """Lists archived files, with Unarchive and permanent Delete."""

    def __init__(self, dir_name, scan_files, file_kind="weight", parent=None):
        """Args:
            dir_name (str): The live weight directory, not its `.backup` folder.
            scan_files (callable): scan_files(dir_name) -> list of file names,
                so the archive is listed with the tab's current format rules.
            file_kind (str): Noun used in warnings, e.g. "deformer weight".
        """
        super().__init__(parent)
        self.setWindowTitle(tr("{app_title}: Archives", app_title=APP_TITLE))
        self.setModal(True)
        self._dir_name = dir_name
        self._backup_dir = weight_files.get_backup_dir(dir_name)
        self._scan_files = scan_files
        self._file_kind = file_kind
        self._restored_names = []

        layout = QtWidgets.QVBoxLayout(self)

        path_label = QtWidgets.QLabel(self._backup_dir)
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        self.file_list = QtWidgets.QListWidget()
        self.file_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.file_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(
            self._show_file_context_menu
        )
        self.file_list.itemDoubleClicked.connect(
            lambda *_: self.unarchive_selected()
        )
        self.file_list.setToolTip(
            tr("Right-click for Unarchive and Delete.\n"
               "Double-click an entry to unarchive it.")
        )
        layout.addWidget(self.file_list)

        self._count_label = QtWidgets.QLabel()
        layout.addWidget(self._count_label)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        self._unarchive_button = buttons.addButton(
            tr("Unarchive"), QtWidgets.QDialogButtonBox.ActionRole
        )
        self._unarchive_button.clicked.connect(
            lambda *_: self.unarchive_selected()
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh()
        self.resize(460, 420)

    # ---- state

    def restored_names(self) -> list:
        """Names restored into the live directory during this session."""
        return list(self._restored_names)

    def selected_names(self) -> list:
        return [item.text() for item in self.file_list.selectedItems()]

    # ---- listing

    def refresh(self):
        """Rescan the archive folder, preserving what is still selected."""
        names = self._scan_files(self._backup_dir)
        selected = set(self.selected_names())
        self.file_list.blockSignals(True)
        self.file_list.setUpdatesEnabled(False)
        try:
            self.file_list.clear()
            self.file_list.addItems(names)
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                if item.text() in selected:
                    item.setSelected(True)
        finally:
            self.file_list.setUpdatesEnabled(True)
            self.file_list.blockSignals(False)
        if names:
            self._count_label.setText(tr("{count} archived file(s)", count=len(names)))
        else:
            self._count_label.setText(tr("Archive folder is empty."))

    # ---- context menu

    def _show_file_context_menu(self, point):
        item = self.file_list.itemAt(point)
        if item is not None and not item.isSelected():
            self.file_list.clearSelection()
            item.setSelected(True)
            self.file_list.setCurrentItem(item)

        has_selection = bool(self.selected_names())
        menu = QtWidgets.QMenu(self.file_list)
        menu.setToolTipsVisible(True)
        icon_color = self.file_list.palette().color(
            QtGui.QPalette.WindowText
        )

        def menu_icon(svg_filename):
            return make_colored_svg_icon(
                svg_icon_path(svg_filename), CONTEXT_MENU_ICON_SIZE, icon_color
            )

        unarchive_action = menu.addAction(
            menu_icon(ICON_ARCHIVE_SVG), tr("Unarchive")
        )
        unarchive_action.setEnabled(has_selection)
        unarchive_action.setToolTip(
            tr("Move the selected file(s) back into {dir_name}.", dir_name=self._dir_name)
        )
        menu.addSeparator()
        delete_action = menu.addAction(menu_icon(ICON_DELETE_SVG), tr("Delete"))
        delete_action.setEnabled(has_selection)
        delete_action.setToolTip(tr("Permanently delete the selected file(s)."))
        menu.addSeparator()
        open_dir_action = menu.addAction(
            menu_icon(ICON_OPEN_SVG), tr("Open Directory")
        )
        refresh_action = menu.addAction(menu_icon(ICON_REFRESH_SVG), tr("Refresh"))

        chosen = exec_menu(menu, self.file_list.mapToGlobal(point))
        if chosen is None:
            return

        if chosen is unarchive_action:
            self.unarchive_selected()
        elif chosen is delete_action:
            self.delete_selected()
        elif chosen is open_dir_action:
            self.open_directory()
        elif chosen is refresh_action:
            self.refresh()

    # ---- operations

    def unarchive_selected(self):
        """Move the selected archived files back into the live directory."""
        file_names = self.selected_names()
        if not file_names:
            feedback.display_warning(
                tr(
                    "Select archived {file_kind} file(s) to unarchive.",
                    file_kind=tr(self._file_kind),
                )
            )
            return

        if not confirm_with_items(
            self,
            tr("{app_title}: Unarchive Files", app_title=APP_TITLE),
            tr(
                "Move {count} file(s) back to {dir_name}?",
                count=len(file_names),
                dir_name=self._dir_name,
            ),
            file_names,
            confirm_label=tr("Unarchive"),
        ):
            return

        try:
            restored = weight_files.unarchive_weight_files(
                self._dir_name, file_names
            )
        except OSError as exc:
            feedback.display_error(tr("Unarchive failed: {exc}", exc=exc))
            self.refresh()
            return

        self._restored_names.extend(restored)
        feedback.display_info(tr("Unarchived {count} file(s).", count=len(restored)))
        self.refresh()

    def delete_selected(self):
        """Permanently delete the selected archived files."""
        file_names = self.selected_names()
        if not file_names:
            feedback.display_warning(
                tr("Select archived {file_kind} file(s) to delete.", file_kind=tr(self._file_kind))
            )
            return

        if not confirm_with_items(
            self,
            tr("{app_title}: Delete Archived Files", app_title=APP_TITLE),
            tr("Permanently delete {count} archived file(s)?", count=len(file_names)),
            file_names,
            confirm_label=tr("Delete"),
        ):
            return

        try:
            weight_files.delete_weight_files(self._backup_dir, file_names)
        except OSError as exc:
            feedback.display_error(tr("Delete failed: {exc}", exc=exc))
        self.refresh()

    def open_directory(self):
        if not io.open_directory(self._backup_dir):
            feedback.display_warning(
                tr("Invalid archive directory: {backup_dir}", backup_dir=self._backup_dir)
            )


def show_archive_dialog(parent, dir_name, scan_files, file_kind="weight") -> list:
    """Browse dir_name's archive folder.

    Returns:
        list: Names restored into dir_name, for the caller to reselect. Empty
            when nothing was unarchived.
    """
    dialog = ArchiveDialog(
        dir_name, scan_files, file_kind=file_kind, parent=parent
    )
    if hasattr(dialog, "exec"):
        dialog.exec()
    else:
        dialog.exec_()

    return dialog.restored_names()
