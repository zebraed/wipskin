"""mGear skin IO wrapper (optional dependency)."""

from __future__ import annotations

import json
import os

from wipskin.api import metadata
from wipskin.api import io
from wipskin.api import file_cache
from wipskin.api import norm_path
from wipskin.api import tr

EXT_JSKIN = "jSkin"
EXT_GSKIN = "gSkin"
# MEMO: mGear manifest is always .gSkinPack; use_json selects .jSkin vs .gSkin members
EXT_JSKIN_PACK = "jSkinPack"
EXT_GSKIN_PACK = "gSkinPack"
MGEAR_PACK_EXT = ".gSkinPack"

FILE_EXTENSIONS = (EXT_JSKIN, EXT_GSKIN, EXT_JSKIN_PACK, EXT_GSKIN_PACK)
PACK_EXTENSIONS = (EXT_JSKIN_PACK, EXT_GSKIN_PACK)
#: Sidecar "format" value for skin files and packs alike.
METADATA_FORMAT = "mgear"
#: Sidecar keys this format writes beyond the shared ones, for the viewer.
AUDIT_FIELDS = (("mGear version", "mgear_version"),)

# What the pack editor can do with one member.
PACK_ACTION_KEEP = "keep"
PACK_ACTION_LATEST = "latest"
PACK_ACTION_REEXPORT = "reexport"
PACK_ACTION_FILE = "file"


def is_available():
    try:
        import mgear.core.skin  # noqa: F401
        return True
    except ImportError:
        return False


def _skin_module():
    import mgear.core.skin as mgear_skin_mod
    return mgear_skin_mod


def _require_mgear():
    if not is_available():
        raise ImportError(
            "mGear is not installed. Install mGear 4.x to use the mGear skin format."
        )


def list_export_transforms(shape_names):
    """Convert skinnable shape paths (mesh/nurbsCurve/nurbsSurface/lattice, or
    already-resolved transforms) to transform DAG paths.

    mGear exportSkin / exportSkinPack expect transform nodes, not shape nodes.
    """
    from maya import cmds

    from wipskin.api.maya import scene

    transforms = []
    seen = set()
    for name in shape_names:
        if not name:
            continue
        node_type = cmds.nodeType(name)
        if node_type in scene.DEFORMABLE_SHAPE_TYPES:
            parents = cmds.listRelatives(name, parent=True, fullPath=True)
            if not parents:
                continue
            transform = parents[0]
        else:
            transform = name
        if transform in seen:
            continue
        seen.add(transform)
        transforms.append(transform)
    return transforms


def _as_export_pynodes(shape_names):
    import mgear.pymaya as pm

    transform_names = list_export_transforms(shape_names)
    if not transform_names:
        return []
    return [pm.PyNode(name) for name in transform_names]


def _normalize_skin_path(file_path, use_json):
    base, ext = os.path.splitext(file_path)
    if use_json:
        if ext.lower() != ".jskin":
            return base + ".jSkin"
    else:
        if ext.lower() != ".gskin":
            return base + ".gSkin"
    return file_path


def _normalize_pack_path(pack_path):
    """mGear exportSkinPack accepts only .gSkinPack manifest paths.

    use_json controls whether member files are .jSkin or .gSkin.
    """
    base, ext = os.path.splitext(pack_path)
    if ext.lower() != ".gskinpack":
        return base + MGEAR_PACK_EXT
    return pack_path


def list_gskin_pack_base_names(directory):
    """Return sorted base names of .gSkinPack files in directory (no extension)."""
    return io.list_base_names_for_extension(directory, EXT_GSKIN_PACK)


def sanitize_pack_base_name(name):
    """Strip pack extension / path / illegal filename characters from a typed name.

    Returns:
        str: Empty string when nothing usable remains.
    """
    return io.sanitize_export_base_name(
        name,
        strip_extensions=(EXT_GSKIN_PACK, EXT_JSKIN_PACK),
    )


def get_mgear_version():
    """Return the installed mGear version string, or empty when unavailable."""
    try:
        import mgear
        return str(mgear.getVersion())
    except Exception:
        return ""


def _short_node_name(node_name):
    short = str(node_name).rsplit("|", 1)[-1]
    if ":" in short:
        short = short.rsplit(":", 1)[-1]
    return short


