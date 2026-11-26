"""
Profile where deformer-weight export/import time actually goes — RUN INSIDE
MAYA. Companion to profile_skin_io.py, but for wipskin's *deformer* weight
IO (cluster/softMod/wrap/etc via deformer.py).

Both export_deformer_weight and import_deformer_weight now try a bulk path
first (Rust-native XML I/O + MFnMesh.getPoints / cmds.setAttr bulk write,
Phase 3B) and fall back to the old ET-based / cmds.deformerWeights path only
when the bulk path isn't applicable (non-mesh geometry, non-"index" import
method, ignore_names, etc). This script always calls the real
export_deformer_weight/import_deformer_weight entry points, so it measures
whichever path actually ran -- the step labels describe what the *old* path
used to do; read the printed ms against the plan file's Phase 3B numbers to
tell which path was taken.

Note: MFnWeightGeometryFilter (the generic geometryFilter weight API used by
cluster/softMod/wrap/etc, as opposed to MFnSkinCluster) has getWeights()
*and* a bulk-capable setWeight() -- despite the singular name, the
setWeight(path, components, values) overload takes a values array parallel
to components, so it IS the OpenMaya bulk-write floor for import (the
earlier version of this script called the nonexistent plural setWeights()
and crashed here). _bulk_apply_deformer_weights uses cmds.setAttr instead
of this because it already has the weights as a flat list from the native
XML reader and avoids building an MFnSingleIndexedComponent; compare this
step's ms against cmds.setAttr's floor (scripts/probe_deformer_weight_setattr.py)
to see whether that choice still holds.

  Export side
    - deformer.export_deformer_weight_for_shape(...) : the ACTUAL wipskin
                                                    single-shape export path
                                                    (bulk-first, Phase 3C)
    - MFnMesh.getPoints (bulk API)               : raw position read, floor
    - MFnWeightGeometryFilter.getWeights         : raw weight read, floor
                                                    (if the deformer supports it)
    - ET.parse of the written file               : pure-Python re-parse cost

  Import side
    - deformer.import_deformer_weight(...)       : the ACTUAL wipskin import
                                                    path (bulk-first)
    - MFnWeightGeometryFilter.setWeight          : raw weight apply, floor
                                                    (if the deformer supports it)
"""

import os
import sys
import tempfile
import time

from maya import cmds
import maya.api.OpenMaya as om2

try:
    import maya.api.OpenMayaAnim as oma2
except ImportError:
    oma2 = None

try:
    import xml.etree.ElementTree as ET
except ImportError:
    ET = None


def _import_deformer_module():
    """
    Best-effort import of wipskin.deformer so this script profiles the
    ACTUAL export_deformer_weight/import_deformer_weight code, not a
    reimplementation of it.
    """
    try:
        from wipskin.formats import deformer
        return deformer
    except ImportError:
        pass
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return None
    repo_root = os.path.normpath(os.path.join(script_dir, ".."))
    parent = os.path.join(repo_root, "python")
    if parent not in sys.path:
        sys.path.insert(0, parent)
    try:
        from wipskin.formats import deformer
        return deformer
    except ImportError:
        return None


deformer_module = _import_deformer_module()


class step:
    """Context manager printing the elapsed time of a block."""

    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        ms = (time.perf_counter() - self.t0) * 1000.0
        print("  %-46s %10.1f ms" % (self.label, ms))
        return False


def _selected_deformed_shape():
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        raise RuntimeError("Select a deformed mesh (or its transform) first.")
    node = sel[0]
    if cmds.nodeType(node) == "mesh":
        return node
    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                fullPath=True, type="mesh") or []
    if not shapes:
        raise RuntimeError("Selection has no polygon mesh shape.")
    return shapes[0]


