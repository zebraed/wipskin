<p align="center">
  <img src="python/wipskin/ui/icons/wipskin.svg" alt="WipSkin" width="96">
</p>

# WipSkin

English | [日本語](README_JA.md)

A skin weight and deformer weight tool for Maya. Export and import skin weights and deformer weights (cluster, softMod, and others) as Maya XML from one window with a versioned file list.

mGear and ngSkinTools are supported as plugins. If they are installed in Maya, their files can be used as well.

## Description

WipSkin is a file browser for weight files, with Import / Export buttons to apply and save them.

- **SkinWeight**: skin weights as Maya deformerWeights XML (`.xml`), including WIP packs that split a skin into layers. If mGear or ngSkinTools is installed, the **Format** list also offers those formats (see [Optional formats](#optional-formats)).
- **DeformerWeight**: weights of non-skin deformers as XML.
- **Versioned files**: exports can be saved as `name.0001.ext`, `name.0002.ext`, and so on. The file list shows either every version or only the latest.
- **Viewer and comments**: select a file to see what it contains and which influences it uses, and attach a comment that is stored next to the file.
- **File management**: rename, archive, delete, and restore weight files without leaving the window.

## Requirements

| Item | Notes |
| --- | --- |
| **Maya** | 2023, 2024, 2025, 2026, or 2027. |
| **mGear** | Optional. mGear 4.x enables the mGear format. |
| **ngSkinTools** | Optional. ngSkinTools2 ships with Maya 2027 and enables the ngSkinTools format. On earlier Maya versions, install ngSkinTools2 separately. |
| **wipskin_native** | Optional. A Rust accelerator for XML. Used automatically when it loads (Python 3.10 or later, so not on Maya 2023); otherwise a pure Python path is used. |

XML and Deformer weights need nothing else. mGear and ngSkinTools are not required: a format whose package is missing is greyed out in the **Format** list, and its tooltip tells you what is missing.

## Installation

1. Copy this repository anywhere, for example `D:/tools/wipskin`.
2. Add its `python` folder to Maya's `PYTHONPATH`, for example in `Maya.env`.

   ```
   PYTHONPATH=D:/tools/wipskin/python
   ```

   Or add it for the current session only.

   ```python
   import sys
   sys.path.insert(0, r"D:/tools/wipskin/python")
   ```

## Usage

Open the window from the Script Editor (Python tab).

```python
import wipskin
wipskin.showUI()
```

The window can be docked. Opening it again closes the previous one. The window size, the options, the last directory, and the selected format are saved between sessions.

### The window

Both tabs share the same layout.

```
Weight Dir : [ path                       ] [set]
Format: [XML v]   Version View: (Full) (Latest)
+-----------+  +---------------------+
| Files     |  | Viewer: file info   |
|           |  |                     |
+-----------+  +---------------------+
| Influences|  | Comment             |
+-----------+  +---------------------+
[Import] [Export]
> Import Options
> Export Options
```

- **Weight Dir**: the folder that holds your weight files. Press **set** to browse, or type a path. Right-click the history icon next to it to pick a recent folder.
- **Version View**: **Latest** shows only the newest version of each file, **Full** shows all of them.
- **Files**: the weight files in that folder. Select one and press **Import** to apply it.
- **Viewer**: shows the contents of the selected file. Double-click an influence to select it in Maya, or press **select all** to select every listed influence that exists in the scene.
- **Comment**: a note for the selected file. Press **Update Comment** to save it without exporting again.
- **Import Options / Export Options**: collapsible panels. Their contents change with the selected format.

#### Files list right-click menu

| Entry | Description |
| --- | --- |
| **Export All Skins in Scene...** | (SkinWeight tab) Export every skinned mesh in the scene, one file per mesh named after it, with the current format and its Export options. A list of the meshes is shown for confirmation first. |
| **Rename** | Rename one file. Its comment moves with it. |
| **Generate Opposite Side...** | (XML format and DeformerWeight tab) Copy the selected files with a side string replaced, for example `_L` to `_R`, in both the file name and its content. |
| **Import** | Import the selected file. |
| **Archive** | Move the selected files to a `.backup` folder instead of deleting them. |
| **Delete** | Delete the selected files. |
| **Show Archives...** | Browse the archive folder to unarchive or permanently delete files. |
| **Open Directory** / **Refresh** | Open the folder in the file browser, or rescan it. |

For XML (and mGear) files, the influence list has **Rename Influence...** in its right-click menu. It is for fixing the influence names stored in a file after joints were renamed in the scene.

### SkinWeight

1. Select the mesh(es) in Maya. Importing and exporting work on the selected mesh hierarchy.
2. Press **Export**, choose a name, and the weights are written to the Weight Dir. Or select a file in the list and press **Import**.

**import as**: **saved shape** applies a file to the mesh it was exported from; **selected shape** applies it to the mesh you selected, whatever its name.

**Export Options** common to all formats:

- **auto naming**: use the selected mesh name (or the scene name for several meshes) as the file name.
- **version number**: append a four-digit version, `name.0001.ext`.

#### XML

Maya's deformerWeights XML.

| Import option | Description |
| --- | --- |
| **method** | How weights are matched when the mesh does not match 1:1: `index`, `nearest`, `bilinear`, `barycentric`, or `over`. |
| **mode** | **replace** overwrites the weights; **add** adds to the current weights. |
| **Ignore names** | Match influences by order instead of by name. |
| **Normalize weights** | Normalize the skinCluster after import. |
| **Restore BindPreMatrix** | Restore the bind pose saved in the file. |

| Export option | Description |
| --- | --- |
| **optimize** | Prune small weights and remove unused influences. |
| **Save BindPreMatrix** | Save the bind pose of each influence, for **Restore BindPreMatrix** later. |
| **Export as WIP Skin** | Export a WIP pack instead of a single file. A dialog opens where you drag influences into named groups. The pack holds a **Base** and one **Layer** per group, so skin work can be split into separate files. |

#### Optional formats

These can be chosen in the **Format** list only when their package is installed. You can ignore them if you work with XML.

##### mGear

Needs mGear 4.x. It handles `.jSkin` / `.gSkin` files and `.gSkinPack` packs (a list of member files). Selecting a pack and pressing Import imports every member in it.

| Import option | Description |
| --- | --- |
| **Import .gSkinPack Version** | Which version of the pack's member files to import. **Latest** uses the newest version of each member file found in the Weight Dir; **Recorded** uses the exact file names stored in the pack. The members shown in the viewer follow this choice too. |

| Export option | Description |
| --- | --- |
| **format** | Write members as `.jSkin` (JSON) or `.gSkin`. |
| **Export as .gSkinPack** | Export all selected meshes as one pack (`.gSkinPack`). The member file type is set by **format** above. |

With a pack selected, double-click it or use the right-click menu to open a pack editor. For each member, choose whether to keep the recorded file, point it at the latest version, or export it again from the scene. The pack is saved as a new version.

##### ngSkinTools

The `.json` format of ngSkinTools2 layers. It exports and imports the layers stacked on a skinCluster, not the weights themselves. The destination mesh needs a skinCluster, so bind it first with XML, mGear, or another format.

Export covers only meshes that have ngSkinTools layers enabled, including **Export All Skins in Scene...** in the Files list. File names get `_ngSkintools` after the transform name, for example `body_ngSkintools.0001.json`. The viewer shows the layer count, the vertex count, the layer names, and the influences used.

| Import option | Description |
| --- | --- |
| **Vertex Transfer** | How the file's vertices are matched to the destination mesh. **Vertex ID** matches by vertex index (for identical meshes). **Closest Surface Point** matches each vertex to the closest point on the exported mesh. **UV Space** does the same in UV space. |
| **Add Missing Influences** | Before importing, add the file's influences that the skinCluster lacks, at weight 0. Influences missing from the scene are skipped. On by default. |
| **Replace Existing Layers** | Before importing, delete the layers the skinCluster already has. With **Choose Layers on Import** on, only the existing layers named like a chosen layer are replaced. Off adds the file's layers on top of the existing ones. On by default. |
| **Choose Layers on Import** | Ask which of the file's layers to import, file by file. Canceling the dialog stops the remaining files. On by default. |

The Export options are only the two shared by all formats.

### DeformerWeight

Exports and imports weights of cluster, softMod, and other deformers as XML.

1. Select the deformed geometry and press **Update deformer list**.
2. Select the deformer(s) in the left list. Optionally select shapes in **Deformed shapes** to export only those.
3. Press **Export**. Each shape is written to its own file, named `shape_deformer.xml`.
4. To restore, select a file and press **Import**.

Import options are **import as**, **method**, and **Ignore names**, with the same meaning as in XML. Export options are **auto naming** and **version number**.

### Options

| Menu | Description |
| --- | --- |
| **Options > Language** | Switch the window between English and Japanese. The window reopens. |
| **Help > About...** | Version and author. |

Every Import / Export option has **Reset To Default** in its right-click menu.

### Script

The window is the main interface. These are available from Python.

```python
import wipskin

wipskin.showUI()    # open the window
wipskin.Reload()    # development: reload the package, then call showUI() again
```

## Development

```bash
python -m pytest tests -q
```

Tests that need Maya are skipped outside Maya. `Reload()` re-imports the `wipskin` package and any plugin that registered a format. After replacing `python/wipskin/_native/wipskin_native.pyd`, restart Maya. Set `WIPSKIN_NO_NATIVE=1` to force the pure Python path.

## Adding a format

A skin weight format can be added as a plugin, without editing WipSkin. The smallest plugin is a few lines: name the format and its file extension, and its files are listed, versioned, renamed, and shown in the viewer. Add a reader and a writer and Import / Export work too.

```python
from wipskin import api


class StudioSkin(api.SkinFormat):
    mode = "studioskin"
    label = "Studio Skin"
    extensions = ("sskin",)


api.register_skin_format(StudioSkin)
```

Put the module on `PYTHONPATH` and set `WIPSKIN_PLUGINS=my_module` (several modules are separated like `PATH` entries) before `wipskin.showUI()`. See [docs/PLUGINS.md](docs/PLUGINS.md) for the guide, and [examples/plugins](examples/plugins/wipskin_jsonskin) for a working example. mGear and ngSkinTools are built the same way (`python/wipskin/plugins`).

## License

[MIT License](LICENSE)
