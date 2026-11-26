"""Reader of the ngSkinTools layer JSON (``export_json`` output), without ngSkinTools2 or Maya.

Only the keys the viewer and the file filter need are read. Everything else
in the file is ignored, so a newer ngSkinTools2 that adds keys keeps working.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from wipskin.api import file_cache


@dataclass(frozen=True)
class LayerEntry:
    """One layer recorded in a layer file.

    Attributes:
        id (int): Layer id inside the file.
        name (str): Layer name.
        parent_id (int | None): Id of the group layer holding it; None at the top.
        index (int): Position among its siblings (the highest is drawn on top).
    """

    id: int
    name: str
    parent_id: int | None = None
    index: int = 0


@dataclass(frozen=True)
class LayerFileSummary:
    """What the viewer shows for one ngSkinTools layer file.

    Attributes:
        vertex_count (int | None): Vertex count of the exported mesh, when recorded.
        layer_names (list): Layer names in file order.
        layers (list): LayerEntry per layer, in file order.
        influences (list): Influence long paths (or names when no path is recorded).
    """

    vertex_count: int | None = None
    layer_names: list = field(default_factory=list)
    layers: list = field(default_factory=list)
    influences: list = field(default_factory=list)


def _get_vertex_count(data: dict) -> int | None:
    mesh = data.get("mesh")
    if not isinstance(mesh, dict):
        return None

    positions = mesh.get("vertPositions")
    if not isinstance(positions, list):
        return None

    return len(positions) // 3


def _get_int(data, key: str, default):
    value = data.get(key) if isinstance(data, dict) else None
    if isinstance(value, int) and not isinstance(value, bool):
        return value

    return default


def _get_layer_entry(layer, position: int) -> LayerEntry:
    name = layer.get("name") if isinstance(layer, dict) else None
    if not isinstance(name, str):
        name = f"Layer {position + 1}"

    return LayerEntry(
        id=_get_int(layer, "id", position + 1),
        name=name,
        parent_id=_get_int(layer, "parentId", None),
        index=_get_int(layer, "index", position),
    )


def match_imported_layers(file_layers, imported_layers) -> dict:
    """Pair each layer of a file with the layer its import created.

    Import keeps the hierarchy and the order among siblings, but gives new
    ids, and other layers may already sit next to them. So the two trees are
    walked together, siblings sorted by index.

    Args:
        file_layers (iterable): LayerEntry of the file.
        imported_layers (iterable): Objects with ``id``, ``name``,
            ``parent_id`` and ``index``: only the layers the import created
            (ngSkinTools2 ``Layer`` objects fit).

    Returns:
        dict: File layer id -> imported layer.

    Raises:
        ValueError: The trees differ in shape or in a layer name.
    """
    file_layers = list(file_layers)
    imported_layers = list(imported_layers)
    matched = {}

    def walk(file_parent_id, imported_parent_id):
        file_siblings = sorted(
            (entry for entry in file_layers if entry.parent_id == file_parent_id),
            key=lambda entry: entry.index,
        )
        imported_siblings = sorted(
            (layer for layer in imported_layers if layer.parent_id == imported_parent_id),
            key=lambda layer: layer.index,
        )
        if len(file_siblings) != len(imported_siblings):
            raise ValueError("Imported layers do not match the layers in the file")

        for entry, layer in zip(file_siblings, imported_siblings):
            if entry.name != layer.name:
                raise ValueError(
                    f"Imported layer '{layer.name}' does not match '{entry.name}' in the file"
                )

            matched[entry.id] = layer
            walk(entry.id, layer.id)

    walk(None, None)
    return matched


def _get_influence_name(influence) -> str | None:
    if isinstance(influence, str):
        return influence

    if isinstance(influence, dict):
        for key in ("path", "name"):
            value = influence.get(key)
            if isinstance(value, str) and value:
                return value

    return None


def list_display_names(influence_paths) -> list:
    """Short names for the viewer; the full path only where two share a short name.

    Args:
        influence_paths (iterable): Influence long paths (or plain names).

    Returns:
        list: One display name per path, in the same order.
    """
    influence_paths = list(influence_paths)
    leaves = [path.rsplit("|", 1)[-1] for path in influence_paths]
    counts = Counter(leaves)
    return [
        path if counts[leaf] > 1 else leaf
        for path, leaf in zip(influence_paths, leaves)
    ]


def _parse_layer_file(path: str) -> LayerFileSummary:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("Not an ngSkinTools layer file: top level is not an object")

    layers = data.get("layers")
    influences = data.get("influences")
    if not isinstance(layers, list) or not isinstance(influences, list):
        raise ValueError("Not an ngSkinTools layer file: 'layers' / 'influences' missing")

    names = [_get_influence_name(influence) for influence in influences]
    entries = [_get_layer_entry(layer, position) for position, layer in enumerate(layers)]
    return LayerFileSummary(
        vertex_count=_get_vertex_count(data),
        layer_names=[entry.name for entry in entries],
        layers=entries,
        influences=[name for name in names if name is not None],
    )


def read_layer_file(path: str) -> LayerFileSummary:
    """Summarize an ngSkinTools layer file (cached while its mtime and size are unchanged).

    Args:
        path (str): Layer JSON path.

    Returns:
        LayerFileSummary: Layers and influences recorded in the file.

    Raises:
        OSError: The file cannot be read.
        ValueError: The file is not JSON or not an ngSkinTools layer file.
    """
    return file_cache.memoize_by_stat(path, _parse_layer_file)


def is_layer_file(path: str) -> bool:
    """True when path is an ngSkinTools layer JSON (other ``.json`` files are not)."""
    try:
        read_layer_file(path)
    except (OSError, ValueError):
        return False

    return True
