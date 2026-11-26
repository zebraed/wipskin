"""Weight-file directory operations shared by the SkinWeight and Deformer tabs.

Pure filesystem logic (no Qt, no Maya) so it can be unit tested directly.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys

from wipskin.core import io
from wipskin.core import metadata
from wipskin.core.path_utils import norm_path

BACKUP_DIR_NAME = ".backup"
_FILE_ATTRIBUTE_HIDDEN = 0x02


def scan_weight_files(dir_name: str, extensions, predicate=None) -> list:
    """Return sorted weight file names in dir_name matching the extensions.

    Args:
        dir_name (str): Directory to scan. Missing/empty dirs return [].
        extensions (iterable): Extensions without dot, case-insensitive.
        predicate (callable, optional): Optional filter taking the full
            path; entries where it returns False are skipped. Sidecar
            metadata files are always skipped.
    """
    if not dir_name or not os.path.isdir(dir_name):
        return []
    allowed = {str(ext).lower() for ext in extensions}
    names = []
    # scandir yields names without a per-entry stat round trip, which matters
    # on network drives with many files.
    with os.scandir(dir_name) as entries:
        for entry in entries:
            name = entry.name
            if metadata.is_sidecar_filename(name):
                continue
            entry_ext = os.path.splitext(name)[1].lstrip(".").lower()
            if entry_ext not in allowed:
                continue
            if predicate is not None:
                full_path = norm_path(os.path.join(dir_name, name))
                if not predicate(full_path):
                    continue
            names.append(name)
    return sorted(names)


def scan_subdir_weight_files(dir_name: str, subdir_suffix: str, extensions) -> list:
    """Scan immediate subdirectories of dir_name whose name ends with
    subdir_suffix for files matching extensions (no dot, case-insensitive).

    Sidecar metadata files are skipped. Only one level deep -- used by WIP
    Skin packs (see formats.wip_skin), which are deliberately flat (no tree
    UI).

    Returns:
        list: "subdir_name/file_name" relative paths (forward slashes),
            sorted.
    """
    if not dir_name or not os.path.isdir(dir_name):
        return []
    allowed = {str(ext).lower() for ext in extensions}
    names = []
    with os.scandir(dir_name) as entries:
        for entry in entries:
            if not entry.is_dir() or not entry.name.endswith(subdir_suffix):
                continue
            with os.scandir(entry.path) as sub_entries:
                for sub_entry in sub_entries:
                    sub_name = sub_entry.name
                    if metadata.is_sidecar_filename(sub_name):
                        continue
                    sub_ext = os.path.splitext(sub_name)[1].lstrip(".").lower()
                    if sub_ext not in allowed:
                        continue
                    names.append(f"{entry.name}/{sub_name}")
    return sorted(names)


def unique_path(path: str) -> str:
    """Return path, appending 'Copy' to the basename until it does not exist."""
    path = norm_path(path)
    while os.path.exists(path):
        parts = path.split(".")
        if len(parts) >= 2:
            parts[-2] = parts[-2] + "Copy"
        path = norm_path(".".join(parts))
    return path


def copy_to_next_version(dir_name: str, file_name: str) -> str:
    """Duplicate a weight file as the next ``basename.NNNN.ext`` version.

    Used by edits that must not touch the file the user selected, so the
    original stays importable if the edit turns out to be wrong.

    Args:
        dir_name (str): Weight directory holding file_name.
        file_name (str): Files-list name of the source file.

    Returns:
        str: Files-list name of the new version.

    Raises:
        OSError: When the source file does not exist.
    """
    src_path = norm_path(os.path.join(dir_name, file_name))
    if not os.path.isfile(src_path):
        raise OSError(f"Weight file not found: {src_path}")

    base_name, _version, ext = io.parse_versioned_filename(
        os.path.basename(file_name)
    )
    dst_path = io.resolve_export_path(
        os.path.dirname(src_path), base_name, ext, auto_version=True
    )
    shutil.copy2(src_path, dst_path)
    metadata.copy_sidecar(src_path, dst_path)

    subdir = os.path.dirname(file_name)
    new_name = os.path.basename(dst_path)
    return f"{subdir}/{new_name}" if subdir else new_name


def _remove_emptied_subdirs(dir_name: str, file_names: list):
    """Drop subdirectories that the just-removed names left empty.
    """
    subdirs = {
        os.path.dirname(file_name) for file_name in file_names
        if os.path.dirname(file_name)
    }
    for subdir in subdirs:
        path = norm_path(os.path.join(dir_name, subdir))
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)


def delete_weight_files(dir_name: str, file_names: list):
    """Delete weight files (and their metadata sidecars) from dir_name."""
    for file_name in file_names:
        full_path = norm_path(os.path.join(dir_name, file_name))
        if os.path.isfile(full_path):
            os.remove(full_path)
            metadata.delete_sidecar(full_path)
    _remove_emptied_subdirs(dir_name, file_names)


def _hide_windows_folder(path: str):
    """Best-effort: set the Windows hidden attribute on path.

    No-op on other platforms -- the leading-dot name is the only "hidden"
    signal there, matching wipskin's existing sidecar-file convention.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.kernel32.SetFileAttributesW(str(path), _FILE_ATTRIBUTE_HIDDEN)
    except OSError:
        pass


