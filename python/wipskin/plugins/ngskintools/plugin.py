"""Entry module of the bundled ngSkinTools plugin: importing it registers the layer .json format.

Kept apart from the package __init__ so the pure modules (constants,
format, weights, layer_file) import outside Maya without registering anything.
"""

import os

from wipskin import api
from wipskin.plugins.ngskintools.ui.adapter import NgSkinToolsFormatIO

api.register_skin_format(NgSkinToolsFormatIO)

# Translations live beside the code; see wipskin.api.register_locales.
api.register_locales(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
)
