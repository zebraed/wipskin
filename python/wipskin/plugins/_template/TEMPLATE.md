# Plugin template

English | [日本語](TEMPLATE_JA.md)

Copy this folder to start a new skin weight format. WipSkin never loads it:
the leading underscore keeps it out of `BUNDLED_PLUGINS`, and nothing scans
the `plugins` folder.

## Make a plugin from it

1. Copy `_template` to `python/wipskin/plugins/<name>` (a bundled plugin), or
   to `<anywhere on PYTHONPATH>/<package>` (an external one).
2. Replace `wipskin.plugins._template` in `plugin.py` and `format.py` with the
   new package path.
3. In `constants.py`, set `MODE`, `LABEL` and `EXTENSION`.
4. In `format.py`, replace the body of `read_weights` / `write_weights` with
   your file encoding. Listing, versioning, comments, the viewer summary and
   the scene side of Import / Export come from WipSkin.
5. Load it:
   - bundled: add `"wipskin.plugins.<name>.plugin"` to `BUNDLED_PLUGINS` in
     `plugins/__init__.py`;
   - external: set `WIPSKIN_PLUGINS=<package>.plugin` before
     `wipskin.showUI()`.

## Files

| File | Role |
| --- | --- |
| `constants.py` | Format id, label and extension. No imports. |
| `format.py` | The format class and its codec. No Maya or Qt import. |
| `plugin.py` | Entry module: importing it registers the format and locales. |
| `locales/ja.json` | Japanese texts for `tr()` strings (source text is the key). |

Need your own Import / Export options or dialogs? Add a `ui/` package with a
`SkinFormatIO` and `SkinFormatOptions` (see `docs/PLUGINS.md`, levels 2 and 3)
and register that class from `plugin.py` instead. Qt code stays under `ui/`.
