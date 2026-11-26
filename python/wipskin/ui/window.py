"""WipSkin main window: a thin shell that composes the tab views, controllers
and shared comment panel, and manages Maya window/workspace lifecycle.
"""

from __future__ import annotations

import functools
import os

from maya import cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from wipskin.ui.qt_compat import QActionGroup, QtCore, QtWidgets

from wipskin.core import feedback
from wipskin.core import i18n
from wipskin.core import metadata
from wipskin.core import plugin_loader
# The one place the core names the bundled plugins (a list of module names;
# nothing is imported from the plugins here).
from wipskin.plugins import BUNDLED_PLUGINS
from wipskin.formats.deformer import xml as deformer_xml
from wipskin.formats.skin import registry as skin_registry
from wipskin.formats.skin.base import Availability
from wipskin.core.constants import (
    APP_TITLE,
    APP_WINDOW_NAME,
    DEFAULT_VIEWER_SPLITTER_SIZES,
    SETTING_DEFORMER_VIEWER_SPLITTER_SIZES,
    SETTING_LANGUAGE,
    SETTING_LAST_TOP_TAB,
    SETTING_SKIN_WEIGHT_MODE,
    SETTING_VIEWER_SPLITTER_SIZES,
    __author__,
    __copyright__,
    __email__,
    __license__,
    __status__,
    __version__,
)
from wipskin.ui.controllers.deformer_io import DeformerIOController
from wipskin.ui.controllers.skin_formats import registry as skin_format_registry
from wipskin.ui.controllers.skin_io import SkinIOController
from wipskin.ui.settings import SettingsModel
from wipskin.ui.common import ResetRegistry
from wipskin.ui.deformer_tab import DeformerTabView
from wipskin.ui.extras_dialog import ExtrasDialog
from wipskin.ui.skin_tab import SkinWeightTabView
from wipskin.ui.widgets import (
    apply_maya_window_icon,
    make_menu_bar_brand_widget,
)
from wipskin.core.i18n import tr


def _workspace_control_name():
    return f"{APP_WINDOW_NAME}WorkspaceControl"


def _maya_main_window_widget():
    from maya import OpenMayaUI as omui

    from wipskin.ui.qt_compat import wrapInstance

    main_window_ptr = omui.MQtUtil.mainWindow()
    if not main_window_ptr:
        return None
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


def close_existing_window():
    """Close any existing WipSkin window/workspaceControl, dockable or not.
    """
    from wipskin.ui.qt_compat import isValid

    control_name = _workspace_control_name()
    if cmds.workspaceControl(control_name, query=True, exists=True):
        cmds.deleteUI(control_name, control=True)

    main_window = _maya_main_window_widget()
    if main_window is None:
        return
    for q_widget in main_window.findChildren(QtWidgets.QWidget, APP_WINDOW_NAME):
        if isValid(q_widget):
            q_widget.close()


