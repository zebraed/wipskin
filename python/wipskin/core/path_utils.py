"""File path normalization for WipSkin."""

from __future__ import annotations

import os


def norm_path(path: str) -> str:
    """Normalize a file path and use forward slashes."""
    if not path:
        return path
    return os.path.normpath(path).replace("\\", "/")
