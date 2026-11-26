"""WIP Skin (multi-layer XML pack) IO for WipSkin.

A WIP pack is a JSON `.wip` manifest plus a set of Maya deformerWeights XML
"members" (one Base + zero or more named layer groups) in a
`<base_name>_wip/` subdirectory. Import composes Base (replace) + each
enabled group's weights times its ratio (additive, not renormalized).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
import xml.etree.ElementTree as ET

from wipskin.core import io
from wipskin.core import metadata
from wipskin.core.constants import __version__
from wipskin.core.path_utils import norm_path
from wipskin.core.i18n import tr

EXT = "wip"
#: Sidecar "format" value for .wip manifests.
METADATA_FORMAT = "wip"
WIP_DIR_SUFFIX = "_wip"
SCHEMA_VERSION = 1

BASE_GROUP_LABEL = "Base"
BASE_SOURCE_SCENE = "scene"
BASE_SOURCE_EXISTING_XML = "existing_xml"
BASE_SOURCES = (BASE_SOURCE_SCENE, BASE_SOURCE_EXISTING_XML)

COMPOSE_REPLACE = "replace"
COMPOSE_RAW_ADD = "raw_add"

BASE_MEMBER_SUFFIX = "_base"
LAYER_MEMBER_SUFFIX = "_layer"

# Member XML extension. Duplicated from xml_skin.EXT (rather than imported)
# so the pure naming helpers below stay importable without Maya.
MEMBER_EXT = "xml"
# Sidecar "format" of member XMLs; duplicated from xml_skin.METADATA_FORMAT
# for the same reason.
MEMBER_METADATA_FORMAT = "xml"

DEFAULT_RATIO = 100.0
MAX_RATIO = 200.0

_INVALID_TOKEN_CHARS_RE = re.compile(r"[^0-9A-Za-z_\-]+")


# ------------------
# Naming / paths

def wip_dir_name(base_name: str) -> str:
    """Return the subdirectory name for a WIP pack (e.g. ``body_wip``).

    Args:
        base_name (str): Pack base name without version or extension.

    Returns:
        str: ``base_name`` plus ``WIP_DIR_SUFFIX``.
    """
    return f"{base_name}{WIP_DIR_SUFFIX}"


def wip_dir_path(weight_dir: str, base_name: str) -> str:
    """Return the absolute path of a WIP pack subdirectory.

    Args:
        weight_dir (str): Parent Weight directory.
        base_name (str): Pack base name.

    Returns:
        str: Normalized ``weight_dir/<base_name>_wip`` path.
    """
    return norm_path(os.path.join(weight_dir, wip_dir_name(base_name)))


def sanitize_group_token(name: str) -> str:
    """Convert a display group name into a filename-safe member token.

    Strips a trailing ``layer`` word so tokens do not become
    ``..._layer_layer`` once ``LAYER_MEMBER_SUFFIX`` is appended.

    Args:
        name (str): UI display name for a Layer group.

    Returns:
        str: Sanitized token, or ``""`` when nothing usable remains.
    """
    token = io.sanitize_export_base_name(name)
    token = _INVALID_TOKEN_CHARS_RE.sub("_", token)
    token = re.sub(r"_{2,}", "_", token).strip("_-")
    if token.lower().endswith("layer"):
        token = token[: len(token) - len("layer")].rstrip("_-")
    return token


def is_valid_group_display_name(name: str) -> bool:
    """Return whether ``name`` can be turned into a member filename token.

    Args:
        name (str): Candidate Layer group display name.

    Returns:
        bool: True when ``sanitize_group_token(name)`` is non-empty.
    """
    return bool(sanitize_group_token(name))


def base_member_filename(base_name: str, version: int = 0) -> str:
    """Return the Base member XML filename for a pack.

    Args:
        base_name (str): Pack base name.
        version (int): Version stamp. ``0`` omits the ``.NNNN`` segment.

    Returns:
        str: Filename such as ``body_base.xml`` or ``body_base.0001.xml``.
    """
    if version:
        return f"{base_name}{BASE_MEMBER_SUFFIX}.{int(version):04d}.{MEMBER_EXT}"
    return f"{base_name}{BASE_MEMBER_SUFFIX}.{MEMBER_EXT}"


def group_member_filename(base_name: str, group_name: str, version: int = 0) -> str:
    """Return a Layer member XML filename for a pack.

    Args:
        base_name (str): Pack base name.
        group_name (str): Layer group display name (sanitized into a token).
        version (int): Version stamp. ``0`` omits the ``.NNNN`` segment.

    Returns:
        str: Filename such as ``body_arm_layer.xml``.

    Raises:
        ValueError: When ``group_name`` sanitizes to an empty token.
    """
    token = sanitize_group_token(group_name)
    if not token:
        raise ValueError(f"Invalid group name for member filename: {group_name!r}")
    stem = f"{base_name}_{token}{LAYER_MEMBER_SUFFIX}"
    if version:
        return f"{stem}.{int(version):04d}.{MEMBER_EXT}"
    return f"{stem}.{MEMBER_EXT}"


def manifest_filename(base_name: str, version: int = 0) -> str:
    """Return the ``.wip`` manifest filename for a pack.

    Args:
        base_name (str): Pack base name.
        version (int): Version stamp. ``0`` omits the ``.NNNN`` segment.

    Returns:
        str: Filename such as ``body.wip`` or ``body.0001.wip``.
    """
    if version:
        return f"{base_name}.{int(version):04d}.{EXT}"
    return f"{base_name}.{EXT}"


def find_latest_manifest_filename(weight_dir: str, base_name: str) -> str:
    """Find the newest ``base_name[.NNNN].wip`` under the pack directory.

    Args:
        weight_dir (str): Parent Weight directory.
        base_name (str): Pack base name.

    Returns:
        str: Manifest filename, or ``""`` when none exists.
    """
    directory = wip_dir_path(weight_dir, base_name)
    return io.find_latest_versioned_filename(directory, base_name, EXT)


def next_export_version(weight_dir: str, base_name: str, auto_version: bool) -> int:
    """Return the version number to stamp on a new manifest and its members.

    Args:
        weight_dir (str): Parent Weight directory.
        base_name (str): Pack base name.
        auto_version (bool): When False, return ``0`` (no version suffix;
            may overwrite a previous unversioned export).

    Returns:
        int: ``0`` when auto-version is off; otherwise ``max existing + 1``.
    """
    if not auto_version:
        return 0
    directory = wip_dir_path(weight_dir, base_name)
    max_version = 0
    if os.path.isdir(directory):
        for entry in os.listdir(directory):
            parsed_base, version, parsed_ext = io.parse_versioned_filename(entry)
            if parsed_base == base_name and parsed_ext == EXT and version > max_version:
                max_version = version
    return max_version + 1


def new_group_id() -> str:
    """Return a new opaque Layer group id (hex UUID without dashes).

    Returns:
        str: 32-character hex string.
    """
    return uuid.uuid4().hex


def build_manifest(
    shape: str,
    skin_cluster: str,
    vertex_count: int,
    base_name: str,
    version: int,
    base_member: str,
    base_influences: list,
    base_source: str,
    base_source_file: str,
    groups: list,
) -> dict:
    """Build the manifest dict written to a ``.wip`` file.

    Args:
        shape (str): Mesh shape name recorded in the pack.
        skin_cluster (str): skinCluster name recorded in the pack.
        vertex_count (int): Mesh vertex count at export time.
        base_name (str): Pack base name.
        version (int): Pack version stamp (``0`` = unversioned).
        base_member (str): Base member XML filename inside the pack dir.
        base_influences (list): Influence names owned by Base.
        base_source (str): ``BASE_SOURCE_SCENE`` or ``BASE_SOURCE_EXISTING_XML``.
        base_source_file (str): Source XML basename when using Existing XML;
            otherwise ``""``.
        groups (list): Layer dicts with keys
            ``id`` / ``name`` / ``member`` / ``influences`` / optional ``ratio``.

    Returns:
        dict: Manifest payload ready for ``write_manifest``.

    Raises:
        ValueError: When ``base_source`` is not a known source constant.
    """
    if base_source not in BASE_SOURCES:
        raise ValueError(f"Invalid base_source: {base_source!r}")
    group_entries = []
    for group in groups:
        group_entries.append({
            "id": group["id"],
            "name": group["name"],
            "member": group["member"],
            "influences": list(group["influences"]),
            "ratio": float(group.get("ratio", DEFAULT_RATIO)),
            "compose": COMPOSE_RAW_ADD,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "base_name": base_name,
        "version": int(version),
        "shape": shape,
        "skin_cluster": skin_cluster,
        "vertex_count": int(vertex_count),
        "base": {
            "member": base_member,
            "influences": list(base_influences),
            "source": base_source,
            "source_file": base_source_file or "",
            "compose": COMPOSE_REPLACE,
        },
        "groups": group_entries,
        "tool_version": __version__,
    }


def write_manifest(path: str, manifest_data: dict):
    """Write manifest JSON via a temp file and ``os.replace``.

    Avoids leaving a truncated ``.wip`` if the write fails mid-stream.

    Args:
        path (str): Destination ``.wip`` path.
        manifest_data (dict): Manifest payload from ``build_manifest``.
    """
    path = norm_path(path)
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    tmp_path = f"{path}.tegtmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as file_id:
        json.dump(manifest_data, file_id, ensure_ascii=False, indent=2, sort_keys=False)
        file_id.write("\n")
    os.replace(tmp_path, path)


def validate_manifest_schema(data) -> list:
    """Validate the structural fields of a loaded manifest dict.

    Args:
        data: Parsed JSON value (expected to be a dict).

    Returns:
        list: Human-readable error strings; empty means structurally valid.
    """
    errors = []
    if not isinstance(data, dict):
        return ["Manifest is not a JSON object."]
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"Unsupported WIP schema_version: {data.get('schema_version')!r}")
    base = data.get("base")
    if not isinstance(base, dict) or not base.get("member"):
        errors.append("Manifest is missing a valid 'base' entry.")
    if not isinstance(data.get("groups"), list):
        errors.append("Manifest is missing a 'groups' list.")
    if not data.get("shape"):
        errors.append("Manifest is missing 'shape'.")
    return errors


def read_manifest(path: str) -> dict:
    """Load and validate a ``.wip`` manifest from disk.

    Args:
        path (str): Absolute or relative path to the manifest file.

    Returns:
        dict: Validated manifest payload.

    Raises:
        ValueError: When the JSON fails schema validation.
        OSError: When the file cannot be read.
        json.JSONDecodeError: When the file is not valid JSON.
    """
    path = norm_path(path)
    with open(path, encoding="utf-8") as file_id:
        data = json.load(file_id)
    errors = validate_manifest_schema(data)
    if errors:
        raise ValueError(f"Invalid WIP manifest {path}: " + "; ".join(errors))
    return data


def rename_wip_pack(weight_dir: str, old_base_name: str, new_base_name: str) -> str:
    """Rename an entire WIP pack (manifests, member XMLs, subdirectory) to
    ``new_base_name``, since a plain single-file rename would leave member
    filenames out of sync.

    Args:
        weight_dir (str): Parent Weight directory.
        old_base_name (str): Current pack base name.
        new_base_name (str): Destination pack base name.

    Returns:
        str: Newest renamed manifest as
            ``"<new_base>_wip/name.wip"`` (Files list format), or ``""``
            when the pack had no manifests.

    Raises:
        ValueError: For an empty/unchanged name or a name collision.
        OSError: When a member file referenced by a manifest is missing.
    """
    new_base_name = new_base_name.strip()
    if not new_base_name:
        raise ValueError("New base name is empty.")
    if new_base_name == old_base_name:
        raise ValueError("New base name is unchanged.")

    old_wip_dir = wip_dir_path(weight_dir, old_base_name)
    if not os.path.isdir(old_wip_dir):
        raise ValueError(f"WIP pack directory not found: {old_wip_dir}")
    new_wip_dir = wip_dir_path(weight_dir, new_base_name)
    if os.path.isdir(new_wip_dir):
        raise ValueError(f"A WIP pack directory already exists: {new_wip_dir}")

    manifest_names = []
    for entry in os.listdir(old_wip_dir):
        parsed_base, _version, parsed_ext = io.parse_versioned_filename(entry)
        if parsed_base == old_base_name and parsed_ext == EXT:
            manifest_names.append(entry)

    newest_new_name = ""
    newest_version = -1
    for manifest_name in sorted(manifest_names):
        manifest_path = os.path.join(old_wip_dir, manifest_name)
        manifest_data = read_manifest(manifest_path)
        version = int(manifest_data.get("version", 0))

        base_entry = manifest_data["base"]
        new_base_member = base_member_filename(new_base_name, version)
        if base_entry["member"] != new_base_member:
            metadata.rename_weight_with_sidecar(
                os.path.join(old_wip_dir, base_entry["member"]),
                os.path.join(old_wip_dir, new_base_member),
            )
            base_entry["member"] = new_base_member

        for group in manifest_data.get("groups", []):
            new_member = group_member_filename(new_base_name, group["name"], version)
            if group["member"] != new_member:
                metadata.rename_weight_with_sidecar(
                    os.path.join(old_wip_dir, group["member"]),
                    os.path.join(old_wip_dir, new_member),
                )
                group["member"] = new_member

        manifest_data["base_name"] = new_base_name
        write_manifest(manifest_path, manifest_data)

        new_manifest_name = manifest_filename(new_base_name, version)
        if new_manifest_name != manifest_name:
            metadata.rename_weight_with_sidecar(
                manifest_path, os.path.join(old_wip_dir, new_manifest_name)
            )

        if version > newest_version:
            newest_version = version
            newest_new_name = new_manifest_name

    os.rename(old_wip_dir, new_wip_dir)

    if not newest_new_name:
        return ""
    return f"{wip_dir_name(new_base_name)}/{newest_new_name}"


def list_pack_version_names(weight_dir: str, display_name: str) -> list:
    """Files-list names owned by one WIP manifest: its members plus itself.

    Args:
        weight_dir (str): Parent Weight directory.
        display_name (str): Files-list entry, ``"<base>_wip/name.wip"``.

    Returns:
        list: Names relative to weight_dir, manifest last so the members are
            moved or removed first.
    """
    manifest_path = norm_path(os.path.join(weight_dir, display_name))
    if not os.path.isfile(manifest_path):
        return []

    pack_dir_name = os.path.dirname(display_name)
    try:
        manifest_data = read_manifest(manifest_path)
    except (OSError, ValueError):
        # Unreadable manifest: still ours to remove, just without its members.
        return [display_name]

    members = [manifest_data["base"]["member"]]
    members.extend(group["member"] for group in manifest_data.get("groups", []))

    names = []
    for member in members:
        name = f"{pack_dir_name}/{member}" if pack_dir_name else member
        if name in names:
            continue
        if os.path.isfile(os.path.join(weight_dir, name)):
            names.append(name)

    names.append(display_name)
    return names


def list_manifest_influences(manifest: dict) -> list:
    """Influence names a manifest declares, base first then each group.

    Args:
        manifest (dict): Parsed ``.wip`` manifest.

    Returns:
        list: Unique influence names, in the order the viewer lists them.
    """
    names = list(manifest["base"]["influences"])
    for group in manifest.get("groups", []):
        for influence in group["influences"]:
            if influence not in names:
                names.append(influence)
    return names


def rename_influence(
    weight_dir: str,
    display_name: str,
    old_name: str,
    new_name: str,
) -> str:
    """Write a new pack version with one influence renamed throughout.

    Copies the selected version's manifest and member XMLs to the next
    version number, rewriting the name in both the manifest's influence
    lists and each member's ``<weights source=...>``. The source version is
    left untouched.

    Args:
        weight_dir (str): Parent Weight directory.
        display_name (str): Files-list entry, ``"<base>_wip/name.wip"``.
        old_name (str): Influence name to replace.
        new_name (str): Replacement name.

    Returns:
        str: Files-list name of the new manifest.

    Raises:
        ValueError: When the influence is absent, new_name already exists,
            or a member file referenced by the manifest is missing.
    """
    from wipskin.formats.skin.xml import weights as xml_skin

    manifest_path = norm_path(os.path.join(weight_dir, display_name))
    manifest = read_manifest(manifest_path)

    existing = list_manifest_influences(manifest)
    if old_name not in existing:
        raise ValueError(f"Influence not in this pack: {old_name}")

    if new_name in existing:
        raise ValueError(f"Influence already exists in this pack: {new_name}")

    pack_dir = os.path.dirname(manifest_path)
    base_name = manifest["base_name"]
    version = next_export_version(weight_dir, base_name, auto_version=True)

    # Copy every member to the new version first: a failure partway through
    # then leaves the source version and its manifest untouched.
    renames = [(
        manifest["base"]["member"],
        base_member_filename(base_name, version),
        manifest["base"],
    )]
    for group in manifest.get("groups", []):
        renames.append((
            group["member"],
            group_member_filename(base_name, group["name"], version),
            group,
        ))

    for old_member, new_member, entry in renames:
        src = norm_path(os.path.join(pack_dir, old_member))
        if not os.path.isfile(src):
            raise ValueError(f"Pack member is missing: {old_member}")

        dst = norm_path(os.path.join(pack_dir, new_member))
        shutil.copy2(src, dst)
        metadata.copy_sidecar(src, dst)
        xml_skin.rename_influence(dst, old_name, new_name)

        entry["member"] = new_member
        entry["influences"] = [
            new_name if influence == old_name else influence
            for influence in entry["influences"]
        ]

    manifest["version"] = version
    new_manifest_name = manifest_filename(base_name, version)
    new_manifest_path = norm_path(os.path.join(pack_dir, new_manifest_name))
    write_manifest(new_manifest_path, manifest)
    metadata.copy_sidecar(manifest_path, new_manifest_path)

    return f"{wip_dir_name(base_name)}/{new_manifest_name}"


def format_manifest_viewer_text(manifest: dict) -> str:
    """Build multi-line summary text for the WIP pack file viewer.

    Args:
        manifest (dict): Loaded manifest payload.

    Returns:
        str: Viewer text with shape/cluster header and group summary body.
    """
    header_lines = [
        tr("Shape: {shape}", shape=manifest.get("shape", "")),
        tr("Skin cluster: {cluster}", cluster=manifest.get("skin_cluster", "")),
    ]
    base = manifest.get("base", {})
    body_lines = [
        tr("Vertices: {count}", count=manifest.get("vertex_count", "")),
        tr("Base source: {source}", source=base.get("source", "")),
        tr(
            "Base influences: {count}",
            count=len(base.get("influences", [])),
        ),
        tr("Groups: {count}", count=len(manifest.get("groups", []))),
    ]
    for group in manifest.get("groups", []):
        ratio = float(group.get("ratio", DEFAULT_RATIO))
        body_lines.append(tr(
            "  - {name}: {count} influence(s), default ratio {ratio}%",
            name=group["name"],
            count=len(group["influences"]),
            ratio=f"{ratio:.0f}",
        ))
    return metadata.join_viewer_sections(header_lines, body_lines)


def is_wip_manifest_file(path: str) -> bool:
    """Return whether ``path`` is a readable, schema-valid ``.wip`` manifest.

    Args:
        path (str): Candidate file path.

    Returns:
        bool: True when the extension is ``.wip`` and ``read_manifest`` succeeds.
    """
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext != EXT:
        return False
    try:
        read_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return True


# ------------------
# Group-assignment validation (pure)

def validate_group_assignment(
    base_influences: list,
    groups: list,
    scene_influences: list,
    base_locked: bool = False,
) -> list:
    """Validate an Export dialog's influence assignment.

    Checks empty Base, duplicate group names, multi-group ownership of the
    same influence, and unassigned influences.

    Args:
        base_influences (list): Influence names assigned to Base.
        groups (list): ``(name, influences)`` pairs in export order.
        scene_influences (list): Influences currently on the skinCluster.
        base_locked (bool): True when Base comes from Existing XML (Base
            influences are fixed; only non-Base scene influences must be
            assigned to Layer groups).

    Returns:
        list: Human-readable error strings; empty list means valid.
    """
    errors = []
    if not base_influences:
        errors.append("Base group is empty.")

    seen_names = set()
    for name, _influences in groups:
        key = str(name).strip().lower()
        if not key:
            errors.append("A group name is empty.")
            continue
        if key in seen_names:
            errors.append(f"Duplicate group name: {name}")
        seen_names.add(key)

    owners_by_influence = {}
    for influence in base_influences:
        owners_by_influence.setdefault(influence, []).append(BASE_GROUP_LABEL)
    for name, influences in groups:
        for influence in influences:
            owners_by_influence.setdefault(influence, []).append(name)

    for influence, owners in owners_by_influence.items():
        if len(owners) > 1:
            errors.append(
                f"Influence assigned to multiple groups: {influence} "
                f"({', '.join(owners)})"
            )

    assignable = scene_influences
    if base_locked:
        assignable = [inf for inf in scene_influences if inf not in base_influences]
    assigned = set(owners_by_influence.keys())
    unassigned = [inf for inf in assignable if inf not in assigned]
    if unassigned:
        errors.append("Unassigned influence(s): " + ", ".join(unassigned))

    return errors


def diff_existing_base_influences(base_influences: list, scene_influences: list) -> tuple:
    """Compare Existing-XML Base influences against the scene skinCluster.

    Args:
        base_influences (list): Influences recorded in the Existing Base XML.
        scene_influences (list): Influences currently on the skinCluster.

    Returns:
        tuple: ``(missing_in_scene, new_in_scene)``.
            ``missing_in_scene`` are Base XML influences absent from the
            scene (must be resolved before export). ``new_in_scene`` are
            scene influences not covered by Base (Layer candidates).
    """
    scene_set = set(scene_influences)
    base_set = set(base_influences)
    missing_in_scene = [inf for inf in base_influences if inf not in scene_set]
    new_in_scene = [inf for inf in scene_influences if inf not in base_set]
    return missing_in_scene, new_in_scene


def validate_existing_base_xml(path: str, shape_name: str, vertex_count) -> list:
    """Validate an Existing-XML Base before copying it into a WIP pack.

    The file must be a normal skin weight XML whose shape and vertex count
    match the mesh being exported.

    Args:
        path (str): Candidate Base XML path.
        shape_name (str): Expected mesh shape name from the export selection.
        vertex_count: Expected mesh vertex count, or ``None`` to skip that check.

    Returns:
        list: Human-readable error strings; empty list means valid.
    """
    from wipskin.formats.skin.xml import weights as xml_skin

    errors = []
    if not xml_skin.is_skin_weight_file(path):
        errors.append(f"Not a skin weight XML: {path}")
        return errors
    info = xml_skin.parse_file_info(path)
    xml_shape = info.get("shape", "")
    if xml_shape and shape_name and xml_shape != shape_name:
        errors.append(
            f"Base XML shape '{xml_shape}' does not match selected mesh "
            f"'{shape_name}'."
        )
    xml_vert_count = info.get("mesh_vert_count")
    if (
        xml_vert_count is not None
        and vertex_count is not None
        and int(xml_vert_count) != int(vertex_count)
    ):
        errors.append(
            f"Base XML vertex count ({xml_vert_count}) does not match the "
            f"selected mesh ({vertex_count})."
        )
    return errors


# ------------------
# Partial XML export (pure XML filtering, no Maya)

def write_filtered_skin_xml(source_path: str, dest_path: str, keep_influences) -> int:
    """Copy a skin weight XML, keeping only selected ``<weights>`` blocks.

    Preserves shape / vertexConnections / deformer-attribute blocks so the
    member file stays a valid, self-contained deformerWeights XML.

    Args:
        source_path (str): Full skin weight XML to filter from.
        dest_path (str): Destination member XML path.
        keep_influences: Influence names whose ``<weights source=...>``
            blocks should be kept.

    Returns:
        int: Number of ``<weights>`` blocks kept.
    """
    keep = set(keep_influences)
    tree = ET.parse(source_path)
    root = tree.getroot()
    kept = 0
    for element in list(root):
        if element.tag != "weights":
            continue
        source = element.attrib.get("source", "")
        if source in keep:
            kept += 1
        else:
            root.remove(element)

    bind_pre_matrices = root.find("bindPreMatrices")
    if bind_pre_matrices is not None:
        for element in list(bind_pre_matrices):
            if element.attrib.get("source", "") not in keep:
                bind_pre_matrices.remove(element)
        if not list(bind_pre_matrices):
            root.remove(bind_pre_matrices)

    dest_path = norm_path(dest_path)
    directory = os.path.dirname(dest_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    tree.write(dest_path, encoding="utf-8", xml_declaration=True)
    return kept


def _patch_filtered_max_influences(dest_path: str):
    """Recompute ``maxInfluences`` after filtering a member XML.

    The source export value is stale once influences outside the group have
    been dropped.

    Args:
        dest_path (str): Filtered member XML path to patch in place.
    """
    from wipskin.formats.skin.xml import weights as xml_skin

    xml_skin._patch_max_influences_in_file(dest_path)


# ------------------
# Export orchestration (Maya)

def _mesh_vertex_count(shape: str) -> int:
    """Return the polygon vertex count for a mesh shape.

    Args:
        shape (str): Mesh shape DAG path or name.

    Returns:
        int: ``MFnMesh.numVertices``.
    """
    import maya.api.OpenMaya as om2

    selection = om2.MSelectionList()
    selection.add(shape)
    mesh_fn = om2.MFnMesh(selection.getDagPath(0))
    return mesh_fn.numVertices


def _scene_influences(skc: str) -> list:
    """Return influence names currently bound to a skinCluster.

    Args:
        skc (str): skinCluster node name.

    Returns:
        list: Influence names; empty list when the query returns ``None``.
    """
    from maya import cmds

    influences = cmds.skinCluster(skc, query=True, influence=True)
    if influences is None:
        return []
    return list(influences)


def export_wip(
    shape: str,
    weight_dir: str,
    base_name: str,
    base_source: str,
    groups: list,
    base_influences: list = None,
    existing_base_xml_path: str = "",
    auto_version: bool = False,
    comment: str = None,
) -> dict:
    """Export a WIP pack: filtered Base + Layer member XMLs plus their manifest.

    Args:
        shape (str): Skinned mesh shape long path.
        weight_dir (str): Weight directory (the WIP pack goes in
            weight_dir/<base_name>_wip/).
        base_source (str): BASE_SOURCE_SCENE or BASE_SOURCE_EXISTING_XML.
        groups (list): Ordered Layer groups, each with "name",
            "influences", and optional "id" / "ratio" (default 100).
        base_influences (list, optional): Required when base_source is
            BASE_SOURCE_SCENE; influences assigned to Base.
        existing_base_xml_path (str, optional): Required when base_source is
            BASE_SOURCE_EXISTING_XML; a previously-exported normal skin XML.
        auto_version (bool): When True, stamp the next ``.NNNN`` version.
        comment (str, optional): Sidecar comment written with each member
            and the manifest.

    Returns:
        dict: Keys ``manifest_path``, ``member_paths``, ``manifest``.

    Raises:
        ValueError: For unsupported shapes, missing skinCluster, invalid
            assignment, or a bad export directory.
    """
    from maya import cmds

    from wipskin.formats import scene
    from wipskin.formats.skin.xml import weights as xml_skin

    if cmds.nodeType(shape) != "mesh":
        raise ValueError(f"WIP export only supports polygon mesh shapes: {shape}")
    skc = scene.get_skin_cluster(shape)
    if not skc:
        raise ValueError(f"No skinCluster on: {shape}")
    if base_source not in BASE_SOURCES:
        raise ValueError(f"Invalid base_source: {base_source!r}")

    scene_influences = _scene_influences(skc)
    group_pairs = [(group["name"], list(group["influences"])) for group in groups]

    if base_source == BASE_SOURCE_SCENE:
        if not base_influences:
            raise ValueError("Base group is empty.")
        errors = validate_group_assignment(
            base_influences, group_pairs, scene_influences, base_locked=False
        )
        if errors:
            raise ValueError("Invalid WIP group assignment: " + "; ".join(errors))
    else:
        if not existing_base_xml_path or not os.path.isfile(existing_base_xml_path):
            raise ValueError(f"Base XML not found: {existing_base_xml_path}")
        base_info = xml_skin.parse_file_info(existing_base_xml_path)
        base_influences = list(base_info["influences"])
        vertex_count = _mesh_vertex_count(shape)
        errors = validate_existing_base_xml(
            existing_base_xml_path, base_info.get("shape", ""), vertex_count
        )
        missing_in_scene, _new_in_scene = diff_existing_base_influences(
            base_influences, scene_influences
        )
        if missing_in_scene:
            errors.append(
                "Base XML influence(s) not on the current skinCluster: "
                + ", ".join(missing_in_scene)
            )
        errors.extend(
            validate_group_assignment(
                base_influences, group_pairs, scene_influences, base_locked=True
            )
        )
        if errors:
            raise ValueError("Invalid WIP group assignment: " + "; ".join(errors))

    weight_dir = norm_path(weight_dir)
    if not os.path.isdir(weight_dir):
        raise ValueError(f"Invalid export directory: {weight_dir}")
    wip_dir = wip_dir_path(weight_dir, base_name)
    if not os.path.isdir(wip_dir):
        os.makedirs(wip_dir)
    version = next_export_version(weight_dir, base_name, auto_version)

    member_paths = []
    tmp_path = None
    try:
        needs_scene_export = base_source == BASE_SOURCE_SCENE or bool(groups)
        if needs_scene_export:
            tmp_name = f"__wip_tmp_{base_name}.{xml_skin.EXT}"
            [tmp_path] = xml_skin.export_skin(
                [shape], wip_dir, filename=tmp_name,
                auto_name=False, auto_version=False, optimize=False,
                save_bind_pre_matrix=True,
            )

        base_member = base_member_filename(base_name, version)
        base_path = norm_path(os.path.join(wip_dir, base_member))
        if base_source == BASE_SOURCE_SCENE:
            write_filtered_skin_xml(tmp_path, base_path, base_influences)
            _patch_filtered_max_influences(base_path)
            metadata.write_export_sidecar(
                base_path, MEMBER_METADATA_FORMAT, comment=comment,
                extra={"deformer": skc, "shape": cmds.ls(shape)[0]},
            )
        else:
            import shutil
            shutil.copy2(existing_base_xml_path, base_path)
            metadata.write_export_sidecar(
                base_path, MEMBER_METADATA_FORMAT, comment=comment,
                extra={
                    "deformer": skc,
                    "shape": cmds.ls(shape)[0],
                    "wip_base_source_file": os.path.basename(existing_base_xml_path),
                },
            )
        member_paths.append(base_path)

        group_entries = []
        for group in groups:
            member = group_member_filename(base_name, group["name"], version)
            member_path = norm_path(os.path.join(wip_dir, member))
            write_filtered_skin_xml(tmp_path, member_path, group["influences"])
            _patch_filtered_max_influences(member_path)
            metadata.write_export_sidecar(
                member_path, MEMBER_METADATA_FORMAT, comment=comment,
                extra={"deformer": skc, "shape": cmds.ls(shape)[0]},
            )
            member_paths.append(member_path)
            group_entries.append({
                "id": group.get("id") or new_group_id(),
                "name": group["name"],
                "member": member,
                "influences": list(group["influences"]),
                "ratio": float(group.get("ratio", DEFAULT_RATIO)),
            })

        if base_source == BASE_SOURCE_SCENE:
            shape_name = xml_skin.parse_file_info(base_path).get("shape", "")
        else:
            shape_name = base_info.get("shape", "")

        manifest_data = build_manifest(
            shape=shape_name,
            skin_cluster=skc,
            vertex_count=_mesh_vertex_count(shape),
            base_name=base_name,
            version=version,
            base_member=base_member,
            base_influences=base_influences,
            base_source=base_source,
            base_source_file=(
                os.path.basename(existing_base_xml_path)
                if base_source == BASE_SOURCE_EXISTING_XML else ""
            ),
            groups=group_entries,
        )
        manifest_name = manifest_filename(base_name, version)
        manifest_path = norm_path(os.path.join(wip_dir, manifest_name))
        write_manifest(manifest_path, manifest_data)
        metadata.write_export_sidecar(
            manifest_path, METADATA_FORMAT, comment=comment,
            extra={"deformer": skc, "shape": manifest_data["shape"]},
        )
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.remove(tmp_path)
            metadata.delete_sidecar(tmp_path)

    return {
        "manifest_path": manifest_path,
        "member_paths": member_paths,
        "manifest": manifest_data,
    }


# Import validation + compose (Maya)

def resolve_wip_shape(manifest: dict, shape_override: str = "") -> str:
    """Resolve the scene mesh shape a WIP pack targets.

    Args:
        manifest (dict): Loaded manifest payload.
        shape_override (str): Selected shape to prefer over the recorded name.
            Empty string means use the manifest shape.

    Returns:
        str: Scene shape path/name.

    Raises:
        ValueError: When the recorded shape cannot be found in the scene.
    """
    if shape_override:
        return shape_override
    from wipskin.formats.skin.xml import weights as xml_skin

    return xml_skin._find_scene_shape(manifest.get("shape", ""))


def _member_path(wip_dir: str, member_name: str) -> str:
    """Join a pack directory and member filename into a normalized path.

    Args:
        wip_dir (str): Pack subdirectory path.
        member_name (str): Base or Layer member filename.

    Returns:
        str: Normalized absolute/relative member path.
    """
    return norm_path(os.path.join(wip_dir, member_name))


def _enabled_groups(manifest: dict, enabled_group_ids) -> list:
    """Return Layer group entries whose ids are enabled for import.

    Args:
        manifest (dict): Loaded manifest payload.
        enabled_group_ids: Iterable of group id strings to include.

    Returns:
        list: Matching group dicts in manifest order.
    """
    enabled_ids = set(enabled_group_ids)
    return [group for group in manifest.get("groups", []) if group["id"] in enabled_ids]


def validate_import(
    directory: str,
    filename: str,
    enabled_group_ids,
    group_ratios: dict = None,
    shape_override: str = "",
) -> list:
    """Validate a WIP pack before Import edits the scene.

    Args:
        directory (str): Directory containing the ``.wip`` manifest.
        filename (str): Manifest filename (not a full path).
        enabled_group_ids (iterable): Layer group ids that will be composed.
        group_ratios (dict, optional): ``{group_id: ratio}`` overrides in the
            0..100 UI range. Missing ids fall back to the manifest ratio.
        shape_override (str, optional): Mesh shape to target instead of the
            shape recorded in the manifest.

    Returns:
        list: Human-readable error strings; empty list means OK to proceed.
    """
    from maya import cmds

    from wipskin.formats.skin.xml import weights as xml_skin

    errors = []
    path = norm_path(os.path.join(directory, filename))
    try:
        manifest = read_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"Failed to read WIP manifest: {exc}"]

    wip_dir = os.path.dirname(path)
    if group_ratios is None:
        group_ratios = {}

    base = manifest["base"]
    base_path = _member_path(wip_dir, base["member"])
    if not os.path.isfile(base_path):
        errors.append(f"Missing Base member XML: {base['member']}")

    active_groups = _enabled_groups(manifest, enabled_group_ids)
    for group in active_groups:
        ratio = float(group_ratios.get(group["id"], group.get("ratio", DEFAULT_RATIO)))
        if ratio < 0.0 or ratio > MAX_RATIO:
            errors.append(
                f"Ratio out of range (0-{MAX_RATIO:.0f}) for group "
                f"'{group['name']}': {ratio}"
            )
        member_path = _member_path(wip_dir, group["member"])
        if not os.path.isfile(member_path):
            errors.append(f"Missing member XML for group '{group['name']}': {group['member']}")

    try:
        shape = resolve_wip_shape(manifest, shape_override)
    except ValueError as exc:
        errors.append(str(exc))
        shape = ""

    if shape:
        if cmds.nodeType(shape) != "mesh":
            errors.append(f"Target shape is not a polygon mesh: {shape}")
        else:
            vertex_count = _mesh_vertex_count(shape)
            manifest_vertex_count = manifest.get("vertex_count")
            if (
                manifest_vertex_count is not None
                and int(manifest_vertex_count) != vertex_count
            ):
                errors.append(
                    "Vertex count mismatch: manifest recorded "
                    f"{manifest_vertex_count}, scene mesh has {vertex_count}."
                )

    needed_influences = list(base["influences"])
    for group in active_groups:
        for influence in group["influences"]:
            if influence not in needed_influences:
                needed_influences.append(influence)
    missing_influences = [
        influence for influence in needed_influences if not cmds.objExists(influence)
    ]
    if missing_influences:
        errors.append(
            "Influence(s) not in the scene: " + ", ".join(missing_influences)
        )

    if os.path.isfile(base_path):
        base_xml_influences = set(xml_skin.parse_file_info(base_path)["influences"])
        recorded = set(base["influences"])
        if base_xml_influences != recorded:
            errors.append(
                "Base member XML influences do not match the manifest record."
            )
    for group in active_groups:
        member_path = _member_path(wip_dir, group["member"])
        if not os.path.isfile(member_path):
            continue
        xml_influences = set(xml_skin.parse_file_info(member_path)["influences"])
        recorded = set(group["influences"])
        if xml_influences != recorded:
            errors.append(
                f"Group '{group['name']}' member XML influences do not match "
                "the manifest record."
            )

    return errors


def _build_group_weight_matrix(member_path, scene_influences, num_verts):
    """Build a flat row-major weight matrix from one WIP member XML.

    Args:
        member_path (str): Absolute path to a Base or Layer member XML.
        scene_influences (list): Influence names in skinCluster order. Columns
            missing from the XML are filled with 0.0.
        num_verts (int): Vertex count of the target mesh.

    Returns:
        list: Flat ``num_verts * len(scene_influences)`` weight values.
    """
    from wipskin.formats.skin.xml import weights as xml_skin

    root = ET.parse(member_path).getroot()
    return xml_skin._build_weight_matrix_from_xml(root, scene_influences, num_verts)


def _compose_weight_matrix(base_matrix, weighted_matrices, num_verts, num_inf) -> list:
    """Add Layer matrices onto Base without per-vertex renormalization.

    Computes ``base + sum(matrix * ratio)`` for each ``(matrix, ratio)`` pair.
    Ratio must already be in the 0..1 range (UI percent divided by 100).

    Args:
        base_matrix (list): Flat Base weights, length ``num_verts * num_inf``.
        weighted_matrices (list): ``(matrix, ratio)`` pairs. Each matrix matches
            ``base_matrix`` shape; ``ratio <= 0`` pairs are skipped.
        num_verts (int): Vertex count.
        num_inf (int): Influence count (skinCluster column count).

    Returns:
        list: Flat composed weights, same length as ``base_matrix``.
    """
    import numpy as np

    result = np.asarray(base_matrix, dtype=float).reshape(num_verts, num_inf).copy()
    for matrix, ratio in weighted_matrices:
        if ratio <= 0.0:
            continue
        result += np.asarray(matrix, dtype=float).reshape(num_verts, num_inf) * ratio
    return result.reshape(-1).tolist()


def prepare_wip_compose(directory: str, filename: str, shape_override: str = "") -> dict:
    """One-time setup shared by every apply_wip_compose() call for a session.

    Args:
        directory (str): Directory containing the ``.wip`` manifest.
        filename (str): Manifest filename (not a full path).
        shape_override (str, optional): Mesh shape to target instead of the
            shape recorded in the manifest.

    Returns:
        dict: Opaque context for apply_wip_compose()/finalize_wip_compose().
    """
    from maya import cmds
    import maya.api.OpenMaya as om2
    import maya.api.OpenMayaAnim as oma2

    from wipskin.formats import scene
    from wipskin.formats.skin.xml import weights as xml_skin

    path = norm_path(os.path.join(directory, filename))
    manifest = read_manifest(path)
    wip_dir = os.path.dirname(path)

    shape = resolve_wip_shape(manifest, shape_override)
    transform = scene.get_shape_transform(shape)
    base = manifest["base"]
    all_groups = manifest.get("groups", [])

    # Every group's influences, not just enabled ones, so a scene edit isn't
    # needed later if the enabled set changes.
    needed_influences = list(base["influences"])
    for group in all_groups:
        for influence in group["influences"]:
            if influence not in needed_influences:
                needed_influences.append(influence)

    skc = scene.get_skin_cluster(shape)
    if not skc:
        skc_name = manifest.get("skin_cluster")
        skc_kwargs = {"toSelectedBones": True}
        if skc_name:
            skc_kwargs["name"] = skc_name
        created = cmds.skinCluster(needed_influences + [transform], **skc_kwargs)
        skc = created[0] if isinstance(created, list) else created
    else:
        current_influences = cmds.skinCluster(skc, query=True, influence=True)
        if current_influences is None:
            current_influences = []
        for influence in needed_influences:
            if influence not in current_influences:
                cmds.skinCluster(skc, edit=True, addInfluence=influence)

    # A locked influence (Paint Skin Weights "Lock Weights") silently ignores
    # setWeights() in apply_wip_compose().
    for influence in needed_influences:
        cmds.skinCluster(skc, edit=True, influence=influence, lockWeights=False)

    # Restore bindPreMatrix (captured by export_wip) instead of trusting
    # Maya's auto-assigned bind reference, which is wrong for controller-driven joints.
    bind_pre_matrices = {}
    member_names = [base["member"]] + [group["member"] for group in all_groups]
    for member_name in member_names:
        member_path = _member_path(wip_dir, member_name)
        if not os.path.isfile(member_path):
            continue
        bind_pre_matrices.update(
            xml_skin._read_bind_pre_matrices(ET.parse(member_path).getroot())
        )
    xml_skin._apply_bind_pre_matrices(skc, bind_pre_matrices)

    # shape_dag/skc_fn aren't cached in the context -- apply_wip_compose()
    # re-resolves them from the name strings each call, since a long-lived
    # MDagPath/MFnSkinCluster can go stale mid-session.
    selection = om2.MSelectionList()
    selection.add(shape)
    shape_dag = selection.getDagPath(0)
    mesh_fn = om2.MFnMesh(shape_dag)
    num_verts = mesh_fn.numVertices

    skc_selection = om2.MSelectionList()
    skc_selection.add(skc)
    skc_fn = oma2.MFnSkinCluster(skc_selection.getDependNode(0))
    scene_influences = [
        inf_path.partialPathName() for inf_path in skc_fn.influenceObjects()
    ]
    num_inf = len(scene_influences)

    base_matrix = _build_group_weight_matrix(
        _member_path(wip_dir, base["member"]), scene_influences, num_verts
    )

    # cache every group member's weight matrix, not just enabled ones
    group_matrices = {}
    for group in all_groups:
        group_matrices[group["id"]] = _build_group_weight_matrix(
            _member_path(wip_dir, group["member"]), scene_influences, num_verts
        )

    return {
        "skc": skc,
        "shape": shape,
        "num_verts": num_verts,
        "num_inf": num_inf,
        "base_matrix": base_matrix,
        "group_matrices": group_matrices,
        "manifest": manifest,
        "path": path,
    }


def apply_wip_compose(context: dict, enabled_group_ids, group_ratios: dict = None):
    """Fast per-tick apply: compose cached matrices and write weights once.

    Args:
        context (dict): Result of prepare_wip_compose().
        enabled_group_ids (iterable): Layer group ids to include. Base is
            always applied.
        group_ratios (dict, optional): ``{group_id: ratio}`` overrides in the
            0..100 UI range. Missing ids fall back to the manifest ratio.
    """
    import maya.api.OpenMaya as om2
    import maya.api.OpenMayaAnim as oma2

    if group_ratios is None:
        group_ratios = {}
    enabled_ids = set(enabled_group_ids)

    weighted_matrices = []
    for group in context["manifest"].get("groups", []):
        if group["id"] not in enabled_ids:
            continue
        matrix = context["group_matrices"].get(group["id"])
        if matrix is None:
            continue
        ratio = float(group_ratios.get(group["id"], group.get("ratio", DEFAULT_RATIO)))
        weighted_matrices.append((matrix, ratio / 100.0))

    composed = _compose_weight_matrix(
        context["base_matrix"], weighted_matrices, context["num_verts"], context["num_inf"]
    )

    # Re-resolve the live API handles fresh every call (see
    # prepare_wip_compose's comment) instead of trusting cached ones.
    selection = om2.MSelectionList()
    selection.add(context["shape"])
    shape_dag = selection.getDagPath(0)
    comp_fn = om2.MFnSingleIndexedComponent()
    component = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(context["num_verts"])))
    skc_selection = om2.MSelectionList()
    skc_selection.add(context["skc"])
    skc_fn = oma2.MFnSkinCluster(skc_selection.getDependNode(0))

    influence_indices = om2.MIntArray(list(range(context["num_inf"])))
    weight_array = om2.MDoubleArray(composed)
    skc_fn.setWeights(shape_dag, component, influence_indices, weight_array, False)


def finalize_wip_compose(context: dict, normalize_interactive: bool = False):
    """Apply the final normalizeWeights mode after one or more applies.

    Args:
        context (dict): Result of prepare_wip_compose().
        normalize_interactive (bool): When False (default), leave composed
            values as raw Post weights (``normalizeWeights=Post``). When True,
            force-normalize per vertex and set ``normalizeWeights=Interactive``.
    """
    from maya import cmds

    skc = context["skc"]
    has_normalize_attr = cmds.attributeQuery("normalizeWeights", node=skc, exists=True)
    if normalize_interactive:
        if has_normalize_attr:
            cmds.setAttr(f"{skc}.normalizeWeights", 1)  # interactive
        cmds.skinCluster(skc, edit=True, forceNormalizeWeights=True)
    elif has_normalize_attr:
        cmds.setAttr(f"{skc}.normalizeWeights", 2)  # post


def compose_wip(
    directory: str,
    filename: str,
    enabled_group_ids,
    group_ratios: dict = None,
    shape_override: str = "",
    normalize_interactive: bool = False,
) -> str:
    """Compose a WIP pack onto the scene skinCluster in a single call.

    Args:
        directory (str): Directory containing the ``.wip`` manifest.
        filename (str): Manifest filename (not a full path).
        enabled_group_ids (iterable): Layer group ids to include. Base is
            always applied.
        group_ratios (dict, optional): ``{group_id: ratio}`` overrides in the
            0..100 UI range. Missing ids fall back to the manifest ratio.
        shape_override (str, optional): Mesh shape to target instead of the
            shape recorded in the manifest.
        normalize_interactive (bool): When False (default), leave composed
            values as raw Post weights (``normalizeWeights=Post``). When True,
            force-normalize per vertex and set ``normalizeWeights=Interactive``.

    Returns:
        str: The skinCluster name that received the composed weights.
    """
    context = prepare_wip_compose(directory, filename, shape_override=shape_override)
    apply_wip_compose(context, enabled_group_ids, group_ratios)
    finalize_wip_compose(context, normalize_interactive)
    print(f"// WipSkin WIP import: {context['path']} -> {context['skc']}")
    return context["skc"]
