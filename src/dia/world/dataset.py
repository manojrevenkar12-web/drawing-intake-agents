"""Generate the drawing packages: per customer layout, current drawings (some with their previous revision), as
vector PDFs or scans. Writes the files the reader gets under data/<split>/ and the truth under data/truth/<split>/,
which only the evaluation reads."""

from __future__ import annotations

import json
import random
from pathlib import Path

import cv2

from dia.settings import ROOT, load
from dia.world.layouts import LAYOUTS
from dia.world.model import Sheet
from dia.world.parts import make_part, revise
from dia.world.render import degrade, rasterize, render

DATA = ROOT / "data"


def _emit(sheet: Sheet, pdf: bytes, rng: random.Random, out: Path, truth: Path, dpi: int) -> None:
    lay = LAYOUTS[sheet.layout]
    if sheet.medium == "scan":
        img, tf = degrade(rasterize(pdf, dpi), rng, lay.language)
        cv2.imwrite(str(out / f"{sheet.id}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        extra = {"scan": {**tf, "dpi": dpi}}
    else:
        (out / f"{sheet.id}.pdf").write_bytes(pdf)
        extra = {}
    (truth / f"{sheet.id}.json").write_text(json.dumps({**sheet.to_dict(), **extra}, ensure_ascii=False, indent=1))


def generate(
    split: str,
    layouts: list[str],
    per_layout: int,
    seed: int,
    root: Path = DATA,
    dpi: int | None = None,
    scan_share: float | None = None,
    revision_share: float | None = None,
) -> list[str]:
    s = load()
    dpi = dpi or s.render.scan_dpi
    scan_share = s.world.scan_share if scan_share is None else scan_share
    revision_share = s.world.revision_share if revision_share is None else revision_share
    out, truth = root / split, root / "truth" / split
    out.mkdir(parents=True, exist_ok=True)
    truth.mkdir(parents=True, exist_ok=True)
    ids = []
    for li, name in enumerate(layouts):
        lay = LAYOUTS[name]
        for i in range(per_layout):
            rng = random.Random(f"{seed}-{split}-{name}-{i}")
            base = f"{name}-{i:03d}"
            part = make_part(rng, name, lay.language)
            prev_id = None
            changes = []
            if rng.random() < revision_share:
                prev = Sheet(
                    f"{base}-r0", name, split, "scan" if rng.random() < scan_share else "vector", part, lay.sheet
                )
                _emit(prev, render(prev, lay, rng), rng, out, truth, dpi)
                ids.append(prev.id)
                part, changes = revise(rng, part, name, lay.language)
                prev_id = prev.id
            sheet = Sheet(
                base,
                name,
                split,
                "scan" if rng.random() < scan_share else "vector",
                part,
                lay.sheet,
                previous=prev_id,
                changes=changes,
            )
            _emit(sheet, render(sheet, lay, rng), rng, out, truth, dpi)
            ids.append(sheet.id)
        del li
    (root / f"{split}_index.json").write_text(json.dumps(ids, indent=1))
    return ids


def main() -> None:
    s = load()
    generate("dev", s.world.dev_layouts, s.world.drawings_per_layout_dev, s.world.seed)
    generate("heldout", s.world.heldout_layouts, s.world.drawings_per_layout_heldout, s.world.seed)


if __name__ == "__main__":
    main()