def describe_pack_member(directory, recorded_name):
    """Build Member View fields for one packFiles entry.

    Display uses "recorded -> latestVer" when a newer version exists.
    """
    recorded_name = os.path.basename(str(recorded_name or "").strip())
    base_name, recorded_version, ext = io.parse_versioned_filename(recorded_name)
    latest_name = io.find_latest_versioned_filename(directory, base_name, ext)
    latest_version = 0
    if latest_name:
        _latest_base, latest_version, _latest_ext = io.parse_versioned_filename(
            latest_name
        )
    display = recorded_name
    if latest_name and latest_version > recorded_version:
        display = f"{recorded_name} -> {int(latest_version):04d}"
    recorded_path = os.path.join(directory, recorded_name) if directory else ""
    latest_path = os.path.join(directory, latest_name) if latest_name else ""
    return {
        "recorded": recorded_name,
        "latest": latest_name,
        "recorded_version": recorded_version,
        "latest_version": latest_version,
        "display": display,
        "recorded_exists": bool(recorded_path and os.path.isfile(recorded_path)),
        "latest_exists": bool(latest_path and os.path.isfile(latest_path)),
    }


def list_pack_member_base_names(pack_path):
    """Return geometry base names from a .gSkinPack packFiles list.

    Args:
        pack_path (str): Path to a .gSkinPack / .jSkinPack manifest.

    Returns:
        list: Unique base names in packFiles order.
    """
    pack_path = norm_path(pack_path)
    with open(pack_path, encoding="utf-8") as file_id:
        pack_data = json.load(file_id)
    base_names = []
    seen = set()
    for recorded_name in pack_data.get("packFiles", []):
        recorded_name = os.path.basename(str(recorded_name or "").strip())
        if not recorded_name:
            continue
        base_name, _version, _ext = io.parse_versioned_filename(recorded_name)
        if not base_name or base_name in seen:
            continue
        seen.add(base_name)
        base_names.append(base_name)
    return base_names


def _find_transforms_for_base_name(base_name):
    """Return long-path transforms whose short leaf name matches base_name."""
    from maya import cmds

    from wipskin.api.maya import scene

    target = _short_node_name(base_name)
    if not target:
        return []

    candidates = []
    seen = set()
    for pattern in (target, f"*:{target}"):
        found = cmds.ls(pattern, long=True)
        if not found:
            continue
        for node in found:
            if node in seen:
                continue
            node_type = cmds.nodeType(node)
            if node_type == "transform":
                if _short_node_name(node) != target:
                    continue
                seen.add(node)
                candidates.append(node)
            elif node_type in scene.DEFORMABLE_SHAPE_TYPES:
                parents = cmds.listRelatives(node, parent=True, fullPath=True)
                if not parents:
                    continue
                transform = parents[0]
                if transform in seen:
                    continue
                if _short_node_name(transform) != target:
                    continue
                seen.add(transform)
                candidates.append(transform)
    return candidates


def get_sidecar_member_records(pack_path) -> dict:
    """Member records the pack sidecar stored at export time.

    Args:
        pack_path (str): Path to a .gSkinPack / .jSkinPack manifest.

    Returns:
        dict: Member base name -> record dict. Empty for packs exported
            before member paths were recorded.
    """
    sidecar = metadata.read_sidecar(pack_path)
    if not sidecar:
        return {}

    records = {}
    for member in sidecar.get("members", []):
        if not isinstance(member, dict):
            continue
        member_file = os.path.basename(str(member.get("file", "")).strip())
        if not member_file:
            continue
        base_name, _version, _ext = io.parse_versioned_filename(member_file)
        if not base_name or base_name in records:
            continue
        records[base_name] = member
    return records


def _find_transforms_from_record(record):
    """Return the recorded transform as a one-item list when still in the scene.

    Falls through to the recorded shape path when the transform was renamed or
    reparented but the shape path still resolves.
    """
    from maya import cmds

    from wipskin.api.maya import scene

    for key in ("transform", "shape"):
        recorded = str(record.get(key, "")).strip()
        if not recorded:
            continue
        resolved = cmds.ls(recorded, long=True)
        if not resolved:
            continue
        node = resolved[0]
        if cmds.nodeType(node) in scene.DEFORMABLE_SHAPE_TYPES:
            parents = cmds.listRelatives(node, parent=True, fullPath=True)
            if not parents:
                continue
            return [parents[0]]

        return [node]
    return []


def _find_member_transforms(base_name, record):
    """Resolve one pack member to scene transforms.
    """
    if record:
        transforms = _find_transforms_from_record(record)
        if transforms:
            return transforms

    return _find_transforms_for_base_name(base_name)


