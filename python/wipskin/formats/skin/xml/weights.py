"""Maya deformerWeights XML skin IO."""

from __future__ import annotations

import os
import re
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
from wipskin.core.i18n import tr

EXT = "xml"
#: Sidecar "format" value for plain skin XMLs (and .wip member XMLs).
METADATA_FORMAT = "xml"
ROOT_TAG = "deformerWeight"

# Sidecar key holding cached viewer stats for a weight file.
SKIN_STATS_CACHE_KEY = "viewer_stats"

SAVED_ATTRIBUTES = [
    "skinningMethod",
    "normalizeWeights",
    "maintainMaxInfluences",
    "maxInfluences",
    "deformUserNormals",
    "relativeSpaceMode",
    "relativeSpaceMatrix",
    "dqsSupportNonRigid",
    "weightDistribution",
]

WEIGHT_PRECISION = 0.000001

SKIN_METHODS = ("classic linear", "dual quaternion", "weight blended")
NORMALIZE_WEIGHTS_LABELS = ("none", "interactive", "post")

ATTRIBUTE_LABELS = {
    "skinningMethod": "Skin method",
    "normalizeWeights": "Normalize weights",
    "maintainMaxInfluences": "Maintain max influences",
    "maxInfluences": "Max influences",
    "deformUserNormals": "Deform user normals",
    "relativeSpaceMode": "Relative space mode",
    "relativeSpaceMatrix": "Relative space matrix",
    "dqsSupportNonRigid": "DQS support non rigid",
    "weightDistribution": "Weight distribution",
}


# Not a real joint influence -- Maya's own blendWeights block (weight blended skinning).
BLEND_WEIGHTS_SOURCE = "baseLayer"


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_bool(value):
    return str(bool(int(value)))


