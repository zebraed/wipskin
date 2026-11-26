# Writing a WipSkin skin format plugin

English | [日本語](PLUGINS_JA.md)

A plugin adds a skin weight file format to the **SkinWeight** tab without
editing WipSkin. The bundled mGear and ngSkinTools formats are plugins too
(`python/wipskin/plugins/`), built only on the API described here.

> **Stability:** `wipskin.api.API_VERSION` is `(0, 1)`. While the major
> version is 0 the API is provisional: names may still change between minor
> versions. Check `API_VERSION` if your plugin depends on something newer.

## Contents

1. [Loading a plugin](#1-loading-a-plugin)
2. [Level 0: list your files](#2-level-0-list-your-files)
3. [Level 1: fill the viewer](#3-level-1-fill-the-viewer)
4. [Level 2: import and export](#4-level-2-import-and-export)
5. [Level 3: your own flows and options](#5-level-3-your-own-flows-and-options)
6. [Package layout and import rules](#6-package-layout-and-import-rules)
7. [Testing your plugin](#7-testing-your-plugin)
8. [Translating your plugin](#8-translating-your-plugin)
9. [Format reference](#9-format-reference)

Write only what you need: each level adds a few methods on top of the
previous one, and everything you leave out falls back to a default.

| Level | You write | You get |
|---|---|---|
| 0 | `mode`, `label`, `extensions` | Files list, versioned names, Rename / Delete / Archive, comments (sidecar), viewer header. Import / Export greyed out with a tooltip |
| 1 | `describe(path)` | Viewer metadata and an influence list (dimmed when missing from the scene, double-click selects) |
| 2 | `read_weights` / `write_weights` | Import / Export through WipSkin's shared skinCluster engine; a viewer summary even without `describe` |
| 3 | A `SkinFormatIO` (and `SkinFormatOptions`) | Your own Import / Export flows, option widgets, menus and dialogs |

A working Level 2 example lives in
[`examples/plugins/wipskin_jsonskin`](../examples/plugins/wipskin_jsonskin).

## 1. Loading a plugin

A plugin is a Python module that calls `wipskin.api.register_skin_format()`
when imported. WipSkin imports the modules listed in the `WIPSKIN_PLUGINS`
environment variable (separated like `PATH` entries: `;` on Windows, `:`
elsewhere) every time `wipskin.showUI()` opens the window:

```text
PYTHONPATH=<repo>/python;<your plugin folder>
WIPSKIN_PLUGINS=my_studio_skin.plugin
```

- Registration takes effect in the next window that opens.
- A plugin that fails to import is reported as a warning and skipped; the
  other formats keep working.
- `wipskin.Reload()` re-imports registered plugins together with WipSkin.
- Registering a `mode` twice raises `ValueError` and registers nothing.

Your format appears in the **Format** combo after XML, mGear and ngSkinTools. If
the format cannot run in the session (see `get_availability` below) its
entry is greyed out with your reason as the tooltip.

## 2. Level 0: list your files

```python
# my_studio_skin/plugin.py
from wipskin import api


class StudioSkin(api.SkinFormat):
    mode = "studioskin"       # identifier-like; used in settings keys
    label = "Studio Skin"     # shown in the Format combo
    extensions = ("sskin",)   # without the dot


api.register_skin_format(StudioSkin)
```

That is a complete plugin. WipSkin fills in the rest:

| Attribute | Default |
|---|---|
| `viewer_title` | `"Studio Skin Viewer"` |
| `metadata_format` (sidecar `"format"` value) | the `mode` |
| `export_auto_naming_setting` | `setting_wipskin_studioskin_exportAutoNaming`, default `False` |

## 3. Level 1: fill the viewer

```python
class StudioSkin(api.SkinFormat):
    ...

    def describe(self, path):
        header = read_my_header(path)   # your parser
        return api.ViewerInfo(
            meta_lines=[f"Mesh: {header.mesh}", f"Vertices: {header.count}"],
            influences=header.joints,
        )
```

Raise `OSError` or `ValueError` for files you cannot read; the viewer shows
the message instead of the file.

## 4. Level 2: import and export

Implement the file encoding and nothing else:

```python
class StudioSkin(api.SkinFormat):
    ...

    def read_weights(self, path):
        ...
        return api.SkinWeightData.from_vertex_weights(shape, rows)

    def write_weights(self, path, data):
        for row in data.list_vertex_weights():   # {influence: weight}
            ...
```

### `SkinWeightData`

The weights of one shape, dense and vertex-major (the layout
`MFnSkinCluster.getWeights` / `setWeights` use):

| Member | Meaning |
|---|---|
| `shape` | Name the weights were exported from (Import "saved shape" looks it up) |
| `influences` | Influence names, in column order |
| `weights` | Flat list: weight of influence `i` on vertex `v` is `weights[v * len(influences) + i]` |
| `vertex_count` | Number of vertex rows |
| `from_vertex_weights(shape, rows, influences=None)` | Build from one `{influence: weight}` dict per vertex |
| `list_vertex_weights()` | One `{influence: weight}` dict per vertex, zero weights left out |

It validates itself: an empty or repeated influence list, or weights that do
not fill whole rows, raise `ValueError`.

### What WipSkin does around your codec

**Export** (one file per selected skinned mesh):

- Collects the mesh's skinCluster weights into `SkinWeightData`.
- Names the file like the XML export: the shape name with *Auto Naming*,
  otherwise the base name you type (numbered `_0001`, `_0002`, ... when
  several shapes are selected), plus `.NNNN` with *version number*.
- Calls `write_weights` on a temporary file and swaps it in, so a failing
  writer never leaves a truncated file behind.
- Writes the sidecar (comment, user, scene).

**Import** (each selected file):

- Calls `read_weights`, then applies the result to the recorded shape, or to
  the first selected shape when *Import As* is "selected shape".
- Binds the mesh first when it has no skinCluster, adds missing influences
  to an existing one, and unlocks them (locked influences ignore weight
  writes).
- Matches influences by full DAG path, so namespaces and duplicate short
  names are safe; an ambiguous name is an error.
- Gives weight 0 to scene influences your data does not name, then
  normalizes.

**Limits:** polygon meshes only, matched by vertex index; the vertex count
must equal the data's.

## 5. Level 3: your own flows and options

Register a `wipskin.api.ui.SkinFormatIO` subclass instead of the format
class when you need option widgets, menus or a different Import / Export:

```python
from wipskin import api
from wipskin.api import ui
from wipskin.api.maya import feedback, scene


class StudioOptions(ui.SkinFormatOptions):
    def build_import_page(self, layout):
        self.mirror_check = ui.QtWidgets.QCheckBox("Mirror on import")
        ui.bind_checkbox(self._settings, "setting_studio_mirror", self.mirror_check)
        layout.addWidget(self.mirror_check)

    def build_export_page(self, layout):
        layout.addStretch()


class StudioSkinIO(ui.SkinFormatIO):
    format_class = StudioSkin
    options_class = StudioOptions

    def import_weights(self, mode):
        paths = self.host.resolve_import_paths(mode)
        if not paths:
            return
        with self.host.undo_chunk("importStudioSkin"):
            ...


api.register_skin_format(StudioSkinIO)
```

Declare the settings your options read, so they have defaults:

```python
class StudioSkin(api.SkinFormat):
    ...
    def get_default_settings(self):
        return {"setting_studio_mirror": False}
```

### What an adapter may use

An adapter reaches the tab only through `self.host` (`wipskin.api.ui.Host`):

| Area | Host members |
|---|---|
| Session | `settings`, `parent_widget` (parent for your dialogs), `viewer` |
| Files list | `get_directory()`, `refresh_files()`, `select_files(names)`, `list_selected_names()`, `list_selected_paths()` |
| Tab options | `import_as_mode()`, `export_auto_naming()`, `export_version_number()`, `get_export_comment()`, `get_export_base_name(names)` |
| Viewer | `get_selected_viewer_file(msg)`, `clear_viewer(msg)`, `set_influence_list_chrome()`, `set_member_list_chrome()`; `viewer.set_header/set_meta/set_list_items/set_list_entries/...` |
| Plumbing | `resolve_import_paths(mode)`, `undo_chunk(name)`, `exporting_shapes(shapes)`, `is_node_in_scene(name)`, `select_existing_nodes(names, msg)` |

Overridable adapter hooks (all optional): `update_viewer`, `import_weights`,
`export_weights`, `list_scene_export_shapes`, `get_scene_export_note` and
`export_scene_weights` (the Files right-click "Export All Skins in Scene...";
the default runs `export_weights` once with every shape selected, and
`export_each_shape(shapes)` runs it per shape for flows that merge the
selection into one file), `rename_influence`, `rename_file`, `list_file_actions`
(Files right-click entries), `list_menu_actions` (Options menu entries; an
extension point that no bundled plugin uses at the moment),
`edit_selected_file`, `on_selector_changed`, `print_current_selection`.
The Import / Export buttons enable themselves when you override
`import_weights` / `export_weights`; set `supports_import` /
`supports_export` on the class to decide yourself.

`wipskin.api.maya.skin_engine` gives Level 3 adapters the same
`collect_skin_weights(node)` / `apply_skin_weights(node, data)` the shared
flow uses.

## 6. Package layout and import rules

Mirror WipSkin's own layering, as the bundled plugins do:

```
my_studio_skin/
    __init__.py      empty
    plugin.py        entry module: imports ui/adapter (if any) and registers
    constants.py     mode, settings keys, DEFAULT_SETTINGS     ┐ no Qt;
    format.py        your SkinFormat                           │ importable
    weights.py       the only module importing your file library┘ outside Maya
    ui/              (Level 3 only)
        __init__.py
        adapter.py   SkinFormatIO
        options.py   SkinFormatOptions
```

Rules (WipSkin's own tests enforce them on the bundled plugins and the
example):

- Import WipSkin **only** through `wipskin.api`, `wipskin.api.maya` and
  `wipskin.api.ui`. Everything else is internal and may change at any time.
- Keep Qt (`wipskin.api.ui`, PySide) inside `ui/`, so the format and codec
  stay testable without Maya's UI.
- Keep `__init__.py` empty and register in `plugin.py`, so importing
  `format.py` in a test registers nothing.
- Do not import heavy or optional libraries at module import time. Override
  `get_availability()` to report `api.Availability.NOT_INSTALLED` (a normal
  setup, no warning) or `MISSING_DEPENDENCY` (installed but broken, warned
  each time the window opens), and `get_unavailable_reason()` for the
  tooltip.

## 7. Testing your plugin

`wipskin.api.testing.SkinFormatContractTests` runs the checks registration
and the SkinWeight tab rely on. It needs no Maya:

```python
import unittest
from wipskin import api
from wipskin.api.testing import SkinFormatContractTests
from my_studio_skin.format import StudioSkin


class TestStudioSkinContract(SkinFormatContractTests, unittest.TestCase):
    format_class = StudioSkin

    def make_sample_data(self):      # enables the write/read round trip
        return api.SkinWeightData("body", ["hip", "knee"], [1, 0, 0.5, 0.5])
```

It checks the identity fields, extensions, registration (mode and settings
keys), declared defaults, availability, file listing and, with sample data,
that `write_weights` then `read_weights` gives the same weights back.
Scene-side behavior (binding, applying) needs Maya and is not covered.

## 8. Translating your plugin

WipSkin's window can show Japanese (Options > Language). The English text in
the code is the key, so a text with no translation simply stays English.

```python
# my_studio_skin/ui/adapter.py
from wipskin.api import tr

feedback.display_info(tr("Exported {count} file(s)", count=len(paths)))
```

- Wrap every text a user reads in `tr()`: labels, tooltips, dialog titles and
  messages. Use `{name}` fields for values rather than building the string
  with an f-string, so the translator can move them. `tr`'s first argument
  is positional only, so a field may even be called `source`.
- Do not wrap identifiers: settings keys, file extensions, file format names
  such as `.jSkin`.
- Put your translations beside your code and register the folder once, in
  your entry module:

```
my_studio_skin/
    plugin.py
    locales/
        ja.json          {"Exported {count} file(s)": "{count}個のファイルを書き出しました"}
```

```python
# my_studio_skin/plugin.py
import os
from wipskin import api

api.register_locales(os.path.join(os.path.dirname(__file__), "locales"))
```

- A catalog is a JSON object from the English text to its translation. A
  translation must keep the same `{fields}` as its source.
- Your catalog is merged with WipSkin's when a language loads; if two
  catalogs translate the same text, the one registered later wins. Texts
  WipSkin itself already translates (for example "Set a weight directory
  first.") need no entry of yours.
- The wording a format declares as class attributes (`viewer_title`,
  `viewer_selector_label`, `viewer_selector_tooltip`, `viewer_print_tooltip`,
  `viewer_meta_tooltip`) is passed through `tr()` by the tab, so translate
  those strings in your catalog too. Strings you build as class or module
  constants are evaluated once at import; pass them through `tr()` where
  they are shown.
- A language your plugin has no file for stays English; a catalog that
  cannot be read is skipped with a warning and never stops the window.
- Switching the language reopens the window, because every text is fixed
  when its widget is created.
- Run the same check WipSkin does on its own catalogs: every text passed to
  `tr("...")` has an entry, and no entry is left over. See
  `tests/test_i18n_coverage.py` for a template.

## 9. Format reference

`wipskin.api.SkinFormat` (alias of `SkinWeightFormat`):

| Member | Default | Purpose |
|---|---|---|
| `mode`, `label`, `extensions` | required | Identity and files |
| `viewer_title` | `"<label> Viewer"` | Viewer group title |
| `metadata_format` | `mode` | Sidecar `"format"`; `get_metadata_format(path)` per file |
| `export_auto_naming_setting` | generated key | Auto Naming checkbox setting |
| `pack_extensions` | `()` | Extensions tinted as packs in the Files list |
| `is_text_format` | `False` | Whether a text replace on the file is safe |
| `supports_temp_file`, `get_temp_file_path()` | `False`, `None` | Import / Export Temp buttons |
| `has_chunk_selector` and `viewer_selector_label`, `viewer_selector_tooltip`, `viewer_print_tooltip` | off | Viewer selector row and Print button |
| `viewer_meta_tooltip` | generic | Tooltip of the viewer's metadata box |
| `fallback_rank` | `100` | Where the tab lands when the saved format cannot run (lowest wins) |
| `get_availability()`, `get_unavailable_reason()` | available | Disable the format in this session |
| `get_default_settings()` | `{}` | Defaults for the settings keys you read |
| `describe(path)` | codec summary or empty | Viewer contents |
| `read_weights(path)`, `write_weights(path, data)` | not implemented | Level 2 codec |
| `list_files(directory)`, `get_file_predicate()` | by extension | Which files the Files list shows |
| `expand_file_names(directory, names)` | as-is | What Archive / Delete act on for a selection |
| `can_rename_influence(name)` | `False` | Allow the viewer's influence rename |
| `influence_node_types()` | any | Node types influences must be to count as present |
