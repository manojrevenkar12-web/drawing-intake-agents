"""What changed between two revisions of a drawing.

The two sheets are first aligned (the same dimension rarely sits at the same place: the CAD system re-centres views
when the part changes), using dimensions that read identically on both. Dimensions are then paired by position,
kind and value with an optimal assignment, and every unpaired or altered pair becomes a change."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from dia.perceive.dimensions import ReadDim
from dia.perceive.reader import Reading

MAX_PAIR_MM = 22.0
SURE_CONF = 0.85  # a dimension read with less confidence (or with a repaired text) cannot alone prove a change
TEXT_NEAR_MM = 4.0


def _sure(d: ReadDim) -> bool:
    return d.conf >= SURE_CONF and not d.repairs


def _text_near(r: Reading, x: float, y: float) -> bool:
    return any(abs(i.cx - x) < TEXT_NEAR_MM and abs(i.cy - y) < TEXT_NEAR_MM for i in r.items)


@dataclass
class Found:
    kind: str  # dimension_changed | tolerance_changed | feature_added | feature_removed | field_changed
    what: str  # the dimension text or field name
    before: str = ""
    after: str = ""
    x: float = 0.0  # where on the sheet it is (current sheet; previous sheet for removals)
    y: float = 0.0
    on_previous: bool = False
    certain: bool = True  # False: may be a reading error (OCR repair, low confidence, text seen but not parsed)


def _tol(d: ReadDim) -> tuple:
    return (d.tol_kind, round(d.plus, 3), round(d.minus, 3), d.fit)


def _offset(prev: list[ReadDim], cur: list[ReadDim]) -> tuple[float, float]:
    """Median shift of dimensions that read identically on both sheets."""
    shifts = []
    for a in prev:
        same = [b for b in cur if b.signature() == a.signature() and b.vertical == a.vertical]
        if len(same) == 1:
            shifts.append((same[0].x - a.x, same[0].y - a.y))
    if not shifts:
        return 0.0, 0.0
    s = np.median(np.array(shifts), 0)
    return float(s[0]), float(s[1])


def compare(prev: Reading, cur: Reading) -> list[Found]:
    out: list[Found] = []
    for fld in ("material", "mass_kg", "general_tolerance"):
        fa, fb = prev.fields[fld], cur.fields[fld]
        if fa.value and fb.value and fa.value != fb.value:
            out.append(Found("field_changed", fld, fa.value, fb.value, certain=not (fa.checks or fb.checks)))
    P, C = prev.dims, cur.dims
    if not P or not C:
        return out
    dx, dy = _offset(P, C)
    cost = np.full((len(P), len(C)), 1e6)
    for i, a in enumerate(P):
        for j, b in enumerate(C):
            if a.kind != b.kind or a.vertical != b.vertical:
                continue
            dist = float(np.hypot(b.x - (a.x + dx), b.y - (a.y + dy)))
            if dist > MAX_PAIR_MM:
                continue
            cost[i, j] = (
                dist
                + (0 if a.nominal == b.nominal else 6)
                + (0 if _tol(a) == _tol(b) else 3)
                + (0 if a.count == b.count else 2)
            )
    rows, cols = linear_sum_assignment(cost)
    paired_p, paired_c = set(), set()
    for i, j in zip(rows, cols, strict=True):
        if cost[i, j] >= 1e6:
            continue
        paired_p.add(i)
        paired_c.add(j)
        a, b = P[i], C[j]
        sure = _sure(a) and _sure(b)
        if a.nominal != b.nominal:
            out.append(Found("dimension_changed", b.text, a.text, b.text, b.x, b.y, certain=sure))
        elif _tol(a) != _tol(b):
            out.append(Found("tolerance_changed", b.text, a.text, b.text, b.x, b.y, certain=sure))
        elif a.count != b.count:
            kind = "feature_added" if b.count > a.count else "feature_removed"
            out.append(Found(kind, b.text, a.text, b.text, b.x, b.y, certain=sure))
    for j, b in enumerate(C):
        if j not in paired_c:
            seen = _text_near(prev, b.x - dx, b.y - dy)
            out.append(Found("feature_added", b.text, "", b.text, b.x, b.y, certain=_sure(b) and not seen))
    for i, a in enumerate(P):
        if i not in paired_p:
            seen = _text_near(cur, a.x + dx, a.y + dy)
            out.append(
                Found("feature_removed", a.text, a.text, "", a.x, a.y, on_previous=True, certain=_sure(a) and not seen)
            )
    return out