def _get_member_dag_paths(node):
    """Long DAG paths identifying one pack member, for the pack sidecar.

    Args:
        node (str): Transform or shape the member was exported from.

    Returns:
        dict: "shape" and "transform" long paths, or empty when node carries
            no skinnable shape.
    """
    from maya import cmds

    from wipskin.api.maya import scene

    shape = scene.get_skinnable_shape(node)
    if not shape:
        return {}

    resolved = cmds.ls(shape, long=True)
    if not resolved:
        return {}

    shape_path = resolved[0]
    record = {"shape": shape_path}
    parents = cmds.listRelatives(shape_path, parent=True, fullPath=True)
    if parents:
        record["transform"] = parents[0]
    return record


def _get_bind_metadata(node):
    """Bind shape and skinCluster influences for a node, as sidecar fields.
    """
    from maya import cmds

    from wipskin.api.maya import scene

    shape = scene.get_skinnable_shape(node)
    if not shape:
        return {}

    skin_cluster = scene.get_skin_cluster(shape)
    if not skin_cluster:
        return {}

    influences = cmds.skinCluster(skin_cluster, q=True, inf=True)
    return {
        "shape": cmds.ls(shape)[0],
        "influences": list(influences) if influences else [],
    }


def list_sidecar_influences(path) -> list:
    """Influences recorded when path was exported, or [] when unrecorded."""
    sidecar = metadata.read_sidecar(path)
    if not sidecar:
        return []

    return list(sidecar.get("influences", []))


def export_skin(shape_names, file_path, use_json=True, comment=None):
    _require_mgear()
    mod = _skin_module()
    file_path = _normalize_skin_path(file_path, use_json)
    objs = _as_export_pynodes(shape_names)
    if not objs:
        raise ValueError("No exportable transform found for mGear export.")
    result = mod.exportSkin(filePath=file_path, objs=objs)
    if not result or not os.path.isfile(file_path):
        raise RuntimeError(f"mGear exportSkin failed: {file_path}")
    metadata.write_export_sidecar(
        file_path, METADATA_FORMAT, comment=comment,
        extra=_get_bind_metadata(shape_names[0]) if shape_names else None,
    )
    return file_path


def _export_pack_members(mod, objs, root_path, use_json, comment, auto_version):
    """Export one member file per obj, warning about and skipping unskinned ones.

    Returns:
        list: Member records ("file" plus recorded DAG paths) in obj order.

    Raises:
        RuntimeError: When mGear reports a failed member export.
    """
    from maya.api import OpenMaya as om2

    member_ext = EXT_JSKIN if use_json else EXT_GSKIN
    member_records = []
    for obj in objs:
        label = _short_node_name(obj.stripNamespace())
        if not mod.getSkinCluster(obj):
            om2.MGlobal.displayWarning(f"No skinCluster on: {label}")
            continue
        member_path = io.resolve_export_path(
            root_path, label, member_ext, auto_version=auto_version
        )
        member_path = _normalize_skin_path(member_path, use_json)
        result = mod.exportSkin(filePath=member_path, objs=[obj])
        if not result or not os.path.isfile(member_path):
            raise RuntimeError(f"mGear exportSkin failed: {member_path}")
        metadata.write_export_sidecar(
            member_path, METADATA_FORMAT, comment=comment,
            extra=_get_bind_metadata(str(obj)),
        )
        member_record = {"file": os.path.basename(member_path)}
        member_record.update(_get_member_dag_paths(str(obj)))
        member_records.append(member_record)
    return member_records


def export_skin_pack(
    shape_names,
    pack_path,
    use_json=True,
    comment=None,
    auto_version=False,
):
    """Export member .jSkin/.gSkin files (optionally versioned per mesh), then
    write a .gSkinPack manifest that lists those member filenames.
    """
    _require_mgear()
    mod = _skin_module()
    pack_path = _normalize_pack_path(pack_path)
    objs = _as_export_pynodes(shape_names)
    if not objs:
        raise ValueError("No exportable transform found for mGear export.")
    root_path = os.path.dirname(pack_path)
    if not root_path or not os.path.isdir(root_path):
        raise ValueError(f"Invalid pack export directory: {root_path}")
    member_records = _export_pack_members(
        mod, objs, root_path, use_json, comment, auto_version
    )
    if not member_records:
        raise RuntimeError(f"mGear exportSkinPack produced no skin files: {pack_path}")

    _write_pack_files(
        pack_path,
        [record["file"] for record in member_records],
        member_records,
        get_mgear_version(),
        comment,
    )
    return pack_path


