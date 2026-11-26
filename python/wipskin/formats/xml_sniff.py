"""Identify a weight XML by its root tag, reading only the file header."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from wipskin.core.file_cache import get_stat_stamp
from wipskin.core.path_utils import norm_path

# Incremented when an XML is actually parsed from disk (test hook).
_sniff_count = 0

_tag_cache: dict = {}


def read_root_tag(path):
    """Root element tag of an XML file, or None on failure."""
    global _sniff_count
    _sniff_count += 1
    try:
        with open(path, "rb") as source:
            for _event, elem in ET.iterparse(source, events=("start",)):
                return elem.tag
    except (ET.ParseError, OSError):
        return None
    return None


def classify(path):
    """Cached root tag for path; re-sniffs only when (mtime, size) changes."""
    key = norm_path(path)
    stamp = get_stat_stamp(path)
    if stamp is None:
        _tag_cache.pop(key, None)
        return None

    cached = _tag_cache.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    tag = read_root_tag(path)
    _tag_cache[key] = (stamp, tag)
    return tag


def has_root_tag(path, expected):
    """True when path's root element tag equals expected."""
    return classify(path) == expected


def clear_cache():
    """Drop all cached root-tag classifications."""
    _tag_cache.clear()


def sniff_count():
    """Times an XML has been parsed from disk since last reset (test hook)."""
    return _sniff_count


def reset_sniff_count():
    global _sniff_count
    _sniff_count = 0
