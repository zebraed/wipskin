"""mGear skin format."""

from __future__ import annotations

from wipskin.plugins.mgear.constants import (
    DEFAULT_SETTINGS,
    MODE_MGEAR,
    SETTING_EXPORT_AUTO_NAMING_MGEAR,
)
from wipskin.api import Availability, SkinWeightFormat
from wipskin.plugins.mgear import weights
from wipskin.api import tr


class MgearSkinWeightFormat(SkinWeightFormat):
    """mGear .jSkin / .gSkin and their .gSkinPack packs."""

    mode = MODE_MGEAR
    label = "mGear"
    viewer_title = "mGear Viewer"
    extensions = weights.FILE_EXTENSIONS
    export_auto_naming_setting = SETTING_EXPORT_AUTO_NAMING_MGEAR
    metadata_format = weights.METADATA_FORMAT
    is_text_format = True
    pack_extensions = weights.PACK_EXTENSIONS
    fallback_rank = 2

    @classmethod
    def get_availability(cls) -> Availability:
        if weights.is_available():
            return Availability.AVAILABLE

        return Availability.NOT_INSTALLED

    @classmethod
    def get_unavailable_reason(cls) -> str:
        if cls.is_available():
            return ""

        return tr(
            "mGear is not available in this Maya session. "
            "Install mGear 4.x to use this format."
        )

    def get_default_settings(self) -> dict:
        return dict(DEFAULT_SETTINGS)

    def can_rename_influence(self, name) -> bool:
        return weights.is_renamable_influence_file(name)

    def get_primary_extension(self, export_pack=False, use_json=True) -> str:
        """Extension for a new export, per the tab's format/pack options."""
        if export_pack:
            return weights.EXT_GSKIN_PACK

        return weights.EXT_JSKIN if use_json else weights.EXT_GSKIN
