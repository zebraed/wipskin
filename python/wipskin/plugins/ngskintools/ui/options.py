"""ngSkinTools format Import options."""

from __future__ import annotations

from wipskin.api import tr
from wipskin.api.ui import QtWidgets, SkinFormatOptions, bind_checkbox, bind_radio_value
from wipskin.plugins.ngskintools.constants import (
    SETTING_ADD_MISSING_INFS,
    SETTING_CHOOSE_LAYERS,
    SETTING_REPLACE_LAYERS,
    SETTING_TRANSFER_MODE,
    TRANSFER_CLOSEST_POINT,
    TRANSFER_UV_SPACE,
    TRANSFER_VERTEX_ID,
)


class NgSkinToolsOptions(SkinFormatOptions):
    """How layers are mapped onto the destination mesh on Import."""

    def build_import_page(self, layout):
        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        label = QtWidgets.QLabel(tr("Vertex Transfer:"))
        label.setToolTip(
            tr("How the file's vertices are matched to the destination mesh.")
        )
        row.addWidget(label)

        self.vertex_id_radio = QtWidgets.QRadioButton(tr("Vertex ID"))
        self.vertex_id_radio.setToolTip(
            tr("Match by vertex index. Use when both meshes are identical.")
        )
        self.closest_point_radio = QtWidgets.QRadioButton(tr("Closest Surface Point"))
        self.closest_point_radio.setToolTip(
            tr("Match each vertex to the closest point on the exported mesh.")
        )
        self.uv_space_radio = QtWidgets.QRadioButton(tr("UV Space"))
        self.uv_space_radio.setToolTip(
            tr("Like Closest Surface Point, but matched in UV space.")
        )
        group = QtWidgets.QButtonGroup(self._parent)
        for button in (self.vertex_id_radio, self.closest_point_radio, self.uv_space_radio):
            group.addButton(button)
            row.addWidget(button)

        row.addStretch()
        bind_radio_value(
            self._settings, SETTING_TRANSFER_MODE,
            {
                self.vertex_id_radio: TRANSFER_VERTEX_ID,
                self.closest_point_radio: TRANSFER_CLOSEST_POINT,
                self.uv_space_radio: TRANSFER_UV_SPACE,
            },
            registry=self._registry,
        )

        self.add_missing_infs_check = QtWidgets.QCheckBox(tr("Add Missing Influences"))
        self.add_missing_infs_check.setToolTip(
            tr("Add the file's influences that the skinCluster lacks (weight 0) "
               "before importing. Influences missing from the scene are skipped.")
        )
        layout.addWidget(self.add_missing_infs_check)
        bind_checkbox(
            self._settings, SETTING_ADD_MISSING_INFS, self.add_missing_infs_check,
            registry=self._registry,
        )

        self.replace_layers_check = QtWidgets.QCheckBox(tr("Replace Existing Layers"))
        self.replace_layers_check.setToolTip(
            tr("Delete the layers the skinCluster already has before importing. "
               "With Choose Layers on Import, only the existing layers named "
               "like a chosen layer are replaced. "
               "Off: the file's layers are added on top of them.")
        )
        layout.addWidget(self.replace_layers_check)
        bind_checkbox(
            self._settings, SETTING_REPLACE_LAYERS, self.replace_layers_check,
            registry=self._registry,
        )

        self.choose_layers_check = QtWidgets.QCheckBox(tr("Choose Layers on Import"))
        self.choose_layers_check.setToolTip(
            tr("Ask which of the file's layers to import, file by file. "
               "Canceling the dialog stops the remaining files.")
        )
        layout.addWidget(self.choose_layers_check)
        bind_checkbox(
            self._settings, SETTING_CHOOSE_LAYERS, self.choose_layers_check,
            registry=self._registry,
        )
        layout.addStretch()

    def build_export_page(self, layout):
        layout.addStretch()

    def transfer_mode(self) -> str:
        """Stored vertex transfer mode (one of the TRANSFER_* values)."""
        return self._settings.text(SETTING_TRANSFER_MODE)

    def add_missing_influences(self) -> bool:
        """True when Import should add the file's missing influences first."""
        return self._settings.flag(SETTING_ADD_MISSING_INFS)

    def replace_existing_layers(self) -> bool:
        """True when Import should delete the skinCluster's layers first."""
        return self._settings.flag(SETTING_REPLACE_LAYERS)

    def choose_layers(self) -> bool:
        """True when Import should ask which layers of each file to import."""
        return self._settings.flag(SETTING_CHOOSE_LAYERS)