def build_pack_update_plan(pack_path) -> dict:
    """Resolve every packFiles entry to the newest member file on disk.

    Args:
        pack_path (str): Path to a .gSkinPack / .jSkinPack manifest.

    Returns:
        dict: "entries" (one dict per packFiles entry with "recorded",
            "resolved" and "base_name"), "pack_files" (resolved filenames in
            packFiles order), "changes" (recorded, resolved) pairs that move
            to a newer version, "missing" (recorded names with no file on
            disk), and "mgear_version" as recorded in the manifest.
    """
    pack_path = norm_path(pack_path)
    directory = os.path.dirname(pack_path)
    with open(pack_path, encoding="utf-8") as file_id:
        pack_data = json.load(file_id)

    entries = []
    pack_files = []
    changes = []
    missing = []
    for recorded_name in pack_data.get("packFiles", []):
        recorded_name = os.path.basename(str(recorded_name or "").strip())
        if not recorded_name:
            continue
        base_name, _version, _ext = io.parse_versioned_filename(recorded_name)
        resolved_name = io.resolve_pack_member_filename(
            directory, recorded_name, prefer_latest=True
        )
        entries.append({
            "recorded": recorded_name,
            "resolved": resolved_name,
            "base_name": base_name,
        })
        if not resolved_name:
            missing.append(recorded_name)
            continue
        pack_files.append(resolved_name)
        if resolved_name != recorded_name:
            changes.append((recorded_name, resolved_name))
    return {
        "entries": entries,
        "pack_files": pack_files,
        "changes": changes,
        "missing": missing,
        "mgear_version": str(pack_data.get("mgearVersion", "")),
    }


def _build_member_record(member_name, source_records) -> dict:
    """Record for member_name, carrying source_records' DAG paths when known."""
    base_name, _version, _ext = io.parse_versioned_filename(member_name)
    record = {"file": member_name}
    for key, value in source_records.get(base_name, {}).items():
        if key != "file":
            record[key] = value
    return record


def _write_pack_files(target_path, pack_files, member_records,
                      mgear_version, comment):
    """Write one pack manifest and its sidecar."""
    pack_data = {
        "packFiles": list(pack_files),
        "rootPath": os.path.dirname(target_path),
    }
    if mgear_version:
        pack_data["mgearVersion"] = mgear_version
    with open(target_path, "w", encoding="utf-8", newline="\n") as file_id:
        json.dump(pack_data, file_id, indent=4, sort_keys=True)
        file_id.write("\n")
    pack_extra = {"members": list(member_records)}
    if mgear_version:
        pack_extra["mgear_version"] = mgear_version
    metadata.write_export_sidecar(
        target_path,
        METADATA_FORMAT,
        comment=comment,
        extra=pack_extra,
    )


def list_pack_member_states(pack_path) -> list:
    """Per-member state for the pack editor, in packFiles order.

    Args:
        pack_path (str): Path to a .gSkinPack / .jSkinPack manifest.

    Returns:
        list: One dict per member with "base_name", "recorded", "latest",
            "recorded_version", "latest_version", "has_newer",
            "recorded_exists", "transform" (the scene transform it resolves
            to, "" when absent or ambiguous) and "has_skin_cluster".
    """
    from wipskin.api.maya import scene

    pack_path = norm_path(pack_path)
    directory = os.path.dirname(pack_path)
    records = get_sidecar_member_records(pack_path)
    states = []
    for entry in build_pack_update_plan(pack_path)["entries"]:
        base_name = entry["base_name"]
        described = describe_pack_member(directory, entry["recorded"])
        transforms = _find_member_transforms(
            base_name, records.get(base_name, {})
        )
        transform = transforms[0] if len(transforms) == 1 else ""
        states.append({
            "base_name": base_name,
            "recorded": described["recorded"],
            "latest": described["latest"],
            "recorded_version": described["recorded_version"],
            "latest_version": described["latest_version"],
            "has_newer": bool(
                described["latest"]
                and described["latest_version"] > described["recorded_version"]
            ),
            "recorded_exists": described["recorded_exists"],
            "transform": transform,
            "has_skin_cluster": bool(
                transform and scene.get_skin_cluster(transform)
            ),
        })
    return states


