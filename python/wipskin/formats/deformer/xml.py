"""Deformer weight XML IO (excluding skinCluster)."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from maya import cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2

from wipskin.core import io
from wipskin.core import metadata
from wipskin.formats import scene
from wipskin.formats import xml_accel
from wipskin.core import file_cache
from wipskin.formats import xml_sniff
from wipskin.core.path_utils import norm_path


EXT = "xml"
#: Sidecar "format" value for deformer weight XMLs.
METADATA_FORMAT = "deformer"
# Distinct from Maya's native deformerWeight root used by skin XML
ROOT_TAG = "customDeformerWeight"
# Older exports used a misspelled root tag; keep accepting them on read :D
LEGACY_ROOT_TAGS = ("deformwerWeights",)


def is_deformer_weight_file(path):
    """True if path is a deformer-weight XML (not Maya skin deformerWeight XML)."""
    tag = xml_sniff.classify(path)
    if tag == ROOT_TAG:
        return True
    return tag in LEGACY_ROOT_TAGS


def _as_string_list(values):
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        return list(values)
    return [values]


def _node_short_name(node_name):
    return node_name.rsplit("|", 1)[-1]


def _list_deformer_geometries(deformer_name):
    """Return [(geo_index, shape_long, shape_short), ...] for a deformer.

    geo_index is the weightList multi index (not always 0..n-1).
    """
    shapes = _as_string_list(cmds.deformer(deformer_name, q=True, geometry=True))
    if not shapes:
        return []

    indices = _as_string_list(
        cmds.deformer(deformer_name, q=True, geometryIndices=True)
    )
    result = []
    for i, shape in enumerate(shapes):
        shape_long_list = cmds.ls(shape, long=True)
        if not shape_long_list:
            continue
        shape_long = shape_long_list[0]
        if i < len(indices):
            geo_index = int(indices[i])
        else:
            geo_index = i
        result.append((geo_index, shape_long, _node_short_name(shape_long)))
    return result


def _read_deformer_weights(deformer_name, geo_index, vtx_count, default=1.0):
    """Read per-vertex weights for one geometry index on a deformer.

    Uses weightList[geoIndex] so multi-shape deformers do not mix geometries
    (unlike querying via percent on each component).
    """
    weights = [float(default)] * int(vtx_count)
    if vtx_count <= 0:
        return weights

    plug = f"{deformer_name}.weightList[{geo_index}].weights"
    last = int(vtx_count) - 1
    try:
        values = cmds.getAttr(f"{plug}[0:{last}]")
    except (RuntimeError, ValueError, TypeError):
        values = None

    if isinstance(values, (list, tuple)) and values:
        for i, value in enumerate(values):
            if i >= vtx_count:
                break
            weights[i] = float(value)
        return weights

    indices = cmds.getAttr(plug, multiIndices=True)
    if not indices:
        return weights
    for index in indices:
        if 0 <= index < vtx_count:
            weights[index] = float(cmds.getAttr(f"{plug}[{index}]"))
    return weights


def _match_shape_on_deformer(shape_name, deformer_shapes_long):
    """Resolve a shape name from XML against long shape paths on a deformer."""
    if not shape_name:
        return ""
    resolved = cmds.ls(shape_name, long=True)
    if resolved and resolved[0] in deformer_shapes_long:
        return resolved[0]

    target_short = _node_short_name(shape_name)
    for shape_long in deformer_shapes_long:
        if _node_short_name(shape_long) == target_short:
            return shape_long
    return ""


def _resolve_shape_from_selection(node=None):
    """Resolve a mesh/shape long name from the given node or current selection."""
    if node is None:
        selection = cmds.ls(sl=True, long=True, objectsOnly=True)
        if not selection:
            selection = cmds.ls(sl=True, long=True)
        if not selection:
            return ""
        node = selection[0]

    if "." in node:
        node = node.split(".")[0]

    resolved = cmds.ls(node, long=True)
    if not resolved:
        return ""
    node = resolved[0]

    if scene.is_deformable_shape_type(node):
        return node

    shapes = cmds.listRelatives(
        node, shapes=True, fullPath=True, noIntermediate=False
    )
    if not shapes:
        return ""
    return shapes[0]


def _list_shapes_from_selection(items=None):
    """Return unique deformed shape paths from all selected/provided items."""
    if items is None:
        items = cmds.ls(sl=True, long=True, objectsOnly=True)
        if not items:
            items = cmds.ls(sl=True, long=True)
    else:
        items = _as_string_list(items)

    shapes = []
    seen = set()
    for item in items:
        shape = _resolve_shape_from_selection(item)
        if not shape:
            continue
        shape_long = cmds.ls(shape, long=True)
        if not shape_long:
            continue
        shape = shape_long[0]
        if shape in seen:
            continue
        seen.add(shape)
        shapes.append(shape)
    return shapes


def _deformer_affects_shape(deformer_node, shape):
    """True when deformer_node deforms shape (short/long name safe)."""
    deformed = cmds.deformer(deformer_node, q=True, geometry=True)
    deformed = _as_string_list(deformed)
    if not deformed:
        return False

    shape_long = cmds.ls(shape, long=True)
    if not shape_long:
        return False
    shape_long = shape_long[0]
    shape_short = shape_long.rsplit("|", 1)[-1]

    for geom in deformed:
        geom_long = cmds.ls(geom, long=True)
        if geom_long and geom_long[0] == shape_long:
            return True
        geom_short = geom.rsplit("|", 1)[-1]
        if geom_short == shape_short:
            return True
    return False


def list_deformers_from_selection(node=None):
    """List unique deformers from all selected/provided geometry.

    Returns:
        list: (deformer_name, node_type) pairs.
    """
    shapes = _list_shapes_from_selection(node)
    if not shapes:
        return []

    results = []
    seen = set()
    for shape in shapes:
        history = cmds.listHistory(shape, pruneDagObjects=True)
        if not history:
            continue
        for hist_node in history:
            if not cmds.objectType(hist_node, isa="geometryFilter"):
                continue
            node_type = cmds.nodeType(hist_node)
            if node_type in ("tweak", "skinCluster"):
                continue
            if not _deformer_affects_shape(hist_node, shape):
                continue

            uuids = cmds.ls(hist_node, uuid=True)
            identity = uuids[0] if uuids else hist_node
            if identity in seen:
                continue
            seen.add(identity)
            results.append((hist_node, node_type))
    return results


def deformer_shape_count(deformer_name):
    """Return the number of geometry shapes affected by a deformer."""
    return len(_list_deformer_geometries(deformer_name))


def list_deformer_shapes(deformer_name):
    """Return [(shape_long, node_type), ...] for the geometry affected by a
    deformer, for UI shape-selection lists.
    """
    return [
        (shape_long, cmds.nodeType(shape_long))
        for _geo_index, shape_long, _shape_short
        in _list_deformer_geometries(deformer_name)
    ]


def parse_file_info(path):
    """Parse deformer weight XML metadata for the file viewer, memoized by
    (mtime, size). The returned dict is treated as read-only by callers.

    Returns:
        dict: With deformer, shape, influences, path.
    """
    return file_cache.memoize_by_stat(path, _parse_file_info)


def _parse_file_info(path):
    path = norm_path(path)
    tree = ET.parse(path)
    root = tree.getroot()
    info = {
        "path": path,
        "deformer": "",
        "shape": "",
        "vertex_count": 0,
        "shapes": [],
        "influences": [],
    }
    for element in root:
        tag = element.tag
        if tag == "shape":
            shape_name = element.attrib.get("name", "")
            if shape_name and not info["shape"]:
                info["shape"] = shape_name
            vertex_count = _parse_vertex_count(element.attrib.get("size", ""))
            if vertex_count is None:
                vertex_count = _parse_vertex_count(element.attrib.get("max", ""))
            if shape_name:
                info["shapes"].append({
                    "name": shape_name,
                    "vertex_count": vertex_count,
                })
            if vertex_count is not None and not info["vertex_count"]:
                info["vertex_count"] = vertex_count
        elif tag == "weights":
            deformer_name = element.attrib.get("deformer", "")
            if deformer_name and not info["deformer"]:
                info["deformer"] = deformer_name
            shape_name = element.attrib.get("shape", "")
            if shape_name and not info["shape"]:
                info["shape"] = shape_name
            source = element.attrib.get("source", "")
            if source:
                info["influences"].append(source)
    return info


def _parse_vertex_count(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _resolve_shape_export_filename(
    deformer_name,
    shape_name,
    directory,
    filename,
    auto_name,
    auto_version,
):
    """Build a "{shape}_{deformer}.xml" (optionally versioned) filename."""
    deformer_short = _node_short_name(deformer_name)
    shape_short = _node_short_name(shape_name)
    combined_short = f"{shape_short}_{deformer_short}"
    if auto_name:
        base_name = combined_short
    elif filename:
        base_name, _version, _ext = io.parse_versioned_filename(
            os.path.basename(filename)
        )
    else:
        base_name = combined_short
    if auto_version:
        return os.path.basename(io.resolve_export_path(directory, base_name, EXT, True))
    if filename and not auto_name:
        return os.path.basename(filename)
    return f"{base_name}.{EXT}"


def _shape_geo_index(deformer_name, shape_name):
    target_short = _node_short_name(shape_name)
    for geo_index, _shape_long, shape_short in _list_deformer_geometries(deformer_name):
        if shape_short == target_short:
            return geo_index
    return None


def export_deformer_weight_for_shape(
    deformer_name,
    shape_name,
    directory,
    filename=None,
    auto_name=False,
    auto_version=False,
):
    """Export one shape's weights on a deformer to its own weight XML file.

    One file per shape: Maya's multi-shape export drops shapes, duplicates
    <weights> blocks, and rejects -vertexConnections for the whole deformer
    as soon as any member is non-mesh.
    """
    directory = norm_path(directory)
    if not os.path.isdir(directory):
        raise ValueError(f"Invalid export directory: {directory}")
    if not cmds.objExists(deformer_name):
        raise ValueError(f"Deformer does not exist: {deformer_name}")
    if not cmds.objExists(shape_name):
        raise ValueError(f"Shape does not exist: {shape_name}")

    geo_index = _shape_geo_index(deformer_name, shape_name)
    if geo_index is None:
        raise ValueError(
            f"{shape_name} is not among {deformer_name}'s affected geometry."
        )

    file_name = _resolve_shape_export_filename(
        deformer_name, shape_name, directory, filename, auto_name, auto_version,
    )
    full_path = norm_path(os.path.join(directory, file_name))

    if cmds.nodeType(shape_name) == "mesh":
        # ElementTree DOM construction dominates export cost on large
        # meshes; fall back to it only when native is unavailable.
        if not _bulk_export_deformer_weight_xml(
            deformer_name, geo_index, shape_name, file_name, directory
        ):
            _export_deformer_weight_xml(
                deformer_name, geo_index, shape_name, file_name, directory
            )
    else:
        # Our writers can only embed mesh geometry (positions + topology).
        _export_deformer_weight_via_maya_standard(
            deformer_name, shape_name, file_name, directory
        )

    metadata.write_export_sidecar(full_path, METADATA_FORMAT)
    print(f"// WipSkin deformer export: {full_path}")
    return full_path


def export_deformer_weight(
    deformer_name,
    directory,
    filename=None,
    auto_name=False,
    auto_version=False,
):
    """Export every shape affected by a deformer, each to its own XML file.

    A manual filename can only name one output, so multi-shape deformers
    fall back to the shape_deformer convention for every job.

    Returns:
        list: The exported file paths.
    """
    directory = norm_path(directory)
    if not os.path.isdir(directory):
        raise ValueError(f"Invalid export directory: {directory}")
    if not cmds.objExists(deformer_name):
        raise ValueError(f"Deformer does not exist: {deformer_name}")

    geometries = _list_deformer_geometries(deformer_name)
    if not geometries:
        raise ValueError(f"{deformer_name} has no affected geometry to export.")

    per_job_filename = filename if len(geometries) == 1 else None

    paths = []
    for _geo_index, shape_long, _shape_short in geometries:
        paths.append(export_deformer_weight_for_shape(
            deformer_name, shape_long, directory,
            filename=per_job_filename,
            auto_name=auto_name,
            auto_version=auto_version,
        ))
    return paths


def _export_deformer_weight_via_maya_standard(
    deformer_name,
    shape_long,
    filename,
    directory,
):
    """Export one shape via Maya's own cmds.deformerWeights, for non-mesh
    geometry our writers can't embed.

    No -vertexConnections: Maya rejects it for the deformer's whole geometry
    set once any member is non-mesh, even with -shape scoping the call. The
    embedded <shape> data stays Maya's truncated placeholder, so these files
    are not a usable source for Maya's spatial import methods ("index"
    reimport only reads <weights>).

    The root tag is rewritten to ROOT_TAG so is_deformer_weight_file does
    not classify the result as a skin file; nothing on the read side
    validates the root tag.
    """
    cmds.deformerWeights(
        filename, export=True, deformer=deformer_name, path=directory,
        shape=shape_long, weightPrecision=6,
    )
    output_path = norm_path(os.path.join(directory, filename))
    with open(output_path, "r", encoding="utf-8") as file_id:
        content = file_id.read()
    content = content.replace("<deformerWeight>", f"<{ROOT_TAG}>", 1)
    content = content.replace("</deformerWeight>", f"</{ROOT_TAG}>", 1)
    with open(output_path, "w", encoding="utf-8") as file_id:
        file_id.write(content)


def _bulk_export_deformer_weight_xml(
    deformer_name,
    geo_index,
    shape_long,
    filename,
    directory,
):
    """Write one shape's deformer weight XML natively, skipping ElementTree.

    Returns:
        bool: False when native is unavailable, and the caller must fall
            back to _export_deformer_weight_xml.
    """
    if not xml_accel.native_available():
        return False

    shape_short = _node_short_name(shape_long)
    selection_list = om2.MGlobal.getSelectionListByName(shape_long)
    dag_path = selection_list.getDagPath(0)
    mesh_fn = om2.MFnMesh(dag_path)
    vtx_num = mesh_fn.numVertices

    positions = []
    for point in mesh_fn.getPoints(om2.MSpace.kWorld):
        positions.extend((point.x, point.y, point.z))

    world_matrix = list(cmds.getAttr(f"{shape_long}.worldMatrix[0]"))

    polygon_counts = []
    polygon_connects = []
    face_iterator = om2.MItMeshPolygon(dag_path)
    while not face_iterator.isDone():
        verts = list(face_iterator.getVertices())
        polygon_counts.append(len(verts))
        polygon_connects.extend(verts)
        face_iterator.next()

    weights = _read_deformer_weights(deformer_name, geo_index, vtx_num)

    output_path = norm_path(os.path.join(directory, filename))
    # The Rust writer is multi-shape capable; the single-element lists are
    # because this function only ever writes one shape per call.
    return xml_accel.native_write_deformer_weight_xml(
        output_path, os.path.basename(filename), deformer_name,
        [shape_short], [world_matrix], [positions],
        [polygon_counts], [polygon_connects], [weights],
    )


def _append_mesh_shape_element(root, shape_long, shape_short):
    """Append an embedded mesh <shape> block used for spatial import methods."""
    shape_element = ET.SubElement(root, "shape")
    shape_element.attrib["name"] = shape_short
    shape_element.attrib["stride"] = "3"

    # One MFnMesh over the DAG path drives every geometry query below. The DAG
    # path (not the bare depend node) is required so getPoints(kWorld) applies
    # the world transform.
    selection_list = om2.MGlobal.getSelectionListByName(shape_long)
    dag_path = selection_list.getDagPath(0)
    mesh_fn = om2.MFnMesh(dag_path)

    vtx_num = mesh_fn.numVertices
    shape_element.attrib["size"] = str(vtx_num)
    shape_element.attrib["max"] = str(vtx_num)

    matrix_values = cmds.getAttr(f"{shape_long}.worldMatrix[0]")
    matrix_str = " ".join(str(value) for value in matrix_values)
    shape_element.attrib["worldMatrix"] = matrix_str

    # One bulk world-space query for all vertices, instead of a cmds.xform
    # round trip per vertex (the old export's dominant per-vertex cost).
    points = mesh_fn.getPoints(om2.MSpace.kWorld)
    for vtx_index in range(vtx_num):
        point = points[vtx_index]
        point_element = ET.SubElement(shape_element, "point")
        point_element.attrib["index"] = str(vtx_index)
        point_element.attrib["value"] = f"{point.x} {point.y} {point.z}"

    polygon_counts_element = ET.SubElement(shape_element, "polygonCounts")
    face_num = mesh_fn.numPolygons
    polygon_counts_element.attrib["size"] = str(face_num)

    face_iterator = om2.MItMeshPolygon(dag_path)

    face_count_strings = []
    face_connect_strings = []
    connect_size = 0
    while not face_iterator.isDone():
        vertex_count = face_iterator.polygonVertexCount()
        face_count_strings.append(str(vertex_count))
        indices = list(face_iterator.getVertices())
        face_connect_strings.append(" ".join(str(idx) for idx in indices))
        connect_size += vertex_count
        face_iterator.next()

    polygon_counts_element.attrib["polygonCounts"] = " ".join(face_count_strings)

    connects_element = ET.SubElement(shape_element, "polygonConnects")
    connects_element.attrib["polygonConnects"] = " ".join(face_connect_strings)
    connects_element.attrib["size"] = str(connect_size)
    return vtx_num


def _append_weights_element(root, deformer_name, shape_short, weights):
    vtx_num = len(weights)
    weights_element = ET.SubElement(root, "weights")
    weights_element.attrib["deformer"] = deformer_name
    weights_element.attrib["source"] = "baseLayer"
    weights_element.attrib["shape"] = shape_short
    weights_element.attrib["layer"] = "0"
    weights_element.attrib["defaultValue"] = "-1.000"
    weights_element.attrib["size"] = str(vtx_num)
    weights_element.attrib["max"] = str(vtx_num)

    for vtx_index, weight_value in enumerate(weights):
        weight_element = ET.SubElement(weights_element, "point")
        weight_element.attrib["index"] = str(vtx_index)
        weight_element.attrib["value"] = str(weight_value)


def _export_deformer_weight_xml(
    deformer_name,
    geo_index,
    shape_long,
    filename,
    directory,
):
    """Write one shape's deformer weight XML with embedded mesh geometry.

    The <shape> block is written before the <weights> block, matching
    Maya's deformerWeights layout.
    """
    root = ET.Element(ROOT_TAG)
    header = ET.SubElement(root, "headerInfo")
    # Basename only (same convention as skin XML headerInfo)
    header.attrib["fileName"] = os.path.basename(filename)

    shape_short = _node_short_name(shape_long)
    vtx_num = _append_mesh_shape_element(root, shape_long, shape_short)
    weights = _read_deformer_weights(deformer_name, geo_index, vtx_num)
    _append_weights_element(root, deformer_name, shape_short, weights)

    # Indent in place (ElementTree, 3.9+) instead of rebuilding the whole
    # document as a second minidom DOM just to pretty-print it. The hasattr
    # guard degrades to unindented-but-valid XML on Python < 3.9.
    if hasattr(ET, "indent"):
        ET.indent(root, space="    ")
    output_path = norm_path(os.path.join(directory, filename))
    with open(output_path, "w", encoding="utf-8") as file_id:
        file_id.write('<?xml version="1.0" encoding="utf-8"?>\n')
        file_id.write(ET.tostring(root, encoding="unicode"))
        file_id.write("\n")


def _list_import_target_shapes(info, deformer_name, import_as, shape=""):
    """Resolve scene shape long paths to import into for a deformer weight file."""
    deformer_shapes = [
        shape_long
        for _geo_index, shape_long, _shape_short in _list_deformer_geometries(
            deformer_name
        )
    ]
    if not deformer_shapes:
        return []

    if import_as == "selected":
        if shape:
            target = _match_shape_on_deformer(shape, deformer_shapes)
            if not target:
                target = _resolve_shape_from_selection(shape)
            if target and target in deformer_shapes:
                return [target]
            if target:
                matched = _match_shape_on_deformer(target, deformer_shapes)
                if matched:
                    return [matched]
            return []

        selected = _resolve_shape_from_selection()
        if not selected:
            raise ValueError("No mesh selected for import.")
        matched = _match_shape_on_deformer(selected, deformer_shapes)
        if not matched:
            raise ValueError(
                f"Selected shape is not affected by {deformer_name}: {selected}"
            )
        return [matched]

    targets = []
    seen = set()
    for entry in info.get("shapes", []):
        matched = _match_shape_on_deformer(entry.get("name", ""), deformer_shapes)
        if matched and matched not in seen:
            seen.add(matched)
            targets.append(matched)
    if not targets:
        matched = _match_shape_on_deformer(info.get("shape", ""), deformer_shapes)
        if matched:
            targets.append(matched)
    return targets


def import_deformer_weight(
    directory,
    filename,
    method="index",
    import_as="saved",
    shape="",
    deformer="",
    ignore_names=False,
):
    """Import deformer weights from XML using Maya deformerWeights.

    Multi-shape files are imported one shape at a time with -skip, because
    Maya's deformerWeights mixes geometries when multiple shapes are passed.
    """
    directory = norm_path(directory)
    file_path = norm_path(os.path.join(directory, filename))
    if not os.path.isfile(file_path):
        raise ValueError(f"File not found: {file_path}")

    info = parse_file_info(file_path)
    deformer_name = deformer
    if not deformer_name:
        deformer_name = info["deformer"]
    if not deformer_name:
        raise ValueError("No deformer name in weight file.")
    if not cmds.objExists(deformer_name):
        raise ValueError(f"Deformer does not exist: {deformer_name}")

    target_shapes = _list_import_target_shapes(
        info, deformer_name, import_as, shape=shape
    )
    if not target_shapes:
        raise ValueError(
            f"No matching shapes on {deformer_name} for import from {filename}"
        )

    deformer_shape_shorts = [
        shape_short
        for _geo_index, _shape_long, shape_short in _list_deformer_geometries(
            deformer_name
        )
    ]

    # Bulk setAttr instead of Maya's deformerWeights XML reader (~67x faster
    # on a 100k-vert mesh). Spatial methods and ignoreName remapping need
    # Maya's own reader, so they stay off this path.
    use_bulk = method == "index" and not ignore_names

    for target_shape in target_shapes:
        target_short = _node_short_name(target_shape)
        skip = [
            shape_short
            for shape_short in deformer_shape_shorts
            if shape_short != target_short
        ]
        if use_bulk and _bulk_apply_deformer_weights(
            deformer_name, file_path, target_shape
        ):
            continue
        import_kwargs = {
            "im": True,
            "method": method,
            "deformer": deformer_name,
            "path": directory,
            "shape": target_shape,
            "ignoreName": bool(ignore_names),
        }
        if skip:
            import_kwargs["skip"] = skip
        cmds.deformerWeights(filename, **import_kwargs)

    print(f"// WipSkin deformer import: {filename} -> {deformer_name}")
    return deformer_name


def _bulk_apply_deformer_weights(deformer_name, file_path, target_shape):
    """Apply one shape's weights via the native reader plus a bulk write.

    Returns:
        bool: False when this shape is not eligible, and the caller must
            fall back to cmds.deformerWeights.
    """
    if not xml_accel.native_available():
        return False

    target_short = _node_short_name(target_shape)
    geo_index = None
    for g_idx, _shape_long, shape_short in _list_deformer_geometries(deformer_name):
        if shape_short == target_short:
            geo_index = g_idx
            break
    if geo_index is None:
        return False

    vtx_num = cmds.polyEvaluate(target_shape, vertex=True)
    if not vtx_num:
        return False

    weights = xml_accel.native_read_deformer_weights(file_path, target_short, vtx_num)
    if weights is None:
        return False

    if not _set_weights_via_geometry_filter(deformer_name, target_shape, weights):
        plug = f"{deformer_name}.weightList[{geo_index}].weights"
        last = vtx_num - 1
        cmds.setAttr(f"{plug}[0:{last}]", *weights, size=vtx_num)
    return True


def _set_weights_via_geometry_filter(deformer_name, target_shape, weights):
    """Apply weights via MFnWeightGeometryFilter.setWeight's bulk overload.
    """
    try:
        sel = om2.MSelectionList()
        sel.add(deformer_name)
        sel.add(target_shape)
        weight_filter_fn = oma2.MFnWeightGeometryFilter(sel.getDependNode(0))
        shape_dag = sel.getDagPath(1)
        comp_fn = om2.MFnSingleIndexedComponent()
        component = comp_fn.create(om2.MFn.kMeshVertComponent)
        comp_fn.addElements(list(range(len(weights))))
        weight_filter_fn.setWeight(shape_dag, component, om2.MDoubleArray(weights))
    except (RuntimeError, TypeError):
        return False
    return True
