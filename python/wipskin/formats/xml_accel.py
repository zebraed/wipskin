"""Dispatch point for the optional wipskin_native (Rust) accelerator."""

from __future__ import annotations

import os
import sys


def _load_native():
    """Best-effort load of wipskin_native from _native/. None on any failure."""
    if os.environ.get("WIPSKIN_NO_NATIVE") == "1":
        return None
    # _native/ lives at the wipskin package root (python/wipskin/_native/),
    # one level up from this module's own package (formats/).
    native_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_native"
    )
    # insert(0), not append: a stale wipskin_native earlier on sys.path
    # must not shadow this repo's build.
    if native_dir in sys.path:
        sys.path.remove(native_dir)
    sys.path.insert(0, native_dir)
    try:
        import wipskin_native
        return wipskin_native
    except Exception:
        pass


_native = _load_native()


def native_available():
    """True when the Rust accelerator loaded successfully."""
    return _native is not None


def native_build_weight_matrix(path, scene_influences, num_verts):
    """Native skin-XML weight-matrix builder (streaming, no ElementTree DOM).

    Returns:
        list | None: The flat row-major matrix, or None when native is
            unavailable / fails (callers must fall back).
    """
    if _native is None:
        return None
    try:
        return _native.build_weight_matrix(path, list(scene_influences), num_verts)
    except Exception:
        return None


def native_write_skin_xml(
    path,
    file_name,
    world_matrix,
    deformer_name,
    deformer_type,
    attributes,
    shape_name,
    group,
    positions,
    influence_names,
    weight_matrix,
    default_value,
    tolerance,
    polygon_counts=(),
    polygon_connects=(),
):
    """Native streaming skin-XML writer (Maya deformerWeights-compatible).

    Returns:
        bool: False only when native is unavailable. Mid-write errors propagate.
    """
    if _native is None:
        return False

    _native.write_skin_xml(
        path,
        file_name,
        list(world_matrix),
        deformer_name,
        deformer_type,
        list(attributes),
        shape_name,
        group,
        list(positions),
        list(influence_names),
        list(weight_matrix),
        default_value,
        tolerance,
        list(polygon_counts),
        list(polygon_connects),
    )
    return True


def native_read_deformer_weights(path, shape_name, num_verts):
    """Native deformer-weight reader for shape_name's <weights> block.

    Returns:
        list | None: The weight list, or None when native is unavailable / fails.
    """
    if _native is None:
        return None
    try:
        return _native.read_deformer_weights(path, shape_name, num_verts)
    except Exception:
        return None


def native_write_deformer_weight_xml(
    path,
    file_name,
    deformer_name,
    shape_names,
    world_matrices,
    positions_list,
    polygon_counts_list,
    polygon_connects_list,
    weights_list,
):
    """Native customDeformerWeight XML writer (weightList-based deformers;
    not blendShape). Every *_list must match shape_names order.

    Returns:
        bool: False only when native is unavailable. Mid-write errors propagate.
    """
    if _native is None:
        return False

    _native.write_deformer_weight_xml(
        path,
        file_name,
        deformer_name,
        list(shape_names),
        [list(m) for m in world_matrices],
        [list(p) for p in positions_list],
        [list(c) for c in polygon_counts_list],
        [list(c) for c in polygon_connects_list],
        [list(w) for w in weights_list],
    )
    return True