def get_backup_dir(dir_name: str) -> str:
    """Path of dir_name's archive subfolder, which need not exist yet."""
    return norm_path(os.path.join(dir_name, BACKUP_DIR_NAME))


def archive_weight_files(dir_name: str, file_names: list) -> list:
    """Move weight files (and their metadata sidecars) into a `.backup`
    subfolder of dir_name, instead of deleting them.

    Name collisions with an already-archived file are resolved the same way
    Rename resolves them (appending 'Copy').

    Returns:
        list: The final basenames used inside `.backup`, skipping any
            file_names entry that doesn't exist.
    """
    backup_dir = get_backup_dir(dir_name)
    os.makedirs(backup_dir, exist_ok=True)
    _hide_windows_folder(backup_dir)
    archived_names = []
    for file_name in file_names:
        src_path = norm_path(os.path.join(dir_name, file_name))
        if not os.path.isfile(src_path):
            continue
        dst_path = unique_path(os.path.join(backup_dir, file_name))
        # A WIP pack entry is "<base>_wip/name.wip", so the destination
        # subdirectory has to exist before the move.
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        metadata.rename_weight_with_sidecar(src_path, dst_path)
        archived_names.append(os.path.basename(dst_path))
    _remove_emptied_subdirs(dir_name, file_names)
    return archived_names


def unarchive_weight_files(dir_name: str, file_names: list) -> list:
    """Move files (and their sidecars) out of dir_name's `.backup` folder.

    file_names are relative to the archive folder, so a WIP pack member reads
    as "<base>_wip/name.wip" exactly as the archive listing reports it.
    Collisions with a live file are resolved the same way Rename resolves
    them (appending 'Copy').

    Returns:
        list: Restored names relative to dir_name, skipping any file_names
            entry that is not in the archive.
    """
    backup_dir = get_backup_dir(dir_name)
    restored_names = []
    for file_name in file_names:
        src_path = norm_path(os.path.join(backup_dir, file_name))
        if not os.path.isfile(src_path):
            continue
        dst_path = unique_path(os.path.join(dir_name, file_name))
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        metadata.rename_weight_with_sidecar(src_path, dst_path)
        restored_names.append(
            os.path.relpath(dst_path, dir_name).replace(os.sep, "/")
        )
    _remove_emptied_subdirs(backup_dir, file_names)
    return restored_names


def rename_weight_file(
    dir_name: str,
    cur_name: str,
    new_name: str,
    default_ext: str = "",
) -> tuple:
    """Rename a weight file, moving its sidecar metadata with it.

    When new_name has no extension, default_ext (without dot) is appended.
    Name collisions are resolved by appending 'Copy' to the basename.

    Returns:
        tuple: (final_new_name, had_sidecar).

    Raises:
        OSError: On failure.
    """
    base, ext = os.path.splitext(new_name)
    if not ext and default_ext:
        new_name = f"{base}.{default_ext}"
    cur_path = norm_path(os.path.join(dir_name, cur_name))
    new_path = unique_path(os.path.join(dir_name, new_name))
    had_sidecar = metadata.rename_weight_with_sidecar(cur_path, new_path)
    return os.path.basename(new_path), had_sidecar


def convert_weight_files(
    dir_name: str,
    file_names: list,
    source: str,
    destination: str,
    replace_content: bool,
) -> list:
    """Copy weight files replacing source->destination in names (and
    content when replace_content).

    Thin passthrough to io.convert_weight_files so controllers only depend
    on the models package.
    """
    return io.convert_weight_files(
        dir_name,
        file_names,
        source,
        destination,
        replace_content=replace_content,
    )
