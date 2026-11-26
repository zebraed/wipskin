"""Weight file path utilities for WipSkin (listing, export paths, Convert)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from wipskin.core import metadata
from wipskin.core.path_utils import norm_path

_VERSIONED_FILENAME_RE = re.compile(r"^(.+)\.(\d{4})\.([^.]+)$")
_MULTI_EXPORT_INDEX_RE = re.compile(r"_(\d{4})$")


def parse_versioned_filename(filename: str) -> tuple:
    """Split a versioned filename into base name, version int, and extension.

    Versioned form: basename.NNNN.ext (four zero-padded digits).
    Non-versioned files use version 0.
    """
    match = _VERSIONED_FILENAME_RE.match(filename)
    if match:
        return match.group(1), int(match.group(2)), match.group(3)
    base_name, dot_ext = os.path.splitext(filename)
    ext = dot_ext[1:] if dot_ext.startswith(".") else dot_ext
    return base_name, 0, ext


def filter_files_for_view(filenames: list, mode: str = "latest") -> list:
    """Filter filenames for the file viewer.

    mode 'full' returns all names sorted; 'latest' returns the highest
    version per (base_name, ext) group.
    """
    if mode == "full":
        return sorted(filenames)
    best_by_key = {}
    for name in filenames:
        base_name, version, ext = parse_versioned_filename(name)
        key = (base_name, ext)
        if key not in best_by_key or version > best_by_key[key][0]:
            best_by_key[key] = (version, name)
    return sorted([best_by_key[key][1] for key in best_by_key])


def find_latest_versioned_filename(
    directory: str,
    base_name: str,
    extension: str,
) -> str:
    """Return the highest-version filename for base_name.ext in directory.

    Prefers versioned matches (base.NNNN.ext). If none exist, returns
    base.ext when that unversioned file is present, otherwise "".
    """
    directory = norm_path(directory)
    if not directory or not os.path.isdir(directory) or not base_name:
        return ""
    ext = extension.lstrip(".")
    best_name = ""
    best_version = -1
    unversioned_name = f"{base_name}.{ext}"
    for entry in os.listdir(directory):
        parsed_base, version, parsed_ext = parse_versioned_filename(entry)
        if parsed_base != base_name or parsed_ext.lower() != ext.lower():
            continue
        if version > best_version:
            best_version = version
            best_name = entry
    if best_name:
        return best_name
    if os.path.isfile(os.path.join(directory, unversioned_name)):
        return unversioned_name
    # Case-insensitive fallback for extension spelling (jSkin vs jskin)
    for entry in os.listdir(directory):
        parsed_base, version, parsed_ext = parse_versioned_filename(entry)
        if parsed_base == base_name and parsed_ext.lower() == ext.lower():
            return entry
    return ""


def resolve_pack_member_filename(
    directory: str,
    recorded_name: str,
    prefer_latest: bool = True,
) -> str:
    """Resolve a packFiles entry to an on-disk filename.

    When prefer_latest is True, return the newest base.NNNN.ext for the
    recorded entry's (base, ext). Otherwise return recorded_name when it
    exists on disk.
    """
    directory = norm_path(directory)
    recorded_name = os.path.basename(str(recorded_name or "").strip())
    if not recorded_name:
        return ""
    base_name, _version, ext = parse_versioned_filename(recorded_name)
    if prefer_latest:
        latest = find_latest_versioned_filename(directory, base_name, ext)
        if latest:
            return latest
        return ""
    if directory and os.path.isfile(os.path.join(directory, recorded_name)):
        return recorded_name
    return ""


def open_directory(path: str) -> bool:
    """Open a directory in the OS file manager."""
    path = norm_path(path)
    if not os.path.isdir(path):
        return False
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)
    return True


def resolve_export_path(
    directory: str,
    base_name: str,
    extension: str,
    auto_version: bool = False,
) -> str:
    """Build the full export path for a new weight file.

    base_name must not include a version suffix or extension.
    When auto_version is True, scan directory for base_name.NNNN.ext and use
    the next four-digit version. Otherwise use base_name.ext (may overwrite).
    """
    directory = norm_path(directory)
    ext = extension.lstrip(".")
    if auto_version:
        max_version = 0
        if os.path.isdir(directory):
            for entry in os.listdir(directory):
                parsed_base, version, parsed_ext = parse_versioned_filename(entry)
                if parsed_base == base_name and parsed_ext == ext:
                    if version > max_version:
                        max_version = version
        next_version = max_version + 1
        filename = f"{base_name}.{int(next_version):04}.{ext}"
    else:
        filename = f"{base_name}.{ext}"
    return norm_path(os.path.join(directory, filename))


def unique_filename_in_directory(directory: str, filename: str) -> str:
    """Return filename, or an incremented versioned name if it already exists."""
    full_path = os.path.join(directory, filename)
    if not os.path.exists(full_path):
        return filename
    base_name, version, ext = parse_versioned_filename(filename)
    if version == 0:
        version = 1
    while True:
        candidate = f"{base_name}.{int(version):04}.{ext}"
        candidate_path = os.path.join(directory, candidate)
        if not os.path.exists(candidate_path):
            return candidate
        version += 1


def list_base_names_for_extension(directory: str, extension: str) -> list:
    """Return sorted unique base names for files with the given extension.

    Versioned files (base.NNNN.ext) contribute the unversioned base name.
    Multi-export suffixes (base_0001) are stripped so the combobox shows
    the shared manual-naming root only.
    """
    directory = norm_path(directory)
    if not directory or not os.path.isdir(directory):
        return []
    ext = extension.lstrip(".").lower()
    names = set()
    for entry in os.listdir(directory):
        base_name, _version, parsed_ext = parse_versioned_filename(entry)
        if parsed_ext.lower() != ext:
            continue
        base_name = strip_multi_export_index(base_name)
        if base_name:
            names.add(base_name)
    return sorted(names, key=lambda value: value.lower())


def strip_multi_export_index(base_name: str) -> str:
    """Remove a trailing _NNNN multi-export index from a base name."""
    if not base_name:
        return ""
    match = _MULTI_EXPORT_INDEX_RE.search(base_name)
    if not match:
        return base_name
    return base_name[: match.start()]


def apply_multi_export_index(base_name: str, index: int) -> str:
    """Append a 1-based _NNNN multi-export index to a base name."""
    return f"{base_name}_{int(index):04d}"


def sanitize_export_base_name(name, strip_extensions=()) -> str:
    """Strip path / known extensions / illegal filename characters from a typed name.

    Returns:
        str: Empty string when nothing usable remains.
    """
    if name is None:
        return ""
    text = str(name).strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    lower = text.lower()
    for extension in strip_extensions:
        suffix = extension if extension.startswith(".") else f".{extension}"
        if lower.endswith(suffix.lower()):
            text = text[: -len(suffix)]
            lower = text.lower()
            break
    text = text.strip().rstrip(".")
    for char in '<>:"/\\|?*':
        text = text.replace(char, "")
    return text.strip()


def is_probably_text_file(path: str) -> bool:
    """True if the file looks like UTF-8 text (for Convert content replace)."""
    try:
        with open(path, "rb") as file_id:
            sample = file_id.read(8192)
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def convert_weight_files(
    directory: str,
    filenames: list,
    source: str,
    destination: str,
    replace_content: bool = False,
) -> list:
    """Copy weight files replacing source with destination in filenames.

    When replace_content is True and the file is text, also replace inside the file.
    Binary files always copy bytes only.

    Returns:
        list: (src_name, dst_name) pairs written.
    """
    if not source:
        return []
    directory = norm_path(directory)
    created = []
    for src_name in filenames:
        dst_name = src_name.replace(source, destination)
        if dst_name == src_name:
            continue
        src_path = os.path.join(directory, src_name)
        if not os.path.isfile(src_path):
            continue
        dst_name = unique_filename_in_directory(directory, dst_name)
        dst_path = os.path.join(directory, dst_name)
        use_content_replace = replace_content and is_probably_text_file(src_path)
        if use_content_replace:
            with open(src_path, encoding="utf-8") as file_id:
                data = file_id.read()
            data = data.replace(source, destination)
            with open(dst_path, "w", encoding="utf-8", newline="\n") as file_id:
                file_id.write(data)
        else:
            shutil.copy2(src_path, dst_path)
        metadata.copy_sidecar(src_path, dst_path)
        created.append((src_name, dst_name))
    return created