def _float_or_none(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_skin_deformer_element(root):
    """Return the skinCluster's <deformer> element, or None.

    Exported files can contain <deformer> entries for other deformers on
    the same shape (blendShape, deltaMush, ...). Prefer type="skinCluster",
    then fall back to entries without a type attribute (older files).
    """
    untyped = None
    for element in root:
        if element.tag != "deformer":
            continue
        deformer_type = element.attrib.get("type", "")
        if deformer_type == "skinCluster":
            return element
        if deformer_type == "" and untyped is None:
            untyped = element
    return untyped


def _list_other_deformer_names(root, skin_element):
    """Return names of <deformer> entries other than the skinCluster's."""
    names = []
    for element in root:
        if element.tag != "deformer":
            continue
        if element is skin_element:
            continue
        name = element.attrib.get("name", "")
        if name:
            names.append(name)
    return names


def _list_skin_weights_elements(root, include_blend_weights=False):
    """Return <weights> elements that belong to the skinCluster, by document order."""
    skin_element = _find_skin_deformer_element(root)
    other_names = _list_other_deformer_names(root, skin_element)

    result = []
    current = None
    for element in root:
        if element.tag == "deformer":
            current = element
            continue
        if element.tag != "weights":
            continue
        if current is not None and current is not skin_element:
            continue
        if not include_blend_weights:
            if element.attrib.get("source", "") == BLEND_WEIGHTS_SOURCE:
                continue
        deformer_name = element.attrib.get("deformer", "")
        if deformer_name and deformer_name in other_names:
            continue
        result.append(element)
    return result


def _get_xml_attribute_value(root, attr_name):
    deformer = _find_skin_deformer_element(root)
    if deformer is None:
        return None
    for attr_element in deformer:
        if attr_element.tag != "attribute":
            continue
        if attr_element.attrib.get("name", "") == attr_name:
            return attr_element.attrib.get("value", "")
    return None


def _get_max_influences_from_weights(root, tolerance=WEIGHT_PRECISION):
    """Return the highest number of non-zero weights on any single vertex."""
    vert_counts = {}
    for element in _list_skin_weights_elements(root):
        for point in element:
            if point.tag != "point":
                continue
            index = _int_or_none(point.attrib.get("index"))
            if index is None:
                continue
            weight = _float_or_none(point.attrib.get("value"))
            if weight is None:
                continue
            if abs(weight) > tolerance:
                vert_counts[index] = vert_counts.get(index, 0) + 1
    if not vert_counts:
        return None
    return max(vert_counts.values())


def _get_effective_max_influences(root, tolerance=WEIGHT_PRECISION):
    """Return maxInfluences that can hold all weights in the XML.

    skinCluster.maxInfluences may be stale when maintainMaxInfluences is off.
    """
    weight_max = _get_max_influences_from_weights(root, tolerance)
    attr_max = _int_or_none(_get_xml_attribute_value(root, "maxInfluences"))

    if weight_max is None:
        return attr_max
    if attr_max is None:
        return weight_max
    return max(attr_max, weight_max)


def _set_xml_attribute(root, attr_name, attr_value):
    deformer = _find_skin_deformer_element(root)
    if deformer is None:
        return

    value_text = str(attr_value)
    for attr_element in deformer:
        if attr_element.tag != "attribute":
            continue
        if attr_element.attrib.get("name", "") == attr_name:
            attr_element.set("value", value_text)
            return
    ET.SubElement(
        deformer,
        "attribute",
        {"name": attr_name, "value": value_text},
    )


def _patch_max_influences_in_file(path, tolerance=WEIGHT_PRECISION):
    """Update maxInfluences in a skin weight XML to match its weight data."""
    return _finalize_exported_skin_xml(path, deformer_name="", tolerance=tolerance)


def _set_deformer_name_in_xml(root, deformer_name):
    changed = False
    if not deformer_name:
        return changed

    # Only rename the skinCluster's own entry, not other deformers' stubs.
    skin_element = _find_skin_deformer_element(root)
    if skin_element is not None:
        if skin_element.attrib.get("name", "") != deformer_name:
            skin_element.set("name", deformer_name)
            changed = True

    # baseLayer (blendWeights) belongs to the skinCluster; rename it too
    for element in _list_skin_weights_elements(root, include_blend_weights=True):
        if element.attrib.get("deformer", "") != deformer_name:
            element.set("deformer", deformer_name)
            changed = True
    return changed


def _set_header_filename(root, path):
    """Replace the exported <headerInfo fileName="..."> with just the base
    file name, so relocating the weight file/project later doesn't leave a
    stale absolute path behind.
    """
    basename = os.path.basename(path)
    for element in root:
        if element.tag == "headerInfo":
            if element.attrib.get("fileName", "") != basename:
                element.set("fileName", basename)
                return True
            return False
    return False


def _find_header_info_element(root):
    for element in root:
        if element.tag == "headerInfo":
            return element
    return None


def _skin_deformer_rename_needed(root, deformer_name):
    """True when _set_deformer_name_in_xml would actually change a name. Used to
    route the rare rename case to the DOM writer.
    """
    if not deformer_name:
        return False
    skin_element = _find_skin_deformer_element(root)
    if skin_element is not None and skin_element.attrib.get("name", "") != deformer_name:
        return True
    for element in _list_skin_weights_elements(root, include_blend_weights=True):
        if element.attrib.get("deformer", "") != deformer_name:
            return True
    return False


def _replace_xml_attr(line, attr_name, new_value):
    """Replace the first attr="..." occurrence on a single XML line."""
    return re.sub(
        rf'{re.escape(attr_name)}="[^"]*"',
        f'{attr_name}="{new_value}"',
        line,
        count=1,
    )


def _rewrite_skin_xml_header(path, new_filename=None, new_max_influences=None):
    """Patch only the header attributes of a skin weight XML, streaming every
    other line through untouched instead of re-serializing the whole DOM."""
    tmp_path = path + ".tegtmp"
    header_done = False
    with open(path, "r", encoding="utf-8") as src, \
            open(tmp_path, "w", encoding="utf-8") as dst:
        for line in src:
            if not header_done:
                if "<weights" in line:
                    header_done = True
                else:
                    if new_filename is not None and "<headerInfo" in line:
                        line = _replace_xml_attr(line, "fileName", new_filename)
                    if new_max_influences is not None and 'name="maxInfluences"' in line:
                        line = _replace_xml_attr(line, "value", str(new_max_influences))
            dst.write(line)
    os.replace(tmp_path, path)


def _finalize_exported_skin_xml(path, deformer_name="", tolerance=WEIGHT_PRECISION):
    """Normalize exported skin XML metadata (header fileName, maxInfluences,
    deformer rename) to match the scene nodes."""
    path = norm_path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    effective_max = _get_effective_max_influences(root, tolerance)

    header_element = _find_header_info_element(root)
    new_filename = None
    if header_element is not None:
        basename = os.path.basename(path)
        if header_element.attrib.get("fileName", "") != basename:
            new_filename = basename

    max_attr_value = _get_xml_attribute_value(root, "maxInfluences")
    new_max = None
    if effective_max is not None and _int_or_none(max_attr_value) != effective_max:
        new_max = effective_max

    rename_needed = _skin_deformer_rename_needed(root, deformer_name)
    needs_max_insert = new_max is not None and max_attr_value is None

    if rename_needed or needs_max_insert:
        changed = _set_deformer_name_in_xml(root, deformer_name)
        changed = _set_header_filename(root, path) or changed
        if new_max is not None:
            _set_xml_attribute(root, "maxInfluences", new_max)
            changed = True
        if changed:
            tree.write(path, encoding="utf-8", xml_declaration=True)
        return effective_max

    if new_filename is not None or new_max is not None:
        _rewrite_skin_xml_header(
            path, new_filename=new_filename, new_max_influences=new_max
        )
    return effective_max


def _format_skin_method(value):
    index = _int_or_none(value)
    if index is None:
        return value
    if 0 <= index < len(SKIN_METHODS):
        return SKIN_METHODS[index]
    return value


def _format_attribute_value(name, value):
    if value == "":
        return value
    if name == "skinningMethod":
        return _format_skin_method(value)
    if name == "normalizeWeights":
        index = _int_or_none(value)
        if index is not None and 0 <= index < len(NORMALIZE_WEIGHTS_LABELS):
            return NORMALIZE_WEIGHTS_LABELS[index]
        return value
    if name in ("maintainMaxInfluences", "deformUserNormals", "dqsSupportNonRigid"):
        return _format_bool(value)
    if name == "relativeSpaceMatrix":
        return value
    index = _int_or_none(value)
    if index is not None and name not in ("maxInfluences",):
        return str(index)
    return value


def _append_attribute_line(lines, label, value):
    # The English label is the identity here; only the shown text follows
    # the language.
    shown = tr(label)
    if len(value) > 72 or (label == "Relative space matrix" and " " in value):
        lines.append(f"{shown}:")
        lines.append(f"  {value}")
    else:
        lines.append(f"{shown}: {value}")


def is_skin_weight_file(path):
    """True if path is Maya skin deformerWeight XML (not wipskin deformer-weight XML)."""
    return xml_sniff.has_root_tag(path, ROOT_TAG)


def _saved_attributes_for_node(node):
    """Return SAVED_ATTRIBUTES that exist on the given deformer node."""
    result = []
    for attr_name in SAVED_ATTRIBUTES:
        if cmds.attributeQuery(attr_name, node=node, exists=True):
            result.append(attr_name)
    return result


def _apply_deformer_attribute(node, attr_name, attr_value):
    """Restore a deformer attribute from XML, skipping missing or empty values."""
    if attr_value == "":
        return
    if not cmds.attributeQuery(attr_name, node=node, exists=True):
        return

    plug = f"{node}.{attr_name}"
    attr_type = cmds.getAttr(plug, type=True)
    if attr_type == "bool":
        cmds.setAttr(plug, bool(int(attr_value)))
    elif attr_type == "matrix":
        parts = attr_value.split()
        if len(parts) != 16:
            om2.MGlobal.displayWarning(
                f"Skip invalid matrix value for {plug}"
            )
            return
        matrix = [float(part) for part in parts]
        cmds.setAttr(plug, matrix, type="matrix")
    elif attr_type in ("short", "long", "byte", "enum"):
        cmds.setAttr(plug, int(attr_value))
    elif attr_type in ("float", "double"):
        cmds.setAttr(plug, float(attr_value))
    else:
        om2.MGlobal.displayWarning(
            f"Skip unsupported attribute type for {plug}: {attr_type}"
        )


def _collect_deformer_attributes(node):
    result = []
    for attr_name in _saved_attributes_for_node(node):
        plug = f"{node}.{attr_name}"
        attr_type = cmds.getAttr(plug, type=True)
        value = cmds.getAttr(plug)
        if attr_type == "bool":
            value_str = "1" if value else "0"
        elif attr_type in ("short", "long", "byte", "enum"):
            value_str = str(int(value))
        elif attr_type in ("float", "double"):
            value_str = str(value)
        elif attr_type == "matrix":
            value_str = " ".join(str(part) for part in value)
        else:
            om2.MGlobal.displayWarning(
                f"Skip unsupported attribute type for {plug}: {attr_type}"
            )
            continue
        result.append((attr_name, attr_type, value_str))
    return result


BIND_PRE_MATRIX_CONTAINER_TAG = "bindPreMatrices"
BIND_PRE_MATRIX_TAG = "bindPreMatrix"


def _collect_bind_pre_matrices(skc):
    """Read the current bindPreMatrix for every influence on skc.

    Returns:
        dict: {influence_name: [16 floats]}.
    """
    skc_selection = om2.MSelectionList()
    skc_selection.add(skc)
    skc_fn = oma2.MFnSkinCluster(skc_selection.getDependNode(0))
    result = {}
    for inf_path in skc_fn.influenceObjects():
        index = skc_fn.indexForInfluenceObject(inf_path)
        matrix = cmds.getAttr(f"{skc}.bindPreMatrix[{index}]")
        result[inf_path.partialPathName()] = list(matrix)
    return result


def _write_bind_pre_matrices_block(path, bind_pre_matrices):
    """Add/replace the <bindPreMatrices> block in an already-written skin XML.
    """
    if not bind_pre_matrices:
        return
    tree = ET.parse(path)
    root = tree.getroot()
    existing = root.find(BIND_PRE_MATRIX_CONTAINER_TAG)
    if existing is not None:
        root.remove(existing)

    siblings = list(root)
    if siblings:
        siblings[-1].tail = "\n  "

    container = ET.SubElement(root, BIND_PRE_MATRIX_CONTAINER_TAG)
    container.text = "\n    "
    container.tail = "\n"
    entries = list(bind_pre_matrices.items())
    for index, (name, matrix) in enumerate(entries):
        element = ET.SubElement(container, BIND_PRE_MATRIX_TAG, {
            "source": name,
            "value": " ".join(str(part) for part in matrix),
        })
        element.tail = "\n    " if index < len(entries) - 1 else "\n  "
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _read_bind_pre_matrices(root):
    """Parse a <bindPreMatrices> block written by _write_bind_pre_matrices_block.

    Returns:
        dict: {influence_name: [16 floats]}. Empty when the block is absent,
            or skips any entry whose value isn't a well-formed 16-value matrix.
    """
    result = {}
    container = root.find(BIND_PRE_MATRIX_CONTAINER_TAG)
    if container is None:
        return result
    for element in container.findall(BIND_PRE_MATRIX_TAG):
        source = element.attrib.get("source", "")
        value = element.attrib.get("value", "")
        if not source or not value:
            continue
        parts = value.split()
        if len(parts) != 16:
            continue
        try:
            result[source] = [float(part) for part in parts]
        except ValueError:
            continue
    return result


def _apply_bind_pre_matrices(skc, bind_pre_matrices):
    """Overwrite bindPreMatrix on skc for every influence bind_pre_matrices covers.

    Influences the dict doesn't mention are left untouched. Safe to call
    with an empty dict.
    """
    if not bind_pre_matrices:
        return
    skc_selection = om2.MSelectionList()
    skc_selection.add(skc)
    skc_fn = oma2.MFnSkinCluster(skc_selection.getDependNode(0))
    for inf_path in skc_fn.influenceObjects():
        matrix = bind_pre_matrices.get(inf_path.partialPathName())
        if matrix is None:
            continue
        index = skc_fn.indexForInfluenceObject(inf_path)
        cmds.setAttr(f"{skc}.bindPreMatrix[{index}]", matrix, type="matrix")


def _bulk_export_skin_xml(shape, skc, full_path, file_name):
    """Write skin XML natively instead of cmds.deformerWeights(export=True).

    Returns:
        bool: True when written by the native path. False when this
            shape/skinCluster isn't eligible (non-mesh, weight blended) or
            the native module isn't available -- caller must fall back.
    """
    if cmds.nodeType(shape) != "mesh":
        return False
    if not xml_accel.native_available():
        return False
    if int(cmds.getAttr(f"{skc}.skinningMethod")) == 2:
        return False

    selection = om2.MSelectionList()
    selection.add(shape)
    shape_dag = selection.getDagPath(0)
    mesh_fn = om2.MFnMesh(shape_dag)
    num_verts = mesh_fn.numVertices

    positions = []
    for point in mesh_fn.getPoints(om2.MSpace.kWorld):
        positions.extend((point.x, point.y, point.z))

    world_matrix = list(cmds.getAttr(f"{shape}.worldMatrix[0]"))

    polygon_counts = []
    polygon_connects = []
    face_iterator = om2.MItMeshPolygon(shape_dag)
    while not face_iterator.isDone():
        verts = list(face_iterator.getVertices())
        polygon_counts.append(len(verts))
        polygon_connects.extend(verts)
        face_iterator.next()

    comp_fn = om2.MFnSingleIndexedComponent()
    component = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(num_verts)))

    skc_selection = om2.MSelectionList()
    skc_selection.add(skc)
    skc_fn = oma2.MFnSkinCluster(skc_selection.getDependNode(0))

    influence_names = [
        path.partialPathName() for path in skc_fn.influenceObjects()
    ]
    weights, _got_inf = skc_fn.getWeights(shape_dag, component)

    attributes = _collect_deformer_attributes(skc)
    shape_short = scene.get_node_leaf_name(shape)

    return xml_accel.native_write_skin_xml(
        full_path,
        file_name,
        world_matrix,
        skc,
        "skinCluster",
        attributes,
        shape_short,
        0,
        positions,
        influence_names,
        list(weights),
        -1.0,
        WEIGHT_PRECISION,
        polygon_counts,
        polygon_connects,
    )


