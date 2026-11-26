"""qt_compat resolves classes that moved between PySide2 and PySide6.

Qt 6 moved QAction and QActionGroup from QtWidgets to QtGui; the tab builds
a QActionGroup, so a wrong lookup only shows up when the window opens in
Maya. These tests load qt_compat against fake PySide modules laid out like
each real one (a class is absent from the module it is not in), so the
mistake is caught without Maya or Qt installed.
"""

import importlib
import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

QT_COMPAT_PATH = os.path.join(PARENT, "wipskin", "ui", "qt_compat.py")


class _Marker:
    def __init__(self, name):
        self.name = name


def _module(name, **members):
    module = types.ModuleType(name)
    for key, value in members.items():
        setattr(module, key, value)
    return module


def _fake_pyside(major, action_group_in_gui):
    """sys.modules entries shaped like PySide<major>."""
    prefix = f"PySide{major}"
    shiboken = f"shiboken{major}"
    gui_members = {}
    widgets_members = {}
    marker = _Marker(f"{prefix}.QActionGroup")
    (gui_members if action_group_in_gui else widgets_members)[
        "QActionGroup"
    ] = marker
    qt_core = _module(f"{prefix}.QtCore", QByteArray=object)
    qt_gui = _module(f"{prefix}.QtGui", **gui_members)
    qt_widgets = _module(f"{prefix}.QtWidgets", **widgets_members)
    qt_uitools = _module(f"{prefix}.QtUiTools")
    package = _module(
        prefix, QtCore=qt_core, QtGui=qt_gui, QtWidgets=qt_widgets,
        QtUiTools=qt_uitools,
    )
    package.__path__ = []
    modules = {
        prefix: package,
        f"{prefix}.QtCore": qt_core,
        f"{prefix}.QtGui": qt_gui,
        f"{prefix}.QtWidgets": qt_widgets,
        f"{prefix}.QtUiTools": qt_uitools,
        shiboken: _module(
            shiboken, isValid=lambda obj: True, wrapInstance=lambda *a: None
        ),
    }
    return modules, marker


class TestActionGroupLookup(unittest.TestCase):

    def _import_qt_compat(self, fake_modules, hide):
        patched = {name: None for name in hide}
        patched.update(fake_modules)
        # QtSvg is optional in qt_compat; a missing one must not matter.
        patched.setdefault("PySide6.QtSvg", None)
        patched.setdefault("PySide2.QtSvg", None)
        # Loaded from its file: importing wipskin.ui.qt_compat would run
        # wipskin/ui/__init__.py, which opens the window module (needs Maya).
        spec = importlib.util.spec_from_file_location(
            "_qt_compat_under_test", QT_COMPAT_PATH
        )
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, patched):
            spec.loader.exec_module(module)
        return module

    def test_pyside6_takes_it_from_qtgui(self):
        modules, marker = _fake_pyside(6, action_group_in_gui=True)
        compat = self._import_qt_compat(
            modules, hide=["PySide2", "shiboken2"],
        )
        self.assertEqual(compat.PYSIDE_VERSION, 6)
        self.assertIs(compat.QActionGroup, marker)

    def test_pyside2_takes_it_from_qtwidgets(self):
        modules, marker = _fake_pyside(2, action_group_in_gui=False)
        compat = self._import_qt_compat(
            modules, hide=["PySide6", "shiboken6"],
        )
        self.assertEqual(compat.PYSIDE_VERSION, 2)
        self.assertIs(compat.QActionGroup, marker)

    def test_it_is_part_of_the_public_names(self):
        modules, _marker = _fake_pyside(6, action_group_in_gui=True)
        compat = self._import_qt_compat(
            modules, hide=["PySide2", "shiboken2"],
        )
        self.assertIn("QActionGroup", compat.__all__)


class TestNoDirectQActionGroupUse(unittest.TestCase):
    """UI code asks qt_compat for QActionGroup instead of QtWidgets."""

    def test_no_module_uses_qtwidgets_qactiongroup(self):
        package_dir = os.path.join(PARENT, "wipskin")
        offenders = []
        for dirpath, _dirs, files in os.walk(package_dir):
            for name in files:
                if not name.endswith(".py") or name == "qt_compat.py":
                    continue

                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                for needle in (
                    "QtWidgets.QActionGroup", "QtWidgets.QAction(",
                    "QtWidgets.QShortcut", "QtWidgets.QUndo",
                ):
                    if needle in text:
                        offenders.append(f"{os.path.relpath(path, PARENT)}: {needle}")
        self.assertEqual(offenders, [], "moved to QtGui in Qt 6; use qt_compat")


if __name__ == "__main__":
    unittest.main()
