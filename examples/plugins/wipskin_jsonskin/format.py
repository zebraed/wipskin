"""A JSON skin weight format: the smallest plugin that also imports/exports.

Only the file encoding lives here. Listing, versioning, comments, the viewer
summary and the scene side of Import/Export all come from WipSkin, which
calls read_weights / write_weights. No Maya or Qt import, so this module is
unit-testable on its own (see tests/test_example_plugin.py).

File layout::

    {"version": 1,
     "shape": "body",
     "influences": ["hip", "knee"],
     "vertices": [{"hip": 1.0}, {"hip": 0.25, "knee": 0.75}]}
"""

from __future__ import annotations

import json

from wipskin import api

_FILE_VERSION = 1


class JsonSkinFormat(api.SkinFormat):
    """Per-vertex influence weights stored as JSON (``.jsonskin``)."""

    mode = "jsonskin"
    label = "JSON Skin"
    extensions = ("jsonskin",)
    is_text_format = True

    def read_weights(self, path):
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)

        if document.get("version") != _FILE_VERSION:
            raise ValueError(
                f"Unsupported {self.label} version: {document.get('version')}"
            )

        return api.SkinWeightData.from_vertex_weights(
            document["shape"],
            document["vertices"],
            influences=document["influences"],
        )

    def write_weights(self, path, data):
        document = {
            "version": _FILE_VERSION,
            "shape": data.shape,
            "influences": data.influences,
            "vertices": data.list_vertex_weights(),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=1)
