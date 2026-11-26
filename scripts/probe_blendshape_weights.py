"""
Probe blendShape weight structure — RUN INSIDE MAYA.

Needed to design deformer.py's blendShape support (currently missing --
deformer.py's _read_deformer_weights only reads {node}.weightList[...],
which blendShape nodes don't have; blendShape weights live under a
completely different attribute structure).

Select a blendShape deformer node (e.g. "blendShape1") or its base/target
mesh, then run this in the Script Editor (Python tab).
"""

import os
import tempfile

from maya import cmds


def _selected_blendshape():
    sel = cmds.ls(sl=True) or []
    if not sel:
        raise RuntimeError("Select a blendShape node or its mesh first.")
    for node in sel:
        if cmds.nodeType(node) == "blendShape":
            return node
    # Selection might be a mesh/transform -- walk history for a blendShape.
    for node in sel:
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or [node]
        for shape in shapes:
            for hist in (cmds.listHistory(shape, pruneDagObjects=True) or []):
                if cmds.nodeType(hist) == "blendShape":
                    return hist
    raise RuntimeError("No blendShape node found in selection/history.")


bs_node = _selected_blendshape()
print("=" * 66)
print("blendShape node:", bs_node)
print("=" * 66)

print("\n--- weight attribute aliases (target display names) ---")
aliases = cmds.aliasAttr(bs_node, query=True) or []
print(aliases)

print("\n--- weight[] multi-indices ---")
weight_indices = cmds.getAttr(f"{bs_node}.weight", multiIndices=True) or []
print("indices:", weight_indices)
for i in weight_indices:
    try:
        val = cmds.getAttr(f"{bs_node}.weight[{i}]")
        print(f"  weight[{i}] = {val}")
    except Exception as exc:
        print(f"  weight[{i}] error: {exc}")

print("\n--- envelope ---")
try:
    print("envelope =", cmds.getAttr(f"{bs_node}.envelope"))
except Exception as exc:
    print("envelope error:", exc)

print("\n--- inputTarget structure ---")
input_target_indices = cmds.getAttr(f"{bs_node}.inputTarget", multiIndices=True) or []
print("inputTarget indices:", input_target_indices)

for geo_idx in input_target_indices:
    print(f"\n  inputTarget[{geo_idx}]:")
    try:
        base_weights_indices = cmds.getAttr(
            f"{bs_node}.inputTarget[{geo_idx}].baseWeights", multiIndices=True
        )
        print(f"    baseWeights indices (count={len(base_weights_indices or [])}):",
              (base_weights_indices or [])[:10], "...")
        if base_weights_indices:
            sample = [
                cmds.getAttr(f"{bs_node}.inputTarget[{geo_idx}].baseWeights[{i}]")
                for i in base_weights_indices[:5]
            ]
            print("    baseWeights sample values:", sample)
    except Exception as exc:
        print("    baseWeights error:", exc)

    group_indices = cmds.getAttr(
        f"{bs_node}.inputTarget[{geo_idx}].inputTargetGroup", multiIndices=True
    ) or []
    print(f"    inputTargetGroup indices: {group_indices}")

    for group_idx in group_indices:
        plug = (
            f"{bs_node}.inputTarget[{geo_idx}]"
            f".inputTargetGroup[{group_idx}].targetWeights"
        )
        try:
            tw_indices = cmds.getAttr(plug, multiIndices=True)
            print(f"    targetWeights[{group_idx}] indices "
                  f"(count={len(tw_indices or [])}): {(tw_indices or [])[:10]} ...")
            if tw_indices:
                sample = [
                    cmds.getAttr(f"{plug}[{i}]") for i in tw_indices[:5]
                ]
                print(f"      sample values: {sample}")
        except Exception as exc:
            print(f"    targetWeights[{group_idx}] error: {exc}")

print("\n" + "=" * 66)
print("cmds.deformerWeights(export=True) full output for this blendShape")
print("=" * 66)
tmp_dir = tempfile.mkdtemp(prefix="wipskin_bs_probe_")
try:
    cmds.deformerWeights(
        "probe_blendshape.xml", export=True, deformer=bs_node, path=tmp_dir,
        weightPrecision=6,
    )
    out_path = os.path.join(tmp_dir, "probe_blendshape.xml")
    with open(out_path, encoding="utf-8") as f:
        content = f.read()
    print(content)
    print("\n(file left at:", out_path, ")")
except Exception as exc:
    print("cmds.deformerWeights(export=True) failed:", exc)
