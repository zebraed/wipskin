"""Maya user-feedback helpers shared by WipSkin UI and controllers."""

from __future__ import annotations

from maya import cmds
from maya.api import OpenMaya as om2

from wipskin.core.constants import APP_TITLE


def display_info(message: str):
    om2.MGlobal.displayInfo(f"{APP_TITLE}: {message}")


def display_warning(message: str):
    om2.MGlobal.displayWarning(f"{APP_TITLE}: {message}")


def display_error(message: str):
    om2.MGlobal.displayError(f"{APP_TITLE}: {message}")


def confirm(
    title: str,
    message: str,
    confirm_label: str = "Continue",
    default_to_confirm: bool = False,
) -> bool:
    """Modal confirm dialog.

    Listing many names here makes the dialog outgrow the screen; use
    ui.confirm_list_dialog.confirm_with_items for that.

    Returns:
        bool: True when the user picks confirm_label.
    """
    result = cmds.confirmDialog(
        title=title,
        message=message,
        button=(confirm_label, "Cancel"),
        defaultButton=confirm_label if default_to_confirm else "Cancel",
        cancelButton="Cancel",
        dismissString="Cancel",
    )
    return result == confirm_label


def show_error_dialog(title: str, message: str):
    cmds.confirmDialog(title=title, message=message, button="Ok")