def _uses_vertex_connections(shape_type):
    """Maya only supports -vertexConnections on mesh shapes."""
    return shape_type == "mesh"


def _normalize_import_method(method, shape):
    shape_type = cmds.nodeType(shape)
    if method in ("barycentric", "bilinear") and not _uses_vertex_connections(shape_type):
        om2.MGlobal.displayWarning(
            f"WipSkin XML: '{method}' needs vertexConnections (mesh only). "
            f"Using 'index' for {shape}."
        )
        return "index"
    return method


def _find_scene_shape(shape_name):
    """Resolve a skinnable shape long path from a name stored in skin weight XML."""
    if not shape_name:
        raise ValueError("No shape name in skin weight file.")

    shape = scene.get_skinnable_shape(shape_name)
    if shape:
        return shape

    target_leaf = scene.get_node_leaf_name(shape_name)
    for shape_type in scene.DEFORMABLE_SHAPE_TYPES:
        for candidate in cmds.ls(type=shape_type, long=True):
            if not scene.is_usable_shape(candidate):
                continue
            if scene.get_node_leaf_name(candidate) == target_leaf:
                return candidate

    raise ValueError(f"Shape not found in scene: {shape_name}")


def list_influence_sources(root) -> list:
    """Influence names carried by a skin XML root, in document order.

    Covers both places an influence name appears: the per-influence
    ``<weights source=...>`` blocks and the optional ``<bindPreMatrices>``
    entries. Maya's own blendWeights block is not an influence and is left
    out.

    Args:
        root (Element): Parsed ``<deformerWeight>`` root.

    Returns:
        list: Unique influence names.
    """
    names = []
    for element in _list_skin_weights_elements(root):
        source = element.attrib.get("source", "")
        if source and source not in names:
            names.append(source)

    container = root.find(BIND_PRE_MATRIX_CONTAINER_TAG)
    if container is not None:
        for element in container.findall(BIND_PRE_MATRIX_TAG):
            source = element.attrib.get("source", "")
            if source and source not in names:
                names.append(source)
    return names