def _export_pack_edit_members(actions, directory, use_json) -> dict:
    """Export the members an edit marks for re-export, keyed by base name."""
    transforms = [
        action.get("transform", "") for action in actions
        if action.get("action") == PACK_ACTION_REEXPORT
    ]
    transforms = [name for name in transforms if name]
    if not transforms:
        return {}

    _require_mgear()
    objs = _as_export_pynodes(transforms)
    if not objs:
        raise ValueError("No exportable transform found for mGear export.")

    records = {}
    for record in _export_pack_members(
        _skin_module(), objs, directory, use_json, None, True
    ):
        base_name, _version, _ext = io.parse_versioned_filename(record["file"])
        records[base_name] = record
    return records


def _get_member_extension(entries) -> str:
    """Member extension, lowercase without dot, that a pack's entries share."""
    for entry in entries:
        if os.path.splitext(entry["recorded"])[1].lower() == ".gskin":
            return EXT_GSKIN.lower()

    return EXT_JSKIN.lower()


def get_pack_member_extension(pack_path) -> str:
    """Extension ("jskin" or "gskin") of the member files a pack lists."""
    return _get_member_extension(build_pack_update_plan(pack_path)["entries"])


def _validate_pack_actions(actions, entries, member_ext):
    """Reject a bad edit before any member file is written."""
    seen = set()
    for action in actions:
        base_name = action["base_name"]
        choice = action["action"]
        if base_name in seen:
            raise ValueError(f"Pack edit names a member twice: {base_name}")

        seen.add(base_name)
        if choice == PACK_ACTION_FILE:
            file_name = os.path.basename(str(action.get("file", "")).strip())
            file_ext = os.path.splitext(file_name)[1].lstrip(".").lower()
            if file_ext != member_ext:
                raise ValueError(
                    f"Cannot add {file_name}: this pack's members are "
                    f".{member_ext} files."
                )
        elif choice in (PACK_ACTION_KEEP, PACK_ACTION_LATEST):
            if base_name not in entries:
                raise ValueError(f"Pack has no member named: {base_name}")
        elif choice != PACK_ACTION_REEXPORT:
            raise ValueError(f"Unknown pack member action: {choice}")


def apply_pack_edit(pack_path, actions) -> str:
    """Write a new pack version from one action per member.

    Members are written in the order given. The manifest and every
    re-exported member file are always versioned up, so the pack this one was
    edited from keeps pointing at data that never changes under it. Member
    files are written in the format the pack already uses, so an edit cannot
    mix .jSkin and .gSkin members.

    Args:
        pack_path (str): Source .gSkinPack / .jSkinPack manifest.
        actions (list): Dicts with "base_name" and "action", one per member of
            the pack to write. PACK_ACTION_KEEP and PACK_ACTION_LATEST name a
            member the pack already lists. PACK_ACTION_REEXPORT needs the
            scene "transform" to export and may name a new member, which is
            appended. PACK_ACTION_FILE needs the member "file" in the pack's
            directory and replaces the member of that name, or appends it.

    Returns:
        str: Path of the written manifest.

    Raises:
        ValueError: When the pack directory is invalid, a member is named
            twice, an action names an unknown member or an unknown action, or
            a file is not in the pack's member format.
        RuntimeError: When a chosen member has no file on disk, or mGear
            skipped a requested re-export.
    """
    pack_path = norm_path(pack_path)
    directory = os.path.dirname(pack_path)
    if not directory or not os.path.isdir(directory):
        raise ValueError(f"Invalid pack directory: {directory}")

    plan = build_pack_update_plan(pack_path)
    entries = {entry["base_name"]: entry for entry in plan["entries"]}
    source_records = get_sidecar_member_records(pack_path)
    member_ext = _get_member_extension(plan["entries"])
    _validate_pack_actions(actions, entries, member_ext)
    new_records = _export_pack_edit_members(
        actions, directory, member_ext == EXT_JSKIN.lower()
    )

    pack_files = []
    member_records = []
    unresolved = []
    for action in actions:
        base_name = action["base_name"]
        choice = action["action"]
        entry = entries.get(base_name)
        if choice == PACK_ACTION_REEXPORT:
            record = new_records.get(base_name)
            if record is None:
                unresolved.append(f"{base_name} (no skinCluster to export)")
                continue
        elif choice == PACK_ACTION_FILE:
            file_name = os.path.basename(str(action["file"]).strip())
            if not os.path.isfile(os.path.join(directory, file_name)):
                unresolved.append(f"{file_name} (no file on disk)")
                continue

            record = _build_member_record(file_name, source_records)
        elif choice == PACK_ACTION_LATEST:
            if not entry["resolved"]:
                unresolved.append(f"{base_name} (no file on disk)")
                continue

            record = _build_member_record(entry["resolved"], source_records)
        else:
            record = _build_member_record(entry["recorded"], source_records)

        pack_files.append(record["file"])
        member_records.append(record)

    if unresolved:
        raise RuntimeError(
            "Cannot write pack, unresolved member(s): " + ", ".join(unresolved)
        )

    if not pack_files:
        raise RuntimeError(f"Pack edit produced no members: {pack_path}")

    pack_base_name, _version, _ext = io.parse_versioned_filename(
        os.path.basename(pack_path)
    )
    target_path = io.resolve_export_path(
        directory, pack_base_name, EXT_GSKIN_PACK, auto_version=True
    )
    mgear_version = get_mgear_version()
    if not mgear_version:
        mgear_version = plan["mgear_version"]
    _write_pack_files(
        target_path, pack_files, member_records, mgear_version, None
    )
    return target_path


