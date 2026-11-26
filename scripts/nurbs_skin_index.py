import os
import re
import xml.etree.ElementTree as ET
from maya import cmds


def list_shapes():
    nodes = cmds.ls(sl=True, l=True)
    if not nodes:
        return []

    shapes = []
    seen = set()
    shape_types = ("mesh", "nurbsCurve", "nurbsSurface")
    for node in nodes:
        targets = []
        for shape_type in shape_types:
            if cmds.objectType(node, isa=shape_type):
                targets.append(node)
                break

        for shape_type in shape_types:
            children = cmds.listRelatives(node, ad=True, f=True, ni=True, typ=shape_type)
            if not children:
                continue

            targets.extend(children)

        for shape in targets:
            if shape in seen:
                continue

            if cmds.attributeQuery("intermediateObject", node=shape, exists=True):
                if cmds.getAttr(shape + ".intermediateObject"):
                    continue

            seen.add(shape)
            shapes.append(shape)
    return shapes


def get_skin(shape):
    history = cmds.listHistory(shape, pdo=True)
    if not history:
        return ""

    skins = cmds.ls(history, typ="skinCluster")
    if not skins:
        return ""

    return skins[0]


def read_skin_file(file_path):
    root = ET.parse(file_path).getroot()
    skin_name = ""
    xml_shape = ""
    max_influences = None
    for element in root:
        if element.tag == "shape" and not xml_shape:
            xml_shape = element.attrib.get("name", "")

    for element in root:
        if element.tag != "deformer" or element.attrib.get("type", "") != "skinCluster":
            continue

        skin_name = element.attrib.get("name", "")
        for attr in element:
            if attr.tag != "attribute" or attr.attrib.get("name") != "maxInfluences":
                continue

            value = attr.attrib.get("value", "")
            if value.lstrip("-").isdigit():
                max_influences = int(value)
        break

    influences = []
    seen = set()
    for element in root:
        if element.tag != "weights":
            continue

        if skin_name and element.attrib.get("deformer", "") != skin_name:
            continue

        source = element.attrib.get("source", "")
        if not source or source == "baseLayer" or source in seen:
            continue

        seen.add(source)
        influences.append(source)
    return skin_name, xml_shape, influences, max_influences


def list_scene_influences(influences):
    found = []
    for name in influences:
        if cmds.objExists(name):
            found.append(name)
            continue

        cmds.warning("Missing influence: %s" % name)
    return found


def create_skin(shape, skin_name, influences, max_influences):
    kwargs = {"toSelectedBones": True}
    if skin_name:
        kwargs["name"] = skin_name

    if max_influences is not None:
        kwargs["maximumInfluences"] = max_influences

    created = cmds.skinCluster(influences + [shape], **kwargs)
    if isinstance(created, list):
        return created[0]
    return created


def is_intermediate(node):
    if not cmds.attributeQuery("intermediateObject", node=node, exists=True):
        return False
    return bool(cmds.getAttr(node + ".intermediateObject"))


def get_scene_shape(shape_name):
    if not shape_name:
        cmds.warning("No shape name in file.")
        return ""

    found = cmds.ls(shape_name, l=True)
    if found and len(found) == 1:
        node = found[0]
        if cmds.objectType(node, isa="transform"):
            for shape_type in ("mesh", "nurbsCurve", "nurbsSurface"):
                children = cmds.listRelatives(node, s=True, f=True, ni=True, typ=shape_type)
                if not children:
                    continue
                return children[0]
        elif not is_intermediate(node):
            return node

    leaf = shape_name.rsplit("|", 1)[-1]
    bare = leaf.split(":")[-1]
    matches = []
    for shape_type in ("mesh", "nurbsCurve", "nurbsSurface"):
        nodes = cmds.ls(typ=shape_type, l=True)
        if not nodes:
            continue

        for node in nodes:
            if is_intermediate(node):
                continue

            node_leaf = node.rsplit("|", 1)[-1]
            if node_leaf == leaf or node_leaf.split(":")[-1] == bare:
                matches.append(node)

    unique = []
    seen = set()
    for node in matches:
        if node in seen:
            continue
        seen.add(node)
        unique.append(node)

    if len(unique) == 1:
        return unique[0]

    if len(unique) > 1:
        cmds.warning("Multiple shapes named %s" % shape_name)
        return ""

    cmds.warning("Shape not in scene: %s" % shape_name)
    return ""


def file_name(shape):
    short = cmds.ls(shape)[0]
    return short.replace("|", "_").replace(":", "_") + ".xml"


def export_skin(directory):
    if not os.path.isdir(directory):
        raise RuntimeError("Not a directory: %s" % directory)

    for shape in list_shapes():
        skin = get_skin(shape)
        if not skin:
            cmds.warning("No skinCluster: %s" % shape)
            continue

        name = file_name(shape)
        cmds.deformerWeights(name, ex=True, df=skin, sh=shape, p=directory, wp=6)
        print(os.path.join(directory, name))


def import_skin(file_path):
    if not os.path.isfile(file_path):
        raise RuntimeError("Not a file: %s" % file_path)

    directory, name = os.path.split(file_path)
    skin_name, xml_shape, influences, max_influences = read_skin_file(file_path)
    shape = get_scene_shape(xml_shape)
    if not shape:
        return

    scene_influences = list_scene_influences(influences)
    skin = get_skin(shape)
    if not skin and not scene_influences:
        cmds.warning("No influences from file found in the scene: %s" % file_path)
        return

    cmds.undoInfo(openChunk=True)
    try:
        if not skin:
            skin = create_skin(shape, skin_name, scene_influences, max_influences)

        scene_shape = cmds.ls(shape)[0]
        import_kwargs = {
            "im": True,
            "method": "index",
            "deformer": skin,
            "path": directory,
        }
        if xml_shape and xml_shape != scene_shape:
            import_kwargs["shape"] = scene_shape
            import_kwargs["remap"] = "%s;%s" % (re.escape(xml_shape), scene_shape)

        imported = cmds.deformerWeights(name, **import_kwargs)
        if not imported:
            cmds.warning("Import applied nothing: %s -> %s" % (file_path, skin))
            return

        cmds.skinCluster(skin, e=True, fnw=True)
        print("%s -> %s" % (file_path, shape))
    finally:
        cmds.undoInfo(closeChunk=True)


#export_skin("ここに書き出し先ディレクトリパス")
#import_skin("ここに読み込み元XMLパス")