def rename_influence_in_root(root, old_name: str, new_name: str) -> int:
    """Rewrite one influence name throughout a parsed skin XML.

    Matching is whole-value and exact, so renaming ``joint_1`` never touches
    ``joint_10``, and a namespace is just part of the name.

    Args:
        root (Element): Parsed ``<deformerWeight>`` root, edited in place.
        old_name (str): Influence name to replace.
        new_name (str): Replacement name.

    Returns:
        int: Number of attributes rewritten.
    """
    changed = 0
    for element in _list_skin_weights_elements(root):
        if element.attrib.get("source", "") == old_name:
            element.set("source", new_name)
            changed += 1

    container = root.find(BIND_PRE_MATRIX_CONTAINER_TAG)
    if container is not None:
        for element in container.findall(BIND_PRE_MATRIX_TAG):
            if element.attrib.get("source", "") == old_name:
                element.set("source", new_name)
                changed += 1
    return changed


def rename_influence(path: str, old_name: str, new_name: str) -> int:
    """Rewrite one influence name in a skin XML file, in place.

    Args:
        path (str): Skin weight XML to edit.
        old_name (str): Influence name to replace.
        new_name (str): Replacement name.

    Returns:
        int: Number of attributes rewritten; 0 leaves the file untouched.

    Raises:
        ValueError: When new_name is already used by another influence.
    """
    path = norm_path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    existing = list_influence_sources(root)
    if old_name not in existing:
        return 0

    if new_name in existing:
        raise ValueError(f"Influence already exists in this file: {new_name}")

    changed = rename_influence_in_root(root, old_name, new_name)
    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return changed


