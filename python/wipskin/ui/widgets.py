"""Small Qt helpers shared by WipSkin UI modules."""

import os

from wipskin.ui.qt_compat import QtCore, QtGui, QtWidgets, QSvgRenderer, wrapInstance
from wipskin.core.i18n import tr

_ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

def exec_menu(menu, global_pos):
    """Show a context menu (PySide2 exec_ / PySide6 exec compatibility)."""
    if hasattr(menu, "exec"):
        return menu.exec(global_pos)
    return menu.exec_(global_pos)


ICON_IMPORT_SVG = "import.svg"
ICON_EXPORT_SVG = "export.svg"
ICON_WIPSKIN_SVG = "wipskin.svg"
ICON_REFRESH_SVG = "refresh.svg"
ICON_OPEN_SVG = "open.svg"
ICON_DELETE_SVG = "delete.svg"
ICON_RENAME_SVG = "rename.svg"
ICON_ARCHIVE_SVG = "archive.svg"
ICON_HISTORY_SVG = "history.svg"
ICON_OPPOSITE_SIDE_SVG = "opposite_side.svg"

# Built-in Maya icon (not bundled -- resolved through Maya's own Qt resource
# system, registered as ":/<name>" inside a Maya PySide session).
ICON_LAYER_EDITOR_MAYA = "layerEditor.png"

IO_BUTTON_ICON_SIZE = 16
MENU_BRAND_ICON_SIZE = 20
CONTEXT_MENU_ICON_SIZE = 16


def make_separator(mode="horizontal"):
    """Make a QFrame designed to be a horizontal/vertical separator."""
    widget_separator = QtWidgets.QFrame()
    if mode == "horizontal":
        widget_separator.setFrameStyle(QtWidgets.QFrame.HLine)
    elif mode == "vertical":
        widget_separator.setFrameStyle(QtWidgets.QFrame.VLine)
    widget_separator.setSizePolicy(
        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
    )
    return widget_separator


def svg_icon_path(filename):
    """Resolve a filename under the package icons/ directory."""
    return os.path.join(_ICONS_DIR, filename)


def make_maya_builtin_icon(resource_name):
    """Load a built-in Maya icon (e.g. "layerEditor.png") via Maya's own Qt
    resource system, registered as ":/<name>" inside a Maya PySide session.
    Returns a null QIcon (isNull() True) when the resource isn't found.
    """
    return QtGui.QIcon(f":/{resource_name}")


def _load_qsvg_renderer():
    if QSvgRenderer is None:
        raise ImportError("QtSvg is not available")
    return QSvgRenderer


def make_colored_svg_icon(svg_path, size, color=None):
    """Render a monochrome SVG and tint it to match UI text color."""
    if color is None:
        color = QtGui.QColor(255, 255, 255)

    try:
        qsvg_renderer = _load_qsvg_renderer()
    except ImportError:
        return QtGui.QIcon(svg_path)

    renderer = qsvg_renderer(svg_path)
    if not renderer.isValid():
        return QtGui.QIcon(svg_path)

    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    colored = QtGui.QPixmap(size, size)
    colored.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(colored)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_Source)
    painter.fillRect(colored.rect(), color)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_DestinationIn)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()

    return QtGui.QIcon(colored)


def make_svg_window_icon(svg_filename, sizes=(16, 24, 32, 48, 64)):
    """Build a window icon from an SVG, preserving its original colors."""
    path = svg_icon_path(svg_filename)
    if not os.path.isfile(path):
        return QtGui.QIcon()

    try:
        qsvg_renderer = _load_qsvg_renderer()
    except ImportError:
        return QtGui.QIcon(path)

    renderer = qsvg_renderer(path)
    if not renderer.isValid():
        return QtGui.QIcon(path)

    icon = QtGui.QIcon()
    for size in sizes:
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def make_svg_pixmap(svg_filename, size):
    """Render an SVG to a pixmap at a single size."""
    path = svg_icon_path(svg_filename)
    if not os.path.isfile(path):
        return QtGui.QPixmap()

    try:
        qsvg_renderer = _load_qsvg_renderer()
    except ImportError:
        icon = QtGui.QIcon(path)
        pixmap = icon.pixmap(size, size)
        if pixmap.isNull():
            return QtGui.QPixmap()
        return pixmap

    renderer = qsvg_renderer(path)
    if not renderer.isValid():
        return QtGui.QPixmap()

    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def make_menu_bar_brand_widget(parent=None):
    """Small logo widget for the menu bar top-left corner."""
    label = QtWidgets.QLabel(parent)
    pixmap = make_svg_pixmap(ICON_WIPSKIN_SVG, MENU_BRAND_ICON_SIZE)
    if pixmap.isNull():
        label.hide()
        return label

    label.setPixmap(pixmap)
    label.setFixedSize(MENU_BRAND_ICON_SIZE, MENU_BRAND_ICON_SIZE)
    label.setToolTip("WipSkin")
    return label


