"""Entry module: importing it adds the template format to WipSkin."""

import os

from wipskin import api
from wipskin.plugins._template.format import TemplateSkinFormat

api.register_skin_format(TemplateSkinFormat)

# Translations live beside the code; see wipskin.api.register_locales.
api.register_locales(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
)
