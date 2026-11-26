"""Deformer tab view: deformer list, weight-file explorer, XML viewer, options."""

from __future__ import annotations

from wipskin.ui.qt_compat import QtCore, QtWidgets

from wipskin.formats.deformer import xml as deformer_io
from wipskin.core.constants import (
    DEFORMER_IMPORT_METHODS,
    IMPORT_AS_SAVED,
    IMPORT_AS_SELECTED,
    SETTING_DEFORMER_EXPORT_AUTO_NAMING,
    SETTING_DEFORMER_EXPORT_OPTIONS_EXPANDED,
    SETTING_DEFORMER_EXPORT_VERSION_NUMBER,
    SETTING_DEFORMER_IMPORT_AS,
    SETTING_DEFORMER_IMPORT_IGNORE_NAMES,
    SETTING_DEFORMER_IMPORT_METHOD,
    SETTING_DEFORMER_IMPORT_OPTIONS_EXPANDED,
    SETTING_DEFORMER_EXPLORER_LEFT_SPLITTER_SIZES,
    SETTING_DEFORMER_SPLITTER_SIZES,
    SETTING_DEFORMER_VIEWER_SPLITTER_SIZES,
    XML_METHOD_INDEX,
)
from wipskin.core import weight_files
from wipskin.ui.common import (
    FileExplorerSection,
    ViewerPanel,
    bind_checkbox,
    bind_radio_value,
    build_collapsible_group,
)
from wipskin.ui.widgets import make_separator
from wipskin.core.i18n import tr


