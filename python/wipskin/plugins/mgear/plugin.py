"""Entry module of the bundled mGear plugin: importing it registers .jSkin /
.gSkin and their packs.

Kept apart from the package __init__ so the pure modules (constants,
format, weights) import outside Maya without registering anything.
"""

import os

from wipskin import api
from wipskin.plugins.mgear.ui.adapter import MgearFormatIO

api.register_skin_format(MgearFormatIO)

# Translations live beside the code; see wipskin.api.register_locales.
api.register_locales(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
)
