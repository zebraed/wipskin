"""mGear skin format id, settings keys and option values (no mGear imports)."""

MODE_MGEAR = "mgear"

SETTING_EXPORT_AUTO_NAMING_MGEAR = "setting_wipskin_exportAutoNamingMgear"
SETTING_MGEAR_EXPORT_FORMAT = "setting_wipskin_mgearExportFormat"
SETTING_MGEAR_EXPORT_PACK = "setting_wipskin_mgearExportPack"
SETTING_MGEAR_PACK_BASE_NAME = "setting_wipskin_mgearPackBaseName"
SETTING_MGEAR_PACK_IMPORT_VERSION = "setting_wipskin_mgearPackImportVersion"

MGEAR_FORMAT_JSKIN = "jSkin"
MGEAR_FORMAT_GSKIN = "gSkin"
MGEAR_PACK_VERSION_LATEST = "latest"
MGEAR_PACK_VERSION_RECORDED = "recorded"

DEFAULT_SETTINGS = {
    SETTING_EXPORT_AUTO_NAMING_MGEAR: False,
    SETTING_MGEAR_EXPORT_FORMAT: MGEAR_FORMAT_JSKIN,
    SETTING_MGEAR_EXPORT_PACK: False,
    SETTING_MGEAR_PACK_IMPORT_VERSION: MGEAR_PACK_VERSION_LATEST,
}
