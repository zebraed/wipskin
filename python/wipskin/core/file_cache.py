"""Cache results keyed on a file's (mtime, size)."""

from __future__ import annotations

import os

from wipskin.core.path_utils import norm_path

_result_cache: dict = {}


def get_stat_stamp(path):
    """Return (st_mtime_ns, st_size) for path, or None when unstattable."""
    try:
        stat_result = os.stat(path)
    except OSError:
        return None

    return (stat_result.st_mtime_ns, stat_result.st_size)


def memoize_by_stat(path, compute):
    """Return compute(path), cached while (mtime, size) is unchanged."""
    key = norm_path(path)
    stamp = get_stat_stamp(path)
    if stamp is None:
        return compute(path)

    cached = _result_cache.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    result = compute(path)
    _result_cache[key] = (stamp, result)
    return result


def clear_cache():
    """Drop every memoized result."""
    _result_cache.clear()