def parse_file_info(path):
    """Parse skin weight XML metadata for the file viewer, memoized by
    (mtime, size). The returned dict is treated as read-only by callers.

    Returns:
        dict: With deformer, shape, influences, attributes, path,
            saved_vert_count, mesh_vert_count.
    """
    return file_cache.memoize_by_stat(path, _parse_file_info)


def _parse_file_info(path):
    path = norm_path(path)
    cached = _read_cached_skin_stats(path)
    if cached is not None:
        return cached
    root = ET.parse(path).getroot()
    stats = _extract_skin_stats(root, path)
    _cache_skin_stats(path, stats)
    return stats


def _extract_skin_stats(root, path, tolerance=WEIGHT_PRECISION):
    """Build the viewer info dict in a single pass over the weight points."""
    info = {
        "path": path,
        "deformer": "",
        "shape": "",
        "influences": [],
        "attributes": [],
        "saved_vert_count": None,
        "mesh_vert_count": None,
    }

    skin_element = _find_skin_deformer_element(root)
    if skin_element is not None:
        info["deformer"] = skin_element.attrib.get("name", "")
        for attr_element in skin_element:
            if attr_element.tag != "attribute":
                continue
            attr_name = attr_element.attrib.get("name", "")
            if not attr_name:
                continue
            info["attributes"].append({
                "name": attr_name,
                "value": attr_element.attrib.get("value", ""),
            })

    for element in root:
        if element.tag == "shape":
            info["shape"] = element.attrib.get("name", "")
            info["mesh_vert_count"] = _int_or_none(element.attrib.get("size"))

    saved_vert_indices = set()
    vert_counts = {}
    for element in _list_skin_weights_elements(root):
        source = element.attrib.get("source", "")
        if source:
            info["influences"].append(source)
        if not info["deformer"]:
            deformer_name = element.attrib.get("deformer", "")
            if deformer_name:
                info["deformer"] = deformer_name
        for point in element:
            if point.tag != "point":
                continue
            index = _int_or_none(point.attrib.get("index"))
            if index is None:
                continue
            saved_vert_indices.add(index)
            weight = _float_or_none(point.attrib.get("value"))
            if weight is not None and abs(weight) > tolerance:
                vert_counts[index] = vert_counts.get(index, 0) + 1

    if saved_vert_indices:
        info["saved_vert_count"] = len(saved_vert_indices)

    weight_max = max(vert_counts.values()) if vert_counts else None
    info["weight_max_influences"] = weight_max

    attr_max = _int_or_none(_get_xml_attribute_value(root, "maxInfluences"))
    if weight_max is None:
        info["effective_max_influences"] = attr_max
    elif attr_max is None:
        info["effective_max_influences"] = weight_max
    else:
        info["effective_max_influences"] = max(attr_max, weight_max)

    return info