def _first_deformer(shape):
    """Any non-skinCluster geometryFilter in the shape's history."""
    for hist in (cmds.listHistory(shape, pruneDagObjects=True) or []):
        if not cmds.objectType(hist, isa="geometryFilter"):
            continue
        node_type = cmds.nodeType(hist)
        if node_type in ("tweak", "skinCluster"):
            continue
        return hist, node_type
    raise RuntimeError(
        "No non-skinCluster deformer (cluster/softMod/wrap/...) found in "
        "the selection's history."
    )


def profile():
    if deformer_module is None:
        raise RuntimeError(
            "Could not import wipskin.formats.deformer -- add the repo's "
            "python/ directory to sys.path first (see README)."
        )

    shape = _selected_deformed_shape()
    deformer_name, deformer_type = _first_deformer(shape)

    sel = om2.MSelectionList()
    sel.add(shape)
    shape_dag = sel.getDagPath(0)
    mesh_fn = om2.MFnMesh(shape_dag)
    num_verts = mesh_fn.numVertices

    print("=" * 66)
    print("Deformer IO profile")
    print("  mesh shape     :", shape.rsplit("|", 1)[-1])
    print("  deformer       :", deformer_name, "(%s)" % deformer_type)
    print("  vertices       :", num_verts)
    print("  wipskin.deformer importable:", deformer_module is not None)
    print("=" * 66)

    tmp_dir = tempfile.mkdtemp(prefix="wipskin_deformer_prof_")

    print("\n[EXPORT]")
    # export_deformer_weight_for_shape (not export_deformer_weight) -- Phase
    # 3C moved to one file per shape, so export_deformer_weight now returns
    # a list of paths (one per shape on the deformer). This script profiles
    # exactly the selected shape, so it calls the single-shape entry point
    # directly instead of picking one element out of that list.
    with step("deformer.export_deformer_weight_for_shape (wipskin, bulk-first)"):
        full_path = deformer_module.export_deformer_weight_for_shape(
            deformer_name, shape, tmp_dir, auto_name=True,
        )
    size_mb = os.path.getsize(full_path) / (1024.0 * 1024.0)
    file_name = os.path.basename(full_path)
    print("  -> file: %s (%.2f MB)" % (file_name, size_mb))

    with step("MFnMesh.getPoints (bulk API, raw floor)"):
        mesh_fn.getPoints(om2.MSpace.kWorld)

    weight_filter_fn = None
    if oma2 is not None:
        try:
            wf_sel = om2.MSelectionList()
            wf_sel.add(deformer_name)
            weight_filter_fn = oma2.MFnWeightGeometryFilter(
                wf_sel.getDependNode(0)
            )
            comp_fn = om2.MFnSingleIndexedComponent()
            component = comp_fn.create(om2.MFn.kMeshVertComponent)
            comp_fn.addElements(list(range(num_verts)))
            with step("MFnWeightGeometryFilter.getWeights (bulk API, raw floor)"):
                original_weights = weight_filter_fn.getWeights(shape_dag, component)
            print("  -> weight values: %d" % len(original_weights))
        except RuntimeError as exc:
            print("  MFnWeightGeometryFilter not usable on this deformer:", exc)
            weight_filter_fn = None

    root = None
    if ET is not None:
        with step("ET.parse of exported file (pure Python)"):
            root = ET.parse(full_path).getroot()
        if root is not None:
            point_count = sum(
                1 for el in root.iter() if el.tag == "point"
            )
            print("  -> <point> elements in file: %d" % point_count)

    print("\n[IMPORT]")
    with step("deformer.import_deformer_weight (wipskin, bulk-first)"):
        deformer_module.import_deformer_weight(
            tmp_dir, file_name, method="index", import_as="saved",
        )

    if weight_filter_fn is not None:
        with step("MFnWeightGeometryFilter.setWeight (bulk API, raw floor)"):
            weight_filter_fn.setWeight(shape_dag, component, original_weights)

    print("\nTemp file:", full_path)
    print("(delete the temp folder when done)")


if __name__ == "__main__" or True:
    profile()
