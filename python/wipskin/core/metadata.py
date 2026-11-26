"""Sidecar metadata for WipSkin weight files (.<target>.info)."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime

from wipskin.core.constants import APP_TITLE, __version__
from wipskin.core.path_utils import norm_path
from wipskin.core.i18n import tr

SCHEMA_VERSION = 1
SIDECAR_SUFFIX = ".info"

COMMENT_PLACEHOLDER_NO_COMMENT = "No comment written"
COMMENT_PLACEHOLDER_NO_SELECTION = "Select a weight file first"


def is_sidecar_filename(filename: str) -> bool:
    """True when filename is a WipSkin sidecar (e.g. .arm.0001.xml.info)."""
    basename = os.path.basename(filename)
    if not basename.startswith("."):
        return False
    return basename.endswith(SIDECAR_SUFFIX)


def sidecar_path(weight_path: str) -> str:
    """Return the sidecar path for a weight file."""
    weight_path = norm_path(weight_path)
    directory = os.path.dirname(weight_path)
    basename = os.path.basename(weight_path)
    return norm_path(
        os.path.join(directory, f".{basename}{SIDECAR_SUFFIX}")
    )


def read_sidecar(weight_path: str) -> dict | None:
    """Load sidecar JSON for weight_path.

    Returns:
        dict | None: None when missing or invalid.
    """
    path = sidecar_path(weight_path)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as file_id:
            data = json.load(file_id)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _current_user() -> str:
    for key in ("USER", "USERNAME"):
        value = os.getenv(key)
        if value:
            return value
    return "Unknown"


def _iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _source_scene() -> str:
    try:
        from maya import cmds

        scene_path = cmds.file(q=True, sn=True)
        if scene_path:
            return os.path.basename(scene_path)
    except Exception:
        pass
    return ""


def build_export_metadata(
    weight_path: str,
    format_name: str,
    comment: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Build sidecar payload for an export, merging preserved fields from existing."""
    weight_path = norm_path(weight_path)
    target = os.path.basename(weight_path)
    exported = _iso_timestamp()
    exported_by = _current_user()
    existing = read_sidecar(weight_path)

    if existing:
        created = existing.get("created", exported)
        created_by = existing.get("created_by", exported_by)
        if comment is None:
            comment = existing.get("comment", "")
    else:
        created = exported
        created_by = exported_by
        if comment is None:
            comment = ""

    payload = {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "comment": comment,
        "created": created,
        "created_by": created_by,
        "exported": exported,
        "exported_by": exported_by,
        "tool": APP_TITLE,
        "tool_version": __version__,
        "source_scene": _source_scene(),
        "format": format_name,
    }
    if extra:
        for key, value in extra.items():
            if value not in (None, ""):
                payload[key] = value
    return payload


def _windows_file_attrs(path: str) -> int | None:
    if sys.platform != "win32":
        return None
    import ctypes

    attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
    if attrs == -1:
        return None
    return attrs


def _set_windows_file_attrs(path: str, attrs: int) -> None:
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.kernel32.SetFileAttributesW(path, attrs)


def _prepare_sidecar_for_write(path: str) -> None:
    """Clear hidden on Windows so an existing sidecar can be overwritten."""
    attrs = _windows_file_attrs(path)
    if attrs is None:
        return
    file_attribute_hidden = 0x02
    if attrs & file_attribute_hidden:
        _set_windows_file_attrs(path, attrs & ~file_attribute_hidden)


def _set_sidecar_hidden(path: str) -> None:
    """Mark sidecar hidden on Windows (leading dot does not hide files there)."""
    if sys.platform != "win32":
        return
    if not path or not os.path.isfile(path):
        return
    attrs = _windows_file_attrs(path)
    if attrs is None:
        return
    file_attribute_hidden = 0x02
    _set_windows_file_attrs(path, attrs | file_attribute_hidden)


def _write_sidecar_data(weight_path: str, data: dict) -> str:
    weight_path = norm_path(weight_path)
    path = sidecar_path(weight_path)
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    if os.path.isfile(path):
        _prepare_sidecar_for_write(path)
    with open(path, "w", encoding="utf-8", newline="\n") as file_id:
        json.dump(data, file_id, ensure_ascii=False, indent=2)
        file_id.write("\n")
    _set_sidecar_hidden(path)
    return path


def write_comment_sidecar(
    weight_path: str,
    comment: str,
    format_name: str | None = None,
) -> str:
    """Overwrite comment in the sidecar, creating metadata when missing.

    Args:
        weight_path (str): Weight file the sidecar belongs to.
        comment (str): New comment text.
        format_name (str, optional): Sidecar "format" for a sidecar that does
            not exist yet; an existing sidecar keeps its own.

    Returns:
        str: Path of the written sidecar.

    Raises:
        ValueError: When no sidecar exists and format_name is None.
    """
    weight_path = norm_path(weight_path)
    existing = read_sidecar(weight_path)
    if existing:
        data = dict(existing)
        data["comment"] = comment
        data["target"] = os.path.basename(weight_path)
        data["exported"] = _iso_timestamp()
        data["exported_by"] = _current_user()
    else:
        if format_name is None:
            raise ValueError(
                f"No sidecar yet for {weight_path}: pass format_name."
            )

        data = build_export_metadata(
            weight_path, format_name, comment=comment
        )
    return _write_sidecar_data(weight_path, data)


