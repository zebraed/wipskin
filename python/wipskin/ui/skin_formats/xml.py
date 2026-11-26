"""XML skin format Import/Export options."""

from __future__ import annotations

from wipskin.core.constants import (
    XML_IMPORT_METHODS,
    XML_METHOD_INDEX,
)
from wipskin.formats.skin.xml.constants import (
    SETTING_XML_EXPORT_BIND_PRE_MATRIX,
    SETTING_XML_EXPORT_OPTIMIZE,
    SETTING_XML_EXPORT_WIP,
    SETTING_XML_IMPORT_BIND_PRE_MATRIX,
    SETTING_XML_IMPORT_IGNORE_NAMES,
    SETTING_XML_IMPORT_METHOD,
    SETTING_XML_IMPORT_MODE,
    SETTING_XML_IMPORT_NORMALIZE,
    XML_MODE_ADD,
    XML_MODE_REPLACE,
)
from wipskin.ui.common import bind_checkbox, bind_radio_value
from wipskin.ui.qt_compat import QtWidgets
from wipskin.ui.skin_formats.base import SkinFormatOptions
from wipskin.core.i18n import tr


class XmlSkinFormatOptions(SkinFormatOptions):
    """Maya deformerWeights XML options."""

    def build_import_page(self, layout_import):
        method_row = QtWidgets.QHBoxLayout()
        layout_import.addLayout(method_row)
        method_row.addWidget(QtWidgets.QLabel(tr("method:")))
        method_group = QtWidgets.QButtonGroup(self._parent)
        self._xml_method_radios = {}
        for method_value in XML_IMPORT_METHODS:
            radio = QtWidgets.QRadioButton(method_value)
            method_group.addButton(radio)
            method_row.addWidget(radio)
            self._xml_method_radios[radio] = method_value
        method_row.addStretch()
        bind_radio_value(
            self._settings, SETTING_XML_IMPORT_METHOD, self._xml_method_radios,
        )

        mode_row = QtWidgets.QHBoxLayout()
        layout_import.addLayout(mode_row)
        mode_row.addWidget(QtWidgets.QLabel(tr("mode:")))
        mode_group = QtWidgets.QButtonGroup(self._parent)
        self.xml_mode_replace_radio = QtWidgets.QRadioButton(tr("replace"))
        self.xml_mode_add_radio = QtWidgets.QRadioButton(tr("add"))
        mode_group.addButton(self.xml_mode_replace_radio)
        mode_group.addButton(self.xml_mode_add_radio)
        mode_row.addWidget(self.xml_mode_replace_radio)
        mode_row.addWidget(self.xml_mode_add_radio)
        mode_row.addStretch()
        bind_radio_value(
            self._settings, SETTING_XML_IMPORT_MODE,
            {
                self.xml_mode_replace_radio: XML_MODE_REPLACE,
                self.xml_mode_add_radio: XML_MODE_ADD,
            },
        )

        self.xml_ignore_names_check = QtWidgets.QCheckBox(tr("Ignore names"))
        self.xml_ignore_names_check.setToolTip(
            tr("Ignore influence names on import and match by order instead "
               "(Maya deformerWeights -ignoreName).")
        )
        bind_checkbox(
            self._settings, SETTING_XML_IMPORT_IGNORE_NAMES,
            self.xml_ignore_names_check,
        )

        self.xml_normalize_check = QtWidgets.QCheckBox(tr("Normalize weights"))
        self.xml_normalize_check.setToolTip(
            tr("After import, force-normalize skinCluster weights "
               "(same as Maya Import Deformer Weights).")
        )
        bind_checkbox(
            self._settings, SETTING_XML_IMPORT_NORMALIZE,
            self.xml_normalize_check,
        )

        self.xml_import_bind_pre_matrix_check = QtWidgets.QCheckBox(
            tr("Restore BindPreMatrix")
        )
        self.xml_import_bind_pre_matrix_check.setToolTip(
            tr("Overwrite bindPreMatrix from the file's saved values (requires "
               "'Save BindPreMatrix' at export) instead of trusting the current "
               "scene pose. Needed when a new skinCluster/influence is created "
               "on a rig where joints are driven by controllers -- the current "
               "pose (and 'Go to Bind Pose') can't be trusted in that case.")
        )
        bind_checkbox(
            self._settings, SETTING_XML_IMPORT_BIND_PRE_MATRIX,
            self.xml_import_bind_pre_matrix_check,
        )

        flag_row = QtWidgets.QHBoxLayout()
        layout_import.addLayout(flag_row)
        flag_row.addWidget(self.xml_ignore_names_check)
        flag_row.addWidget(self.xml_normalize_check)
        flag_row.addWidget(self.xml_import_bind_pre_matrix_check)
        flag_row.addStretch()
        layout_import.addStretch()

    def build_export_page(self, layout_export):
        self.xml_export_optimize_check = QtWidgets.QCheckBox(tr("optimize"))
        self.xml_export_optimize_check.setToolTip(
            tr("Prune small weights and remove unused influences before export.")
        )
        bind_checkbox(
            self._settings, SETTING_XML_EXPORT_OPTIMIZE,
            self.xml_export_optimize_check,
        )

        self.xml_export_bind_pre_matrix_check = QtWidgets.QCheckBox(
            tr("Save BindPreMatrix")
        )
        self.xml_export_bind_pre_matrix_check.setToolTip(
            tr("Also save each influence's current bindPreMatrix in the XML, "
               "so a later import can restore the correct bind reference via "
               "'Restore BindPreMatrix' instead of trusting the scene pose at "
               "import time.")
        )
        bind_checkbox(
            self._settings, SETTING_XML_EXPORT_BIND_PRE_MATRIX,
            self.xml_export_bind_pre_matrix_check,
        )
        flag_row = QtWidgets.QHBoxLayout()
        layout_export.addLayout(flag_row)
        flag_row.addWidget(self.xml_export_optimize_check)
        flag_row.addWidget(self.xml_export_bind_pre_matrix_check)
        flag_row.addStretch()

        self.xml_export_wip_check = QtWidgets.QCheckBox(tr("Export as WIP Skin"))
        self.xml_export_wip_check.setToolTip(
            tr("Export a WIP pack (Base + named Layer groups) instead of a "
               "single skin XML. Opens a dialog to assign influences to groups.")
        )
        bind_checkbox(
            self._settings, SETTING_XML_EXPORT_WIP,
            self.xml_export_wip_check,
        )
        layout_export.addWidget(self.xml_export_wip_check)
        layout_export.addStretch()

    def import_method(self) -> str:
        for radio, method_value in self._xml_method_radios.items():
            if radio.isChecked():
                return method_value
        return XML_METHOD_INDEX

    def import_mode(self) -> str:
        if self.xml_mode_replace_radio.isChecked():
            return XML_MODE_REPLACE
        return XML_MODE_ADD

    def import_ignore_names(self) -> bool:
        return self.xml_ignore_names_check.isChecked()

    def import_normalize(self) -> bool:
        return self.xml_normalize_check.isChecked()

    def import_bind_pre_matrix(self) -> bool:
        return self.xml_import_bind_pre_matrix_check.isChecked()

    def export_optimize(self) -> bool:
        return self.xml_export_optimize_check.isChecked()

    def export_bind_pre_matrix(self) -> bool:
        return self.xml_export_bind_pre_matrix_check.isChecked()

    def export_wip(self) -> bool:
        return self.xml_export_wip_check.isChecked()
