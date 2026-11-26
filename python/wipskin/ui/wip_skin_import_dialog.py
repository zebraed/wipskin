"""WIP Skin Import dialog: per-group enable/ratio for a .wip pack.
"""

from __future__ import annotations

import os

from maya import cmds, mel

from wipskin.ui.qt_compat import QtCore, QtWidgets

from wipskin.core import feedback
from wipskin.core.constants import APP_TITLE
from wipskin.formats.skin.xml.constants import (
    SETTING_WIP_IMPORT_NORMALIZE,
    WIP_NORMALIZE_INTERACTIVE,
    WIP_NORMALIZE_POST,
)
from wipskin.formats.skin.xml import wip as wip_skin
from wipskin.ui.common import bind_radio_value
from wipskin.ui.widgets import ICON_LAYER_EDITOR_MAYA, make_maya_builtin_icon
from wipskin.core.i18n import tr

_REALTIME_APPLY_INTERVAL_MS = 40
_REALTIME_UNDO_CHUNK_NAME = "wipRealtimeImport"
_REALTIME_ON_STYLE = (
    "background-color: #2ecc71; color: white; font-weight: bold; "
    "padding: 3px 10px; border-radius: 3px;"
)


class _GroupRow(QtWidgets.QWidget):
    ratio_changed = QtCore.Signal()
    drag_released = QtCore.Signal()

    def __init__(self, group: dict, parent=None):
        super().__init__(parent)
        self.group = group
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layer_icon = make_maya_builtin_icon(ICON_LAYER_EDITOR_MAYA)
        if not layer_icon.isNull():
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(layer_icon.pixmap(16, 16))
            icon_label.setToolTip(tr("Layer group"))
            layout.addWidget(icon_label)

        self.checkbox = QtWidgets.QCheckBox(group["name"])
        self.checkbox.setChecked(True)
        self.checkbox.setMinimumWidth(140)
        self.checkbox.toggled.connect(self._on_toggled)
        layout.addWidget(self.checkbox)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, int(wip_skin.MAX_RATIO))
        self.slider.setValue(int(round(float(group.get("ratio", wip_skin.DEFAULT_RATIO)))))
        layout.addWidget(self.slider, 1)

        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(0, int(wip_skin.MAX_RATIO))
        self.spin.setSuffix("%")
        self.spin.setValue(self.slider.value())
        layout.addWidget(self.spin)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.sliderReleased.connect(self.drag_released.emit)
        self.spin.valueChanged.connect(self._on_spin_changed)
        self._on_toggled(True)

    def _on_toggled(self, checked):
        self.slider.setEnabled(checked)
        self.spin.setEnabled(checked)
        self.ratio_changed.emit()
        # Atomic change (not a drag) -- treat it as already "released" so
        # the Paint Skin Weights refresh (see the dialog) runs right away.
        self.drag_released.emit()

    def _on_slider_changed(self, value):
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)
        self.ratio_changed.emit()

    def _on_spin_changed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.ratio_changed.emit()
        self.drag_released.emit()

    def is_enabled_group(self) -> bool:
        return self.checkbox.isChecked()

    def ratio(self) -> float:
        return float(self.spin.value())


