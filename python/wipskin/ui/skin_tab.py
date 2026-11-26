"""SkinWeight tab view: format mode row, file explorer, chunk viewer, and the
per-format import/export option pages.

Pure view code — reads/writes widgets and persists prefs; all IO flows are
driven by controllers.skin_io.SkinIOController through typed accessors.
"""

from __future__ import annotations

from wipskin.ui.qt_compat import QtCore, QtGui, QtWidgets

from wipskin.formats.skin import registry as skin_registry
from wipskin.ui.skin_formats.base import SkinFormatContext
from wipskin.core.constants import (
    DEFAULT_CONVERT_DST,
    DEFAULT_CONVERT_SRC,
    IMPORT_AS_SAVED,
    IMPORT_AS_SELECTED,
    SETTING_CONVERT_DST,
    SETTING_CONVERT_SRC,
    SETTING_EXPORT_OPTIONS_EXPANDED,
    SETTING_EXPORT_VERSION_NUMBER,
    SETTING_EXPLORER_LEFT_SPLITTER_SIZES,
    SETTING_IMPORT_AS,
    SETTING_IMPORT_OPTIONS_EXPANDED,
    SETTING_OPTIONS_SPLITTER_SIZES,
    SETTING_SKIN_WEIGHT_MODE,
    SETTING_SPLITTER_SIZES,
    SETTING_VIEWER_SPLITTER_SIZES,
)
from wipskin.ui.common import (
    FileExplorerSection,
    ViewerPanel,
    bind_checkbox,
    bind_radio_value,
    build_collapsible_group,
)
from wipskin.ui.widgets import make_separator
from wipskin.core.i18n import tr

_PACK_ITEM_COLOR = QtGui.QColor(110, 200, 110)


def set_option_stack_page(stack: QtWidgets.QStackedWidget, index: int):
    """Switch a QStackedWidget page, collapsing hidden pages so the stack only
    takes the height of the visible page.
    """
    for page_index in range(stack.count()):
        page = stack.widget(page_index)
        if page_index == index:
            page.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred,
                QtWidgets.QSizePolicy.Maximum,
            )
        else:
            page.setSizePolicy(
                QtWidgets.QSizePolicy.Ignored,
                QtWidgets.QSizePolicy.Ignored,
            )
    stack.setCurrentIndex(index)
    stack.adjustSize()


def make_option_stack(page_builders) -> QtWidgets.QStackedWidget:
    """QStackedWidget with one page per builder(layout) callable."""
    stack = QtWidgets.QStackedWidget()
    stack.setSizePolicy(
        QtWidgets.QSizePolicy.Preferred,
        QtWidgets.QSizePolicy.Maximum,
    )
    for builder in page_builders:
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        builder(page_layout)
        stack.addWidget(page)
    return stack