def _file_stat_stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size]


def _read_cached_skin_stats(path):
    """Return viewer stats cached in the file's sidecar, if still fresh for
    the current (mtime, size)."""
    sidecar = metadata.read_sidecar(path)
    if not sidecar:
        return None
    cache = sidecar.get(SKIN_STATS_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    info = cache.get("info")
    if not isinstance(info, dict):
        return None
    if cache.get("stamp") != _file_stat_stamp(path):
        return None
    result = dict(info)
    result["path"] = norm_path(path)
    return result


def _cache_skin_stats(path, stats):
    """Stash freshly-parsed viewer stats in the file's sidecar. Only
    augments an existing sidecar; never creates one just for browsing."""
    stamp = _file_stat_stamp(path)
    if stamp is None:
        return
    stored = {key: value for key, value in stats.items() if key != "path"}
    metadata.update_sidecar(
        path, {SKIN_STATS_CACHE_KEY: {"stamp": stamp, "info": stored}}
    )


def format_viewer_text(info):
    """Build multi-line summary text for the XML file viewer."""
    header_lines = []
    shape = info.get("shape", "")
    if shape:
        header_lines.append(tr("Mesh: {shape}", shape=shape))

    deformer = info.get("deformer", "")
    if deformer:
        header_lines.append(tr("Skin cluster: {deformer}", deformer=deformer))

    sidecar = metadata.read_sidecar(info.get("path", ""))
    header_lines.extend(metadata.format_audit_lines(sidecar))

    body_lines = []

    saved_vert_count = info.get("saved_vert_count")
    mesh_vert_count = info.get("mesh_vert_count")
    if saved_vert_count is not None or mesh_vert_count is not None:
        saved_text = str(saved_vert_count) if saved_vert_count is not None else "—"
        mesh_text = str(mesh_vert_count) if mesh_vert_count is not None else "—"
        body_lines.append(tr(
            "Saved verts: {saved} / {total}", saved=saved_text, total=mesh_text,
        ))

    body_lines.append(tr(
        "Influences: {count}", count=len(info.get("influences", [])),
    ))

    attributes = info.get("attributes", [])
    attr_values = {}
    for entry in attributes:
        attr_values[entry["name"]] = entry["value"]

    if "skinningMethod" in attr_values:
        body_lines.append(tr(
            "Skin method: {method}",
            method=_format_skin_method(attr_values["skinningMethod"]),
        ))

    for attr_name in SAVED_ATTRIBUTES:
        if attr_name == "skinningMethod":
            continue
        if attr_name not in attr_values:
            continue
        label = ATTRIBUTE_LABELS.get(attr_name, attr_name)
        value = attr_values[attr_name]
        if attr_name == "maxInfluences":
            effective_max = info.get("effective_max_influences")
            if effective_max is not None:
                value = str(effective_max)
        value = _format_attribute_value(attr_name, value)
        _append_attribute_line(body_lines, label, value)

    for entry in attributes:
        attr_name = entry["name"]
        if attr_name in SAVED_ATTRIBUTES:
            continue
        label = ATTRIBUTE_LABELS.get(attr_name, attr_name)
        value = _format_attribute_value(attr_name, entry["value"])
        _append_attribute_line(body_lines, label, value)

    if (
        saved_vert_count is not None
        and mesh_vert_count is not None
        and saved_vert_count < mesh_vert_count
    ):
        body_lines.append(
            tr("Note: partial vert export (not all mesh verts in this file)")
        )

    return metadata.join_viewer_sections(header_lines, body_lines)


def _resolve_export_filename(
    shape_name,
    directory,
    filename,
    auto_name,
    auto_version,
    multi_index=None,
):
    short_name = shape_name.rsplit("|", 1)[-1]
    if scene.is_deformable_shape_type(shape_name):
        short_name = scene.get_shape_transform(shape_name).rsplit("|", 1)[-1]
    if auto_name:
        base_name = short_name
    elif filename:
        # Strip an existing version suffix (base.NNNN.ext) before re-versioning
        base_name, _version, _ext = io.parse_versioned_filename(
            os.path.basename(filename)
        )
    else:
        base_name = short_name
    if multi_index is not None:
        base_name = io.apply_multi_export_index(base_name, multi_index)
    if auto_version:
        return os.path.basename(io.resolve_export_path(directory, base_name, EXT, True))
    if filename and not auto_name and multi_index is None:
        return os.path.basename(filename)
    return f"{base_name}.{EXT}"


def export_skin(
    mesh_names,
    directory,
    filename=None,
    auto_name=False,
    auto_version=False,
    optimize=False,
    comment=None,
    save_bind_pre_matrix=False,
):
    """Export skin weights to Maya deformerWeights XML for each skinnable shape.

    Args:
        save_bind_pre_matrix (bool): When True, also write each influence's
            current bindPreMatrix into a <bindPreMatrices> block, so a later
            import can restore it via _apply_bind_pre_matrices() instead of
            relying on the rig being at bind pose at import time.
    """
    directory = norm_path(directory)
    if not os.path.isdir(directory):
        raise ValueError(f"Invalid export directory: {directory}")

    export_jobs = []
    for item_name in mesh_names:
        shape = scene.get_skinnable_shape(item_name)
        if not shape:
            shapes = scene.list_skinnable_shapes_under(item_name)
            if not shapes:
                om2.MGlobal.displayWarning(f"No skinnable shape on: {item_name}")
                continue
            shape = shapes[0]

        skc = scene.get_skin_cluster(shape)
        if not skc:
            om2.MGlobal.displayWarning(f"No skinCluster on: {shape}")
            continue

        transform = scene.get_shape_transform(shape)
        export_jobs.append((shape, skc, transform))

    use_multi_index = (
        (not auto_name)
        and bool(filename)
        and len(export_jobs) > 1
    )

    exported_paths = []
    for job_index, (shape, skc, transform) in enumerate(export_jobs, start=1):
        if optimize:
            cmds.skinPercent(skc, transform, pruneWeights=WEIGHT_PRECISION)
            if cmds.attributeQuery("deformUserNormals", node=skc, exists=True):
                cmds.setAttr(f"{skc}.deformUserNormals", 0)

        multi_index = job_index if use_multi_index else None
        file_name = _resolve_export_filename(
            shape, directory, filename, auto_name, auto_version,
            multi_index=multi_index,
        )
        full_path = norm_path(os.path.join(directory, file_name))

        if not _bulk_export_skin_xml(shape, skc, full_path, file_name):
            export_kwargs = {
                "export": True,
                "deformer": skc,
                "path": directory,
                "attribute": _saved_attributes_for_node(skc),
                "weightPrecision": 6,
                "weightTolerance": WEIGHT_PRECISION,
                "defaultValue": -1.0,
            }
            if _uses_vertex_connections(cmds.nodeType(shape)):
                export_kwargs["vertexConnections"] = True
            cmds.deformerWeights(file_name, **export_kwargs)

        _finalize_exported_skin_xml(full_path, deformer_name=skc)
        if save_bind_pre_matrix:
            _write_bind_pre_matrices_block(full_path, _collect_bind_pre_matrices(skc))
        metadata.write_export_sidecar(
            full_path,
            METADATA_FORMAT,
            comment=comment,
            extra={
                "deformer": skc,
                "shape": cmds.ls(shape)[0],
            },
        )
        exported_paths.append(full_path)
        print(f"// WipSkin XML export: {full_path}")
    return exported_paths


def _build_weight_matrix_from_xml(root, scene_influences, num_verts):
    """Build a flat (num_verts x len(scene_influences)) weight matrix, row-major
    (vert_index * num_influences + influence_column), from the <weights>
    blocks of a Maya deformerWeights skin XML.
    """
    num_inf = len(scene_influences)
    inf_column = {name: i for i, name in enumerate(scene_influences)}
    matrix = [0.0] * (num_verts * num_inf)
    for element in _list_skin_weights_elements(root):
        column = inf_column.get(element.attrib.get("source", ""))
        if column is None:
            continue
        for point in element:
            if point.tag != "point":
                continue
            row = _int_or_none(point.attrib.get("index"))
            if row is None or row < 0 or row >= num_verts:
                continue
            value = _float_or_none(point.attrib.get("value"))
            if value is None:
                continue
            matrix[row * num_inf + column] = value
    return matrix


def _merge_add_weight_matrix(current, imported, num_verts, num_inf):
    """Add `imported` onto `current` per (vertex, influence), then renormalize
    each vertex row back to sum 1.
    """
    import numpy as np

    cur = np.asarray(current, dtype=float).reshape(num_verts, num_inf)
    inc = np.asarray(imported, dtype=float).reshape(num_verts, num_inf)

    combined = cur + inc
    totals = combined.sum(axis=1)
    nonzero = totals != 0.0
    combined[nonzero] /= totals[nonzero, None]

    return combined.reshape(-1).tolist()


def _bulk_apply_index_weights(target_shape, cur_skc, file_path, add=False):
    """Apply a skin XML's per-vertex weights to cur_skc in one MFnSkinCluster
    API call, instead of Maya's cmds.deformerWeights(im=True) XML reader.

    Args:
        add (bool): Merge into existing weights instead of overwriting; see
            _merge_add_weight_matrix.
    """
    selection = om2.MSelectionList()
    selection.add(target_shape)
    shape_dag = selection.getDagPath(0)

    mesh_fn = om2.MFnMesh(shape_dag)
    num_verts = mesh_fn.numVertices

    comp_fn = om2.MFnSingleIndexedComponent()
    component = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(num_verts)))

    skc_selection = om2.MSelectionList()
    skc_selection.add(cur_skc)
    skc_fn = oma2.MFnSkinCluster(skc_selection.getDependNode(0))

    scene_influences = [
        path.partialPathName() for path in skc_fn.influenceObjects()
    ]

    matrix = xml_accel.native_build_weight_matrix(
        file_path, scene_influences, num_verts
    )
    if matrix is None:
        root = ET.parse(file_path).getroot()
        matrix = _build_weight_matrix_from_xml(root, scene_influences, num_verts)

    if add:
        current, _ = skc_fn.getWeights(shape_dag, component)
        matrix = _merge_add_weight_matrix(
            current, matrix, num_verts, len(scene_influences)
        )

    influence_indices = om2.MIntArray(list(range(len(scene_influences))))
    weight_array = om2.MDoubleArray(matrix)
    skc_fn.setWeights(shape_dag, component, influence_indices, weight_array, False)


