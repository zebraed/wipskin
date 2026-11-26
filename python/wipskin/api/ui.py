"""UI-side API for WipSkin plugins (needs Maya and Qt).

Subclass SkinFormatIO to drive Import/Export and the viewer yourself, and
SkinFormatOptions for an option page. Adapters talk to the tab through
``self.host`` (a Host); option pages get a SkinFormatContext.
"""

from wipskin.ui.common import bind_checkbox, bind_radio_value
from wipskin.ui.confirm_list_dialog import confirm_with_items
from wipskin.ui.controllers.skin_formats.base import SkinFormatIO
from wipskin.ui.controllers.skin_formats.host import SkinTabHost, ViewerPort
from wipskin.ui.export_base_name_dialog import prompt_export_base_name
from wipskin.ui.file_action import FileAction
from wipskin.ui.qt_compat import QtCore, QtGui, QtWidgets
from wipskin.ui.skin_formats.base import (
    NoOptions,
    SkinFormatContext,
    SkinFormatOptions,
)
from wipskin.ui.widgets import (
    ICON_EXPORT_SVG,
    ICON_IMPORT_SVG,
    ICON_RENAME_SVG,
    make_separator,
)

#: What SkinFormatIO.host is: the tab as one adapter sees it.
Host = SkinTabHost

__all__ = [
    "FileAction",
    "Host",
    "ICON_EXPORT_SVG",
    "ICON_IMPORT_SVG",
    "ICON_RENAME_SVG",
    "NoOptions",
    "QtCore",
    "QtGui",
    "QtWidgets",
    "SkinFormatContext",
    "SkinFormatIO",
    "SkinFormatOptions",
    "ViewerPort",
    "bind_checkbox",
    "bind_radio_value",
    "confirm_with_items",
    "make_separator",
    "prompt_export_base_name",
]
