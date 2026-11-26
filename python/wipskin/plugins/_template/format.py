"""Template skin format: a tab separated text file, one row per vertex.

Replace read_weights / write_weights with your own encoding. No Maya or Qt
import, so the codec is unit-testable on its own.

File layout::

    body<TAB>hip<TAB>knee          shape name, then the influence names
    1.0<TAB>0.0                    one row of weights per vertex
    0.25<TAB>0.75
"""

from __future__ import annotations

from wipskin import api
from wipskin.plugins._template import constants


class TemplateSkinFormat(api.SkinFormat):
    """Dense per-vertex weights as text (``.tmplskin``)."""

    mode = constants.MODE
    label = constants.LABEL
    extensions = (constants.EXTENSION,)
    is_text_format = True

    def read_weights(self, path):
        with open(path, encoding="utf-8") as handle:
            header, *rows = handle.read().splitlines()

        shape, *influences = header.split("\t")
        weights = [float(value) for row in rows for value in row.split("\t")]
        return api.SkinWeightData(shape, influences, weights)

    def write_weights(self, path, data):
        count = len(data.influences)
        lines = ["\t".join([data.shape, *data.influences])]
        for start in range(0, len(data.weights), count):
            row = data.weights[start:start + count]
            lines.append("\t".join(repr(value) for value in row))

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
