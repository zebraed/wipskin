"""Dialog to pick which layers of an ngSkinTools file to import."""

from __future__ import annotations

from wipskin.api import tr
from wipskin.api.ui import QtCore, QtGui, QtWidgets

UNCHECKED = 0
PARTIAL = 1
CHECKED = 2

_ID_ROLE = QtCore.Qt.UserRole
_STATE_ROLE = QtCore.Qt.UserRole + 1
_ROW_HEIGHT = 32
_BOX_SIZE = 20
_BOX_MARGIN = 8


class _LayerDelegate(QtWidgets.QStyledItemDelegate):
    """Draws each row as a roomy check box plus the layer name.

    The native indicator is nearly invisible when unchecked on Maya's dark
    style, and too small to hit.
    """

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(_ROW_HEIGHT)
        return size

    def paint(self, painter, option, index):
        state = index.data(_STATE_ROLE)
        palette = option.palette
        rect = option.rect
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        if option.state & QtWidgets.QStyle.State_MouseOver:
            hover = QtGui.QColor(palette.color(QtGui.QPalette.Text))
            hover.setAlpha(24)
            painter.fillRect(rect, hover)

        box = QtCore.QRectF(
            rect.left() + _BOX_MARGIN,
            rect.top() + (rect.height() - _BOX_SIZE) / 2,
            _BOX_SIZE,
            _BOX_SIZE,
        )
        accent = palette.color(QtGui.QPalette.Highlight)
        if state == UNCHECKED:
            painter.setPen(QtGui.QPen(palette.color(QtGui.QPalette.Mid), 1.5))
            painter.setBrush(palette.color(QtGui.QPalette.Base))
        else:
            painter.setPen(QtGui.QPen(accent, 1.5))
            painter.setBrush(accent)

        painter.drawRoundedRect(box, 4, 4)

        mark = QtGui.QPen(QtGui.QColor("white"), 2.2)
        mark.setCapStyle(QtCore.Qt.RoundCap)
        mark.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(mark)
        painter.setBrush(QtCore.Qt.NoBrush)
        if state == CHECKED:
            path = QtGui.QPainterPath()
            path.moveTo(box.left() + 5, box.top() + 10.5)
            path.lineTo(box.left() + 8.8, box.top() + 14.2)
            path.lineTo(box.left() + 15, box.top() + 6)
            painter.drawPath(path)
        elif state == PARTIAL:
            middle = box.top() + _BOX_SIZE / 2
            painter.drawLine(
                QtCore.QPointF(box.left() + 5, middle),
                QtCore.QPointF(box.right() - 5, middle),
            )

        painter.setPen(palette.color(QtGui.QPalette.Text))
        text_rect = rect.adjusted(_BOX_MARGIN * 2 + _BOX_SIZE, 0, -_BOX_MARGIN, 0)
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
            str(index.data(QtCore.Qt.DisplayRole)),
        )
        painter.restore()


class LayerPickerDialog(QtWidgets.QDialog):
    """Layers of one file as a tree of check boxes, drawn like ngSkinTools (top layer first).

    Clicking anywhere on a row toggles it. A group layer is partly checked
    while only some of its children are; it then counts as picked, since its
    children cannot exist without it.
    """

    def __init__(self, file_name, layer_entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Choose Layers"))
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(
            tr("Layers to import from {file_name}:", file_name=file_name)
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(24)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._tree.setFocusPolicy(QtCore.Qt.NoFocus)
        self._tree.setMouseTracking(True)
        self._tree.setItemDelegate(_LayerDelegate(self._tree))
        self._tree.itemClicked.connect(self._toggle)
        layout.addWidget(self._tree)
        self._populate(list(layer_entries))
        self._tree.expandAll()

        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        all_button = QtWidgets.QPushButton(tr("Check All"))
        none_button = QtWidgets.QPushButton(tr("Uncheck All"))
        all_button.clicked.connect(lambda: self._set_all(CHECKED))
        none_button.clicked.connect(lambda: self._set_all(UNCHECKED))
        row.addWidget(all_button)
        row.addWidget(none_button)
        row.addStretch()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(400, 460)

    def _populate(self, entries):
        items = {}
        for entry in sorted(entries, key=lambda entry: entry.index, reverse=True):
            parent_item = items.get(entry.parent_id)
            if parent_item is None and entry.parent_id is not None:
                continue

            item = QtWidgets.QTreeWidgetItem([entry.name])
            item.setData(0, _ID_ROLE, entry.id)
            item.setData(0, _STATE_ROLE, CHECKED)
            if parent_item is None:
                self._tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            items[entry.id] = item

    def _iter_items(self):
        stack = [
            self._tree.topLevelItem(row)
            for row in range(self._tree.topLevelItemCount())
        ]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.child(row) for row in range(item.childCount()))

    def _toggle(self, item, _column=0):
        state = UNCHECKED if item.data(0, _STATE_ROLE) == CHECKED else CHECKED
        self._set_subtree(item, state)
        self._update_ancestors(item)

    def _set_subtree(self, item, state):
        item.setData(0, _STATE_ROLE, state)
        for row in range(item.childCount()):
            self._set_subtree(item.child(row), state)

    def _update_ancestors(self, item):
        parent = item.parent()
        while parent is not None:
            states = {
                parent.child(row).data(0, _STATE_ROLE)
                for row in range(parent.childCount())
            }
            if states == {CHECKED}:
                parent.setData(0, _STATE_ROLE, CHECKED)
            elif states == {UNCHECKED}:
                parent.setData(0, _STATE_ROLE, UNCHECKED)
            else:
                parent.setData(0, _STATE_ROLE, PARTIAL)

            parent = parent.parent()

    def _set_all(self, state):
        for row in range(self._tree.topLevelItemCount()):
            self._set_subtree(self._tree.topLevelItem(row), state)

    def get_checked_ids(self) -> set:
        """Ids of the layers to import: the checked ones and groups partly checked."""
        return {
            item.data(0, _ID_ROLE)
            for item in self._iter_items()
            if item.data(0, _STATE_ROLE) != UNCHECKED
        }


def pick_layers(parent, file_name, layer_entries):
    """Ask which layers of a file to import.

    Args:
        parent (QWidget): Parent of the dialog.
        file_name (str): File name shown in the dialog.
        layer_entries (list): LayerEntry of the file.

    Returns:
        set | None: Ids of the layers to import, or None when canceled.
    """
    dialog = LayerPickerDialog(file_name, layer_entries, parent=parent)
    accepted = dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()
    if accepted != QtWidgets.QDialog.Accepted:
        return None

    return dialog.get_checked_ids()