def write_export_sidecar(
    weight_path: str,
    format_name: str,
    comment: str | None = None,
    extra: dict | None = None,
) -> str:
    """Write or update the sidecar for weight_path after export."""
    weight_path = norm_path(weight_path)
    data = build_export_metadata(
        weight_path, format_name, comment=comment, extra=extra
    )
    return _write_sidecar_data(weight_path, data)


def update_sidecar(weight_path: str, fields: dict) -> str | None:
    """Merge fields into an existing sidecar, preserving the other keys.

    No-op (returns None) when there is no sidecar: we don't create one just to
    cache derived data for a browsed file. Used to stash the viewer stats cache
    (see xml_skin) so re-selecting a large weight file doesn't re-parse it.
    """
    existing = read_sidecar(weight_path)
    if existing is None:
        return None
    data = dict(existing)
    data.update(fields)
    return _write_sidecar_data(weight_path, data)


def delete_sidecar(weight_path: str) -> bool:
    """Remove the sidecar for weight_path when it exists."""
    path = sidecar_path(weight_path)
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def rename_sidecar(src_weight_path: str, dst_weight_path: str) -> bool:
    """Move sidecar alongside a renamed weight file and update target."""
    src_weight_path = norm_path(src_weight_path)
    dst_weight_path = norm_path(dst_weight_path)
    src_path = sidecar_path(src_weight_path)
    if not os.path.isfile(src_path):
        return False
    dst_path = sidecar_path(dst_weight_path)
    if os.path.isfile(dst_path):
        _prepare_sidecar_for_write(dst_path)
        os.remove(dst_path)
    shutil.move(src_path, dst_path)
    _set_sidecar_hidden(dst_path)
    data = read_sidecar(dst_weight_path)
    if data is None:
        return True
    data["target"] = os.path.basename(dst_weight_path)
    _write_sidecar_data(dst_weight_path, data)
    return True


def rename_weight_with_sidecar(src_weight_path: str, dst_weight_path: str) -> bool:
    """Rename a weight file and move its sidecar when present."""
    src_weight_path = norm_path(src_weight_path)
    dst_weight_path = norm_path(dst_weight_path)
    if not os.path.isfile(src_weight_path):
        raise FileNotFoundError(f"Weight file not found: {src_weight_path}")
    if os.path.exists(dst_weight_path):
        raise FileExistsError(f"Destination already exists: {dst_weight_path}")
    had_sidecar = os.path.isfile(sidecar_path(src_weight_path))
    os.rename(src_weight_path, dst_weight_path)
    if had_sidecar:
        rename_sidecar(src_weight_path, dst_weight_path)
    return had_sidecar


def copy_sidecar(src_weight_path: str, dst_weight_path: str) -> bool:
    """Copy sidecar when a weight file is duplicated (e.g. Convert)."""
    src_weight_path = norm_path(src_weight_path)
    dst_weight_path = norm_path(dst_weight_path)
    src_path = sidecar_path(src_weight_path)
    if not os.path.isfile(src_path):
        return False
    data = read_sidecar(src_weight_path)
    if data is None:
        return False
    data["target"] = os.path.basename(dst_weight_path)
    _write_sidecar_data(dst_weight_path, data)
    return True


def format_audit_lines(
    sidecar: dict | None,
    created_by: str | None = None,
    created: str | None = None,
    extra_fields=(),
) -> list:
    """Viewer audit lines from sidecar (no comment, tool name, or format).

    Args:
        sidecar (dict, optional): Sidecar data, or None when there is none.
        created_by (str, optional): Shown when the sidecar has no creator.
        created (str, optional): Shown when the sidecar has no creation time.
        extra_fields (iterable): ``(label, key)`` pairs for sidecar keys a
            format writes on top of the shared ones (e.g. a tool version);
            listed right after "Tool version".

    Returns:
        list: ``"Label: value"`` lines for the values that are set.
    """
    if sidecar is None:
        sidecar = {}

    created_by_val = sidecar.get("created_by", "")
    created_val = sidecar.get("created", "")
    if not created_by_val and created_by:
        created_by_val = created_by
    if not created_val and created:
        created_val = str(created)

    lines = []
    for label, value in (
        (tr("Created by"), created_by_val),
        (tr("Created"), created_val),
        (tr("Exported by"), sidecar.get("exported_by", "")),
        (tr("Exported"), sidecar.get("exported", "")),
        (tr("Tool version"), sidecar.get("tool_version", "")),
        *((tr(label), sidecar.get(key, "")) for label, key in extra_fields),
        (tr("Source scene"), sidecar.get("source_scene", "")),
        (tr("Deformer"), sidecar.get("deformer", "")),
        (tr("Shape"), sidecar.get("shape", "")),
    ):
        if value:
            lines.append(f"{label}: {value}")
    return lines


def join_viewer_sections(header_lines: list, body_lines: list) -> str:
    """Join viewer header and body with a blank line between them."""
    header = [line for line in header_lines if line]
    body = [line for line in body_lines if line]
    if header and body:
        return "\n".join(header + [""] + body)
    return "\n".join(header + body)


def format_viewer_lines(sidecar: dict | None) -> list:
    """Deprecated alias for format_audit_lines without fallbacks."""
    return format_audit_lines(sidecar)
