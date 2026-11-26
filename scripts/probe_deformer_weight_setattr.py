"""
Probe how to bulk-write deformer weights via cmds.setAttr — RUN INSIDE MAYA.

MFnWeightGeometryFilter (maya.api.OpenMayaAnim) has getWeights() but not a
bulk setWeights() in this Maya version (see profile_deformer_io.py's error).
This checks whether cmds.setAttr can write weightList[gi].weights[0:n] in one
call the same way _read_deformer_weights already reads it in bulk, and times
it against a naive per-index setAttr loop (the current cmds.deformerWeights
import path's likely floor, for comparison).

Select the same deformed mesh you profiled with profile_deformer_io.py.
"""

import time

from maya import cmds


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
    for hist in (cmds.listHistory(shape, pruneDagObjects=True) or []):
        if not cmds.objectType(hist, isa="geometryFilter"):
            continue
        node_type = cmds.nodeType(hist)
        if node_type in ("tweak", "skinCluster"):
            continue
        return hist, node_type
    raise RuntimeError("No non-skinCluster deformer found in history.")


shape = _selected_deformed_shape()
deformer_name, deformer_type = _first_deformer(shape)
vtx_num = cmds.polyEvaluate(shape, vertex=True)
print("deformer:", deformer_name, "(%s)" % deformer_type, "verts:", vtx_num)

# geo_index: mirror deformer._list_deformer_geometries' logic minimally
# (assume single-geometry deformer at index 0, matches the common case).
geo_index = 0
plug = f"{deformer_name}.weightList[{geo_index}].weights"
last = vtx_num - 1

t0 = time.perf_counter()
original = cmds.getAttr(f"{plug}[0:{last}]")
read_ms = (time.perf_counter() - t0) * 1000
print("bulk getAttr read: %.1f ms (%d values)" % (read_ms, len(original)))

# Round-trip probe values (won't change the actual look since verts are all
# masked at ~1.0 typically; we restore the original afterward regardless).
probe_values = [min(1.0, v) for v in original]

t0 = time.perf_counter()
try:
    cmds.setAttr(f"{plug}[0:{last}]", *probe_values, size=len(probe_values))
    bulk_write_ms = (time.perf_counter() - t0) * 1000
    print("bulk setAttr write (weights[0:n], size=n): %.1f ms  -- WORKS" % bulk_write_ms)
    bulk_write_ok = True
except Exception as exc:
    bulk_write_ms = (time.perf_counter() - t0) * 1000
    print("bulk setAttr write FAILED after %.1f ms: %s" % (bulk_write_ms, exc))
    bulk_write_ok = False

# Restore original values immediately regardless of which path ran.
cmds.setAttr(f"{plug}[0:{last}]", *original, size=len(original))

# Only run the slow per-index probe on a small subset (1000 verts) -- doing
# all 99842 one at a time would take a very long time and isn't needed to
# see the per-call overhead.
subset_n = min(1000, vtx_num)
t0 = time.perf_counter()
for i in range(subset_n):
    cmds.setAttr(f"{plug}[{i}]", probe_values[i])
per_index_ms = (time.perf_counter() - t0) * 1000
print("per-index setAttr loop (%d of %d verts): %.1f ms  (%.3f ms/vert, "
      "est. full mesh: %.1f ms)"
      % (subset_n, vtx_num, per_index_ms, per_index_ms / subset_n,
         per_index_ms / subset_n * vtx_num))

# Restore again after the per-index probe touched the first subset_n values.
cmds.setAttr(f"{plug}[0:{last}]", *original, size=len(original))

print("\noriginal weights restored")
if bulk_write_ok:
    print("-> use cmds.setAttr(plug[0:n], *values, size=n) for bulk deformer "
          "weight writes")
else:
    print("-> bulk setAttr failed; per-index loop is the fallback (see timing "
          "above) -- report the exact error message")
