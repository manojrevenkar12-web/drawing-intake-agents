"""ISO 2768-1 general tolerances for linear dimensions (classes f, m, c), the values used when a drawing's title
block says e.g. "ISO 2768-m" and a dimension carries no tolerance of its own."""

from __future__ import annotations

import re

# (above, up to and including): permissible deviation +/- mm
RANGES = ((0.5, 3), (3, 6), (6, 30), (30, 120), (120, 400), (400, 1000))
TABLE = {
    "f": (0.05, 0.05, 0.1, 0.15, 0.2, 0.3),
    "m": (0.1, 0.1, 0.2, 0.3, 0.5, 0.8),
    "c": (0.2, 0.3, 0.5, 0.8, 1.2, 2.0),
}

PATTERN = re.compile(r"(?:ISO|DIN\s*ISO)\s*2768\s*[-‐–]?\s*(?P<cls>[fmcv])(?:[A-Z])?", re.I)


def parse_class(text: str) -> str | None:
    m = PATTERN.search(text or "")
    if not m:
        return None
    cls = m["cls"].lower()
    return cls if cls in TABLE else None


def deviation(cls: str, nominal: float) -> float:
    if cls not in TABLE:
        raise KeyError(cls)
    if nominal < 0.5:
        raise ValueError("ISO 2768-1 sets no general tolerance below 0.5 mm")
    for i, (lo, hi) in enumerate(RANGES):
        if lo < nominal <= hi or (i == 0 and nominal == lo):
            return TABLE[cls][i]
    raise ValueError(f"{nominal} mm above the 1000 mm covered here")
