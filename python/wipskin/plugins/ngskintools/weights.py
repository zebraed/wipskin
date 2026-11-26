"""Adapter between WipSkin and the optional ngSkinTools2 package.

Maya 2027 ships ngSkinTools2 (``plug-ins/ngSkinTools``); on Maya 2026 it is a
separate install. This is the only WipSkin module that imports
``ngSkinTools2``. Importing this module never imports it (or Maya):
ngSkinTools2 initializes ``maya.standalone`` when imported outside Maya, so it
is loaded on first use only.
"""

from __future__ import annotations

import importlib.util
import os

from wipskin.plugins.ngskintools import layer_file

#: Layer file extension. ``.json.gz`` is not supported: versioned names need a one-part extension.
EXT = "json"
#: Sidecar "format" value for ngSkinTools layer files.
METADATA_FORMAT = "ngskintools"
PACKAGE_NAME = "ngSkinTools2"


def is_available() -> bool:
    """True when the ngSkinTools2 package is on sys.path (not imported)."""
    return importlib.util.find_spec(PACKAGE_NAME) is not None


def load_ngskintools():
    """Load the ngSkinTools2 plugin and return its ``api`` module.

    Returns:
        module: ``ngSkinTools2.api``.

    Raises:
        ImportError: ngSkinTools2 is not installed.
        RuntimeError: The ngSkinTools2 plugin could not be loaded.
    """
    if not is_available():
        raise ImportError(f"{PACKAGE_NAME} is not installed.")

    from ngSkinTools2 import api
    from ngSkinTools2.api import plugin

    plugin.load_plugin()
    if not plugin.is_plugin_loaded():
        raise RuntimeError(f"Failed to load the {PACKAGE_NAME} plugin.")

    return api


def get_skin_cluster(node):
    """skinCluster that ngSkinTools resolves for a mesh (or skinCluster) node.

    Args:
        node (str): Shape, transform or skinCluster name.

    Returns:
        str | None: The skinCluster, or None when node is not skinned.
    """
    skin_cluster = load_ngskintools().get_related_skin_cluster(node)
    if not skin_cluster:
        return None

    return skin_cluster


def has_layers(skin_cluster) -> bool:
    """True when ngSkinTools layers are enabled on skin_cluster."""
    return bool(load_ngskintools().get_layers_enabled(skin_cluster))


def export_layers(skin_cluster, path):
    """Write the layers of skin_cluster to path through a temporary file.

    Args:
        skin_cluster (str): skinCluster with layers enabled.
        path (str): Destination ``.json`` path.
    """
    api = load_ngskintools()
    temp_path = f"{path}.tmp"
    try:
        api.export_json(skin_cluster, temp_path)
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)

        raise


def import_layers(
    skin_cluster,
    path,
    transfer_mode,
    influence_paths=(),
    replace_existing=False,
    keep_layer_ids=None,
    replace_same_names=False,
):
    """Add the layers in path to skin_cluster, on top of the existing ones or in their place.

    Args:
        skin_cluster (str): Destination skinCluster (see get_skin_cluster).
        path (str): Layer ``.json`` path.
        transfer_mode (str): One of the TRANSFER_* values in constants.
        influence_paths (iterable): Influences from the file to add to
            skin_cluster first with weight 0; those missing from the scene are skipped.
        replace_existing (bool): Delete the layers skin_cluster already has
            before importing. Do it inside one undo chunk: the import can
            still fail after the layers are gone.
        keep_layer_ids (iterable | None): Ids (LayerEntry.id) of the file's
            layers to keep. The others are deleted again right after the
            import, with their child layers. None keeps every layer.
        replace_same_names (bool): Delete only the layers skin_cluster
            already has under the same name as a layer being imported (the
            kept ones, with keep_layer_ids). Other layers stay. Ignored when
            replace_existing is set.

    Raises:
        ValueError: path is not an ngSkinTools layer file (checked before
            anything is deleted), or the imported layers cannot be paired
            with the file's when keep_layer_ids is given.
    """
    from maya import cmds

    summary = layer_file.read_layer_file(path)
    api = load_ngskintools()
    influence_paths = list(influence_paths)
    present = cmds.ls(influence_paths, long=True, type="joint") if influence_paths else []
    if present:
        api.add_influences(present, skin_cluster)

    if replace_existing:
        api.init_layers(skin_cluster).clear()
    elif replace_same_names:
        names = {
            entry.name for entry in summary.layers
            if keep_layer_ids is None or entry.id in keep_layer_ids
        }
        _delete_layers_named(api, skin_cluster, names)

    known_ids = set()
    if keep_layer_ids is not None:
        known_ids = {layer.id for layer in api.init_layers(skin_cluster).list()}

    api.import_json(skin_cluster, file=path, vertex_transfer_mode=transfer_mode)
    if keep_layer_ids is not None:
        _delete_unselected_layers(
            api, skin_cluster, summary.layers, set(keep_layer_ids), known_ids,
        )


def notify_layers_changed():
    """Make an open ngSkinTools window re-read the layers of its target.

    The window re-reads layers only on selection change, undo/redo, or its own
    operations. Layers added or deleted through the API stay listed with stale
    ids until then, and picking one fails in ``ngst2Layers -currentLayer``.
    Does nothing when no ngSkinTools window is open.
    """
    if not is_available():
        return

    from ngSkinTools2.api.session import session

    if not session.active():
        return

    events = session.events
    events.targetChanged.emitIfChanged()
    events.layerListChanged.emitIfChanged()
    events.currentLayerChanged.emitIfChanged()


def _delete_layers_named(api, skin_cluster, names):
    layers = api.init_layers(skin_cluster)
    doomed = [layer for layer in layers.list() if layer.name in names]
    doomed_ids = {layer.id for layer in doomed}
    for layer in doomed:
        # Deleting a group takes its children with it.
        if layer.parent_id not in doomed_ids:
            layers.delete(layer)


def _delete_unselected_layers(api, skin_cluster, file_layers, keep_ids, known_ids):
    layers = api.Layers(skin_cluster)
    imported = [layer for layer in layers.list() if layer.id not in known_ids]
    matched = layer_file.match_imported_layers(file_layers, imported)
    doomed = [
        layer for file_id, layer in matched.items() if file_id not in keep_ids
    ]
    doomed_ids = {layer.id for layer in doomed}
    for layer in doomed:
        # Deleting a group takes its children with it.
        if layer.parent_id not in doomed_ids:
            layers.delete(layer)
