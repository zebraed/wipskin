"""Entry module: importing it adds the JSON Skin format to WipSkin.

Put examples/plugins on PYTHONPATH and set
``WIPSKIN_PLUGINS=wipskin_jsonskin.plugin`` before ``wipskin.showUI()``.
"""

from wipskin import api
from wipskin_jsonskin.format import JsonSkinFormat

api.register_skin_format(JsonSkinFormat)