def import_skin(
    directory,
    filename,
    method="index",
    mode="replace",
    import_as="saved",
    shape="",
    ignore_names=False,
    normalize=True,
    restore_bind_pre_matrix=False,
):
    """Import skin weights from XML using Maya deformerWeights.

    Args:
        restore_bind_pre_matrix (bool): When True and the file has a
            <bindPreMatrices> block (see export_skin's save_bind_pre_matrix),
            overwrite bindPreMatrix on every influence it covers.
    """
    directory = norm_path(directory)
    file_path = norm_path(os.path.join(directory, filename))
    if not os.path.isfile(file_path):
        raise ValueError(f"File not found: {file_path}")

    info = parse_file_info(file_path)
    skc_name = info["deformer"]
    inf_list = list(info["influences"])
    effective_max_influences = info.get("effective_max_influences")

    if import_as == "selected":
        if shape:
            target_shape = scene.get_skinnable_shape(shape)
            if not target_shape:
                shapes = scene.list_skinnable_shapes_under(shape)
                if shapes:
                    target_shape = shapes[0]
        else:
            selection = cmds.ls(sl=True, long=True)
            if not selection:
                raise ValueError("No geometry selected for import.")
            target_shape = scene.get_skinnable_shape(selection[0])
            if not target_shape:
                shapes = scene.list_skinnable_shapes_under(selection[0])
                if shapes:
                    target_shape = shapes[0]
        if not target_shape:
            raise ValueError("No skinnable geometry selected for import.")
    else:
        target_shape = _find_scene_shape(info["shape"])

    cur_skc = scene.get_skin_cluster(target_shape)
    if not cur_skc:
        created = cmds.skinCluster(inf_list + [target_shape], name=skc_name, toSelectedBones=True)
        if isinstance(created, list):
            cur_skc = created[0]
        else:
            cur_skc = created
    else:
        current_infs = cmds.skinCluster(cur_skc, query=True, influence=True)
        if current_infs is None:
            current_infs = []
        for inf in inf_list:
            if inf not in current_infs:
                cmds.skinCluster(cur_skc, edit=True, addInfluence=inf)

    if restore_bind_pre_matrix:
        bind_pre_matrices = _read_bind_pre_matrices(ET.parse(file_path).getroot())
        _apply_bind_pre_matrices(cur_skc, bind_pre_matrices)

    if (
        effective_max_influences is not None
        and cmds.attributeQuery("maxInfluences", node=cur_skc, exists=True)
    ):
        cmds.setAttr(f"{cur_skc}.maxInfluences", effective_max_influences)

    method = _normalize_import_method(method, target_shape)

    bulk_eligible = (
        method == "index"
        and not ignore_names
        and cmds.nodeType(target_shape) == "mesh"
    )
    if mode == "add":
        if not bulk_eligible:
            raise NotImplementedError(
                "XML add mode only supports mesh shapes with the 'index' "
                "method and names honored (no ignoreNames)."
            )
        _bulk_apply_index_weights(target_shape, cur_skc, file_path, add=True)
    elif bulk_eligible:
        _bulk_apply_index_weights(target_shape, cur_skc, file_path)
    else:
        cmds.deformerWeights(
            filename,
            im=True,
            method=method,
            deformer=cur_skc,
            path=directory,
            attribute=_saved_attributes_for_node(cur_skc),
            ignoreName=bool(ignore_names),
        )

    for entry in info["attributes"]:
        attr_name = entry["name"]
        attr_value = entry["value"]
        if attr_name == "maxInfluences" and effective_max_influences is not None:
            attr_value = str(effective_max_influences)
        _apply_deformer_attribute(cur_skc, attr_name, attr_value)

    # Same post-pass as Maya's Import Deformer Weights "Normalize weights"
    if normalize:
        cmds.skinCluster(cur_skc, edit=True, forceNormalizeWeights=True)

    print(f"// WipSkin XML import: {file_path} -> {cur_skc}")
    return cur_skc
