"""ngSkinTools format id, settings keys and option values (no ngSkinTools2 imports)."""

MODE_NGSKINTOOLS = "ngskintools"

# Appended to the exported base name: ``{transform}_ngSkintools.NNNN.json``.
FILE_NAME_SUFFIX = "_ngSkintools"

SETTING_TRANSFER_MODE = "setting_ngskintools_transferMode"
SETTING_ADD_MISSING_INFS = "setting_ngskintools_addMissingInfluences"
SETTING_REPLACE_LAYERS = "setting_ngskintools_replaceExistingLayers"
SETTING_CHOOSE_LAYERS = "setting_ngskintools_chooseLayers"

# Same spellings as ngSkinTools2.api.VertexTransferMode, so the stored value is passed through.
TRANSFER_VERTEX_ID = "vertexId"
TRANSFER_CLOSEST_POINT = "closestPoint"
TRANSFER_UV_SPACE = "uvSpace"

DEFAULT_SETTINGS = {
    SETTING_TRANSFER_MODE: TRANSFER_VERTEX_ID,
    SETTING_ADD_MISSING_INFS: True,
    SETTING_REPLACE_LAYERS: True,
    SETTING_CHOOSE_LAYERS: True,
}