class WipSkinImportDialog(QtWidgets.QDialog):
    """Configure per-group enable/ratio for a WIP Import.
    """

    def __init__(self, directory: str, filename: str, settings, parent=None):
        super().__init__(parent)
        self._directory = directory
        self._filename = filename
        self._settings = settings
        self._manifest = wip_skin.read_manifest(os.path.join(directory, filename))
        self._rows = []
        self._result = None

        self._compose_context = None
        self._realtime_ever_used = False
        self._realtime_timer = QtCore.QTimer(self)
        self._realtime_timer.setSingleShot(True)
        self._realtime_timer.setInterval(_REALTIME_APPLY_INTERVAL_MS)
        self._realtime_timer.timeout.connect(self._apply_realtime)

        base_name = self._manifest.get("base_name", "")
        self.setWindowTitle(tr(
            "{app_title}: WIP Skin Import -- {base_name}",
            app_title=APP_TITLE,
            base_name=base_name,
        ))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(520, 440)
        self._build_ui()
        self._revalidate()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        header_row = QtWidgets.QHBoxLayout()
        info_label = QtWidgets.QLabel(
            tr(
                "Shape: {shape}    Vertices: {count}",
                shape=self._manifest.get('shape', ''),
                count=self._manifest.get('vertex_count', ''),
            )
        )
        header_row.addWidget(info_label)
        header_row.addStretch()
        self.realtime_button = QtWidgets.QPushButton(tr("Realtime: OFF"))
        self.realtime_button.setCheckable(True)
        self.realtime_button.setToolTip(
            tr("When ON, moving a ratio slider or toggling a group applies the "
               "composed weights to the scene immediately (throttled).\n"
               "Cancel undoes the whole Realtime session; turning it back OFF "
               "just stops auto-applying and keeps the current result.")
        )
        self.realtime_button.toggled.connect(self._on_realtime_toggled)
        header_row.addWidget(self.realtime_button)
        layout.addLayout(header_row)

        base_row = QtWidgets.QHBoxLayout()
        layout.addLayout(base_row)
        base_label = QtWidgets.QLabel(tr(
            "{base_group_label} (Replace)",
            base_group_label=wip_skin.BASE_GROUP_LABEL,
        ))
        base_label.setToolTip(tr("Base is always applied at 100% (Replace)."))
        base_row.addWidget(base_label)
        base_row.addStretch()
        base_row.addWidget(QtWidgets.QLabel("100%"))

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        rows_layout = QtWidgets.QVBoxLayout(container)
        for group in self._manifest.get("groups", []):
            row = _GroupRow(group)
            row.ratio_changed.connect(self._on_group_row_changed)
            row.drag_released.connect(self._on_group_row_drag_released)
            rows_layout.addWidget(row)
            self._rows.append(row)
        rows_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        normalize_row = QtWidgets.QHBoxLayout()
        normalize_row.addWidget(QtWidgets.QLabel(tr("Normalize:")))
        self.normalize_post_radio = QtWidgets.QRadioButton(tr("Post"))
        self.normalize_post_radio.setToolTip(
            tr("Default: keep the composed result as raw Post weights "
               "(normalizeWeights=Post, not normalized to sum to 1).")
        )
        self.normalize_interactive_radio = QtWidgets.QRadioButton(tr("Interactive"))
        self.normalize_interactive_radio.setToolTip(
            tr("Force-normalize the composed weights to sum to 1 per vertex "
               "and set normalizeWeights to Interactive.\n"
               "During a Realtime preview this is only applied once, on OK -- "
               "the live drag preview always shows the raw Post result.")
        )
        normalize_group = QtWidgets.QButtonGroup(self)
        normalize_group.addButton(self.normalize_post_radio)
        normalize_group.addButton(self.normalize_interactive_radio)
        normalize_row.addWidget(self.normalize_post_radio)
        normalize_row.addWidget(self.normalize_interactive_radio)
        normalize_row.addStretch()
        bind_radio_value(
            self._settings, SETTING_WIP_IMPORT_NORMALIZE,
            {
                self.normalize_post_radio: WIP_NORMALIZE_POST,
                self.normalize_interactive_radio: WIP_NORMALIZE_INTERACTIVE,
            },
        )
        layout.addLayout(normalize_row)

        self.error_label = QtWidgets.QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #d9534f;")
        layout.addWidget(self.error_label)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText(tr("Import"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _enabled_group_ids(self) -> list:
        return [row.group["id"] for row in self._rows if row.is_enabled_group()]

    def _group_ratios(self) -> dict:
        return {row.group["id"]: row.ratio() for row in self._rows}

    def _revalidate(self) -> bool:
        errors = wip_skin.validate_import(
            self._directory,
            self._filename,
            self._enabled_group_ids(),
            self._group_ratios(),
        )
        self.error_label.setText("\n".join(errors))
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(not errors)
        return not errors

    def _on_group_row_changed(self):
        self._revalidate()
        if self.realtime_button.isChecked():
            self._realtime_timer.start()

    def _on_group_row_drag_released(self):
        if not self.realtime_button.isChecked():
            return
        # Apply the final value immediately instead of waiting for the
        # debounce timer, so releasing the slider never sits at a stale
        # in-between value until the next tick.
        self._realtime_timer.stop()
        self._apply_realtime()

    # ------------------
    # Realtime preview

    def _on_realtime_toggled(self, checked):
        if checked:
            self.realtime_button.setText(tr("Realtime: ON"))
            self.realtime_button.setStyleSheet(_REALTIME_ON_STYLE)
            self._enable_realtime()
        else:
            self.realtime_button.setText(tr("Realtime: OFF"))
            self.realtime_button.setStyleSheet("")
        if self._realtime_ever_used:
            self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText(tr("OK"))

    def _enable_realtime(self):
        if self._compose_context is not None:
            self._apply_realtime()
            return

        opened_chunk = False
        if not self._realtime_ever_used:
            cmds.undoInfo(openChunk=True, chunkName=_REALTIME_UNDO_CHUNK_NAME)
            opened_chunk = True
        try:
            self._compose_context = wip_skin.prepare_wip_compose(
                self._directory, self._filename
            )
        except Exception as exc:
            if opened_chunk:
                cmds.undoInfo(closeChunk=True, chunkName=_REALTIME_UNDO_CHUNK_NAME)
                cmds.undo()
            feedback.display_error(tr("Failed to start Realtime preview: {exc}", exc=exc))
            self.realtime_button.setChecked(False)
            return

        self._realtime_ever_used = True
        self._apply_realtime()

    def _apply_realtime(self):
        if self._compose_context is None:
            return
        try:
            wip_skin.apply_wip_compose(
                self._compose_context, self._enabled_group_ids(), self._group_ratios()
            )
        except Exception as exc:
            feedback.display_error(tr("Realtime WIP preview failed: {exc}", exc=exc))
            return
        self._refresh_paint_skin_weights_color()

    def _refresh_paint_skin_weights_color(self):
        """Re-run Maya's own influence-pick MEL path to reload the Paint
        Skin Weights tool's color display."""
        try:
            current_ctx = cmds.currentCtx()
            if not cmds.artAttrSkinPaintCtx(current_ctx, query=True, exists=True):
                return
            influence = cmds.artAttrSkinPaintCtx(current_ctx, query=True, influence=True)
            if isinstance(influence, (list, tuple)):
                influence = influence[0] if influence else None
            if not influence:
                return
            mel.eval(f"setSmoothSkinInfluence {influence};")
            mel.eval(f"artSkinRevealSelected {current_ctx};")
        except Exception:
            pass

    def _revert_realtime_session(self):
        if not self._realtime_ever_used:
            return
        cmds.undoInfo(closeChunk=True, chunkName=_REALTIME_UNDO_CHUNK_NAME)
        cmds.undo()
        self._realtime_ever_used = False
        self._compose_context = None

    # ------------------
    # Accept / reject

    def accept(self):
        if not self._revalidate():
            QtWidgets.QMessageBox.warning(
                self, self.windowTitle(), self.error_label.text()
            )
            return
        already_applied = False
        if self._realtime_ever_used:
            self._realtime_timer.stop()
            try:
                wip_skin.finalize_wip_compose(
                    self._compose_context, self.normalize_interactive_radio.isChecked()
                )
            except Exception as exc:
                feedback.display_error(str(exc))
                return
            cmds.undoInfo(closeChunk=True, chunkName=_REALTIME_UNDO_CHUNK_NAME)
            already_applied = True
        self._result = {
            "enabled_group_ids": self._enabled_group_ids(),
            "group_ratios": self._group_ratios(),
            "normalize_interactive": self.normalize_interactive_radio.isChecked(),
            "already_applied": already_applied,
        }
        super().accept()

    def reject(self):
        self._realtime_timer.stop()
        self._revert_realtime_session()
        super().reject()

    def result_config(self) -> dict:
        """Resolved import configuration; only valid after accept().
        """
        return self._result