def _wrap_maya_qt_widget(ptr):
    if not ptr:
        return None

    return wrapInstance(int(ptr), QtWidgets.QWidget)


def apply_maya_window_icon(widget, workspace_control_name=None):
    """Apply the WipSkin window icon to the widget and the Maya controls
    registered under its own names (object name, workspace control name).

    Ancestors are deliberately left alone: they can be shared with other
    tools (e.g. Maya's main window), whose windows would inherit the icon.
    """
    icon = make_svg_window_icon(ICON_WIPSKIN_SVG)
    if icon.isNull():
        return

    targets = []
    if widget is not None:
        targets.append(widget)

    try:
        from maya import OpenMayaUI as omui
    except ImportError:
        omui = None

    lookup_names = []
    if widget is not None and widget.objectName():
        lookup_names.append(widget.objectName())
    if workspace_control_name:
        lookup_names.append(workspace_control_name)

    if omui is not None:
        for name in lookup_names:
            for finder in (omui.MQtUtil.findControl, omui.MQtUtil.findWindow):
                qt_widget = _wrap_maya_qt_widget(finder(name))
                if qt_widget is not None:
                    targets.append(qt_widget)

    seen = set()
    for target in targets:
        target_id = id(target)
        if target_id in seen:
            continue
        seen.add(target_id)
        target.setWindowIcon(icon)


def make_io_button(text, svg_filename, tooltip="", callback=None, icon_size=IO_BUTTON_ICON_SIZE):
    """Push button with an SVG icon shown before the label text."""
    button = QtWidgets.QPushButton(text)
    path = svg_icon_path(svg_filename)
    if os.path.isfile(path):
        icon_color = button.palette().color(QtGui.QPalette.ButtonText)
        button.setIcon(make_colored_svg_icon(path, icon_size, icon_color))
        button.setIconSize(QtCore.QSize(icon_size, icon_size))
        button.setText(f" {text}")
    if tooltip:
        button.setToolTip(tooltip)
    if callback is not None:
        button.clicked.connect(callback)
    return button


class ElidedLabel(QtWidgets.QLabel):
    """Single-line label that elides long text instead of wrapping, so its
    height never changes with content (prevents layout jumps).
    """

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed
        )
        self._update_elided_text()

    def setText(self, text):
        self._full_text = text
        self._update_elided_text()

    def text(self):
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self):
        metrics = QtGui.QFontMetrics(self.font())
        available = max(self.width() - 4, 0)
        elided = metrics.elidedText(
            self._full_text, QtCore.Qt.ElideMiddle, available
        )
        super().setText(elided)
        if elided != self._full_text:
            self.setToolTip(self._full_text)
        else:
            self.setToolTip("")


def make_history_label(tooltip="Right-click for recent weight directories."):
    """History control that opens the recent weight-directory menu."""
    label = QtWidgets.QLabel()
    color = QtWidgets.QApplication.palette().color(QtGui.QPalette.WindowText)
    icon = make_colored_svg_icon(
        svg_icon_path(ICON_HISTORY_SVG), CONTEXT_MENU_ICON_SIZE, color
    )
    label.setPixmap(icon.pixmap(CONTEXT_MENU_ICON_SIZE, CONTEXT_MENU_ICON_SIZE))
    label.setToolTip(tr(tooltip))
    label.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
    return label