def list_scene_export_candidates(shape_names) -> list:
    """Describe the scene meshes an export would turn into pack members.

    Args:
        shape_names (list): Skinnable shapes, e.g. from the scene selection.

    Returns:
        list: One dict per exportable transform with "base_name" (the member
            name its file would get), "transform" and "has_skin_cluster".
    """
    from wipskin.api.maya import scene

    candidates = []
    for transform in list_export_transforms(shape_names):
        candidates.append({
            "base_name": _short_node_name(transform),
            "transform": transform,
            "has_skin_cluster": bool(scene.get_skin_cluster(transform)),
        })
    return candidates


def build_selection_actions(states, candidates) -> dict:
    """Plan a pack edit that exports the selected meshes into the pack.

    A selected mesh named like an existing member is re-exported over it, one
    the pack does not list yet is appended, and members the selection does not
    touch keep the file they record.

    Args:
        states (list): list_pack_member_states() result.
        candidates (list): list_scene_export_candidates() result.

    Returns:
        dict: "actions" for apply_pack_edit, plus the member names that are
            "added", "updated" and "kept", and the "skipped" selected meshes
            that have no skinCluster.

    Raises:
        ValueError: When two selected meshes would write the same member name.
    """
    exportable = {}
    skipped = []
    for candidate in candidates:
        base_name = candidate["base_name"]
        if not candidate["has_skin_cluster"]:
            skipped.append(base_name)
            continue

        if base_name in exportable:
            raise ValueError(
                f"Selected meshes share the member name: {base_name}"
            )

        exportable[base_name] = candidate

    actions = []
    updated = []
    kept = []
    for state in states:
        base_name = state["base_name"]
        candidate = exportable.pop(base_name, None)
        if candidate is None:
            actions.append({"base_name": base_name, "action": PACK_ACTION_KEEP})
            kept.append(base_name)
        else:
            actions.append({
                "base_name": base_name,
                "action": PACK_ACTION_REEXPORT,
                "transform": candidate["transform"],
            })
            updated.append(base_name)

    added = []
    for base_name, candidate in exportable.items():
        actions.append({
            "base_name": base_name,
            "action": PACK_ACTION_REEXPORT,
            "transform": candidate["transform"],
        })
        added.append(base_name)
    return {
        "actions": actions,
        "added": added,
        "updated": updated,
        "kept": kept,
        "skipped": skipped,
    }


def build_add_files_actions(states, file_names) -> dict:
    """Plan a pack edit that adds already-exported member files to the pack.

    A file named like an existing member replaces what that member points at,
    any other is appended, and members the files do not touch keep the file
    they record. The chosen file name is recorded as is, version included.

    Args:
        states (list): list_pack_member_states() result.
        file_names (list): Member files in the pack's directory.

    Returns:
        dict: Same shape as build_selection_actions, with "skipped" empty.

    Raises:
        ValueError: When two files would write the same member name.
    """
    by_base = {}
    for file_name in file_names:
        file_name = os.path.basename(file_name)
        base_name, _version, _ext = io.parse_versioned_filename(file_name)
        if base_name in by_base:
            raise ValueError(f"Selected files share the member name: {base_name}")

        by_base[base_name] = file_name

    actions = []
    updated = []
    kept = []
    for state in states:
        base_name = state["base_name"]
        file_name = by_base.pop(base_name, None)
        if file_name is None:
            actions.append({"base_name": base_name, "action": PACK_ACTION_KEEP})
            kept.append(base_name)
        else:
            actions.append({
                "base_name": base_name,
                "action": PACK_ACTION_FILE,
                "file": file_name,
            })
            updated.append(base_name)

    added = []
    for base_name, file_name in by_base.items():
        actions.append({
            "base_name": base_name,
            "action": PACK_ACTION_FILE,
            "file": file_name,
        })
        added.append(base_name)
    return {
        "actions": actions,
        "added": added,
        "updated": updated,
        "kept": kept,
        "skipped": [],
    }


