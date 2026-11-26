"""PySide2/PySide6 compatibility layer"""

try:
    from PySide6 import QtCore, QtGui, QtUiTools, QtWidgets
    from PySide6.QtCore import QByteArray
    from shiboken6 import isValid, wrapInstance
    PYSIDE_VERSION = 6
except ImportError:
    try:
        from PySide2 import QtCore, QtGui, QtUiTools, QtWidgets
        from PySide2.QtCore import QByteArray
        from shiboken2 import isValid, wrapInstance
        PYSIDE_VERSION = 2
    except ImportError as e:
        raise ImportError(
            "Neither PySide6 nor PySide2 could be imported. "
            "Ensure you are running this in a Maya environment "
            "with PySide installed."
        ) from e

# Qt 6 moved QAction and QActionGroup from QtWidgets to QtGui.
if PYSIDE_VERSION == 6:
    QActionGroup = QtGui.QActionGroup
else:
    QActionGroup = QtWidgets.QActionGroup

try:
    if PYSIDE_VERSION == 6:
        from PySide6.QtSvg import QSvgRenderer
    else:
        from PySide2.QtSvg import QSvgRenderer
except ImportError:
    QSvgRenderer = None

__all__ = [
    "QtUiTools",
    "QByteArray",
    "QtCore",
    "QtGui",
    "QtWidgets",
    "QSvgRenderer",
    "QActionGroup",
    "isValid",
    "wrapInstance",
    "PYSIDE_VERSION",
]
