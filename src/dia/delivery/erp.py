"""The plant's ERP is old: it takes material masters and parts lists as fixed-width import files and rejects a
whole file for one bad record. This module writes those files from approved values only, and `LegacyErp` is a
stand-in for the import job, with the same checks, so a delivery can be rehearsed before it touches the real one.

Every record carries an idempotency key (drawing number, revision, content hash), so importing the same drawing
twice changes nothing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# (name, width, required)
MATERIAL_LAYOUT = (
    ("RECTYPE", 4, True),
    ("MATNR", 18, True),
    ("REV", 2, True),
    ("WERKS", 4, True),
    ("MTART", 4, True),
    ("MAKTX", 40, True),
    ("WERKSTOFF", 20, True),
    ("GEWICHT", 9, False),
    ("ALLGTOL", 1, False),
    ("DATUM", 8, True),
    ("IDEMKEY", 16, True),
)
BOM_LAYOUT = (
    ("RECTYPE", 4, True),
    ("MATNR", 18, True),
    ("POSNR", 4, True),
    ("MENGE", 6, True),
    ("IDNRK", 30, True),
    ("POSTP", 40, False),
)


def _fixed(values: dict[str, str], layout) -> str:
    out = []
    for name, width, required in layout:
        v = str(values.get(name, "") or "")
        if required and not v:
            raise ValueError(f"{name} is required")
        if len(v) > width:
            raise ValueError(f"{name} {v!r} longer than {width}")
        out.append(v.ljust(width))
    return "".join(out)


def idempotency_key(drawing_number: str, revision: str, content: bytes) -> str:
    return hashlib.sha256(f"{drawing_number}|{revision}|".encode() + content).hexdigest()[:16]


def material_record(fields: dict[str, str], plant: str, material_type: str, key: str) -> str:
    return _fixed(
        {
            "RECTYPE": "MAT1",
            "MATNR": fields["drawing_number"].replace(" ", ""),
            "REV": fields["revision"][-2:],
            "WERKS": plant,
            "MTART": material_type,
            "MAKTX": fields["title"][:40],
            "WERKSTOFF": fields["material"],
            "GEWICHT": fields.get("mass_kg", ""),
            "ALLGTOL": (fields.get("general_tolerance") or "").upper(),
            "DATUM": fields["date"].replace("-", ""),
            "IDEMKEY": key,
        },
        MATERIAL_LAYOUT,
    )


def bom_records(matnr: str, rows: list[dict]) -> list[str]:
    return [
        _fixed(
            {
                "RECTYPE": "BOM1",
                "MATNR": matnr.replace(" ", ""),
                "POSNR": f"{r['pos']:04d}",
                "MENGE": str(r["qty"]),
                "IDNRK": r["reference"][:30],
                "POSTP": r["description"][:40],
            },
            BOM_LAYOUT,
        )
        for r in rows
        if r.get("qty")
    ]


@dataclass
class LegacyErp:
    """Stand-in for the ERP import job: all-or-nothing per file, duplicate keys are ignored."""

    materials: dict[str, str] = field(default_factory=dict)  # idempotency key -> record
    boms: dict[str, list[str]] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def import_file(self, lines: list[str]) -> dict:
        widths = {"MAT1": sum(w for _, w, _ in MATERIAL_LAYOUT), "BOM1": sum(w for _, w, _ in BOM_LAYOUT)}
        for n, line in enumerate(lines, 1):
            t = line[:4]
            if t not in widths or len(line) != widths[t]:
                self.log.append(f"rejected file: line {n} is not a valid {t} record")
                return {"status": "rejected", "line": n}
        created = 0
        boms: dict[str, list[str]] = {}
        for line in lines:
            if line.startswith("MAT1"):
                key = line[-16:]
                if key in self.materials:
                    continue
                self.materials[key] = line
                created += 1
            else:
                boms.setdefault(line[4:22].strip(), []).append(line)
        self.boms.update(boms)  # a parts list is replaced as a whole, never appended to
        self.log.append(f"imported {created} new material record(s)")
        return {"status": "ok", "created": created}