def build_reexport_all_actions(states) -> list:
    """Actions that re-export every member the scene can export.

    A member with no skinned scene mesh keeps pointing at its newest file on
    disk rather than dropping out of the pack.

    Args:
        states (list): list_pack_member_states() result.

    Returns:
        list: apply_pack_edit actions, in the same order as states.
    """
    actions = []
    for state in states:
        if state["has_skin_cluster"]:
            action = PACK_ACTION_REEXPORT
        else:
            action = PACK_ACTION_LATEST
        actions.append({
            "base_name": state["base_name"],
            "action": action,
            "transform": state["transform"],
        })
    return actions


def get_next_pack_version_name(pack_path) -> str:
    """Filename apply_pack_edit would write for pack_path."""
    pack_path = norm_path(pack_path)
    base_name, _version, _ext = io.parse_versioned_filename(
        os.path.basename(pack_path)
    )
    return os.path.basename(io.resolve_export_path(
        os.path.dirname(pack_path), base_name, EXT_GSKIN_PACK,
        auto_version=True,
    ))


def import_skin(file_path):
    _require_mgear()
    mod = _skin_module()
    return mod.importSkin(filePath=file_path)


def import_skin_pack(file_path, version_mode="latest"):
    """Import each pack member.
    """
    _require_mgear()
    mod = _skin_module()
    file_path = norm_path(file_path)
    prefer_latest = str(version_mode).lower() != "recorded"
    directory = os.path.dirname(file_path)
    with open(file_path, encoding="utf-8") as file_id:
        pack_data = json.load(file_id)
    pack_files = list(pack_data.get("packFiles", []))
    volume_imported = []
    for recorded_name in pack_files:
        resolved_name = io.resolve_pack_member_filename(
            directory, recorded_name, prefer_latest=prefer_latest
        )
        if not resolved_name:
            mode_label = "latest" if prefer_latest else "recorded"
            raise RuntimeError(
                f"Pack member not found ({mode_label}): {recorded_name}"
            )
        skin_path = norm_path(os.path.join(directory, resolved_name))
        result = mod.importSkin(filePath=skin_path)
        if result:
            volume_imported.extend(result)
    return volume_imported


def is_pack_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in (".jskinpack", ".gskinpack")


def is_renamable_influence_file(path) -> bool:
    """True for the JSON member format, whose influence names are editable.

    .gSkin is a binary pickle and .gSkinPack only lists member files, so
    neither can have an influence renamed in place.
    """
    ext = os.path.splitext(str(path))[1].lstrip(".").lower()
    return ext == EXT_JSKIN.lower()


def list_influence_names(path) -> list:
    """Influence names stored in a .jSkin, in file order.

    mGear writes them as the keys of its "weights" dict, stripped of any
    namespace (see mgear.core.skin.collectInfluenceWeights).

    Args:
        path (str): Path to a .jSkin file.

    Returns:
        list: Influence names, or [] when the file has no weights block.
    """
    path = norm_path(path)
    with open(path, encoding="utf-8") as file_id:
        data = json.load(file_id)
    if not isinstance(data, dict):
        return []

    weights = data.get("weights")
    if not isinstance(weights, dict):
        return []

    return list(weights)


def list_influences(path) -> list:
    """Influence names to list for an mGear weight file.

    .jSkin keys are what mGear's importer matches against the scene, so they
    are read from the file itself. .gSkin is a binary pickle, leaving the
    sidecar as the only record. The two can disagree: mGear strips the
    namespace on export (collectInfluenceWeights), while the sidecar keeps
    the scene name.

    Args:
        path (str): Path to a .jSkin or .gSkin file.

    Returns:
        list: Influence names, or [] when neither source has them.
    """
    if is_renamable_influence_file(path):
        try:
            names = list_influence_names(path)
        except (OSError, ValueError):
            names = []

        if names:
            return names

    return list_sidecar_influences(path)


