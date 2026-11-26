"""
Profile where skin-weight export/import time actually goes — RUN INSIDE MAYA.

Select one skinned mesh, then run this in the Script Editor (Python tab).
It times, on the SAME skinCluster:

  Export side
    - cmds.deformerWeights(export=True)         : Maya's XML writer (current path)
    - MFnSkinCluster.getWeights (bulk API)       : raw weight read, no XML
    - ET.parse of the written file               : pure-Python parse cost
    - xml_skin._build_weight_matrix_from_xml     : XML -> weight matrix (Phase 3
                                                    wipskin helper; Maya-free)

  Import side
    - cmds.deformerWeights(im=True)              : Maya's XML reader+apply (old path)
    - xml_skin._bulk_apply_index_weights         : Phase 3 wipskin bulk-API import
                                                    path (parse + matrix build +
                                                    MFnSkinCluster.setWeights, the
                                                    ACTUAL code import_skin now runs
                                                    for method="index")
    - MFnSkinCluster.setWeights (raw bulk API)   : floor reference, no XML at all
    - cmds.skinCluster(forceNormalizeWeights)

  Correctness check
    - Compares the weights applied via cmds.deformerWeights(im=True) against
      the weights applied via xml_skin._bulk_apply_index_weights (both
      followed by the same forceNormalizeWeights pass) and reports the max
      absolute difference. Should be ~0 (floating point noise only).

Read the numbers like this:
  * If cmds.deformerWeights >> getWeights/setWeights, the Maya command layer is
    the bottleneck -> the wipskin bulk API path fixes it, no C++ needed for
    the weight I/O itself.
  * If ET.parse / _build_weight_matrix_from_xml are large relative to
    _bulk_apply_index_weights's total, the Python XML parse is a real cost ->
    a Maya-free C++/Rust parser would help there.
  * getWeights/setWeights are the floor: no rewrite can beat them.
"""

import os
import sys
import tempfile
import time

from maya import cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

try:
    import xml.etree.ElementTree as ET
except ImportError:
    ET = None


def _import_xml_skin():
    """
    Best-effort import of wipskin.xml_skin so this script can profile/verify
    the actual Phase 3 bulk-import code, not just a reimplementation of it.
    Falls back to None (raw-API-only profiling) if wipskin isn't importable
    from this Maya session's sys.path.
    """
    try:
        from wipskin.formats import xml_skin
        return xml_skin
    except ImportError:
        pass
    # Fall back to the repo layout: this file lives in <repo>/scripts/, and
    # wipskin is imported as "wipskin" from <repo>/python on sys.path
    # (see README.md's Maya setup snippet).
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return None
    repo_root = os.path.normpath(os.path.join(script_dir, ".."))
    parent = os.path.join(repo_root, "python")
    if parent not in sys.path:
        sys.path.insert(0, parent)
    try:
        from wipskin.formats import xml_skin
        return xml_skin
    except ImportError:
        return None


xml_skin = _import_xml_skin()


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


def _selected_mesh_shape():
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        raise RuntimeError("Select a skinned mesh first.")
    node = sel[0]
    if cmds.nodeType(node) == "mesh":
        return node
    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                fullPath=True, type="mesh") or []
    if not shapes:
        raise RuntimeError("Selection has no polygon mesh shape.")
    return shapes[0]


def _skin_cluster(shape):
    for hist in (cmds.listHistory(shape, pruneDagObjects=True) or []):
        if cmds.nodeType(hist) == "skinCluster":
            return hist
    raise RuntimeError("No skinCluster found on the selected mesh.")


def _all_vert_component(shape_dag):
    mesh_fn = om2.MFnMesh(shape_dag)
    comp_fn = om2.MFnSingleIndexedComponent()
    comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(mesh_fn.numVertices)))
    return comp, mesh_fn.numVertices


def _max_abs_diff(a, b):
    return max(abs(x - y) for x, y in zip(a, b)) if len(a) == len(b) else float("inf")