class DeformerTabView(QtWidgets.QWidget):
    """View for the Deformer top-level tab."""

    import_requested = QtCore.Signal(str)
    export_requested = QtCore.Signal(str)
    deformer_list_refresh_requested = QtCore.Signal()
    deformer_selection_changed = QtCore.Signal()

    def __init__(self, settings, side_widget: QtWidgets.QWidget, parent=None):
        """Args:
            settings (SettingsModel):
            side_widget (QWidget): Placeholder swapped with the shared
                comment panel when this tab becomes active.
        """
        super().__init__(parent)
        self._settings = settings

        self.viewer = ViewerPanel(
            settings,
            tr("Deformer Viewer"),
            tr("Select a weight file to inspect it."),
            SETTING_DEFORMER_VIEWER_SPLITTER_SIZES,
            list_label=tr("Shapes:"),
            with_select_all=True,
            list_tooltip=tr("Click a shape to select it in Maya."),
        )
        self.viewer.set_list_label(
            tr("Shapes:"),
            select_all_tooltip=tr("Select all listed shapes in Maya."),
        )
        self.section = FileExplorerSection(
            settings,
            SETTING_DEFORMER_SPLITTER_SIZES,
            scan_files=self._scan_files,
            primary_extension=lambda: deformer_io.EXT,
            viewer_panel=self.viewer,
            side_widget=side_widget,
            file_kind="deformer weight",
            left_splitter_setting_key=SETTING_DEFORMER_EXPLORER_LEFT_SPLITTER_SIZES,
            supports_opposite_side=lambda: True,
        )
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(tr("Select deformed geo(s)"))
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)

        deformer_row = QtWidgets.QHBoxLayout()
        layout.addLayout(deformer_row)

        deformer_column = QtWidgets.QVBoxLayout()
        deformer_row.addLayout(deformer_column, 1)
        update_button = QtWidgets.QPushButton(tr("Update deformer list"))
        update_button.setToolTip(tr("List deformers on the selected mesh."))
        update_button.clicked.connect(
            lambda *_: self.deformer_list_refresh_requested.emit()
        )
        deformer_column.addWidget(update_button)
        self.deformer_list = QtWidgets.QListWidget()
        self.deformer_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.deformer_list.setToolTip(
            tr("Select deformers for export. Every affected shape is written "
               "to its own file unless you pick specific shapes on the right.")
        )
        self.deformer_list.itemSelectionChanged.connect(
            lambda: self.deformer_selection_changed.emit()
        )
        deformer_column.addWidget(self.deformer_list)

        shape_column = QtWidgets.QVBoxLayout()
        deformer_row.addLayout(shape_column, 1)
        shape_column.addWidget(QtWidgets.QLabel(tr("Deformed shapes:")))
        self.shape_list = QtWidgets.QListWidget()
        self.shape_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        self.shape_list.setToolTip(
            tr("Shapes affected by the selected deformer(s). Select one or "
               "more to export only those shapes, each to its own file "
               "(named shape_deformer.xml). Leave unselected to export every "
               "shape of the selected deformer(s).")
        )
        shape_column.addWidget(self.shape_list)

        self.section.build_directory_row(layout)
        self.section.build_view_mode_row(layout)

        main_widget = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.section.build_explorer_splitter(main_layout)
        self.section.build_io_row(
            main_layout,
            on_import=lambda: self.import_requested.emit("browser"),
            on_export=lambda: self.export_requested.emit("browser"),
        )
        layout.addWidget(main_widget, 1)

        layout.addWidget(make_separator())
        layout.addWidget(build_collapsible_group(
            self._settings,
            tr("Import Options"),
            SETTING_DEFORMER_IMPORT_OPTIONS_EXPANDED,
            self._build_import_options,
        ))
        layout.addWidget(build_collapsible_group(
            self._settings,
            tr("Export Options"),
            SETTING_DEFORMER_EXPORT_OPTIONS_EXPANDED,
            self._build_export_options,
        ))

    def _build_import_options(self, layout_import):
        import_as_row = QtWidgets.QHBoxLayout()
        layout_import.addLayout(import_as_row)
        import_as_row.addWidget(QtWidgets.QLabel(tr("import as:")))
        import_as_group = QtWidgets.QButtonGroup(self)
        self.import_as_saved_radio = QtWidgets.QRadioButton(tr("saved shape"))
        self.import_as_selected_radio = QtWidgets.QRadioButton(tr("selected shape"))
        import_as_group.addButton(self.import_as_saved_radio, 1)
        import_as_group.addButton(self.import_as_selected_radio, 2)
        import_as_row.addWidget(self.import_as_saved_radio)
        import_as_row.addWidget(self.import_as_selected_radio)
        import_as_row.addStretch()
        bind_radio_value(
            self._settings, SETTING_DEFORMER_IMPORT_AS,
            {
                self.import_as_saved_radio: IMPORT_AS_SAVED,
                self.import_as_selected_radio: IMPORT_AS_SELECTED,
            },
        )

        method_row = QtWidgets.QHBoxLayout()
        layout_import.addLayout(method_row)
        method_label = QtWidgets.QLabel(tr("method:"))
        method_label.setToolTip(
            tr("Interpolation method used by Maya's deformerWeights import when "
               "the target topology doesn't match the saved data 1:1.")
        )
        method_row.addWidget(method_label)
        self._method_radios = {}
        for method_value in DEFORMER_IMPORT_METHODS:
            radio = QtWidgets.QRadioButton(method_value)
            method_row.addWidget(radio)
            self._method_radios[radio] = method_value
        method_row.addStretch()
        bind_radio_value(
            self._settings, SETTING_DEFORMER_IMPORT_METHOD, self._method_radios,
        )

        self.import_ignore_names_check = QtWidgets.QCheckBox(tr("Ignore names"))
        self.import_ignore_names_check.setToolTip(
            tr("Ignore layer/influence names on import and match by order instead "
               "(Maya deformerWeights -ignoreName).")
        )
        bind_checkbox(
            self._settings, SETTING_DEFORMER_IMPORT_IGNORE_NAMES,
            self.import_ignore_names_check,
        )
        layout_import.addWidget(self.import_ignore_names_check)
        layout_import.addStretch()

    def _build_export_options(self, layout_export):
        self.export_auto_naming_check = QtWidgets.QCheckBox(tr("auto naming"))
        self.export_auto_naming_check.setToolTip(
            tr("Name the export file from the deformer instead of using a "
               "selected/manual filename.")
        )
        bind_checkbox(
            self._settings, SETTING_DEFORMER_EXPORT_AUTO_NAMING,
            self.export_auto_naming_check,
        )
        layout_export.addWidget(self.export_auto_naming_check)

        self.export_version_number_check = QtWidgets.QCheckBox(tr("version number"))
        bind_checkbox(
            self._settings, SETTING_DEFORMER_EXPORT_VERSION_NUMBER,
            self.export_version_number_check,
        )
        layout_export.addWidget(self.export_version_number_check)
        layout_export.addStretch()

    # ------------------
    # Typed state accessors (controller interface)

    def _scan_files(self, dir_name: str) -> list:
        return weight_files.scan_weight_files(
            dir_name,
            [deformer_io.EXT],
            predicate=deformer_io.is_deformer_weight_file,
        )

    def import_as_mode(self) -> str:
        if self.import_as_selected_radio.isChecked():
            return IMPORT_AS_SELECTED
        return IMPORT_AS_SAVED

    def import_method(self) -> str:
        for radio, method_value in self._method_radios.items():
            if radio.isChecked():
                return method_value
        return XML_METHOD_INDEX

    def import_ignore_names(self) -> bool:
        return self.import_ignore_names_check.isChecked()

    def add_deformer_item(
        self,
        deformer_name: str,
        node_type: str,
        shape_count: int,
    ):
        shape_label = "shape" if shape_count == 1 else "shapes"
        text = (
            f"{deformer_name} <{node_type}> "
            f"[{shape_count} {shape_label}]"
        )
        item = QtWidgets.QListWidgetItem(text)
        item.setData(QtCore.Qt.UserRole, deformer_name)
        self.deformer_list.addItem(item)

    def export_auto_naming(self) -> bool:
        return self.export_auto_naming_check.isChecked()

    def export_version_number(self) -> bool:
        return self.export_version_number_check.isChecked()

    def selected_deformer_names(self) -> list:
        names = []
        for item in self.deformer_list.selectedItems():
            deformer_name = item.data(QtCore.Qt.UserRole)
            if deformer_name:
                names.append(str(deformer_name))
        return names

    def add_deformer_shape_item(
        self,
        deformer_name: str,
        shape_name: str,
        node_type: str,
    ):
        text = f"{self._short_name(shape_name)} <{deformer_name}> ({node_type})"
        item = QtWidgets.QListWidgetItem(text)
        item.setData(QtCore.Qt.UserRole, (deformer_name, shape_name))
        self.shape_list.addItem(item)

    def selected_deformer_shape_pairs(self) -> list:
        pairs = []
        for item in self.shape_list.selectedItems():
            data = item.data(QtCore.Qt.UserRole)
            if data:
                pairs.append((str(data[0]), str(data[1])))
        return pairs

    @staticmethod
    def _short_name(node_name: str) -> str:
        return str(node_name).rsplit("|", 1)[-1]