class SkinWeightTabView(QtWidgets.QWidget):
    """View for the SkinWeight top-level tab."""

    import_requested = QtCore.Signal(str)   # "browser" | "temp"
    export_requested = QtCore.Signal(str)
    convert_requested = QtCore.Signal()

    def __init__(
        self,
        settings,
        registry,
        comment_panel: QtWidgets.QWidget,
        io_classes: dict,
        project_config=None,
        parent=None,
    ):
        """Args:
            settings (SettingsModel):
            registry (ResetRegistry): Reset-to-default registration.
            comment_panel (QWidget): Shared comment column (owned by the App).
            io_classes (dict): SkinFormatIO subclass per format mode; the tab
                reads its options_class and supports_import/export.
            project_config (dict, optional): Project-level config (showUI's
                arguments such as vc_exec_cmd), handed to every format's
                option page; each reads only the keys it understands.
        """
        super().__init__(parent)
        self._settings = settings
        self._registry = registry
        self._io_classes = dict(io_classes)
        if project_config is None:
            project_config = {}

        self._format_options = {}
        self._stack_index = {}
        for index, skin_format in enumerate(skin_registry.list_skin_formats()):
            context = SkinFormatContext(
                settings=settings,
                registry=registry,
                parent=self,
                skin_format=skin_format,
                # A copy per page, so no page can change what another reads.
                config=dict(project_config),
                request_viewer_refresh=(
                    lambda: self.section.selection_changed.emit()
                ),
            )
            options_class = self._io_classes[skin_format.mode].options_class
            self._format_options[skin_format.mode] = options_class(context)
            self._stack_index[skin_format.mode] = index

        # Title, selector label and tooltips follow the format (apply_mode).
        self.viewer = ViewerPanel(
            settings,
            tr("Viewer"),
            tr("Select a weight file to inspect it."),
            SETTING_VIEWER_SPLITTER_SIZES,
            list_label=tr("Influences:"),
            selector_label="",
            with_select_all=True,
            with_print_button=True,
            list_tooltip=(
                tr("Double-click an influence to select it in Maya "
                   "(Shift/Ctrl modifiers supported).\n"
                   "Dimmed entries are not in the scene.")
            ),
            can_rename_influence=self._can_rename_viewer_influence,
        )
        self.section = FileExplorerSection(
            settings,
            SETTING_SPLITTER_SIZES,
            scan_files=self._scan_files,
            primary_extension=self.primary_extension,
            viewer_panel=self.viewer,
            side_widget=comment_panel,
            file_kind="weight",
            list_min_width=90,
            left_splitter_setting_key=SETTING_EXPLORER_LEFT_SPLITTER_SIZES,
            item_color=self._pack_item_color,
            supports_opposite_side=(
                lambda: self.current_skin_format().supports_opposite_side
            ),
            expand_selection=self._expand_pack_selection,
        )
        self._build_ui()

    # ------------------
    # Build

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(tr("Select mesh(es) in scene"))
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)

        self.section.build_directory_row(layout)

        # Format and version view share one row.
        format_row = self._build_format_mode_row(layout)
        format_row.addSpacing(16)
        self.section.build_view_mode_row(layout, row=format_row)
        format_row.addStretch()

        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.section.build_explorer_splitter(main_layout)
        self._build_convert_panel()
        self.section.build_io_row(
            main_layout,
            on_import=lambda: self.import_requested.emit("browser"),
            on_export=lambda: self.export_requested.emit("browser"),
            import_tooltip=tr("Import weights onto the selected mesh hierarchy."),
            export_tooltip=tr("Export weights from the selected mesh hierarchy."),
            on_import_temp=lambda: self.import_requested.emit("temp"),
            on_export_temp=lambda: self.export_requested.emit("temp"),
        )
        # apply_mode swaps these for an explanation on formats without IO.
        self._io_button_tooltips = {
            self.section.import_button: self.section.import_button.toolTip(),
            self.section.export_button: self.section.export_button.toolTip(),
        }
        main_layout.addWidget(make_separator())

        self._option_groups = [
            build_collapsible_group(
                self._settings,
                tr("Import Options"),
                SETTING_IMPORT_OPTIONS_EXPANDED,
                self._build_import_options,
            ),
            build_collapsible_group(
                self._settings,
                tr("Export Options"),
                SETTING_EXPORT_OPTIONS_EXPANDED,
                self._build_export_options,
            ),
        ]
        options_content = QtWidgets.QWidget()
        options_layout = QtWidgets.QVBoxLayout(options_content)
        options_layout.setContentsMargins(0, 0, 0, 0)
        for group in self._option_groups:
            options_layout.addWidget(group)
            # Deferred: the content's size hint is stale until the layout
            # request posted by the toggle has been processed.
            group.toggled.connect(
                lambda *_: QtCore.QTimer.singleShot(
                    0, self._sync_options_pane_height
                )
            )

        options_layout.addStretch()

        # The option pages differ in height per format. Scrolling them inside
        # a pane of user-chosen height keeps the explorer / viewer above from
        # resizing when the format changes.
        self._options_pane = QtWidgets.QScrollArea()
        self._options_pane.setWidgetResizable(True)
        self._options_pane.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._options_pane.setWidget(options_content)

        self._options_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self._options_splitter.setChildrenCollapsible(False)
        self._options_splitter.addWidget(main_widget)
        self._options_splitter.addWidget(self._options_pane)
        self._options_splitter.setStretchFactor(0, 1)
        self._options_splitter.setStretchFactor(1, 0)
        self._options_splitter.splitterMoved.connect(
            self._save_options_splitter_sizes
        )
        layout.addWidget(self._options_splitter, 1)

        self.apply_mode(self.skin_weight_mode(), save=False, refresh=False)
        self._sync_options_pane_height()

    def showEvent(self, event):
        super().showEvent(event)
        # Sizes applied before the first layout pass are measured against a
        # splitter that has no real height yet; apply them again once it does.
        QtCore.QTimer.singleShot(0, self._sync_options_pane_height)

    def _has_expanded_option_group(self) -> bool:
        return any(group.is_expanded for group in self._option_groups)

    def _sync_options_pane_height(self):
        """Give the options pane its saved height, or pin it to the group
        headers while every group is collapsed.
        """
        pane = self._options_pane
        saved_sizes = self._settings.splitter_sizes(
            SETTING_OPTIONS_SPLITTER_SIZES, [420, 230]
        )
        if self._has_expanded_option_group():
            pane.setMinimumHeight(0)
            # Qt's QWIDGETSIZE_MAX, which PySide6 does not expose.
            pane.setMaximumHeight(16777215)
            pane_height = saved_sizes[1]
        else:
            pane_height = pane.widget().sizeHint().height()
            pane.setFixedHeight(pane_height)

        # The splitter keeps the pane's old slot unless it is told the new
        # split; before the first layout pass it has no height to split yet.
        total = sum(self._options_splitter.sizes())
        if total > 0:
            self._options_splitter.setSizes(
                [max(total - pane_height, 0), pane_height]
            )
        else:
            self._options_splitter.setSizes([saved_sizes[0], pane_height])

    def _save_options_splitter_sizes(self, *_):
        # While every group is collapsed the pane is pinned to its headers;
        # that height must not replace the one the user chose.
        if self._has_expanded_option_group():
            self._settings.save_splitter_sizes(
                SETTING_OPTIONS_SPLITTER_SIZES, self._options_splitter.sizes()
            )

    def _build_format_mode_row(self, parent_layout):
        format_row = QtWidgets.QHBoxLayout()
        parent_layout.addLayout(format_row)
        format_row.addWidget(QtWidgets.QLabel(tr("Format:")))
        self.format_combo = QtWidgets.QComboBox()
        # The mode id rides in UserRole so nothing keys off the shown label.
        for index, skin_format in enumerate(skin_registry.list_skin_formats()):
            self.format_combo.addItem(skin_format.label, skin_format.mode)
            reason = skin_format.get_unavailable_reason()
            if reason:
                # Default model is a QStandardItemModel: grey the entry out
                # and say why on hover, as the radios used to.
                self.format_combo.model().item(index).setEnabled(False)
                self.format_combo.setItemData(
                    index, reason, QtCore.Qt.ToolTipRole
                )
        format_row.addWidget(self.format_combo)

        saved_mode = self._settings.raw_text(SETTING_SKIN_WEIGHT_MODE, "")
        self._set_format_combo_mode(saved_mode)
        self.format_combo.currentIndexChanged.connect(
            self._on_format_mode_changed
        )
        return format_row

    def _set_format_combo_mode(self, mode: str):
        """Select mode's entry, falling back to the registry's pick."""
        start_mode = skin_registry.pick_available_format(mode).mode
        self.format_combo.setCurrentIndex(
            self.format_combo.findData(start_mode)
        )

    def _on_format_mode_changed(self, index):
        if index < 0:
            return
        self.apply_mode(self.skin_weight_mode())

    def apply_mode(self, mode: str, save: bool = True, refresh: bool = True):
        """Switch option pages / viewer chrome to the given format mode."""
        if save:
            self._settings.set(SETTING_SKIN_WEIGHT_MODE, mode)
        skin_format = skin_registry.get_skin_format(mode)
        stack_index = self._stack_index[mode]
        if hasattr(self, "import_option_stack"):
            set_option_stack_page(self.import_option_stack, stack_index)
        if hasattr(self, "export_option_stack"):
            set_option_stack_page(self.export_option_stack, stack_index)
        # The format's wording is English source text; translate it here, so
        # a plugin's own catalog covers it.
        self.viewer.setTitle(tr(skin_format.viewer_title))
        self.viewer.set_chrome(
            tr(skin_format.viewer_selector_label),
            tr(skin_format.viewer_selector_tooltip),
            tr(skin_format.viewer_print_tooltip),
            tr(skin_format.viewer_meta_tooltip),
        )
        io_class = self._io_classes[mode]
        for button, supported, unavailable in (
            (
                self.section.import_button,
                io_class.supports_import,
                tr("Import is not available for {label}.",
                   label=skin_format.label),
            ),
            (
                self.section.export_button,
                io_class.supports_export,
                tr("Export is not available for {label}.",
                   label=skin_format.label),
            ),
        ):
            if button is None:
                continue

            button.setEnabled(supported)
            # Say why when greyed out; restore the button's own tip otherwise.
            if supported:
                button.setToolTip(self._io_button_tooltips[button])
            else:
                button.setToolTip(unavailable)

        has_chunks = skin_format.has_chunk_selector
        if self.viewer.print_button is not None:
            self.viewer.print_button.setVisible(has_chunks)
        if self.viewer.selector_row is not None:
            self.viewer.selector_row.setVisible(has_chunks)
        supports_temp = skin_format.supports_temp_file
        if self.section.import_temp_button is not None:
            self.section.import_temp_button.setEnabled(supports_temp)
        if self.section.export_temp_button is not None:
            self.section.export_temp_button.setEnabled(supports_temp)
        if hasattr(self, "export_auto_naming_check"):
            self._sync_export_auto_naming_checkbox(mode)
        if refresh:
            self.section.refresh()

    def _export_auto_naming_key(self, mode=None) -> str:
        if mode is None:
            mode = self.skin_weight_mode()
        return skin_registry.get_skin_format(mode).export_auto_naming_setting

    def _sync_export_auto_naming_checkbox(self, mode=None):
        key = self._export_auto_naming_key(mode)
        self.export_auto_naming_check.blockSignals(True)
        self.export_auto_naming_check.setChecked(self._settings.flag(key))
        self.export_auto_naming_check.blockSignals(False)

    def _save_export_auto_naming(self):
        key = self._export_auto_naming_key()
        self._settings.set_flag(key, self.export_auto_naming_check.isChecked())

    def _build_convert_panel(self):
        """Convert UI — hidden; convert_requested is wired for later use."""
        self.convert_panel = QtWidgets.QWidget(self)
        convert_layout = QtWidgets.QVBoxLayout(self.convert_panel)
        convert_layout.setContentsMargins(0, 0, 0, 0)
        convert_layout.addWidget(QtWidgets.QLabel(tr("Convert")))
        self.convert_src_edit = QtWidgets.QLineEdit(
            self._settings.raw_text(SETTING_CONVERT_SRC, DEFAULT_CONVERT_SRC)
        )
        self.convert_src_edit.editingFinished.connect(self._save_convert_fields)
        convert_layout.addWidget(self.convert_src_edit)
        convert_layout.addWidget(QtWidgets.QLabel(tr("destination:")))
        self.convert_dst_edit = QtWidgets.QLineEdit(
            self._settings.raw_text(SETTING_CONVERT_DST, DEFAULT_CONVERT_DST)
        )
        self.convert_dst_edit.editingFinished.connect(self._save_convert_fields)
        convert_layout.addWidget(self.convert_dst_edit)
        convert_button = QtWidgets.QPushButton(tr("Convert"))
        convert_button.setToolTip(
            tr("Copy selected XML files with source/destination replaced "
               "in filenames and file content.")
        )
        convert_button.clicked.connect(lambda *_: self.convert_requested.emit())
        convert_layout.addWidget(convert_button)
        self.convert_panel.hide()

    def _save_convert_fields(self):
        self._settings.set(SETTING_CONVERT_SRC, self.convert_src_edit.text())
        self._settings.set(SETTING_CONVERT_DST, self.convert_dst_edit.text())

    # ------------------
    # Import options

    def _build_import_options(self, layout_import):
        layout_import_as = QtWidgets.QHBoxLayout()
        layout_import.addLayout(layout_import_as)
        layout_import_as.addWidget(QtWidgets.QLabel(tr("import as:")))
        group = QtWidgets.QButtonGroup(self)
        self.import_as_saved_radio = QtWidgets.QRadioButton(tr("saved shape"))
        self.import_as_selected_radio = QtWidgets.QRadioButton(tr("selected shape"))
        group.addButton(self.import_as_saved_radio, 1)
        group.addButton(self.import_as_selected_radio, 2)
        layout_import_as.addWidget(self.import_as_saved_radio)
        layout_import_as.addWidget(self.import_as_selected_radio)
        layout_import_as.addStretch()
        bind_radio_value(
            self._settings, SETTING_IMPORT_AS,
            {
                self.import_as_saved_radio: IMPORT_AS_SAVED,
                self.import_as_selected_radio: IMPORT_AS_SELECTED,
            },
            registry=self._registry,
        )
        layout_import.addWidget(make_separator())

        self.import_option_stack = make_option_stack([
            options.build_import_page
            for options in self._ordered_format_options()
        ])
        layout_import.addWidget(self.import_option_stack)

    # ------------------
    # Export options

    def _build_export_options(self, layout_export):
        naming_row = QtWidgets.QHBoxLayout()
        layout_export.addLayout(naming_row)
        self.export_auto_naming_check = QtWidgets.QCheckBox(tr("auto naming"))
        self.export_auto_naming_check.setToolTip(
            tr("Use the selected mesh name (or scene name when multiple meshes) "
               "as the export file base name.")
        )
        naming_row.addWidget(self.export_auto_naming_check)
        self.export_version_number_check = QtWidgets.QCheckBox(tr("version number"))
        self.export_version_number_check.setToolTip(
            tr("Append a four-digit version suffix (basename.NNNN.ext) when "
               "exporting.")
        )
        naming_row.addWidget(self.export_version_number_check)
        naming_row.addStretch()
        self._sync_export_auto_naming_checkbox()
        self.export_auto_naming_check.clicked.connect(self._save_export_auto_naming)
        if self._registry is not None:
            def _reset_export_auto_naming():
                for skin_format in skin_registry.list_skin_formats():
                    key = skin_format.export_auto_naming_setting
                    default = bool(self._settings.default(key))
                    self._settings.set_flag(key, default)
                self._sync_export_auto_naming_checkbox()

            self._registry.register(
                self.export_auto_naming_check, _reset_export_auto_naming
            )
        bind_checkbox(
            self._settings, SETTING_EXPORT_VERSION_NUMBER,
            self.export_version_number_check, registry=self._registry,
        )
        layout_export.addWidget(make_separator())

        self.export_option_stack = make_option_stack([
            options.build_export_page
            for options in self._ordered_format_options()
        ])
        layout_export.addWidget(self.export_option_stack)





    # ------------------
    # Typed state accessors (controller interface)

    def skin_weight_mode(self) -> str:
        format_combo = getattr(self, "format_combo", None)
        if format_combo is not None and format_combo.currentIndex() >= 0:
            return format_combo.currentData()

        return skin_registry.pick_available_format("").mode

    def _ordered_format_options(self) -> list:
        """Option owners in option-stack page order."""
        return [
            self._format_options[skin_format.mode]
            for skin_format in skin_registry.list_skin_formats()
        ]

    def get_format_options(self, mode):
        """SkinFormatOptions for a MODE_* id, for the format's IO flow."""
        return self._format_options[mode]

    def _can_rename_viewer_influence(self) -> bool:
        """ViewerPanel can_rename_influence hook: one rewritable file selected."""
        selected = self.section.selected_names()
        if len(selected) != 1:
            return False

        return self.current_skin_format().can_rename_influence(selected[0])

    def current_skin_format(self):
        """SkinWeightFormat for the selected Format combo entry."""
        return skin_registry.get_skin_format(self.skin_weight_mode())

    def mode_extensions(self) -> list:
        return list(self.current_skin_format().extensions)

    def primary_extension(self) -> str:
        return self._format_options[
            self.skin_weight_mode()
        ].get_primary_extension()

    def _scan_files(self, dir_name: str) -> list:
        return self.current_skin_format().list_files(dir_name)

    def _expand_pack_selection(self, dir_name: str, file_names: list) -> list:
        return self.current_skin_format().expand_file_names(
            dir_name, file_names
        )

    def _pack_item_color(self, name: str):
        """Tint pack manifests: XML .wip and mGear .gSkinPack / .jSkinPack."""
        if self.current_skin_format().is_pack_filename(name):
            return _PACK_ITEM_COLOR

        return None

    def import_as_mode(self) -> str:
        if self.import_as_selected_radio.isChecked():
            return IMPORT_AS_SELECTED
        return IMPORT_AS_SAVED







    def export_auto_naming(self) -> bool:
        return self.export_auto_naming_check.isChecked()

    def export_version_number(self) -> bool:
        return self.export_version_number_check.isChecked()










    def convert_fields(self) -> tuple:
        return self.convert_src_edit.text(), self.convert_dst_edit.text()
