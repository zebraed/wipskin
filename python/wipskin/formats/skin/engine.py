"""Shared skinCluster read/write for formats that only (de)serialize weights.

A format that implements SkinWeightFormat.read_weights / write_weights gets
Import/Export from here: collect_skin_weights() reads a shape into
SkinWeightData and apply_skin_weights() writes one back, binding the shape
first when it has no skinCluster.

Follows the MFnSkinCluster pattern of formats/skin/xml (full vertex
component, influenceObjects() column order, one setWeights call).
Polygon meshes only, matched by vertex index.
"""

from __future__ import annotations

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
from maya import cmds

from wipskin.formats import scene
from wipskin.formats.skin.base import SkinWeightData


def _get_mesh_shape(node) -> str:
    """Skinnable mesh shape of node (a shape or its transform)."""
    shape = scene.get_skinnable_shape(node)
    if not shape:
        shapes = scene.list_skinnable_shapes_under(node)
        if not shapes:
            raise ValueError(f"No skinnable shape on: {node}")

        shape = shapes[0]

    if cmds.nodeType(shape) != "mesh":
        raise ValueError(
            f"{shape} is a {cmds.nodeType(shape)}; this format's weights "
            "apply to polygon meshes only."
        )

    return shape


def _get_dag_path(node):
    selection = om2.MSelectionList()
    selection.add(node)
    return selection.getDagPath(0)


def _get_skin_cluster_fn(skc):
    selection = om2.MSelectionList()
    selection.add(skc)
    return oma2.MFnSkinCluster(selection.getDependNode(0))


def _create_vertex_component(vertex_count):
    comp_fn = om2.MFnSingleIndexedComponent()
    component = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(vertex_count)))
    return component


def _get_long_name(node) -> str:
    """Full DAG path of an existing, unambiguous node."""
    matches = cmds.ls(node, l=True)
    if not matches:
        raise ValueError(f"Influence not in the scene: {node}")

    if len(matches) > 1:
        raise ValueError(
            f"Influence name is ambiguous ({len(matches)} matches): {node}"
        )

    return matches[0]


def collect_skin_weights(node) -> SkinWeightData:
    """Read the skin weights of node's mesh.

    Args:
        node (str): Skinned mesh shape or its transform.

    Returns:
        SkinWeightData: Weights for every vertex, columns in the
        skinCluster's influence order; shape is the transform's shortest
        unique name.

    Raises:
        ValueError: When node is not a skinned polygon mesh.
    """
    shape = _get_mesh_shape(node)
    skc = scene.get_skin_cluster(shape)
    if not skc:
        raise ValueError(f"No skinCluster on: {shape}")

    shape_dag = _get_dag_path(shape)
    vertex_count = om2.MFnMesh(shape_dag).numVertices
    skc_fn = _get_skin_cluster_fn(skc)
    influences = [path.partialPathName() for path in skc_fn.influenceObjects()]
    weights, _influence_count = skc_fn.getWeights(
        shape_dag, _create_vertex_component(vertex_count)
    )
    transform = scene.get_shape_transform(shape)
    return SkinWeightData(
        shape=cmds.ls(transform)[0],
        influences=influences,
        weights=list(weights),
    )


def apply_skin_weights(node, data, normalize=True) -> str:
    """Write data onto node's mesh, binding it first if it is not skinned.

    Missing influences are added to an existing skinCluster and unlocked
    (a locked influence silently ignores setWeights). Scene influences the
    data does not name get weight 0.

    Args:
        node (str): Mesh shape or its transform.
        data (SkinWeightData): Weights to apply; one row per mesh vertex.
        normalize (bool): Force-normalize the weights afterwards.

    Returns:
        str: The skinCluster written to.

    Raises:
        ValueError: When node is not a polygon mesh, its vertex count
            differs from data, or an influence is missing or ambiguous.
    """
    shape = _get_mesh_shape(node)
    shape_dag = _get_dag_path(shape)
    vertex_count = om2.MFnMesh(shape_dag).numVertices
    if vertex_count != data.vertex_count:
        raise ValueError(
            f"{shape} has {vertex_count} vertices but the weights are for "
            f"{data.vertex_count}."
        )

    data_long_names = [_get_long_name(name) for name in data.influences]

    skc = scene.get_skin_cluster(shape)
    if not skc:
        created = cmds.skinCluster(
            data_long_names + [scene.get_shape_transform(shape)], tsb=True,
        )
        skc = created[0] if isinstance(created, list) else created
    else:
        current = cmds.skinCluster(skc, q=True, inf=True)
        if current is None:
            current = []

        current_long_names = {_get_long_name(name) for name in current}
        for long_name in data_long_names:
            if long_name not in current_long_names:
                cmds.skinCluster(skc, e=True, ai=long_name)

    for long_name in data_long_names:
        cmds.skinCluster(skc, e=True, inf=long_name, lw=False)

    # Re-resolve after the edits above: influence order may have changed.
    skc_fn = _get_skin_cluster_fn(skc)
    scene_long_names = [path.fullPathName() for path in skc_fn.influenceObjects()]
    column_by_name = {name: index for index, name in enumerate(scene_long_names)}
    scene_count = len(scene_long_names)
    matrix = data.build_column_matrix(
        [column_by_name[name] for name in data_long_names], scene_count,
    )

    skc_fn.setWeights(
        shape_dag,
        _create_vertex_component(vertex_count),
        om2.MIntArray(list(range(scene_count))),
        om2.MDoubleArray(matrix),
        False,
    )
    if normalize:
        cmds.skinCluster(skc, e=True, fnw=True)

    return skc
