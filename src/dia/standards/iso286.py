"""ISO 286-1 limits and fits for the classes this project resolves.

Standard tolerance grades (IT, micrometres) and shaft fundamental deviations for nominal sizes up to 500 mm, from
ISO 286-1 Table 1 and Tables 2-3 (as reproduced in DIN ISO 286 extracts). Hole classes use the H basis (EI = 0);
shafts f, g, h and js are supported. A class outside this set is reported as unknown rather than guessed.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass

# Upper bounds of the nominal size ranges, "above ... up to and including".
SIZE_UPPER = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)

IT = {
    6: (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7: (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8: (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9: (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
}

# Upper deviation es of shafts, micrometres, same size ranges.
SHAFT_ES = {
    "f": (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68),
    "g": (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20),
    "h": (0,) * 13,
}

CLASS = re.compile(r"^(?P<letter>H|f|g|h|js)(?P<grade>\d{1,2})$")


@dataclass(frozen=True)
class Limits:
    lower: float  # mm deviation from nominal
    upper: float

    @property
    def width(self) -> float:
        return self.upper - self.lower


def size_index(nominal: float) -> int:
    if nominal <= 0 or nominal > SIZE_UPPER[-1]:
        raise ValueError(f"nominal size {nominal} mm is outside 0-500 mm")
    return bisect_left(SIZE_UPPER, nominal)


def it_grade(grade: int, nominal: float) -> float:
    """Tolerance width in mm."""
    if grade not in IT:
        raise KeyError(f"IT{grade} not tabulated here")
    return IT[grade][size_index(nominal)] / 1000


def fit_limits(code: str, nominal: float) -> Limits:
    """Deviations in mm for a tolerance class such as H7, g6 or js9."""
    m = CLASS.match(code.strip())
    if not m:
        raise KeyError(f"tolerance class {code!r} not supported")
    letter, grade = m["letter"], int(m["grade"])
    width = it_grade(grade, nominal)
    if letter == "H":
        return Limits(0.0, width)
    if letter == "js":
        return Limits(-width / 2, width / 2)
    es = SHAFT_ES[letter][size_index(nominal)] / 1000
    return Limits(es - width, es)


def best_grade(width_mm: float, nominal: float) -> int | None:
    """The coarsest IT grade whose width is no larger than `width_mm` (what a process must hold)."""
    fits = [g for g in sorted(IT) if it_grade(g, nominal) <= width_mm + 1e-9]
    return max(fits) if fits else None