def profile():
    shape = _selected_mesh_shape()
    skc = _skin_cluster(shape)

    # Resolve API handles.
    sel = om2.MSelectionList()
    sel.add(shape)
    shape_dag = sel.getDagPath(0)
    sel2 = om2.MSelectionList()
    sel2.add(skc)
    skc_fn = oma2.MFnSkinCluster(sel2.getDependNode(0))

    comp, num_verts = _all_vert_component(shape_dag)
    influences = cmds.skinCluster(skc, query=True, influence=True) or []
    num_inf = len(influences)

    print("=" * 66)
    print("Skin IO profile")
    print("  mesh shape     :", shape.rsplit("|", 1)[-1])
    print("  skinCluster    :", skc)
    print("  vertices       :", num_verts)
    print("  influences     :", num_inf)
    print("  wipskin xml_skin importable:", xml_skin is not None)
    print("=" * 66)

    tmp_dir = tempfile.mkdtemp(prefix="wipskin_prof_")
    file_name = "profile_skin.xml"
    file_path = os.path.join(tmp_dir, file_name)

    print("\n[EXPORT]")
    with step("cmds.deformerWeights(export=True)"):
        cmds.deformerWeights(
            file_name, export=True, deformer=skc, path=tmp_dir,
            weightPrecision=6, defaultValue=-1.0,
        )
    size_mb = os.path.getsize(file_path) / (1024.0 * 1024.0)
    print("  -> file size: %.1f MB" % size_mb)

    original_weights = None
    with step("MFnSkinCluster.getWeights (bulk API, raw floor)"):
        original_weights, got_inf = skc_fn.getWeights(shape_dag, comp)
    print("  -> weight values: %d (verts x influences)" % len(original_weights))

    root = None
    if ET is not None:
        with step("ET.parse of exported file (pure Python)"):
            root = ET.parse(file_path).getroot()

    scene_influences = [
        path.partialPathName() for path in skc_fn.influenceObjects()
    ]

    if xml_skin is not None and root is not None:
        with step("xml_skin._build_weight_matrix_from_xml (Python fallback)"):
            xml_skin._build_weight_matrix_from_xml(
                root, scene_influences, num_verts
            )

    try:
        from wipskin.formats import xml_accel
    except ImportError:
        xml_accel = None
    if xml_accel is not None:
        print("  wipskin_native available:", xml_accel.native_available())
        if xml_accel.native_available():
            with step("xml_accel.native_build_weight_matrix (Rust)"):
                xml_accel.native_build_weight_matrix(
                    file_path, scene_influences, num_verts
                )

    print("\n[IMPORT]")
    with step("cmds.deformerWeights(im=True)  [old path]"):
        cmds.deformerWeights(
            file_name, im=True, method="index", deformer=skc,
            path=tmp_dir, shape=shape,
        )
    with step("cmds.skinCluster(forceNormalizeWeights=True)"):
        cmds.skinCluster(skc, edit=True, forceNormalizeWeights=True)
    weights_via_cmds, _ = skc_fn.getWeights(shape_dag, comp)

    if xml_skin is not None:
        with step("xml_skin._bulk_apply_index_weights  [NEW wipskin path]"):
            # Passing file_path (not a pre-parsed root) lets this use the
            # native Rust parser when available -- see xml_accel.py.
            xml_skin._bulk_apply_index_weights(shape, skc, file_path)
        with step("cmds.skinCluster(forceNormalizeWeights=True)"):
            cmds.skinCluster(skc, edit=True, forceNormalizeWeights=True)
        weights_via_bulk, _ = skc_fn.getWeights(shape_dag, comp)

        diff = _max_abs_diff(list(weights_via_cmds), list(weights_via_bulk))
        print("\n[CORRECTNESS CHECK]")
        print("  max |cmds.deformerWeights result - wipskin bulk result| = %.8f"
              % diff)
        print("  (should be ~0; floating point noise only)")
    else:
        print("\n  wipskin not importable from this Maya session -- skipped "
              "_bulk_apply_index_weights profiling and the correctness check. "
              "Add the repo's python/ directory to sys.path first (see README).")

    with step("MFnSkinCluster.setWeights (bulk API, raw floor)"):
        inf_indices = om2.MIntArray(list(range(got_inf)))
        skc_fn.setWeights(shape_dag, comp, inf_indices, original_weights, False)
    cmds.skinCluster(skc, edit=True, forceNormalizeWeights=True)

    print("\nTemp file:", file_path)
    print("(delete the temp folder when done)")
    print("(original weights restored on the skinCluster)")


if __name__ == "__main__" or True:
    profile()
