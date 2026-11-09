"""Read dimension texts in the views: join the pieces OCR splits a dimension into, repair the usual OCR confusions
(Ø read as @ or 0, ± read as + or #, decimal commas), and parse the result with a small grammar:

    [count x] [Ø | R | M] nominal [x45°] [tolerance]      tolerance: ±d | +d/-d | +d/0 | fit class (H7, g6, js6)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dia.perceive.page import Item

FIT = r"(?:H|h|g|f|js|k|p)\d{1,2}"
NUM = r"\d+(?:\.\d+)?"
GRAMMAR = re.compile(
    rf"^(?:(?P<count>\d{{1,2}})\s*[x×X]\s*)?(?P<prefix>Ø|R|M)?\s*(?P<nominal>{NUM})"
    rf"(?P<chamfer>\s*[x×X]\s*45\s*°?)?"
    rf"(?:\s*(?:(?P<sym>±\s*{NUM})|(?P<asym>\+\s*{NUM}\s*/\s*(?:-\s*{NUM}|0))|(?P<fit>{FIT})))?$"
)


@dataclass
class ReadDim:
    kind: str
    nominal: float
    tol_kind: str  # general | sym | asym | fit
    plus: float = 0.0
    minus: float = 0.0
    fit: str = ""
    count: int = 1
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    vertical: bool = False
    conf: float = 1.0
    repairs: list[str] = field(default_factory=list)

    def signature(self) -> tuple:
        return (
            self.kind,
            round(self.nominal, 3),
            self.tol_kind,
            round(self.plus, 3),
            round(self.minus, 3),
            self.fit,
            self.count,
        )


def repair(text: str) -> tuple[str, list[str]]:
    """Undo common OCR confusions in a dimension text. Returns the text and what was changed."""
    fixes = []
    t = text.strip().replace("—", "-").replace("–", "-").replace("’", "").replace("'", "")
    if "," in t and re.search(r"\d,\d", t):
        t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    t = re.sub(r"\s+", " ", t)
    # Ø read as @, ©, ®, ø, o/O, or 0/8 directly before a number
    new = re.sub(r"(^|\s|x)[@©®øoO∅]\s?(?=\d)", r"\1Ø", t)
    if new != t:
        fixes.append("diameter sign")
        t = new
    new = re.sub(r"(^|\s|x\s?)0(?=[1-9]\d*(?:\.\d+)?(?:\s|$|[A-Za-z]))", r"\1Ø", t)
    if new != t:
        fixes.append("diameter read as 0")
        t = new
    # ± read as #, I+, |+, +- or a lone + without a lower deviation
    new = re.sub(r"(?:#|I\+|\|\+|\+-|\+/-)\s?(?=\d)", "±", t)
    if new != t:
        fixes.append("plus-minus sign")
        t = new
    if re.search(rf"\s\+\s?{NUM}$", t) and "/" not in t:
        t = re.sub(rf"\s\+\s?(?={NUM}$)", " ±", t)
        fixes.append("plus-minus read as plus")
    t = re.sub(r"(?<=\d)\s*[xX]\s*(?=Ø|M|R|\d)", "x ", t) if re.match(r"^\d{1,2}\s*[xX]", t) else t
    t = t.replace("x ", "x ").replace("×", "x")
    t = re.sub(r"^(\d{1,2})x\s*", r"\1x ", t)
    t = re.sub(r"^(\d{1,2})\s*[xX]\s+", r"\1x ", t)
    t = re.sub(r"(?<=\d)\s*°", "°", t)
    # grammar: a count ("2x") or a fit class ("js6") belongs to a diameter, so a leading 8 or 0 there is a Ø
    m = re.match(rf"^(\d{{1,2}}x )?[80](?=\d)({NUM})(\s+(?:{FIT}))?$", t)
    if m and (m[1] or m[3]):
        t = f"{m[1] or ''}Ø{m[2]}{m[3] or ''}"
        fixes.append("diameter read as 8 or 0")
    return t, fixes


def parse(text: str) -> ReadDim | None:
    t, fixes = repair(text)
    m = GRAMMAR.match(t.replace("x ", "x").replace(" x", "x"))
    if not m:
        m = GRAMMAR.match(t)
    if not m:
        return None
    nominal = float(m["nominal"])
    prefix = m["prefix"]
    if m["chamfer"]:
        kind = "chamfer"
    elif prefix == "Ø":
        kind = "diameter"
    elif prefix == "R":
        kind = "radius"
    elif prefix == "M":
        kind = "thread"
    else:
        kind = "linear"
    if nominal <= 0 or nominal > 2000:
        return None
    d = ReadDim(kind, nominal, "general", count=int(m["count"]) if m["count"] else 1, text=t, repairs=fixes)
    if m["sym"]:
        v = float(re.sub(r"[±\s]", "", m["sym"]))
        d.tol_kind, d.plus, d.minus = "sym", v, -v
    elif m["asym"]:
        up, lo = re.sub(r"\s", "", m["asym"])[1:].split("/")
        d.tol_kind, d.plus, d.minus = "asym", float(up), float(lo)
    elif m["fit"]:
        d.tol_kind, d.fit = "fit", m["fit"]
    if kind == "linear" and d.count > 1:
        return None  # "4x 20" is not something this reader trusts
    return d


def join(items: list[Item], max_gap: float) -> list[tuple[str, Item, float, bool]]:
    """Group items that sit on one text line (horizontal) or one column (vertical) with small gaps.
    Returns (text, a representative box as an Item, mean confidence, vertical)."""
    out = []
    for vertical in (False, True):
        pool = sorted([i for i in items if i.vertical == vertical], key=lambda i: i.y1 if vertical else i.x0)
        if vertical:
            pool = sorted(pool, key=lambda i: -i.y1)  # vertical text reads bottom to top
        used = [False] * len(pool)
        for a in range(len(pool)):
            if used[a]:
                continue
            group = [pool[a]]
            used[a] = True
            changed = True
            while changed:
                changed = False
                last = group[-1]
                for b in range(len(pool)):
                    if used[b]:
                        continue
                    o = pool[b]
                    if not vertical:
                        same_line = abs(o.cy - last.cy) < 0.6 * max(last.h, o.h, 1.0)
                        gap = o.x0 - last.x1
                    else:
                        same_line = abs(o.cx - last.cx) < 0.6 * max(last.h, o.h, 1.0)
                        gap = last.y0 - o.y1
                    if same_line and -0.5 <= gap <= max_gap:
                        group.append(o)
                        used[b] = True
                        changed = True
                        break
            text = " ".join(g.text for g in group)
            box = Item(
                text,
                min(g.x0 for g in group),
                min(g.y0 for g in group),
                max(g.x1 for g in group),
                max(g.y1 for g in group),
                vertical,
                min(g.conf for g in group),
            )
            out.append((text, box, box.conf, vertical))
    return out


def read(items: list[Item], max_gap: float) -> list[ReadDim]:
    dims = []
    for text, box, conf, vertical in join(items, max_gap):
        d = parse(text)
        if d is None:
            # a group may hold a dimension plus a stray token: try dropping the last or first piece
            parts = text.split(" ")
            for cand in (" ".join(parts[:-1]), " ".join(parts[1:])):
                if cand and (d := parse(cand)) is not None:
                    break
        if d is None:
            continue
        d.x, d.y, d.vertical = box.cx, box.cy, vertical
        d.conf = conf * (0.85 if d.repairs else 1.0)
        dims.append(d)
    return dims
