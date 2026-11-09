"""One drawing in, one Reading out: regions, title block, parts list, revision table, notes and dimensions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from dia.perceive import ocr
from dia.perceive.dimensions import ReadDim
from dia.perceive.dimensions import read as read_dims
from dia.perceive.fields import FieldRead, Profile, read_title_block
from dia.perceive.page import Item, Page, load
from dia.perceive.regions import Detector, Template
from dia.settings import ROOT
from dia.settings import load as settings

Box = tuple[float, float, float, float]


@dataclass
class Reading:
    source: str
    size_mm: tuple[float, float]
    regions: dict[str, list[Box]]
    fields: dict[str, FieldRead]
    dims: list[ReadDim]
    bom: list[dict]
    revisions: list[tuple[str, str]]
    notes: list[str]
    items: list[Item] = field(default_factory=list, repr=False)
    warnings: list[str] = field(default_factory=list)


def _rows(items: list[Item], tol: float = 2.0) -> list[list[Item]]:
    rows: list[list[Item]] = []
    for it in sorted(items, key=lambda i: i.cy):
        if rows and abs(rows[-1][0].cy - it.cy) < tol:
            rows[-1].append(it)
        else:
            rows.append([it])
    return [sorted(r, key=lambda i: i.x0) for r in rows]


def parse_revisions(items: list[Item]) -> list[tuple[str, str]]:
    out = []
    for row in _rows(items):
        rev = row[0].text.strip()
        if not re.fullmatch(r"[A-Z]|\d{1,2}", rev):
            continue  # the header row, or noise
        out.append((rev, row[-1].text.strip() if len(row) > 1 else ""))
    return out


def parse_bom(items: list[Item]) -> list[dict]:
    out = []
    for row in _rows(items):
        if len(row) < 4 or not row[0].text.strip().isdigit():
            continue
        cells = [r.text.strip() for r in row]
        if len(cells) > 5:  # a split cell: keep pos, qty, then join the middle, last is material
            cells = [cells[0], cells[1], cells[2], " ".join(cells[3:-1]), cells[-1]]
        while len(cells) < 5:
            cells.append("")
        qty = re.sub(r"\D", "", cells[1])
        out.append(
            {
                "pos": int(cells[0]),
                "qty": int(qty) if qty else None,
                "description": cells[2],
                "reference": cells[3],
                "material": cells[4],
            }
        )
    return out


def parse_notes(items: list[Item]) -> list[str]:
    notes: list[str] = []
    for row in _rows(items, tol=1.6):
        text = " ".join(i.text for i in row).strip()
        m = re.match(r"^(\d{1,2})[.)]\s*(.+)$", text)
        if m:
            notes.append(m[2].strip())
        elif notes and text and not re.match(r"^[A-ZÄÖÜa-z ]{3,30}$", text):  # a wrapped line
            notes[-1] += " " + text
    return notes


class Reader:
    def __init__(self, weights: str | Path | None = None, template: Template | None = None):
        s = settings()
        self.s = s
        self.detector = Detector(
            weights or ROOT / "models" / "regions.pt", s.render.detector_width, s.regions.min_area_fraction
        )
        self.template = template

    def regions(self, page: Page) -> dict[str, list[Box]]:
        found = self.detector.detect(page.image, page.size_mm)
        if self.template is not None:
            fallback = self.template.detect(page.image, page.size_mm)
            for k in ("title_block", "notes"):
                if k not in found and k in fallback:
                    found[k] = fallback[k]
        return found

    def read(
        self,
        path: str | Path | None = None,
        data: bytes | None = None,
        name: str = "",
        profile: Profile | None = None,
        regions: dict[str, list[Box]] | None = None,
    ) -> Reading:
        page = load(path, data, name, dpi=self.s.render.scan_dpi)
        regs = regions or self.regions(page)
        warnings = list(page.notes)
        if page.source == "scan":
            page.items = ocr.read_scan(page, regs)
        tb = regs.get("title_block", [])
        tb_items = [i for b in tb for i in page.within(_pad(b, 1.0))]
        rev_items = [i for b in regs.get("revision_table", []) for i in page.within(_pad(b, 1.0))]
        revs = parse_revisions(rev_items)
        fields = read_title_block(tb_items, profile, self.s.fields.max_value_distance_mm, revs, tb[0] if tb else None)
        if not tb:
            warnings.append("no title block found")
        bom = parse_bom([i for b in regs.get("parts_list", []) for i in page.within(_pad(b, 1.0))])
        notes = parse_notes([i for b in regs.get("notes", []) for i in page.within(_pad(b, 1.5))])
        used = {id(i) for i in tb_items + rev_items}
        view_items = [i for b in regs.get("view", []) for i in page.within(_pad(b, 3.0)) if id(i) not in used]
        seen: set[int] = set()
        view_items = [i for i in view_items if not (id(i) in seen or seen.add(id(i)))]  # type: ignore[func-returns-value]
        dims = read_dims(view_items, self.s.dimensions.max_join_gap_mm)
        return Reading(page.source, page.size_mm, regs, fields, dims, bom, revs, notes, page.items, warnings)


def _pad(b: Box, p: float) -> Box:
    return (b[0] - p, b[1] - p, b[2] + p, b[3] + p)
