"""Modal dialog for choosing a .gSkinPack base name when Auto Naming is off.

Thin wrapper around the shared ExportBaseNameDialog.
"""

from __future__ import annotations

from wipskin.api import APP_TITLE
from wipskin.api.ui import prompt_export_base_name
from wipskin.api import tr


def prompt_gskin_pack_base_name(parent, directory, initial_name="") -> str | None:
    """Show the pack-name dialog.

    Returns:
        str: The sanitized base name, or None if cancelled.
    """
    return prompt_export_base_name(
        parent,
        directory,
        extension="gSkinPack",
        initial_name=initial_name,
        title=tr("{app_title}: Export .gSkinPack", app_title=APP_TITLE),
        hint=(
            tr("Enter a base name for the .gSkinPack manifest "
               "(used by mGear rig build import).")
        ),
        existing_label=tr("Existing packs:"),
        placeholder=tr("e.g. character_skin"),
        empty_error=tr("Enter a valid base name for the .gSkinPack file."),
        strip_extensions=("gSkinPack", "jSkinPack"),
    )
