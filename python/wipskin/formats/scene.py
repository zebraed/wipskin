"""Maya scene queries shared by the weight formats.
"""

from __future__ import annotations

from maya import cmds


DEFORMABLE_SHAPE_TYPES = ("mesh", "nurbsCurve", "nurbsSurface", "lattice")
SKINNABLE_COMPONENT_MARKERS = (".vtx[", ".cv[", ".s[", ".pt[")


def get_node_leaf_name(node_name):
    """Return a node's name without its DAG path or namespace."""
    leaf = node_name.rsplit("|", 1)[-1]
    return leaf.split(":")[-1]


def is_deformable_shape_type(node):
    """True for DEFORMABLE_SHAPE_TYPES and their subtypes (bezierCurve etc)."""
    return any(cmds.objectType(node, isa=t) for t in DEFORMABLE_SHAPE_TYPES)


def is_skinnable_component(item):
    """True if item is a component selection (vtx/cv/surface point/lattice pt)."""
    return any(marker in item for marker in SKINNABLE_COMPONENT_MARKERS)


def is_usable_shape(shape):
    """True unless shape is an intermediate (Orig) shape."""
    if not cmds.attributeQuery("intermediateObject", node=shape, exists=True):
        return True
    return not cmds.getAttr(f"{shape}.intermediateObject")


def get_skinnable_shape(node):
    """Resolve a transform or shape node to a skinnable shape long path."""
    resolved = cmds.ls(node, long=True)
    if not resolved:
        return ""
    node_name = resolved[0]
    node_type = cmds.nodeType(node_name)
    if is_deformable_shape_type(node_name):
        if is_usable_shape(node_name):
            return node_name
        return ""

    if node_type != "transform":
        return ""

    for shape_type in DEFORMABLE_SHAPE_TYPES:
        shapes = cmds.listRelatives(
            node_name,
            shapes=True,
            type=shape_type,
            fullPath=True,
            noIntermediate=False,
        )
        if not shapes:
            continue
        for shape in shapes:
            if is_usable_shape(shape):
                return shape
    return ""


def list_skinnable_shapes_under(node):
    """List skinnable shape long paths under a transform or shape node."""
    resolved = cmds.ls(node, long=True)
    if not resolved:
        return []
    node_name = resolved[0]
    node_type = cmds.nodeType(node_name)
    if is_deformable_shape_type(node_name):
        if is_usable_shape(node_name):
            return [node_name]
        return []

    if node_type != "transform":
        return []

    shapes = []
    for shape_type in DEFORMABLE_SHAPE_TYPES:
        rel_kwargs = {
            "allDescendents": True,
            "fullPath": True,
            "type": shape_type,
        }
        if shape_type == "mesh":
            rel_kwargs["noIntermediate"] = True
        found = cmds.listRelatives(node_name, **rel_kwargs)
        if not found:
            continue
        for shape in found:
            if is_usable_shape(shape):
                shapes.append(shape)
    return shapes


def _append_unique_shape(shapes, seen, shape):
    if not shape or shape in seen:
        return
    seen.add(shape)
    shapes.append(shape)


def list_skinnable_shapes(items=None):
    """Return skinnable shape long paths from the selection or provided items.

    Supports mesh, nurbsCurve, nurbsSurface, and lattice geometry.
    """
    if items is None:
        sel_items = cmds.ls(sl=True, flatten=True, long=True)
    else:
        if not isinstance(items, (list, tuple)):
            items = [items]
        sel_items = cmds.ls(items, flatten=True, long=True)

    shapes = []
    seen = set()
    for item in sel_items:
        if is_skinnable_component(item):
            shape = get_skinnable_shape(item.split(".")[0])
            _append_unique_shape(shapes, seen, shape)
            continue

        node_type = cmds.nodeType(item)
        if node_type == "joint":
            skin_clusters = cmds.listConnections(
                item,
                source=False,
                destination=True,
                type="skinCluster",
            )
            if not skin_clusters:
                continue
            for skin_cluster in skin_clusters:
                geoms = cmds.skinCluster(skin_cluster, query=True, geometry=True)
                if not geoms:
                    continue
                if not isinstance(geoms, (list, tuple)):
                    geoms = [geoms]
                for geom in geoms:
                    shape = get_skinnable_shape(geom)
                    _append_unique_shape(shapes, seen, shape)
            continue

        found_shapes = list_skinnable_shapes_under(item)
        if found_shapes:
            for shape in found_shapes:
                _append_unique_shape(shapes, seen, shape)
            continue

        shape = get_skinnable_shape(item)
        _append_unique_shape(shapes, seen, shape)

    return shapes


def list_skinned_shapes(shape_types=None):
    """Return the long paths of every shape a scene skinCluster deforms.

    Args:
        shape_types (tuple, optional): Exact node types to keep, e.g.
            ("mesh",); None keeps every skinnable shape type.

    Returns:
        list: Shape long paths in skinCluster order, without duplicates or
        intermediate (Orig) shapes.
    """
    skin_clusters = cmds.ls(type="skinCluster")
    if not skin_clusters:
        return []

    shapes = []
    seen = set()
    for skin_cluster in skin_clusters:
        geoms = cmds.skinCluster(skin_cluster, query=True, geometry=True)
        if not geoms:
            continue

        if not isinstance(geoms, (list, tuple)):
            geoms = [geoms]

        for geom in geoms:
            shape = get_skinnable_shape(geom)
            if shape and shape_types is not None:
                if cmds.nodeType(shape) not in shape_types:
                    continue

            _append_unique_shape(shapes, seen, shape)

    return shapes


def get_shape_transform(shape):
    """Return the shape's parent transform long path, or shape when parentless."""
    parents = cmds.listRelatives(shape, parent=True, fullPath=True)
    if parents:
        return parents[0]
    return shape


def is_skin_cluster_affecting_shape(skc, shape):
    """True when skinCluster skc deforms shape (long/leaf name safe)."""
    geoms = cmds.skinCluster(skc, query=True, geometry=True)
    if geoms is None:
        return False
    if not isinstance(geoms, (list, tuple)):
        geoms = [geoms]

    shape_long = cmds.ls(shape, long=True)
    if not shape_long:
        return False
    shape_long = shape_long[0]
    shape_leaf = get_node_leaf_name(shape_long)
    for geom in geoms:
        geom_long = cmds.ls(geom, long=True)
        if geom_long and geom_long[0] == shape_long:
            return True
        if get_node_leaf_name(geom) == shape_leaf:
            return True
    return False


def get_skin_cluster(node):
    """Return skinCluster node name for a transform or skinnable shape, or empty string."""
    shape = get_skinnable_shape(node)
    if not shape:
        shapes = list_skinnable_shapes_under(node)
        if not shapes:
            return ""
        shape = shapes[0]

    skin_clusters = cmds.listConnections(
        shape,
        source=True,
        destination=False,
        type="skinCluster",
    )
    if not skin_clusters:
        history = cmds.listHistory(shape, pruneDagObjects=True)
        if history:
            skin_clusters = cmds.ls(history, type="skinCluster")
    if not skin_clusters:
        return ""

    for skc in skin_clusters:
        if is_skin_cluster_affecting_shape(skc, shape):
            return skc
    return skin_clusters[0]