def rename_influence(path: str, old_name: str, new_name: str) -> int:
    """Rewrite one influence name in a .jSkin file, in place.

    mGear's importer matches these keys against the scene by exact name and
    silently drops the ones it can't find, so a stale name loses its weights
    without an error.

    Args:
        path (str): Path to a .jSkin file.
        old_name (str): Influence name to replace.
        new_name (str): Replacement name.

    Returns:
        int: 1 when the influence was renamed, 0 when it was not present.

    Raises:
        ValueError: When new_name is already used by another influence.
    """
    path = norm_path(path)
    with open(path, encoding="utf-8") as file_id:
        data = json.load(file_id)

    weights = data.get("weights") if isinstance(data, dict) else None
    if not isinstance(weights, dict) or old_name not in weights:
        return 0

    if new_name in weights:
        raise ValueError(f"Influence already exists in this file: {new_name}")

    # Rebuild rather than pop/insert so the influence keeps its position;
    # mGear reads the dict by key, but a stable order keeps diffs readable.
    data["weights"] = {
        (new_name if key == old_name else key): value
        for key, value in weights.items()
    }
    with open(path, "w", encoding="utf-8", newline="\n") as file_id:
        json.dump(data, file_id, indent=4, sort_keys=True)
        file_id.write("\n")
    return 1


def parse_file_info(path):
    """Return metadata for the mGear file viewer, memoized by (mtime, size).

    The returned dict is treated as read-only by callers.
    """
    return file_cache.memoize_by_stat(path, _parse_file_info)


def _parse_file_info(path):
    path = norm_path(path)
    ext = os.path.splitext(path)[1].lower()
    info = {
        "path": path,
        "extension": ext.lstrip("."),
        "type": "skin",
        "preview": "",
        "entries": [],
        "mgear_version": "",
    }
    if ext in (f".{value.lower()}" for value in PACK_EXTENSIONS):
        info["type"] = "pack"
        with open(path, encoding="utf-8") as file_id:
            pack_data = json.load(file_id)
        info["entries"] = list(pack_data.get("packFiles", []))
        info["mgear_version"] = str(pack_data.get("mgearVersion", "") or "")
        info["preview"] = f"Pack entries: {len(info['entries'])}"
        return info

    if ext == f".{EXT_JSKIN.lower()}":
        with open(path, encoding="utf-8") as file_id:
            lines = []
            for _index in range(8):
                line = file_id.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))
        info["preview"] = "\n".join(lines)
        return info

    info["preview"] = f"Binary .{EXT_GSKIN} file (preview not available)."
    return info


def format_viewer_text(info):
    """Build multi-line summary text for the mGear file viewer."""
    path = info.get("path", "")
    sidecar = metadata.read_sidecar(path)
    header_lines = []
    body_lines = []

    if info.get("type") == "pack":
        entry_count = len(info.get("entries", []))
        header_lines.append(tr("Pack: {count} entries", count=entry_count))
        sidecar_for_display = dict(sidecar) if sidecar else {}
        pack_version = info.get("mgear_version", "")
        if pack_version and not sidecar_for_display.get("mgear_version"):
            sidecar_for_display["mgear_version"] = pack_version
        header_lines.extend(
            metadata.format_audit_lines(
                sidecar_for_display or None, extra_fields=AUDIT_FIELDS
            )
        )
        return metadata.join_viewer_sections(header_lines, body_lines)

    ext = info.get("extension", "")
    if ext:
        header_lines.append(tr("mGear format: .{ext}", ext=ext))

    mesh_name = _mesh_name_from_jskin(path)
    if mesh_name:
        header_lines.append(tr("Mesh: {mesh}", mesh=mesh_name))

    header_lines.extend(
        metadata.format_audit_lines(sidecar, extra_fields=AUDIT_FIELDS)
    )

    if ext.lower() == EXT_GSKIN.lower():
        body_lines.append(tr("Binary skin data (preview not available)"))

    return metadata.join_viewer_sections(header_lines, body_lines)


def _mesh_name_from_jskin(path):
    ext = os.path.splitext(path)[1].lower()
    if ext != f".{EXT_JSKIN.lower()}":
        return ""
    try:
        with open(path, encoding="utf-8") as file_id:
            data = json.load(file_id)
    except (OSError, json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("geo", "mesh", "obj", "name"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
