"""Shared WipSkin view components used by both top-level tabs.

FileExplorerSection and ViewerPanel factor out the directory / file-list /
viewer plumbing that was previously duplicated between the SkinWeight and
Deformer tabs.
"""

from __future__ import annotations

import os

from wipskin.ui.qt_compat import QtCore, QtGui, QtWidgets

from wipskin.core import feedback
from wipskin.core import io
from wipskin.core.constants import (
    APP_TITLE,
    DEFAULT_CONVERT_DST,
    DEFAULT_CONVERT_SRC,
    DEFAULT_EXPLORER_LEFT_SPLITTER_SIZES,
    DEFAULT_EXPLORER_SPLITTER_SIZES,
    DEFAULT_VIEWER_SPLITTER_SIZES,
    FILE_VIEW_FULL,
    FILE_VIEW_LATEST,
    SETTING_CONVERT_DST,
    SETTING_CONVERT_SRC,
    SETTING_FILE_VIEW_MODE,
    SETTING_LAST_SAVE_PATH,
)
from wipskin.core import weight_files
from wipskin.core.path_utils import norm_path
from wipskin.ui.archive_dialog import show_archive_dialog
from wipskin.ui.confirm_list_dialog import confirm_with_items
from wipskin.ui.opposite_side_dialog import prompt_opposite_side
from wipskin.ui.widgets import (
    CONTEXT_MENU_ICON_SIZE,
    ICON_ARCHIVE_SVG,
    ICON_DELETE_SVG,
    ICON_EXPORT_SVG,
    ICON_IMPORT_SVG,
    ICON_OPEN_SVG,
    ICON_OPPOSITE_SIDE_SVG,
    ICON_REFRESH_SVG,
    ICON_RENAME_SVG,
    ElidedLabel,
    exec_menu,
    MayaCollapsibleGroup,
    make_colored_svg_icon,
    make_history_label,
    make_io_button,
    svg_icon_path,
)
from wipskin.core.i18n import tr


#: Set on a dimmed row: influence not in the scene, or file not on disk.
#: Kept out of the item flags so the row stays selectable and right-clickable.
_MISSING_ROLE = QtCore.Qt.UserRole + 2


def is_missing_item(item) -> bool:
    """True for a dimmed viewer row."""
    return bool(item.data(_MISSING_ROLE))


class ResetRegistry:
    """Right-click 'Reset To Default' support for option widgets, plus a
    reset-everything entry point for the Extras dialog.
    """

    def __init__(self):
        self._callbacks = []

    def register(self, widget: QtWidgets.QWidget, reset_callback, shared: bool = False):
        """Attach a reset context menu to widget.

        shared=True skips adding reset_callback to the reset-all list (for
        widget groups where several widgets share one callback).
        """
        widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda point, w=widget, cb=reset_callback: self._show_menu(w, cb, point)
        )
        if not shared:
            self._callbacks.append(reset_callback)

    def register_group(self, widgets, reset_callback):
        """Register widgets sharing one reset callback; runs once on reset-all."""
        for widget in widgets:
            self.register(widget, reset_callback, shared=True)
        self._callbacks.append(reset_callback)

    def _show_menu(self, widget, reset_callback, point):
        menu = QtWidgets.QMenu(widget)
        action = menu.addAction(tr("Reset To Default"))
        if exec_menu(menu, widget.mapToGlobal(point)) == action:
            reset_callback()

    def apply_all(self):
        """Reset every registered control to its default."""
        for reset_callback in self._callbacks:
            reset_callback()


def bind_checkbox(
    settings,
    key: str,
    checkbox: QtWidgets.QCheckBox,
    registry: ResetRegistry = None,
    on_change=None,
):
    """Initialize a checkbox from a tracked settings flag, persist it on click,
    and (optionally) register a reset-to-default context menu.
    """
    checkbox.setChecked(settings.flag(key))

    def _save(*_):
        settings.set_flag(key, checkbox.isChecked())
        if on_change is not None:
            on_change()

    checkbox.clicked.connect(_save)

    if registry is not None:
        def _reset():
            checkbox.setChecked(bool(settings.default(key)))
            _save()
        registry.register(checkbox, _reset)
    return _save


def bind_radio_value(
    settings,
    key: str,
    value_by_button: dict,
    registry: ResetRegistry = None,
    on_change=None,
):
    """Bind radio buttons to a tracked settings value.

    value_by_button maps QRadioButton -> stored value. The button matching the
    saved value is checked; toggles persist the checked button's value.
    """
    saved = str(settings.value(key))
    buttons = list(value_by_button)
    for button, value in value_by_button.items():
        if str(value) == saved:
            button.setChecked(True)
            break
    else:
        buttons[0].setChecked(True)

    def _save(*_):
        for button, value in value_by_button.items():
            if button.isChecked():
                settings.set(key, value)
                break
        if on_change is not None:
            on_change()

    def _on_toggled(checked):
        if checked:
            _save()

    for button in buttons:
        button.toggled.connect(_on_toggled)

    if registry is not None:
        default = str(settings.default(key))

        def _reset():
            for button, value in value_by_button.items():
                if str(value) == default:
                    button.setChecked(True)
                    return
        registry.register_group(buttons, _reset)
    return _save


