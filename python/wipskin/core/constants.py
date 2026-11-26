"""WipSkin app identity and app-wide QSettings keys.

Constants owned by one skin format live in that format's package
(formats/skin/<name>/constants.py), next to the defaults it declares.
"""

APP_TITLE = "WipSkin"
APP_WINDOW_NAME = "WipSkinWindow"
SETTINGS_ORG = "WipSkin"

__author__ = "zebraed"
__email__ = "contact@sarygamysh.com"
__status__ = "Stable"
__license__ = "MIT"
__copyright__ = "Copyright 2025-2026"
__version__ = "1.4.0"


SETTING_SKIN_WEIGHT_MODE = "setting_wipskin_skinWeightMode"
SETTING_LANGUAGE = "setting_wipskin_language"

# WipSkin-specific UI prefs
SETTING_LAST_TOP_TAB = "setting_wipskin_lastTopTab"
SETTING_RECENT_DIRS = "setting_wipskin_recentDirs"
SETTING_FILE_VIEW_MODE = "setting_wipskin_fileViewMode"
SETTING_CONVERT_SRC = "setting_wipskin_convertSrc"
SETTING_CONVERT_DST = "setting_wipskin_convertDst"
SETTING_SPLITTER_SIZES = "setting_wipskin_splitterSizes"
SETTING_EXPLORER_LEFT_SPLITTER_SIZES = "setting_wipskin_explorerLeftSplitterSizesV2"
SETTING_VIEWER_SPLITTER_SIZES = "setting_wipskin_viewerSplitterSizesV2"
SETTING_IMPORT_AS = "setting_wipskin_importAs"
SETTING_EXPORT_VERSION_NUMBER = "setting_wipskin_exportVersionNumber"
SETTING_IMPORT_OPTIONS_EXPANDED = "setting_wipskin_importOptionsExpanded"
SETTING_EXPORT_OPTIONS_EXPANDED = "setting_wipskin_exportOptionsExpanded"
SETTING_OPTIONS_SPLITTER_SIZES = "setting_wipskin_optionsSplitterSizes"

SETTING_DEFORMER_IMPORT_AS = "setting_wipskin_deformerImportAs"
SETTING_DEFORMER_IMPORT_METHOD = "setting_wipskin_deformerImportMethod"
SETTING_DEFORMER_IMPORT_IGNORE_NAMES = "setting_wipskin_deformerImportIgnoreNames"
SETTING_DEFORMER_EXPORT_AUTO_NAMING = "setting_wipskin_deformerExportAutoNaming"
SETTING_DEFORMER_EXPORT_VERSION_NUMBER = "setting_wipskin_deformerExportVersionNumber"
SETTING_DEFORMER_IMPORT_OPTIONS_EXPANDED = "setting_wipskin_deformerImportOptionsExpanded"
SETTING_DEFORMER_EXPORT_OPTIONS_EXPANDED = "setting_wipskin_deformerExportOptionsExpanded"
SETTING_DEFORMER_SPLITTER_SIZES = "setting_wipskin_deformerSplitterSizes"
SETTING_DEFORMER_EXPLORER_LEFT_SPLITTER_SIZES = (
    "setting_wipskin_deformerExplorerLeftSplitterSizesV2"
)
SETTING_DEFORMER_VIEWER_SPLITTER_SIZES = "setting_wipskin_deformerViewerSplitterSizesV2"

# Maya deformerWeights -method values, shared by the skin XML format and the
# Deformer tab (whose settings default lives here).
XML_METHOD_INDEX = "index"
XML_METHOD_NEAREST = "nearest"
XML_METHOD_BILINEAR = "bilinear"
XML_METHOD_BARYCENTRIC = "barycentric"
XML_METHOD_OVER = "over"

# Skin XML / DeformerWeight import: full set Maya deformerWeights accepts
# (barycentric/bilinear need vertexConnections from mesh export).
XML_IMPORT_METHODS = (
    XML_METHOD_INDEX,
    XML_METHOD_NEAREST,
    XML_METHOD_BILINEAR,
    XML_METHOD_BARYCENTRIC,
    XML_METHOD_OVER,
)

DEFORMER_IMPORT_METHODS = XML_IMPORT_METHODS

IMPORT_AS_SAVED = "saved"
IMPORT_AS_SELECTED = "selected"

MAX_RECENT_DIRS = 9
DEFAULT_CONVERT_SRC = "_L"
DEFAULT_CONVERT_DST = "_R"
DEFAULT_EXPLORER_SPLITTER_SIZES = [120, 610]
DEFAULT_EXPLORER_LEFT_SPLITTER_SIZES = [300, 200]
DEFAULT_VIEWER_SPLITTER_SIZES = [280, 180]
FILE_VIEW_FULL = "full"
FILE_VIEW_LATEST = "latest"

# Last browsed weight directory, shared by every format.
SETTING_LAST_SAVE_PATH = "setting_wipskin_lastSavePath"

REQUESTED_DEFAULTS = {
    SETTING_IMPORT_AS: IMPORT_AS_SAVED,
    SETTING_EXPORT_VERSION_NUMBER: False,
    SETTING_IMPORT_OPTIONS_EXPANDED: True,
    SETTING_EXPORT_OPTIONS_EXPANDED: True,
    SETTING_DEFORMER_IMPORT_AS: IMPORT_AS_SAVED,
    SETTING_DEFORMER_IMPORT_METHOD: XML_METHOD_INDEX,
    SETTING_DEFORMER_IMPORT_IGNORE_NAMES: False,
    SETTING_DEFORMER_EXPORT_AUTO_NAMING: True,
    SETTING_DEFORMER_EXPORT_VERSION_NUMBER: True,
    SETTING_DEFORMER_IMPORT_OPTIONS_EXPANDED: True,
    SETTING_DEFORMER_EXPORT_OPTIONS_EXPANDED: True,
}
