"""XML skin format id, settings keys and option values (no Maya imports)."""

from wipskin.core.constants import XML_METHOD_INDEX

MODE_XML = "xml"

SETTING_EXPORT_AUTO_NAMING_XML = "setting_wipskin_exportAutoNamingXml"
SETTING_XML_IMPORT_METHOD = "setting_wipskin_xmlImportMethod"
SETTING_XML_IMPORT_MODE = "setting_wipskin_xmlImportMode"
SETTING_XML_IMPORT_IGNORE_NAMES = "setting_wipskin_xmlImportIgnoreNames"
SETTING_XML_IMPORT_NORMALIZE = "setting_wipskin_xmlImportNormalize"
SETTING_XML_IMPORT_BIND_PRE_MATRIX = "setting_wipskin_xmlImportBindPreMatrix"
SETTING_XML_EXPORT_OPTIMIZE = "setting_wipskin_xmlExportOptimize"
SETTING_XML_EXPORT_BASE_NAME = "setting_wipskin_xmlExportBaseName"
SETTING_XML_EXPORT_BIND_PRE_MATRIX = "setting_wipskin_xmlExportBindPreMatrix"
SETTING_XML_EXPORT_WIP = "setting_wipskin_xmlExportWip"
SETTING_WIP_IMPORT_NORMALIZE = "setting_wipskin_wipImportNormalize"

XML_MODE_REPLACE = "replace"
XML_MODE_ADD = "add"

WIP_NORMALIZE_POST = "post"
WIP_NORMALIZE_INTERACTIVE = "interactive"

DEFAULT_SETTINGS = {
    SETTING_EXPORT_AUTO_NAMING_XML: True,
    SETTING_XML_IMPORT_METHOD: XML_METHOD_INDEX,
    SETTING_XML_IMPORT_MODE: XML_MODE_REPLACE,
    SETTING_XML_IMPORT_IGNORE_NAMES: False,
    SETTING_XML_IMPORT_NORMALIZE: True,
    SETTING_XML_IMPORT_BIND_PRE_MATRIX: False,
    SETTING_XML_EXPORT_OPTIMIZE: False,
    SETTING_XML_EXPORT_BIND_PRE_MATRIX: True,
    SETTING_XML_EXPORT_WIP: False,
    SETTING_WIP_IMPORT_NORMALIZE: WIP_NORMALIZE_POST,
}