def build_collapsible_group(
    settings,
    title: str,
    setting_key: str,
    content_builder,
) -> MayaCollapsibleGroup:
    """Collapsible options group whose expanded state persists in settings."""
    group = MayaCollapsibleGroup(title, collapsed=not settings.flag(setting_key))
    content_builder(group.content_layout)
    group.toggled.connect(
        lambda is_expanded: settings.set_flag(setting_key, is_expanded)
    )
    return group


class ViewerPanel(QtWidgets.QGroupBox):
    """File viewer panel: header label, optional chunk selector, metadata text,
    and a name list — split vertically with persisted sizes.
    """

    selector_changed = QtCore.Signal(int)
    print_requested = QtCore.Signal()
    select_all_requested = QtCore.Signal()
    item_clicked = QtCore.Signal(object)
    item_activated = QtCore.Signal(object)
    rename_influence_requested = QtCore.Signal(str)

    def __init__(
        self,
        settings,
        title: str,
        placeholder: str,
        splitter_setting_key: str,
        list_label: str = "Influences:",
        selector_label: str = None,
        selector_tooltip: str = "",
        with_select_all: bool = False,
        with_print_button: bool = False,
        print_tooltip: str = "",
        meta_tooltip: str = "",
        list_tooltip: str = "",
        can_rename_influence=None,
        parent=None,
    ):
        super().__init__(title, parent)
        self._settings = settings
        self._placeholder = placeholder
        layout = QtWidgets.QVBoxLayout(self)

        # Elide instead of word-wrap so header height stays constant and the
        # panel doesn't re-layout when the selected file name changes.
        self.file_label = ElidedLabel(placeholder)
        layout.addWidget(self.file_label)

        self.selector_row = None
        self.selector_combo = None
        self._selector_label = None
        if selector_label is not None:
            self.selector_row = QtWidgets.QWidget()
            selector_layout = QtWidgets.QHBoxLayout(self.selector_row)
            selector_layout.setContentsMargins(0, 0, 0, 0)
            self._selector_label = QtWidgets.QLabel(selector_label)
            selector_layout.addWidget(self._selector_label)
            self.selector_combo = QtWidgets.QComboBox()
            if selector_tooltip:
                self.selector_combo.setToolTip(selector_tooltip)
            self.selector_combo.currentIndexChanged.connect(
                lambda index: self.selector_changed.emit(index)
            )
            selector_layout.addWidget(self.selector_combo, 1)
            layout.addWidget(self.selector_row)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        self.splitter = splitter

        meta_widget = QtWidgets.QWidget()
        meta_layout = QtWidgets.QVBoxLayout(meta_widget)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        self.meta_text = QtWidgets.QTextEdit()
        self.meta_text.setReadOnly(True)
        if meta_tooltip:
            self.meta_text.setToolTip(meta_tooltip)
        meta_layout.addWidget(self.meta_text, 1)

        self.print_button = None
        if with_print_button:
            print_row = QtWidgets.QHBoxLayout()
            self.print_button = QtWidgets.QPushButton(tr("Print to Script Editor"))
            if print_tooltip:
                self.print_button.setToolTip(print_tooltip)
            self.print_button.clicked.connect(
                lambda *_: self.print_requested.emit()
            )
            print_row.addWidget(self.print_button)
            print_row.addStretch()
            meta_layout.addLayout(print_row)
        meta_widget.setMinimumHeight(80)

        list_widget = QtWidgets.QWidget()
        list_layout = QtWidgets.QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_header = QtWidgets.QHBoxLayout()
        self._list_label = QtWidgets.QLabel(tr(list_label))
        list_header.addWidget(self._list_label)
        self._select_all_button = None
        if with_select_all:
            self._select_all_button = QtWidgets.QPushButton(tr("select all"))
            self._select_all_button.setToolTip(tr("Select all influences in Maya."))
            self._select_all_button.clicked.connect(
                lambda *_: self.select_all_requested.emit()
            )
            list_header.addWidget(self._select_all_button)
        list_header.addStretch()
        list_layout.addLayout(list_header)
        self.name_list = QtWidgets.QListWidget()
        if list_tooltip:
            self.name_list.setToolTip(list_tooltip)
        self.name_list.itemClicked.connect(
            lambda item: self.item_clicked.emit(item)
        )
        self.name_list.itemDoubleClicked.connect(
            lambda item: self.item_activated.emit(item)
        )
        self._can_rename_influence = can_rename_influence
        if can_rename_influence is not None:
            self.name_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.name_list.customContextMenuRequested.connect(
                self._show_name_context_menu
            )
        list_layout.addWidget(self.name_list, 1)
        list_widget.setMinimumHeight(60)

        # The name list is not placed here: the owning FileExplorerSection
        # puts it under the file list (list_widget), and gives this splitter's
        # lower pane to its side widget (attach_side_widget).
        self.list_widget = list_widget
        self._splitter_key = splitter_setting_key
        splitter.addWidget(meta_widget)
        splitter.splitterMoved.connect(
            lambda *_: settings.save_splitter_sizes(
                splitter_setting_key, splitter.sizes()
            )
        )
        layout.addWidget(splitter, 1)

    def attach_side_widget(self, widget: QtWidgets.QWidget):
        """Place widget in the lower pane, under the metadata text."""
        self.splitter.addWidget(widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes(self._settings.splitter_sizes(
            self._splitter_key, DEFAULT_VIEWER_SPLITTER_SIZES
        ))

    def _show_name_context_menu(self, point):
        item = self.name_list.itemAt(point)
        # Influences missing from the scene are dimmed but still selectable:
        # they are exactly the ones a joint rename left behind, and selecting
        # them is how the user confirms what Rename will act on.
        if item is not None:
            self.name_list.setCurrentItem(item)

        menu = QtWidgets.QMenu(self.name_list)
        menu.setToolTipsVisible(True)
        icon_color = self.name_list.palette().color(QtGui.QPalette.WindowText)
        rename_action = menu.addAction(
            make_colored_svg_icon(
                svg_icon_path(ICON_RENAME_SVG),
                CONTEXT_MENU_ICON_SIZE,
                icon_color,
            ),
            tr("Rename Influence..."),
        )
        rename_action.setEnabled(
            item is not None and self._can_rename_influence()
        )
        rename_action.setToolTip(
            tr("Replace this influence name inside the selected weight file and "
               "save the result as a new version.")
        )

        chosen = exec_menu(menu, self.name_list.mapToGlobal(point))
        if chosen is not rename_action:
            return

        recorded = item.data(QtCore.Qt.UserRole)
        self.rename_influence_requested.emit(
            str(recorded).strip() if recorded else item.text().strip()
        )

    def clear(self, message: str = None):
        """Reset the panel to its placeholder (or a custom message)."""
        self.file_label.setText(message if message is not None else self._placeholder)
        if self.selector_combo is not None:
            self.selector_combo.blockSignals(True)
            self.selector_combo.clear()
            self.selector_combo.blockSignals(False)
        self.meta_text.clear()
        self.name_list.clear()

    def set_header(self, text: str):
        self.file_label.setText(text)

    def set_meta(self, text: str):
        self.meta_text.setPlainText(text)

    def set_selector_items(self, labels: list):
        """Repopulate the selector combo without emitting change signals."""
        self.selector_combo.blockSignals(True)
        self.selector_combo.clear()
        for label in labels:
            self.selector_combo.addItem(label)
        self.selector_combo.blockSignals(False)

    def selector_index(self) -> int:
        if self.selector_combo is None:
            return -1
        return self.selector_combo.currentIndex()

    def set_chrome(self, selector_label, selector_tooltip, print_tooltip,
                   meta_tooltip):
        """Retitle the selector row, print button and metadata box.

        For a tab whose formats each describe these differently.
        """
        if self._selector_label is not None:
            self._selector_label.setText(selector_label)

        if self.selector_combo is not None:
            self.selector_combo.setToolTip(selector_tooltip)

        if self.print_button is not None:
            self.print_button.setToolTip(print_tooltip)

        self.meta_text.setToolTip(meta_tooltip)

    def set_list_label(self, text: str, select_all_tooltip: str = ""):
        """Update the name-list section label (and optional select-all tooltip)."""
        self._list_label.setText(text)
        if self._select_all_button is not None and select_all_tooltip:
            self._select_all_button.setToolTip(select_all_tooltip)

    def set_list_tooltip(self, text: str):
        self.name_list.setToolTip(text)

    def set_list_items(
        self,
        names,
        sort: bool = True,
        missing_predicate=None,
        missing_tooltip: str = "Not in scene",
    ):
        """Repopulate the name list. missing_predicate(name) -> False dims the
        entry and makes it non-selectable (e.g. missing influence / file).
        """
        entries = []
        for name in names:
            entries.append({"display": name, "recorded": name})
        self.set_list_entries(
            entries,
            sort=sort,
            missing_predicate=missing_predicate,
            missing_tooltip=missing_tooltip,
        )

    def set_list_entries(
        self,
        entries,
        sort: bool = False,
        missing_predicate=None,
        missing_tooltip: str = "Not in scene",
    ):
        """Repopulate the name list from entry dicts.

        Each entry may include:
        display, recorded, latest, and optional missing (bool).
        recorded / latest are stored on the item for Member View selection.
        """
        self.name_list.clear()
        if not entries:
            return
        missing_color = self.name_list.palette().color(
            QtGui.QPalette.Disabled, QtGui.QPalette.Text
        )
        rows = list(entries)
        if sort:
            rows = sorted(rows, key=lambda row: str(row.get("display", "")))
        for row in rows:
            display = str(row.get("display", "") or "")
            recorded = str(row.get("recorded", "") or display)
            latest = str(row.get("latest", "") or "")
            item = QtWidgets.QListWidgetItem(display)
            item.setData(QtCore.Qt.UserRole, recorded)
            item.setData(QtCore.Qt.UserRole + 1, latest)
            is_missing = row.get("missing")
            if is_missing is None and missing_predicate is not None:
                is_missing = not missing_predicate(recorded)
            if is_missing:
                item.setForeground(missing_color)
                item.setToolTip(tr(missing_tooltip))
                item.setData(_MISSING_ROLE, True)
            self.name_list.addItem(item)

    def list_names(self, selectable_only: bool = False) -> list:
        """Recorded (or display) names currently in the name list.
        When selectable_only is True, skip dimmed rows.
        """
        names = []
        for index in range(self.name_list.count()):
            item = self.name_list.item(index)
            if selectable_only and is_missing_item(item):
                continue
            recorded = item.data(QtCore.Qt.UserRole)
            text = str(recorded).strip() if recorded else item.text().strip()
            if text:
                names.append(text)
        return names

    def list_member_targets(
        self,
        prefer_latest: bool = True,
        selectable_only: bool = True,
    ) -> list:
        """Filenames to select in Files for Member View rows."""
        names = []
        for index in range(self.name_list.count()):
            item = self.name_list.item(index)
            if selectable_only and is_missing_item(item):
                continue
            recorded = str(item.data(QtCore.Qt.UserRole) or "").strip()
            latest = str(item.data(QtCore.Qt.UserRole + 1) or "").strip()
            if prefer_latest and latest:
                names.append(latest)
            elif recorded:
                names.append(recorded)
        return names


class FileExplorerSection(QtCore.QObject):
    """Directory row + file toolbar + view-mode row + file-list/viewer splitter,
    shared by the SkinWeight and Deformer tabs.

    Two sections can be linked so the weight directory and Full/Latest view
    mode stay in sync across tabs (they share the same settings keys).
    """

    selection_changed = QtCore.Signal()
    item_activated = QtCore.Signal()

    def __init__(
        self,
        settings,
        splitter_setting_key: str,
        scan_files,
        primary_extension,
        viewer_panel: QtWidgets.QWidget,
        side_widget: QtWidgets.QWidget,
        file_kind: str = "weight",
        list_min_width: int = 0,
        left_splitter_setting_key: str = None,
        custom_rename=None,
        item_color=None,
        supports_opposite_side=None,
        expand_selection=None,
        parent=None,
    ):
        """Args:
            scan_files (callable): scan_files(dir_name) -> list of file
                names.
            primary_extension (callable): () -> extension (no dot) appended
                when renaming to a name without extension.
            left_splitter_setting_key (str): Settings key for the vertical
                file-list/viewer name-list split (defaults to
                splitter_setting_key + "_left" when omitted).
            custom_rename (callable, optional): custom_rename(dir_name,
                cur_name) -> None (not applicable; fall through to the
                generic rename prompt) or (True, new_display_name_or_None)
                once it has fully handled the rename itself (own prompt,
                validation, and file I/O). Lets a tab intercept rename for
                file kinds the generic weight_files.rename_weight_file()
                single-file rename can't handle correctly (e.g. a WIP pack,
                whose subdirectory and member filenames must be renamed
                together; see SkinWeightTabView).
            item_color (callable, optional): item_color(name) ->
                QColor/None. Lets a tab tint specific Files list entries
                (e.g. WIP packs) without this generic component knowing
                about file-kind-specific rules.
            expand_selection (callable, optional): expand_selection(
                dir_name, file_names) -> list of the file names Archive and
                Delete should actually act on. Lets a tab turn one list entry
                into the whole set it owns (a WIP pack entry stands for its
                member XMLs too). Omitted means act on the selection as-is.
            supports_opposite_side (callable, optional): () -> bool,
                checked each time the context menu opens. Lets a tab show
                "Generate Opposite Side..." only for text weight formats
                (e.g. XML), not binary ones. Omitted or
                returning False hides the entry entirely.
        """
        super().__init__(parent)
        self._settings = settings
        self._splitter_key = splitter_setting_key
        self._left_splitter_key = (
            left_splitter_setting_key or f"{splitter_setting_key}_left"
        )
        self._scan_files = scan_files
        self._primary_extension = primary_extension
        self._viewer_panel = viewer_panel
        self._side_widget = side_widget
        self._file_kind = file_kind
        self._list_min_width = list_min_width
        self._custom_rename = custom_rename
        self._item_color = item_color
        self._supports_opposite_side = supports_opposite_side
        self._expand_selection = expand_selection
        self._file_actions_provider = None
        self._linked = []
        # When set, refresh() on an inactive (hidden-tab) section is deferred
        # until the section becomes visible, so hidden tabs do no scan work.
        self._active_check = None
        self._needs_refresh = False

        self.dir_edit = None
        self.file_list = None
        self.splitter = None
        self.left_splitter = None
        self.view_full_radio = None
        self.view_latest_radio = None
        self.import_button = None
        self.export_button = None
        self.import_temp_button = None
        self.export_temp_button = None
        # Wired up by build_io_row(); called by the file-list context menu's
        # "Import" entry.
        self._on_import = None

    def set_file_actions_provider(self, provider):
        """Register provider(selected_names) -> list of FileAction.

        Called each time the context menu opens, so a format can offer entries
        that depend on the selection (e.g. only for pack files) without this
        generic component knowing about the format.
        """
        self._file_actions_provider = provider

    def set_custom_rename_provider(self, provider):
        """Register provider(dir_name, cur_name) as the custom_rename hook.

        For a tab whose rename hook lives on an object built after this
        section, so it cannot be passed to the constructor.
        """
        self._custom_rename = provider

    # ---- linking

    def link(self, other: "FileExplorerSection"):
        """Keep directory and view mode synchronized with another section."""
        if other not in self._linked:
            self._linked.append(other)
        if self not in other._linked:
            other._linked.append(self)

    # ---- activation (deferred refresh for hidden tabs)

    def set_active_check(self, is_active):
        """Register a predicate () -> bool telling refresh() whether this section
        is the currently visible one. When it returns False, refresh() only
        marks the section dirty; refresh_if_pending() flushes it on activation.
        """
        self._active_check = is_active

    def refresh_if_pending(self):
        """Run a deferred refresh if one was requested while hidden."""
        if self._needs_refresh:
            self.refresh()

    # ---- state accessors

    def directory(self) -> str:
        text = self.dir_edit.text().strip()
        if not text:
            return ""
        return norm_path(text)

    def view_mode(self) -> str:
        if self.view_full_radio.isChecked():
            return FILE_VIEW_FULL
        return FILE_VIEW_LATEST

    def selected_names(self) -> list:
        return [item.text() for item in self.file_list.selectedItems()]

    def selected_paths(self) -> list:
        dir_name = self.directory()
        if not dir_name:
            return []
        return [
            norm_path(os.path.join(dir_name, name))
            for name in self.selected_names()
        ]

    # ---- builders

    def build_directory_row(self, parent_layout):
        dir_row = QtWidgets.QHBoxLayout()
        parent_layout.addLayout(dir_row)
        self.hist_label = make_history_label()
        self.hist_label.customContextMenuRequested.connect(self._show_recent_dirs_menu)
        dir_row.addWidget(self.hist_label)
        dir_row.addWidget(QtWidgets.QLabel(tr("Weight Dir :")))
        self.dir_edit = QtWidgets.QLineEdit()
        saved_dir = self._settings.raw_text(SETTING_LAST_SAVE_PATH)
        if saved_dir:
            self.dir_edit.setText(norm_path(saved_dir))
        self.dir_edit.editingFinished.connect(self._apply_directory_from_edit)
        dir_row.addWidget(self.dir_edit)
        set_button = QtWidgets.QPushButton(tr("set"))
        set_button.clicked.connect(self.browse_directory)
        dir_row.addWidget(set_button)

    def build_view_mode_row(self, parent_layout, row=None):
        """Add the Full / Latest version view radios.

        Args:
            parent_layout (QLayout): Layout to add the row to.
            row (QHBoxLayout, optional): An existing row to continue instead
                of starting a new one; the caller then ends it (stretch).
        """
        end_row = row is None
        if row is None:
            row = QtWidgets.QHBoxLayout()
            parent_layout.addLayout(row)

        view_row = row
        view_row.addWidget(QtWidgets.QLabel(tr("Version View:")))
        group = QtWidgets.QButtonGroup(self)
        self.view_full_radio = QtWidgets.QRadioButton(tr("Full"))
        self.view_latest_radio = QtWidgets.QRadioButton(tr("Latest"))
        group.addButton(self.view_full_radio)
        group.addButton(self.view_latest_radio)
        view_row.addWidget(self.view_full_radio)
        view_row.addWidget(self.view_latest_radio)
        if end_row:
            view_row.addStretch()

        saved_mode = self._settings.raw_text(SETTING_FILE_VIEW_MODE, FILE_VIEW_LATEST)
        if saved_mode == FILE_VIEW_FULL:
            self.view_full_radio.setChecked(True)
        else:
            self.view_latest_radio.setChecked(True)
        self.view_full_radio.toggled.connect(self._on_view_mode_toggled)
        self.view_latest_radio.toggled.connect(self._on_view_mode_toggled)

    def build_explorer_splitter(self, parent_layout):
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        parent_layout.addWidget(splitter, 1)

        file_list_widget = QtWidgets.QWidget()
        file_list_layout = QtWidgets.QVBoxLayout(file_list_widget)
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.addWidget(QtWidgets.QLabel(tr("Files")))
        self.file_list = QtWidgets.QListWidget()
        self.file_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        if self._list_min_width > 0:
            self.file_list.setMinimumWidth(self._list_min_width)
        self.file_list.itemDoubleClicked.connect(lambda *_: self.item_activated.emit())
        self.file_list.itemSelectionChanged.connect(
            lambda: self.selection_changed.emit()
        )
        self.file_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(
            self._show_file_context_menu
        )
        file_list_layout.addWidget(self.file_list)

        # Left column: file list on top, the viewer's name list (Influences)
        # below it. The comment editor (side_widget) lives under the viewer's
        # metadata text instead.
        left_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        left_splitter.setChildrenCollapsible(False)
        left_splitter.addWidget(file_list_widget)
        left_splitter.addWidget(self._viewer_panel.list_widget)
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 1)
        left_splitter.setSizes(self._settings.splitter_sizes(
            self._left_splitter_key,
            DEFAULT_EXPLORER_LEFT_SPLITTER_SIZES,
        ))
        left_splitter.splitterMoved.connect(
            lambda *_: self._settings.save_splitter_sizes(
                self._left_splitter_key, left_splitter.sizes()
            )
        )
        self.left_splitter = left_splitter

        self._viewer_panel.attach_side_widget(self._side_widget)

        splitter.addWidget(left_splitter)
        splitter.addWidget(self._viewer_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes(self._settings.splitter_sizes(
            self._splitter_key,
            DEFAULT_EXPLORER_SPLITTER_SIZES,
            migrate_three_pane=True,
        ))
        splitter.splitterMoved.connect(
            lambda *_: self._settings.save_splitter_sizes(
                self._splitter_key, splitter.sizes()
            )
        )
        self.splitter = splitter

    def build_io_row(
        self,
        parent_layout,
        on_import,
        on_export,
        import_tooltip: str = "",
        export_tooltip: str = "",
        on_import_temp=None,
        on_export_temp=None,
    ):
        # Shared with the file list's right-click "Import" context menu entry.
        self._on_import = on_import
        io_row = QtWidgets.QHBoxLayout()
        parent_layout.addLayout(io_row)
        self.import_button = make_io_button(
            tr("Import"), ICON_IMPORT_SVG, tooltip=import_tooltip, callback=on_import,
        )
        io_row.addWidget(self.import_button)
        if on_import_temp is not None:
            self.import_temp_button = QtWidgets.QPushButton(tr("Import Temp"))
            self.import_temp_button.clicked.connect(on_import_temp)
            io_row.addWidget(self.import_temp_button)
        self.export_button = make_io_button(
            tr("Export"), ICON_EXPORT_SVG, tooltip=export_tooltip, callback=on_export,
        )
        io_row.addWidget(self.export_button)
        if on_export_temp is not None:
            self.export_temp_button = QtWidgets.QPushButton(tr("Export Temp"))
            self.export_temp_button.clicked.connect(on_export_temp)
            io_row.addWidget(self.export_temp_button)
        io_row.addStretch()

    def _show_file_context_menu(self, point):
        item = self.file_list.itemAt(point)
        if item is not None and not item.isSelected():
            self.file_list.clearSelection()
            item.setSelected(True)
            self.file_list.setCurrentItem(item)

        selected_count = len(self.selected_names())
        has_selection = selected_count > 0

        menu = QtWidgets.QMenu(self.file_list)
        menu.setToolTipsVisible(True)
        icon_color = self.file_list.palette().color(QtGui.QPalette.WindowText)

        def menu_icon(svg_filename):
            return make_colored_svg_icon(
                svg_icon_path(svg_filename), CONTEXT_MENU_ICON_SIZE, icon_color
            )

        format_actions = []
        if self._file_actions_provider is not None:
            for file_action in self._file_actions_provider(self.selected_names()):
                if file_action.icon:
                    menu_action = menu.addAction(
                        menu_icon(file_action.icon), file_action.label
                    )
                else:
                    menu_action = menu.addAction(file_action.label)

                menu_action.setEnabled(file_action.enabled)
                if file_action.tooltip:
                    menu_action.setToolTip(file_action.tooltip)

                format_actions.append((menu_action, file_action))

        if format_actions:
            menu.addSeparator()

        rename_action = menu.addAction(menu_icon(ICON_RENAME_SVG), tr("Rename"))
        rename_action.setEnabled(selected_count == 1)
        opposite_side_action = None
        if self._supports_opposite_side is not None and self._supports_opposite_side():
            opposite_side_action = menu.addAction(
                menu_icon(ICON_OPPOSITE_SIDE_SVG), tr("Generate Opposite Side...")
            )
            opposite_side_action.setEnabled(has_selection)
            opposite_side_action.setToolTip(
                tr("Copy the selected file(s), replacing a source side string "
                   "with a destination side string in the filename and file "
                   "content (e.g. \"_L\" -> \"_R\").")
            )
        menu.addSeparator()
        import_action = menu.addAction(menu_icon(ICON_IMPORT_SVG), tr("Import"))
        import_action.setEnabled(has_selection)
        menu.addSeparator()
        archive_action = menu.addAction(menu_icon(ICON_ARCHIVE_SVG), tr("Archive"))
        archive_action.setEnabled(has_selection)
        archive_action.setToolTip(
            tr(
                "Move the selected file(s) to {backup_dir_name}/ instead of deleting them.",
                backup_dir_name=weight_files.BACKUP_DIR_NAME,
            )
        )
        delete_action = menu.addAction(menu_icon(ICON_DELETE_SVG), tr("Delete"))
        delete_action.setEnabled(has_selection)
        menu.addSeparator()
        show_archives_action = menu.addAction(
            menu_icon(ICON_ARCHIVE_SVG), tr("Show Archives...")
        )
        show_archives_action.setToolTip(
            tr(
                "Browse the {backup_dir_name}/ folder to unarchive or permanently delete "
                "archived files.",
                backup_dir_name=weight_files.BACKUP_DIR_NAME,
            )
        )
        menu.addSeparator()
        open_dir_action = menu.addAction(menu_icon(ICON_OPEN_SVG), tr("Open Directory"))
        refresh_action = menu.addAction(menu_icon(ICON_REFRESH_SVG), tr("Refresh"))

        chosen = exec_menu(menu, self.file_list.mapToGlobal(point))
        if chosen is None:
            return
        chosen_format_action = next(
            (
                file_action for menu_action, file_action in format_actions
                if menu_action is chosen
            ),
            None,
        )
        if chosen_format_action is not None:
            chosen_format_action.callback()
        elif chosen is import_action:
            if self._on_import is not None:
                self._on_import()
        elif chosen is rename_action:
            self.rename_selected()
        elif opposite_side_action is not None and chosen is opposite_side_action:
            self.generate_opposite_side_selected()
        elif chosen is archive_action:
            self.archive_selected()
        elif chosen is delete_action:
            self.delete_selected()
        elif chosen is show_archives_action:
            self.show_archives()
        elif chosen is open_dir_action:
            self.open_directory()
        elif chosen is refresh_action:
            self.refresh()

    # ---- directory handling

    def set_directory(self, dir_name: str, add_recent: bool = False):
        """Set the weight directory, persist it, refresh linked sections."""
        dir_name = norm_path(dir_name)
        self.dir_edit.setText(dir_name)
        self._settings.set(SETTING_LAST_SAVE_PATH, dir_name)
        if add_recent:
            self._settings.add_recent_dir(dir_name)
        self.refresh()
        for partner in self._linked:
            partner.dir_edit.setText(dir_name)
            partner.refresh()

    def _apply_directory_from_edit(self):
        """Apply a typed or pasted path when the Weight Dir field loses focus
        or Enter is pressed.
        """
        text = self.dir_edit.text().strip().strip('"').strip("'")
        if not text:
            return
        dir_name = norm_path(text)
        saved = self._settings.raw_text(SETTING_LAST_SAVE_PATH)
        if saved and norm_path(saved) == dir_name:
            if self.dir_edit.text() != dir_name:
                self.dir_edit.setText(dir_name)
            return
        if not os.path.isdir(dir_name):
            feedback.display_warning(tr("Invalid weight directory: {dir_name}", dir_name=dir_name))
        self.set_directory(dir_name, add_recent=os.path.isdir(dir_name))

    def browse_directory(self):
        start_dir = self.directory()
        if not start_dir:
            start_dir = self._settings.raw_text(SETTING_LAST_SAVE_PATH)
        dir_name = QtWidgets.QFileDialog.getExistingDirectory(
            self.file_list, tr("Set Export Directory"), start_dir
        )
        if not dir_name:
            return
        self.set_directory(dir_name, add_recent=True)

    def _show_recent_dirs_menu(self, point):
        menu = QtWidgets.QMenu(self.hist_label)
        recent = self._settings.recent_dirs()
        if not recent:
            menu.addAction(tr("(empty)")).setEnabled(False)
        else:
            for dir_path in recent:
                action = menu.addAction(dir_path)
                action.triggered.connect(
                    lambda checked=False, path=dir_path: self.set_directory(path)
                )
        exec_menu(menu, self.hist_label.mapToGlobal(point))

    # ---- view mode

    def _on_view_mode_toggled(self, checked):
        if not checked:
            return
        mode = self.view_mode()
        self._settings.set(SETTING_FILE_VIEW_MODE, mode)
        self.refresh()
        for partner in self._linked:
            partner.set_view_mode_silent(mode)
            partner.refresh()

    def set_view_mode_silent(self, mode: str):
        for radio in (self.view_full_radio, self.view_latest_radio):
            radio.blockSignals(True)
        if mode == FILE_VIEW_FULL:
            self.view_full_radio.setChecked(True)
        else:
            self.view_latest_radio.setChecked(True)
        for radio in (self.view_full_radio, self.view_latest_radio):
            radio.blockSignals(False)

    # ---- file list

    def refresh(self):
        """Rescan the directory and repopulate the list, preserving selection.

        Deferred to next activation when this section is not the visible one
        (see set_active_check), so hidden tabs do no scan/parse work.
        """
        if self._active_check is not None and not self._active_check():
            self._needs_refresh = True
            return
        self._needs_refresh = False
        names = self._scan_files(self.directory())
        visible = io.filter_files_for_view(names, self.view_mode())
        selected = set(self.selected_names())
        # Batch the rebuild: one addItems call, one selection pass, and no
        # per-change itemSelectionChanged storm (we emit selection_changed once).
        self.file_list.blockSignals(True)
        self.file_list.setUpdatesEnabled(False)
        try:
            self.file_list.clear()
            for name in visible:
                item = QtWidgets.QListWidgetItem(name)
                if self._item_color is not None:
                    color = self._item_color(name)
                    if color is not None:
                        item.setForeground(color)
                if name in selected:
                    item.setSelected(True)
                self.file_list.addItem(item)
        finally:
            self.file_list.setUpdatesEnabled(True)
            self.file_list.blockSignals(False)
        self.selection_changed.emit()

    def select_files(self, basenames: list, emit_changed: bool = True):
        self.file_list.clearSelection()
        for name in basenames:
            for item in self.file_list.findItems(name, QtCore.Qt.MatchExactly):
                item.setSelected(True)
        if emit_changed:
            self.selection_changed.emit()

    # ---- file operations

    def _require_directory(self) -> str:
        dir_name = self.directory()
        if not dir_name:
            feedback.display_warning(tr("Set a weight directory first."))
        return dir_name

    def open_directory(self):
        dir_name = self._require_directory()
        if not dir_name:
            return
        if not io.open_directory(dir_name):
            feedback.display_warning(tr("Invalid weight directory: {dir_name}", dir_name=dir_name))

    def _expanded_selection(self, dir_name, file_names) -> list:
        """File names Archive/Delete act on, after the tab's expansion hook."""
        if self._expand_selection is None:
            return file_names

        return self._expand_selection(dir_name, file_names)

    def archive_selected(self):
        dir_name = self._require_directory()
        if not dir_name:
            return
        file_names = self.selected_names()
        if not file_names:
            feedback.display_warning(
                tr("Select {file_kind} file(s) to archive.", file_kind=tr(self._file_kind))
            )
            return
        if not confirm_with_items(
            self.file_list,
            tr("{app_title}: Archive Files", app_title=APP_TITLE),
            tr("Move {count} file(s) to Archive Folder?", count=len(file_names)),
            file_names,
            confirm_label=tr("Archive"),
        ):
            return
        weight_files.archive_weight_files(
            dir_name, self._expanded_selection(dir_name, file_names)
        )
        self.refresh()

    def show_archives(self):
        """Browse this directory's archive folder to unarchive or purge files."""
        dir_name = self._require_directory()
        if not dir_name:
            return

        backup_dir = weight_files.get_backup_dir(dir_name)
        if not os.path.isdir(backup_dir):
            feedback.display_warning(tr(
                "No archive folder yet: {backup_dir}",
                backup_dir=backup_dir,
            ))
            return

        restored = show_archive_dialog(
            self.file_list, dir_name, self._scan_files,
            file_kind=self._file_kind,
        )
        if not restored:
            return

        self.refresh()
        self.select_files(restored)

    def delete_selected(self):
        dir_name = self._require_directory()
        if not dir_name:
            return
        file_names = self.selected_names()
        if not file_names:
            feedback.display_warning(
                tr("Select {file_kind} file(s) to delete.", file_kind=tr(self._file_kind))
            )
            return
        if not confirm_with_items(
            self.file_list,
            tr("{app_title}: Delete Files", app_title=APP_TITLE),
            tr("Delete {count} file(s)?", count=len(file_names)),
            file_names,
            confirm_label=tr("Delete"),
        ):
            return
        weight_files.delete_weight_files(
            dir_name, self._expanded_selection(dir_name, file_names)
        )
        self.refresh()

    def rename_selected(self):
        dir_name = self._require_directory()
        if not dir_name:
            return
        selected = self.selected_names()
        if len(selected) != 1:
            feedback.display_warning(tr("Select exactly one file to rename."))
            return
        cur_name = selected[0]

        if self._custom_rename is not None:
            outcome = self._custom_rename(dir_name, cur_name)
            if outcome is not None:
                _handled, new_display_name = outcome
                # None means nothing changed (cancelled/errored before any
                # rename happened); "" vs a real name both mean something on
                # disk changed and the list needs refreshing either way.
                if new_display_name is not None:
                    self.refresh()
                    if new_display_name:
                        self.select_files([new_display_name])
                return

        text, ok = QtWidgets.QInputDialog.getText(
            self.file_list,
            tr("Rename {file_kind} file", file_kind=tr(self._file_kind)),
            tr("New file name:"),
            text=cur_name,
        )
        if not ok or not text.strip() or text.strip() == cur_name:
            return
        try:
            new_name, had_sidecar = weight_files.rename_weight_file(
                dir_name, cur_name, text.strip(),
                default_ext=self._primary_extension(),
            )
        except OSError as exc:
            feedback.display_error(tr(
                "Failed to rename {file_kind} file: {exc}",
                file_kind=tr(self._file_kind),
                exc=exc,
            ))
            return
        if had_sidecar:
            feedback.display_info(tr(
                "Renamed {new_name} (sidecar metadata moved)",
                new_name=new_name,
            ))
        self.refresh()
        self.select_files([new_name])

    def generate_opposite_side_selected(self):
        """Copy the selected file(s), replacing a source side string with a
        destination side string in the filename and file content.
        """
        dir_name = self._require_directory()
        if not dir_name:
            return
        file_names = self.selected_names()
        if not file_names:
            feedback.display_warning(
                tr(
                    "Select {file_kind} file(s) to generate the opposite side for.",
                    file_kind=tr(self._file_kind),
                )
            )
            return
        initial_source = self._settings.raw_text(SETTING_CONVERT_SRC, DEFAULT_CONVERT_SRC)
        initial_destination = self._settings.raw_text(SETTING_CONVERT_DST, DEFAULT_CONVERT_DST)
        result = prompt_opposite_side(
            self.file_list,
            initial_source=initial_source,
            initial_destination=initial_destination,
        )
        if result is None:
            return
        source, destination = result
        self._settings.set(SETTING_CONVERT_SRC, source)
        self._settings.set(SETTING_CONVERT_DST, destination)
        created = weight_files.convert_weight_files(
            dir_name, file_names, source, destination, replace_content=True,
        )
        if not created:
            feedback.display_warning(
                tr(
                    "No opposite-side file(s) generated: none of the selected {file_kind} file "
                    "names contain \"{value}\".",
                    file_kind=tr(self._file_kind),
                    value=source,
                )
            )
            return
        self.refresh()
        self.select_files([pair[1] for pair in created])
