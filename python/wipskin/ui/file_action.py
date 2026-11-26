"""One entry a skin format adds to the Files list's right-click menu."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class FileAction:
    """Menu entry offered for the current file selection.

    Attributes:
        label (str): Menu text.
        callback (callable): Called with no arguments when chosen.
        enabled (bool): False greys the entry out.
        tooltip (str): Explains the entry, or why it is greyed out.
        icon (str): SVG file name from ui/icons, or empty for none.
    """

    label: str
    callback: Callable[[], None]
    enabled: bool = True
    tooltip: str = ""
    icon: str = ""
