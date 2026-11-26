"""ngSkinTools layer (.json) format."""

from __future__ import annotations

from wipskin.api import Availability, SkinWeightFormat, ViewerInfo
from wipskin.api import tr
from wipskin.plugins.ngskintools import layer_file, weights
from wipskin.plugins.ngskintools.constants import DEFAULT_SETTINGS, MODE_NGSKINTOOLS


class NgSkinToolsSkinWeightFormat(SkinWeightFormat):
    """ngSkinTools2 layer JSON, layered on top of an existing skinCluster."""

    mode = MODE_NGSKINTOOLS
    label = "ngSkinTools"
    viewer_title = "ngSkinTools Viewer"
    extensions = (weights.EXT,)
    metadata_format = weights.METADATA_FORMAT
    is_text_format = True
    # Layers need a skinCluster from another format, so never the landing format.
    fallback_rank = 50

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
            "ngSkinTools2 is not installed in this Maya session. It ships with "
            "Maya 2027; on Maya 2026 install ngSkinTools2 to use this format."
        )

    def get_default_settings(self) -> dict:
        return dict(DEFAULT_SETTINGS)

    def get_file_predicate(self):
        return layer_file.is_layer_file

    def influence_node_types(self):
        return ("joint",)

    def describe(self, path):
        summary = layer_file.read_layer_file(path)
        meta_lines = [tr("Layers: {count}", count=len(summary.layer_names))]
        if summary.vertex_count is not None:
            meta_lines.append(tr("Vertices: {count}", count=summary.vertex_count))

        meta_lines.extend(
            tr("  {index}: {name}", index=index, name=name)
            for index, name in enumerate(summary.layer_names, start=1)
        )
        return ViewerInfo(
            meta_lines=meta_lines,
            influences=layer_file.list_display_names(summary.influences),
        )