class App(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """Interactive UI for the humans."""
    object_name = APP_WINDOW_NAME
    singleton_key = None
    name = APP_WINDOW_NAME
    title = APP_TITLE

    def __init__(
        self,
        vcExecCmd=None,
        vcDepotRoot=None,
        docsOverride=None,
        dockable=True,
        *args,
        **kwargs,
    ):
        """Init our main window.

        There are certain defaults that you may want exposed to your team
        consistently: that's what the below parameters are for.

        Args:
            vcExecCmd (str, optional): Default None. Project level config:
                if provided here, this value will be auto-filled into the
                Export tab's Version Control 'Exec Command' section and set
                to be read-only.
            vcDepotRoot (str, optional): Default None. Project level config:
                if provided here, this value will be auto-filled into the
                Export tab's Version Control 'Depot Root' section, and set
                it to be read-only.
            docsOverride (str, optional): Default None. A web address to your
                own custom documentation for the tool, kept for the
                'Documentation...' button of the Extras tab.
        """
        super(App, self).__init__(parent=None, *args, **kwargs)
        self._close_workspace_control()
        self._close_other_instances()

        self.vcExecCmd = vcExecCmd
        self.vcDepotRoot = vcDepotRoot
        self.docsOverride = docsOverride
        self._dockable = dockable
        self._extras_dialog = None

        self.setObjectName(self.object_name)
        self.setWindowTitle(f"{App.title} : {__version__}")
        apply_maya_window_icon(self, _workspace_control_name())
        self.setProperty("saveWindowPref", True)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.settings = SettingsModel(
            extra_defaults=skin_registry.get_default_settings()
        )
        self.registry = ResetRegistry()
        self._apply_saved_language()

        # Not having a format's package at all is a normal setup (mGear,
        # ngSkinTools): only warn when it is installed but cannot run.
        for skin_format in skin_registry.list_skin_formats():
            if skin_format.get_availability() is Availability.MISSING_DEPENDENCY:
                feedback.display_warning(
                    tr(
                        "{unavailable_reason} {label} mode is disabled until installed.",
                        unavailable_reason=skin_format.get_unavailable_reason(),
                        label=skin_format.label,
                    )
                )

        # Fall back when a saved format can't run in this session.
        saved_mode = self.settings.raw_text(SETTING_SKIN_WEIGHT_MODE, "")
        start_mode = skin_registry.pick_available_format(saved_mode).mode
        if start_mode != saved_mode:
            self.settings.set(SETTING_SKIN_WEIGHT_MODE, start_mode)

        self.populate()
        # Reload the last place/side the window was in:
        try:
            self.restoreGeometry(self.settings.raw("geometry", ""))
        except TypeError:
            pass

    # ------------------
    # Window lifecycle

    def closeEvent(self, event: QtCore.QEvent):
        """Save settings when the dockable window is closed."""
        self.settings.set("geometry", self.saveGeometry())
        super(App, self).closeEvent(event)

    def showEvent(self, event: QtCore.QEvent):
        super(App, self).showEvent(event)
        self._schedule_window_icon_apply()

    def _schedule_window_icon_apply(self):
        workspace_name = _workspace_control_name()
        apply_maya_window_icon(self, workspace_name)
        for delay in (0, 200):
            QtCore.QTimer.singleShot(
                delay,
                lambda: apply_maya_window_icon(self, workspace_name),
            )

    def _get_singleton_key(self):
        """Return objectName key used to detect duplicate windows."""
        return self.singleton_key or self.object_name

    def _maya_main_window_widget(self):
        return _maya_main_window_widget()

    def _close_other_instances(self):
        """Close other WipSkin windows under the Maya main window.
        """
        from wipskin.ui.qt_compat import isValid

        singleton_key = self._get_singleton_key()
        parent = self.parent()
        if parent is None:
            parent = self._maya_main_window_widget()
        if parent is None:
            return

        for q_widget in parent.findChildren(QtWidgets.QWidget, singleton_key):
            if q_widget is self:
                continue
            if not isValid(q_widget):
                continue
            q_widget.close()

    def _close_workspace_control(self):
        control_name = _workspace_control_name()
        if cmds.workspaceControl(control_name, query=True, exists=True):
            cmds.deleteUI(control_name, control=True)

    # ------------------
    # Build / wiring

    def populate(self):
        """Create the primary contents of our Window/Widget."""
        layout_main = QtWidgets.QVBoxLayout(self)
        layout_main.addWidget(self._build_menu_bar())

        self._build_comment_panel()

        self.skin_tab = SkinWeightTabView(
            self.settings,
            self.registry,
            comment_panel=self.comment_panel,
            io_classes={
                io_class.format_class.mode: io_class
                for io_class in skin_format_registry.list_format_io_classes()
            },
            # Handed to every format as-is; each option page reads the keys it
            # understands, so this window names no format.
            project_config={
                "vc_exec_cmd": self.vcExecCmd,
                "vc_depot_root": self.vcDepotRoot,
            },
        )
        self.deformer_tab = DeformerTabView(
            self.settings,
            side_widget=self.comment_placeholder,
        )
        self.skin_tab.section.link(self.deformer_tab.section)

        self.tab_widget = QtWidgets.QTabWidget()
        layout_main.addWidget(self.tab_widget)
        self.tab_widget.addTab(self.skin_tab, tr("SkinWeight"))
        self.tab_widget.addTab(self.deformer_tab, tr("DeformerWeight"))
        self.tab_widget.setCurrentIndex(
            self.settings.raw_int(SETTING_LAST_TOP_TAB, 0)
        )
        self.tab_widget.currentChanged.connect(self._on_top_tab_changed)

        # Only the visible tab's section scans on refresh; the hidden one
        # defers until it is switched to (see FileExplorerSection.refresh).
        self.skin_tab.section.set_active_check(
            lambda: self.tab_widget.currentWidget() is self.skin_tab
        )
        self.deformer_tab.section.set_active_check(
            lambda: self.tab_widget.currentWidget() is self.deformer_tab
        )

        self.skin_controller = SkinIOController(
            self.settings,
            self.skin_tab,
            comment_provider=self.export_comment,
        )
        self.deformer_controller = DeformerIOController(
            self.settings,
            self.deformer_tab,
        )
        self._wire_signals()
        # Filled once up front so the Options menu is never empty to open.
        self._update_options_menu()

        self._relocate_comment_panel()
        self.skin_tab.section.refresh()
        self.deformer_tab.section.refresh()

    def _build_menu_bar(self) -> QtWidgets.QMenuBar:
        menu_bar = QtWidgets.QMenuBar(self)
        menu_bar.setCornerWidget(
            make_menu_bar_brand_widget(menu_bar),
            QtCore.Qt.TopLeftCorner,
        )
        self._menu_options = menu_bar.addMenu(tr("Options"))
        self._menu_options.aboutToShow.connect(self._update_options_menu)
        self._build_language_menu()
        menu_extras = menu_bar.addMenu(tr("Extras"))
        action_extras = menu_extras.addAction(tr("Extras..."))
        action_extras.triggered.connect(self._show_extras_dialog)
        # Hidden for now; dialog code remains for verbose / print options.
        menu_extras.menuAction().setVisible(False)
        menu_help = menu_bar.addMenu(tr("Help"))
        action_about = menu_help.addAction(tr("About..."))
        action_about.triggered.connect(self._show_about_dialog)
        return menu_bar

    def _update_options_menu(self):
        """Rebuild the entries the formats offer for the current state."""
        from wipskin.ui.qt_compat import isValid

        # aboutToShow can still fire for a window Qt is tearing down (Maya
        # deletes the closed window's C++ side before this Python object goes).
        if not isValid(self._menu_options):
            return

        self._menu_options.clear()
        deformer_active = self._is_deformer_tab_active()
        format_actions = self.skin_controller.list_menu_actions()
        for file_action in format_actions:
            menu_action = self._menu_options.addAction(file_action.label)
            menu_action.triggered.connect(
                lambda *_, callback=file_action.callback: callback()
            )
            if deformer_active:
                menu_action.setEnabled(False)
                menu_action.setToolTip(
                    tr("Available in the SkinWeight tab.")
                )
                continue

            menu_action.setEnabled(file_action.enabled)
            menu_action.setToolTip(file_action.tooltip)

        # Always last, set apart from the formats' own entries (if any).
        if format_actions:
            self._menu_options.addSeparator()

        self._menu_options.addMenu(self._menu_language)

    def _build_language_menu(self):
        """Create the Language submenu once; the Options menu re-adds it.

        Kept as an attribute (not rebuilt with the Options menu) so clearing
        that menu only detaches it instead of leaking a new submenu each time.
        """
        self._menu_language = QtWidgets.QMenu(tr("Language"), self._menu_options)
        group = QActionGroup(self._menu_language)
        group.setExclusive(True)
        self._language_actions = {}
        for code, name in i18n.LANGUAGES.items():
            action = self._menu_language.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == i18n.get_language())
            action.triggered.connect(
                lambda *_, code=code: self._on_language_picked(code)
            )
            group.addAction(action)
            self._language_actions[code] = action

    def _apply_saved_language(self):
        """Load the language stored in the settings, if it is a known one."""
        saved = self.settings.raw_text(SETTING_LANGUAGE, i18n.DEFAULT_LANGUAGE)
        if saved not in i18n.LANGUAGES:
            saved = i18n.DEFAULT_LANGUAGE

        try:
            problems = i18n.set_language(saved)
        except (OSError, ValueError) as exc:
            feedback.display_warning(
                f"Couldn't load the {saved} language catalog: {exc}"
            )
            i18n.set_language(i18n.DEFAULT_LANGUAGE)
            return

        for problem in problems:
            feedback.display_warning(
                f"Skipped a translation catalog: {problem}"
            )

    def _on_language_picked(self, code):
        """Store the language and reopen the window so every text follows it.

        The UI is built in code, so its texts are fixed when the widgets are
        created; reopening is how a new language reaches all of them.
        """
        if code == i18n.get_language():
            return

        self.settings.set(SETTING_LANGUAGE, code)
        # Deferred: this runs inside a menu action of the window that is
        # about to be replaced.
        QtCore.QTimer.singleShot(
            0,
            functools.partial(
                show_window,
                vc_exec_cmd=self.vcExecCmd,
                vc_depot_root=self.vcDepotRoot,
                docs_override=self.docsOverride,
                dockable=self._dockable,
            ),
        )

    def _wire_signals(self):
        skin_tab = self.skin_tab
        skin_controller = self.skin_controller
        skin_tab.import_requested.connect(skin_controller.import_weights)
        skin_tab.export_requested.connect(skin_controller.export_weights)
        skin_tab.convert_requested.connect(skin_controller.convert_selected)
        skin_tab.section.selection_changed.connect(self._on_skin_selection_changed)
        skin_tab.section.item_activated.connect(
            skin_controller.edit_selected_file
        )
        skin_tab.section.set_file_actions_provider(
            skin_controller.list_file_actions
        )
        skin_tab.section.set_custom_rename_provider(
            skin_controller.rename_file
        )
        skin_tab.viewer.selector_changed.connect(skin_controller.on_chunk_selected)
        skin_tab.viewer.print_requested.connect(skin_controller.print_current_chunk)
        skin_tab.viewer.select_all_requested.connect(
            skin_controller.select_all_influences
        )
        skin_tab.viewer.item_clicked.connect(skin_controller.on_viewer_item_clicked)
        skin_tab.viewer.item_activated.connect(
            skin_controller.on_viewer_item_activated
        )
        skin_tab.viewer.rename_influence_requested.connect(
            skin_controller.rename_influence
        )

        deformer_tab = self.deformer_tab
        deformer_controller = self.deformer_controller
        deformer_tab.import_requested.connect(deformer_controller.import_weights)
        deformer_tab.export_requested.connect(deformer_controller.export_weights)
        deformer_tab.deformer_list_refresh_requested.connect(
            deformer_controller.refresh_deformer_list
        )
        deformer_tab.deformer_selection_changed.connect(
            deformer_controller.refresh_deformer_shape_list
        )
        deformer_tab.section.selection_changed.connect(
            self._on_deformer_selection_changed
        )
        deformer_tab.viewer.select_all_requested.connect(
            deformer_controller.select_all_shapes
        )
        deformer_tab.viewer.item_clicked.connect(
            deformer_controller.select_shape
        )

    # ------------------
    # Extras dialog

    def _ensure_extras_dialog(self) -> ExtrasDialog:
        if self._extras_dialog is None:
            dialog = ExtrasDialog(parent=self)
            dialog.reset_preferences_requested.connect(self._reset_preferences)
            dialog.reset_all_defaults_requested.connect(self._reset_all_defaults)
            self._extras_dialog = dialog
        return self._extras_dialog

    def _show_extras_dialog(self):
        dialog = self._ensure_extras_dialog()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _show_about_dialog(self):
        lines = [
            f"{APP_TITLE}  v{__version__}",
            "",
            tr("Author: {value}", value=__author__),
            tr("Email: {value}", value=__email__),
            tr("Copyright: {value}", value=__copyright__),
            tr("Status: {value}", value=__status__),
            tr("License: {value}", value=__license__),
        ]

        QtWidgets.QMessageBox.about(
            self,
            tr("About {app_title}", app_title=APP_TITLE),
            "\n".join(lines),
        )

    def _reset_preferences(self):
        """Clear all stored preferences."""
        self.settings.clear()
        App(
            vcExecCmd=self.vcExecCmd,
            vcDepotRoot=self.vcDepotRoot,
            docsOverride=self.docsOverride,
            dockable=self._dockable,
        )

    def _reset_all_defaults(self):
        """Reset requested import/export/extras controls to startup defaults."""
        self.registry.apply_all()
        feedback.display_info(tr("All settings reset to defaults"))

    # ------------------
    # Shared comment panel

    def _build_comment_panel(self):
        """Create the single comment column reused by both top-level tabs, plus
        the placeholder swapped into the inactive tab's viewer splitter.
        """
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel(tr("Comment")))
        self.comment_edit = QtWidgets.QPlainTextEdit()
        self.comment_edit.setPlaceholderText(
            tr(metadata.COMMENT_PLACEHOLDER_NO_SELECTION)
        )
        self.comment_edit.setToolTip(
            tr("Sidecar comment for the selected weight file. "
               "Update Comment saves to .<file>.info without re-exporting.")
        )
        layout.addWidget(self.comment_edit, 1)
        self.update_comment_button = QtWidgets.QPushButton(tr("Update Comment"))
        self.update_comment_button.setToolTip(
            tr("Save the comment above to the selected file sidecar metadata. "
               "Creates metadata when none exists.")
        )
        self.update_comment_button.clicked.connect(self._update_comment_cmd)
        self.update_comment_button.setEnabled(False)
        layout.addWidget(self.update_comment_button)
        self.comment_panel = panel

        self.comment_placeholder = QtWidgets.QWidget()

    def _is_deformer_tab_active(self) -> bool:
        return self.tab_widget.currentIndex() == 1

    def _active_section(self):
        if self._is_deformer_tab_active():
            return self.deformer_tab.section
        return self.skin_tab.section

    def _comment_text(self) -> str:
        return self.comment_edit.toPlainText().strip()

    def export_comment(self, auto_version: bool = False) -> str:
        """Return comment text to store on export.

        Versioned exports create a new file and must not reuse the comment
        shown for a previously selected weight file.
        """
        if auto_version:
            return ""
        return self._comment_text()

    def _relocate_comment_panel(self):
        if self._is_deformer_tab_active():
            target_splitter = self.deformer_tab.viewer.splitter
            source_splitter = self.skin_tab.viewer.splitter
        else:
            target_splitter = self.skin_tab.viewer.splitter
            source_splitter = self.deformer_tab.viewer.splitter

        panel = self.comment_panel
        placeholder = self.comment_placeholder
        if panel.parent() is target_splitter:
            self._update_comment_field()
            return

        if panel.parent() is source_splitter:
            panel.setParent(None)
            source_splitter.insertWidget(1, placeholder)

        if placeholder.parent() is target_splitter:
            placeholder.setParent(None)

        target_splitter.insertWidget(1, panel)
        target_splitter.setStretchFactor(0, 1)
        target_splitter.setStretchFactor(1, 0)
        target_splitter.setSizes(self.settings.splitter_sizes(
            SETTING_DEFORMER_VIEWER_SPLITTER_SIZES
            if self._is_deformer_tab_active()
            else SETTING_VIEWER_SPLITTER_SIZES,
            DEFAULT_VIEWER_SPLITTER_SIZES,
        ))
        self._update_comment_field()

    def _update_comment_field(self):
        selected_paths = self._active_section().selected_paths()
        self.update_comment_button.setEnabled(bool(selected_paths))

        self.comment_edit.blockSignals(True)
        if not selected_paths:
            self.comment_edit.clear()
            self.comment_edit.setPlaceholderText(
                tr(metadata.COMMENT_PLACEHOLDER_NO_SELECTION)
            )
        else:
            sidecar = metadata.read_sidecar(selected_paths[0])
            comment = ""
            if sidecar is not None:
                comment = sidecar.get("comment", "")
            self.comment_edit.setPlainText(comment)
            if comment:
                self.comment_edit.setPlaceholderText("")
            else:
                self.comment_edit.setPlaceholderText(
                    tr(metadata.COMMENT_PLACEHOLDER_NO_COMMENT)
                )
        self.comment_edit.blockSignals(False)

    def _comment_sidecar_format(self, file_path: str) -> str:
        if self._is_deformer_tab_active():
            return deformer_xml.METADATA_FORMAT
        return self.skin_tab.current_skin_format().get_metadata_format(
            file_path
        )

    def _update_comment_cmd(self):
        selected_paths = self._active_section().selected_paths()
        if not selected_paths:
            feedback.display_warning(
                tr("Select weight file(s) to update comment.")
            )
            return
        comment = self._comment_text()
        updated = []
        for file_path in selected_paths:
            if not os.path.isfile(file_path):
                feedback.display_warning(tr("File not found: {file_path}", file_path=file_path))
                continue
            metadata.write_comment_sidecar(
                file_path,
                comment,
                format_name=self._comment_sidecar_format(file_path),
            )
            updated.append(os.path.basename(file_path))
        if not updated:
            return
        feedback.display_info(tr("Updated comment for {count} file(s)", count=len(updated)))
        self._update_comment_field()
        if self._is_deformer_tab_active():
            self.deformer_controller.update_viewer()
        else:
            self.skin_controller.update_viewer()

    # ------------------
    # Tab / selection handlers

    def _on_top_tab_changed(self, index: int):
        """Save top-level tab index, move the shared comment panel, refresh."""
        self.settings.set(SETTING_LAST_TOP_TAB, index)
        self._relocate_comment_panel()
        if index == 1:
            self.deformer_tab.section.refresh_if_pending()
        else:
            self.skin_tab.section.refresh_if_pending()

    def _on_skin_selection_changed(self):
        self.skin_controller.update_viewer()
        self._update_comment_field()

    def _on_deformer_selection_changed(self):
        self.deformer_controller.update_viewer()
        self._update_comment_field()


def show_window(
    vc_exec_cmd=None,
    vc_depot_root=None,
    docs_override=None,
    dockable=True,
):
    """Launch the WipSkin UI inside Maya."""
    plugin_loader.import_plugin_modules(
        [*BUNDLED_PLUGINS, *plugin_loader.list_plugin_module_names()],
        on_error=lambda name, exc: feedback.display_warning(
            tr(
                "Couldn't load plugin {name}: {error}",
                name=name,
                error=f"{type(exc).__name__}: {exc}",
            )
        ),
    )
    window = App(
        vcExecCmd=vc_exec_cmd,
        vcDepotRoot=vc_depot_root,
        docsOverride=docs_override,
        dockable=dockable,
    )
    MayaQWidgetDockableMixin.show(window, dockable=dockable)
    window._schedule_window_icon_apply()
    return window