class MayaCollapsibleGroup(QtWidgets.QWidget):
    toggled = QtCore.Signal(bool)

    def __init__(self, title="", collapsed=False, icon=None, parent=None):
        super().__init__(parent)
        self._is_collapsed = collapsed
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Maximum,
        )
        self._setup_ui(title, icon)

    def _setup_ui(self, title, icon=None):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = _CollapsibleGroupHeader(title, not self._is_collapsed, icon=icon)
        self._header.clicked.connect(self._on_header_clicked)
        outer.addWidget(self._header)

        self._content = QtWidgets.QWidget()
        self._content.setObjectName("MayaCollapsibleGroupContent")

        self.content_layout = QtWidgets.QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(20, 3, 6, 6)
        self.content_layout.setSpacing(3)
        outer.addWidget(self._content)

        self._content.setVisible(not self._is_collapsed)

    def _on_header_clicked(self):
        self._is_collapsed = not self._is_collapsed
        self._header.set_expanded(not self._is_collapsed)
        self._content.setVisible(not self._is_collapsed)
        self.toggled.emit(not self._is_collapsed)

    @property
    def is_expanded(self):
        return not self._is_collapsed

    @property
    def title(self):
        return self._header.text()

    @title.setter
    def title(self, value):
        self._header.setText(value)

    @property
    def icon(self):
        return self._header.icon()

    @icon.setter
    def icon(self, value):
        self._header.set_icon(value)
        self._header.updateGeometry()

    def set_expanded(self, expanded):
        if expanded != self.is_expanded:
            self._on_header_clicked()


class _CollapsibleGroupHeader(QtWidgets.QAbstractButton):
    _HEIGHT = 34
    _H_PAD = 6
    _ARROW_LONG = 8
    _ARROW_SHORT = 6
    _ICON_SIZE = 16
    _ICON_GAP = 5
    _TEXT_GAP = 5

    _BG_COLOR = QtGui.QColor("#5a5a5a")
    _BG_HOVER_COLOR = QtGui.QColor("#676767")
    _TEXT_COLOR = QtGui.QColor("#eeeeee")
    _ARROW_COLOR = QtGui.QColor("#eeeeee")

    def __init__(self, title, expanded, icon=None, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._hovered = False
        self._icon = _normalize_header_icon(icon)
        self.setText(title)
        self.setFixedHeight(self._HEIGHT)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def icon(self):
        return QtGui.QIcon(self._icon)

    def set_icon(self, icon):
        self._icon = _normalize_header_icon(icon)
        self.update()

    def set_expanded(self, expanded):
        self._expanded = expanded
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect()

        bg = self._BG_HOVER_COLOR if self._hovered else self._BG_COLOR
        painter.fillRect(rect, bg)

        painter.setPen(QtGui.QColor("#2e2e2e"))
        painter.drawLine(0, rect.height() - 1, rect.width(), rect.height() - 1)

        cy = rect.height() // 2
        self._draw_arrow(painter, self._H_PAD, cy)

        content_x = self._H_PAD + self._ARROW_SHORT + self._TEXT_GAP
        content_x = self._draw_icon(painter, rect, content_x)
        self._draw_title(painter, rect, content_x)

    def _draw_icon(self, painter, rect, x):
        if self._icon.isNull():
            return x

        icon_y = (rect.height() - self._ICON_SIZE) // 2
        icon_rect = QtCore.QRect(x, icon_y, self._ICON_SIZE, self._ICON_SIZE)
        self._icon.paint(
            painter,
            icon_rect,
            QtCore.Qt.AlignCenter,
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off,
        )
        return x + self._ICON_SIZE + self._ICON_GAP

    def _draw_title(self, painter, rect, text_x):
        painter.setPen(self._TEXT_COLOR)
        text_rect = QtCore.QRect(
            text_x, 0, rect.width() - text_x - self._H_PAD, rect.height()
        )
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
            self.text(),
        )

    def _draw_arrow(self, painter, x, cy):
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self._ARROW_COLOR)

        if self._expanded:
            w = self._ARROW_LONG
            h = self._ARROW_SHORT
            hw = w // 2
            hh = h // 2
            points = [
                QtCore.QPoint(x, cy - hh),
                QtCore.QPoint(x + w, cy - hh),
                QtCore.QPoint(x + hw, cy + hh),
            ]
        else:
            w = self._ARROW_SHORT
            h = self._ARROW_LONG
            hh = h // 2
            points = [
                QtCore.QPoint(x, cy - hh),
                QtCore.QPoint(x, cy + hh),
                QtCore.QPoint(x + w, cy),
            ]

        painter.drawPolygon(QtGui.QPolygon(points))

    def sizeHint(self):
        width = 200
        if not self._icon.isNull():
            width += self._ICON_SIZE + self._ICON_GAP
        return QtCore.QSize(width, self._HEIGHT)


def _normalize_header_icon(icon):
    if icon is None:
        return QtGui.QIcon()
    if isinstance(icon, QtGui.QIcon):
        return icon
    if isinstance(icon, str) and icon:
        return QtGui.QIcon(icon)
    return QtGui.QIcon()
