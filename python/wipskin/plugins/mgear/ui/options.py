"""mGear skin format Import/Export options."""

from __future__ import annotations

from wipskin.plugins.mgear.constants import (
    MGEAR_FORMAT_GSKIN,
    MGEAR_FORMAT_JSKIN,
    MGEAR_PACK_VERSION_LATEST,
    MGEAR_PACK_VERSION_RECORDED,
    SETTING_MGEAR_EXPORT_FORMAT,
    SETTING_MGEAR_EXPORT_PACK,
    SETTING_MGEAR_PACK_IMPORT_VERSION,
)
from wipskin.api.ui import bind_checkbox, bind_radio_value
from wipskin.api.ui import QtWidgets
from wipskin.api.ui import SkinFormatOptions
from wipskin.api import tr


class MgearSkinFormatOptions(SkinFormatOptions):
    """mGear .jSkin / .gSkin / pack options."""

    def build_import_page(self, layout_import):
        # A selected pack file is always imported as a pack; this only
        # chooses which member files that import (and the viewer) resolves to.
        version_row = QtWidgets.QHBoxLayout()
        layout_import.addLayout(version_row)
        version_row.addWidget(QtWidgets.QLabel(tr("Import .gSkinPack Version:")))
        self.mgear_pack_version_latest_radio = QtWidgets.QRadioButton(tr("Latest"))
        self.mgear_pack_version_recorded_radio = QtWidgets.QRadioButton(
            tr("Recorded")
        )
        self.mgear_pack_version_latest_radio.setToolTip(
            tr("Resolve each pack member to the newest base.NNNN.jSkin/.gSkin "
               "in the weight directory.")
        )
        self.mgear_pack_version_recorded_radio.setToolTip(
            tr("Import the exact member filenames stored in the .gSkinPack.")
        )
        version_row.addWidget(self.mgear_pack_version_latest_radio)
        version_row.addWidget(self.mgear_pack_version_recorded_radio)
        version_row.addStretch()
        bind_radio_value(
            self._settings, SETTING_MGEAR_PACK_IMPORT_VERSION,
            {
                self.mgear_pack_version_latest_radio: MGEAR_PACK_VERSION_LATEST,
                self.mgear_pack_version_recorded_radio: MGEAR_PACK_VERSION_RECORDED,
            },
            on_change=self._request_viewer_refresh,
        )

        if not self._skin_format.is_available():
            note = QtWidgets.QLabel(self._skin_format.get_unavailable_reason())
            note.setWordWrap(True)
            layout_import.addWidget(note)
        layout_import.addStretch()

    def build_export_page(self, layout_export):
        format_row = QtWidgets.QHBoxLayout()
        layout_export.addLayout(format_row)
        format_row.addWidget(QtWidgets.QLabel(tr("format:")))
        format_group = QtWidgets.QButtonGroup(self._parent)
        self.mgear_format_jskin_radio = QtWidgets.QRadioButton(".jSkin")
        self.mgear_format_gskin_radio = QtWidgets.QRadioButton(".gSkin")
        format_group.addButton(self.mgear_format_jskin_radio)
        format_group.addButton(self.mgear_format_gskin_radio)
        format_row.addWidget(self.mgear_format_jskin_radio)
        format_row.addWidget(self.mgear_format_gskin_radio)
        format_row.addStretch()
        bind_radio_value(
            self._settings, SETTING_MGEAR_EXPORT_FORMAT,
            {
                self.mgear_format_jskin_radio: MGEAR_FORMAT_JSKIN,
                self.mgear_format_gskin_radio: MGEAR_FORMAT_GSKIN,
            },
        )
        self.mgear_export_pack_check = QtWidgets.QCheckBox(tr("Export as .gSkinPack"))
        self.mgear_export_pack_check.setToolTip(
            tr("Export selected meshes as an mGear skin pack manifest "
               "(.gSkinPack). Format above selects .jSkin or .gSkin member files.")
        )
        bind_checkbox(
            self._settings, SETTING_MGEAR_EXPORT_PACK,
            self.mgear_export_pack_check,
        )
        layout_export.addWidget(self.mgear_export_pack_check)
        if not self._skin_format.is_available():
            note = QtWidgets.QLabel(self._skin_format.get_unavailable_reason())
            note.setWordWrap(True)
            layout_export.addWidget(note)
        layout_export.addStretch()

    def get_primary_extension(self) -> str:
        return self._skin_format.get_primary_extension(
            export_pack=self.export_pack(),
            use_json=self.use_json(),
        )

    def use_json(self) -> bool:
        return not self.mgear_format_gskin_radio.isChecked()

    def export_pack(self) -> bool:
        return self.mgear_export_pack_check.isChecked()

    def pack_import_version(self) -> str:
        if self.mgear_pack_version_recorded_radio.isChecked():
            return MGEAR_PACK_VERSION_RECORDED
        return MGEAR_PACK_VERSION_LATEST
