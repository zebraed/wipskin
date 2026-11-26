"""Maya deformerWeights XML skin format."""

from __future__ import annotations

from wipskin.formats.skin.xml.constants import (
    DEFAULT_SETTINGS,
    MODE_XML,
    SETTING_EXPORT_AUTO_NAMING_XML,
)
from wipskin.core import weight_files
from wipskin.formats.skin.base import SkinWeightFormat
from wipskin.formats.skin.xml import weights
from wipskin.formats.skin.xml import wip


class XmlSkinWeightFormat(SkinWeightFormat):
    """Plain deformerWeights XML plus the .wip pack sub-format."""

    mode = MODE_XML
    label = "XML"
    viewer_title = "XML Viewer"
    extensions = (weights.EXT, wip.EXT)
    export_auto_naming_setting = SETTING_EXPORT_AUTO_NAMING_XML
    metadata_format = weights.METADATA_FORMAT
    is_text_format = True
    supports_opposite_side = True
    pack_extensions = (wip.EXT,)
    fallback_rank = 1

    def get_metadata_format(self, path) -> str:
        # .wip manifests record their own value; member XMLs stay "xml".
        if self.is_pack_filename(path):
            return wip.METADATA_FORMAT

        return self.metadata_format

    def get_default_settings(self) -> dict:
        return dict(DEFAULT_SETTINGS)

    def can_rename_influence(self, name) -> bool:
        return True

    def get_file_predicate(self):
        return weights.is_skin_weight_file

    def expand_file_names(self, directory, names) -> list:
        # A .wip entry stands for its member XMLs too.
        expanded = []
        for name in names:
            if self.is_pack_filename(name):
                expanded.extend(wip.list_pack_version_names(directory, name))
                continue

            expanded.append(name)
        return expanded

    def list_files(self, directory) -> list:
        # Plain XMLs sit in directory; WIP packs live one level down in
        # <base>_wip/ and are listed as "base_wip/base.NNNN.wip".
        names = weight_files.scan_weight_files(
            directory, [weights.EXT], predicate=weights.is_skin_weight_file,
        )
        names += weight_files.scan_subdir_weight_files(
            directory, wip.WIP_DIR_SUFFIX, [wip.EXT],
        )
        return sorted(names)
