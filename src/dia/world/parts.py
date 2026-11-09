"""Parametric parts as a customer's designer would draw them: plates, shafts, flanges, brackets and small
assemblies, with their dimensions, tolerances, notes, parts list and revision history.

Each part also carries `views`: what to draw (rectangles, circles, lines) and where each dimension goes, in part
millimetres; the renderer scales and places them on the sheet."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from dia.world.model import BomRow, Change, Dim, Part, Requirement, RevRow, Tol

MATERIALS = {
    "plate": ["S235JR", "S355J2", "1.4301", "EN AW-6082-T6"],
    "bracket": ["DC01", "S235JR", "1.4301"],
    "shaft": ["C45E", "42CrMo4", "1.4305"],
    "flange": ["S355J2", "1.4404", "EN-GJS-400-15"],
    "assembly": ["S235JR", "S355J2"],
}
DENSITY = {  # g/cm3
    "S235JR": 7.85,
    "S355J2": 7.85,
    "1.4301": 7.9,
    "1.4305": 7.9,
    "1.4404": 8.0,
    "EN AW-6082-T6": 2.7,
    "DC01": 7.85,
    "C45E": 7.85,
    "42CrMo4": 7.85,
    "EN-GJS-400-15": 7.1,
}
TITLES = {
    "plate": {
        "en": ["Mounting plate", "Base plate", "Adapter plate", "Cover plate"],
        "de": ["Grundplatte", "Adapterplatte", "Montageplatte", "Abdeckplatte"],
    },
    "bracket": {
        "en": ["Angle bracket", "Sensor bracket", "Support bracket"],
        "de": ["Winkelhalter", "Sensorhalter", "Konsole"],
    },
    "shaft": {"en": ["Drive shaft", "Idler shaft", "Pivot pin"], "de": ["Antriebswelle", "Umlenkwelle", "Lagerbolzen"]},
    "flange": {"en": ["Bearing flange", "Coupling flange"], "de": ["Lagerflansch", "Kupplungsflansch"]},
    "assembly": {
        "en": ["Bearing block assembly", "Guide carriage assembly"],
        "de": ["Lagerbock kpl.", "Führungswagen kpl."],
    },
}

# Notes as printed (per language) and the requirement each one states.
NOTES = {
    "edge_break": (
        {"en": "Break all sharp edges 0.5 x 45°", "de": "Alle scharfen Kanten 0,5 x 45° brechen"},
        Requirement("edge_break", "0.5x45°"),
    ),
    "deburr": ({"en": "Deburr all edges", "de": "Alle Kanten entgraten"}, Requirement("deburr", "yes")),
    "zinc": (
        {"en": "Zinc plated Fe//Zn8//C to ISO 2081", "de": "Galvanisch verzinkt Fe//Zn8//C nach ISO 2081"},
        Requirement("surface", "Fe//Zn8//C", "ISO 2081"),
    ),
    "powder": (
        {"en": "Powder coated RAL 7035", "de": "Pulverbeschichtet RAL 7035"},
        Requirement("surface", "RAL 7035"),
    ),
    "anodise": (
        {"en": "Anodised clear, 15 µm", "de": "Eloxiert farblos, 15 µm"},
        Requirement("surface", "anodised 15 µm"),
    ),
    "cert": (
        {"en": "Material certificate EN 10204 3.1 required", "de": "Abnahmeprüfzeugnis EN 10204 3.1 erforderlich"},
        Requirement("certificate", "3.1", "EN 10204"),
    ),
    "hardened": (
        {"en": "Hardened and tempered 28-32 HRC", "de": "Vergütet auf 28-32 HRC"},
        Requirement("heat_treatment", "28-32 HRC"),
    ),
    "rohs": (
        {"en": "RoHS compliant (2011/65/EU)", "de": "RoHS-konform (2011/65/EU)"},
        Requirement("compliance", "RoHS", "2011/65/EU"),
    ),
    "radii": ({"en": "Unmarked radii R0.5", "de": "Nicht bemaßte Radien R0,5"}, Requirement("unmarked_radius", "0.5")),
}

DRAWING_NUMBER = {
    "acme_rail": lambda r: f"AR-{r.randint(100, 999)}-{r.randint(1000, 9999)}",
    "boltwerk": lambda r: f"BW {r.randint(1000, 9999)}.{r.randint(10, 99)}.{r.randint(1, 999):03d}",
    "nordlicht": lambda r: f"NL{r.randint(100000, 999999)}",
    "sitec": lambda r: f"SIT-{r.randint(10, 99)}-{r.randint(10000, 99999)}",
    "vanderhoek": lambda r: f"VH{r.randint(1000, 9999)}-{r.randint(10, 99)}",
    "kranich": lambda r: f"{r.randint(100, 999)}.{r.randint(100, 999)}.{r.randint(10, 99)}",
    "meridian": lambda r: f"MRC/{r.randint(1000, 9999)}/{r.choice('ABCDEFGH')}",
    "tessaro": lambda r: f"TM{r.randint(10, 99)}{r.randint(1000, 9999)}",
}
REV_STYLE = {"boltwerk": "num", "kranich": "num", "nordlicht": "num"}  # others use letters


def rev_label(layout: str, n: int) -> str:
    return f"{n:02d}" if REV_STYLE.get(layout) == "num" else "ABCDEFGHJK"[n]


@dataclass
class View:
    name: str
    w: float
    h: float
    shapes: list[tuple] = field(default_factory=list)  # ("rect", x, y, w, h) | ("circle", cx, cy, r) | ("line", ...)
    placements: dict[str, tuple] = field(default_factory=dict)  # dim key -> placement


def _general() -> Tol:
    return Tol("general")


def _tol(r: random.Random, nominal: float, fit_choices: list[str] | None = None, p_tight: float = 0.25) -> Tol:
    if fit_choices and r.random() < 0.6:
        return Tol("fit", fit=r.choice(fit_choices))
    u = r.random()
    if u < p_tight:
        v = r.choice([0.05, 0.1, 0.2])
        return Tol("sym", plus=v, minus=-v)
    if u < p_tight + 0.08:
        return Tol("asym", plus=r.choice([0.1, 0.2]), minus=r.choice([0.0, -0.05, -0.1]))
    return _general()


def _rnd(r: random.Random, lo: float, hi: float, step: float = 1.0) -> float:
    return round(r.randrange(int(lo / step), int(hi / step) + 1) * step, 2)


# ------------------------------------------------------------------ families


def plate(r: random.Random) -> tuple[dict, list[Dim]]:
    L, W = _rnd(r, 80, 240, 5), _rnd(r, 50, 150, 5)
    T = r.choice([6, 8, 10, 12, 15, 20])
    n = r.randint(2, 4)
    kind = r.choice(["clear", "fit", "thread"])
    dia = {"clear": r.choice([6.6, 9, 11, 13.5]), "fit": r.choice([8, 10, 12, 16]), "thread": r.choice([6, 8, 10])}[
        kind
    ]
    xs = sorted(r.sample(range(int(L * 0.15), int(L * 0.85), 5), n))
    ys = [round(W * r.choice([0.25, 0.5, 0.75]), 1) for _ in range(n)]
    radius = r.choice([0, 3, 5, 8])
    geo = {
        "L": L,
        "W": W,
        "T": T,
        "holes": [(x, y) for x, y in zip(xs, ys, strict=True)],
        "dia": dia,
        "kind": kind,
        "radius": radius,
    }
    dims = [
        Dim("length", "linear", L, _tol(r, L)),
        Dim("width", "linear", W, _tol(r, W)),
        Dim("thickness", "linear", T, _tol(r, T, p_tight=0.35)),
    ]
    if kind == "thread":
        dims.append(Dim("holes.dia", "thread", dia, Tol("general"), count=n))
    else:
        dims.append(Dim("holes.dia", "diameter", dia, _tol(r, dia, ["H7", "H8"] if kind == "fit" else None), count=n))
    for i, (x, y) in enumerate(geo["holes"]):
        dims.append(Dim(f"hole_{i + 1}.x", "linear", float(x), _tol(r, x, p_tight=0.15)))
        if i == 0 or y != geo["holes"][i - 1][1]:
            dims.append(Dim(f"hole_{i + 1}.y", "linear", float(y), _general()))
    if radius:
        dims.append(Dim("corner.radius", "radius", radius, _general(), count=4))
    return geo, dims


def shaft(r: random.Random) -> tuple[dict, list[Dim]]:
    n = r.randint(2, 4)
    lens = [_rnd(r, 20, 80, 5) for _ in range(n)]
    d0 = _rnd(r, 25, 60, 5)
    dias = [d0]
    for _ in range(n - 1):
        dias.append(max(10, dias[-1] - r.choice([5, 10])))
    if r.random() < 0.3:
        r.shuffle(dias)
    thread = r.random() < 0.5
    geo = {"lens": lens, "dias": dias, "thread": thread, "chamfer": r.choice([0.5, 1.0, 1.5])}
    dims = [Dim("length", "linear", float(sum(lens)), _tol(r, sum(lens)))]
    for i, (ln, d) in enumerate(zip(lens, dias, strict=True)):
        dims.append(Dim(f"step_{i + 1}.dia", "diameter", float(d), _tol(r, d, ["g6", "h6", "f7", "h7", "js6"])))
        if i < n - 1:
            dims.append(Dim(f"step_{i + 1}.len", "linear", float(ln), _tol(r, ln, p_tight=0.2)))
    dims.append(Dim("end.chamfer", "chamfer", geo["chamfer"], _general(), count=2))
    if thread:
        dims.append(Dim("end.thread", "thread", float(min(dias[-1], 20) // 2 * 2), _general()))
    return geo, dims


def flange(r: random.Random) -> tuple[dict, list[Dim]]:
    od = _rnd(r, 90, 220, 10)
    bore = _rnd(r, 20, od * 0.4, 2)
    pcd = round((od + bore) / 2 + r.choice([0, 5, 10]), 0)
    n = r.choice([4, 6, 8])
    hole = r.choice([9, 11, 13.5])
    t = r.choice([12, 15, 20, 25])
    geo = {"od": od, "bore": bore, "pcd": pcd, "n": n, "hole": hole, "t": t}
    dims = [
        Dim("od.dia", "diameter", od, _tol(r, od, p_tight=0.15)),
        Dim("bore.dia", "diameter", bore, _tol(r, bore, ["H7", "H8"])),
        Dim("pcd.dia", "diameter", pcd, _general()),
        Dim("holes.dia", "diameter", hole, _general(), count=n),
        Dim("thickness", "linear", t, _tol(r, t)),
    ]
    return geo, dims


def bracket(r: random.Random) -> tuple[dict, list[Dim]]:
    a, b = _rnd(r, 40, 140, 5), _rnd(r, 30, 110, 5)
    w = _rnd(r, 30, 100, 5)
    t = r.choice([2, 3, 4, 5, 6])
    hole = r.choice([6.6, 9, 11])
    geo = {"a": a, "b": b, "w": w, "t": t, "hole": hole, "bend": t * r.choice([1, 1.5, 2])}
    dims = [
        Dim("leg_a.len", "linear", a, _tol(r, a)),
        Dim("leg_b.len", "linear", b, _tol(r, b)),
        Dim("width", "linear", w, _tol(r, w)),
        Dim("thickness", "linear", float(t), _general()),
        Dim("bend.radius", "radius", geo["bend"], _general()),
        Dim("holes.dia", "diameter", hole, _general(), count=2),
    ]
    return geo, dims


FAMILIES = {"plate": plate, "shaft": shaft, "flange": flange, "bracket": bracket, "assembly": plate}


def _envelope(family: str, g: dict) -> tuple[float, float, float]:
    if family in ("plate", "assembly"):
        e = (g["L"], g["W"], g["T"])
    elif family == "shaft":
        e = (sum(g["lens"]), max(g["dias"]), max(g["dias"]))
    elif family == "flange":
        e = (g["od"], g["od"], g["t"])
    else:
        e = (g["a"], g["w"], g["b"])
    return tuple(sorted((float(x) for x in e), reverse=True))  # type: ignore[return-value]


def _mass(family: str, g: dict, material: str) -> float:
    rho = DENSITY[material] / 1000  # g/mm3
    if family in ("plate", "assembly"):
        v = g["L"] * g["W"] * g["T"]
    elif family == "shaft":
        v = sum(3.1416 * (d / 2) ** 2 * ln for d, ln in zip(g["dias"], g["lens"], strict=True))
    elif family == "flange":
        v = 3.1416 * ((g["od"] / 2) ** 2 - (g["bore"] / 2) ** 2) * g["t"]
    else:
        v = (g["a"] + g["b"]) * g["w"] * g["t"]
    return round(v * rho / 1000 * 0.92, 2)


def make_part(r: random.Random, layout_name: str, language: str, family: str | None = None) -> Part:
    family = family or r.choices(list(FAMILIES), weights=[3, 2, 2, 2, 1])[0]
    geo, dims = FAMILIES[family](r)
    material = r.choice(MATERIALS[family])
    env = _envelope(family, geo)
    notes_keys = r.sample(["edge_break", "deburr", "cert", "rohs", "radii"], r.randint(1, 3))
    if family == "shaft" and material != "1.4305" and r.random() < 0.6:
        notes_keys.append("hardened")
    if material.startswith("EN AW"):
        notes_keys.append("anodise")
    elif material not in ("1.4301", "1.4305", "1.4404") and r.random() < 0.6:
        notes_keys.append(r.choice(["zinc", "powder"]))
    d0 = date(2023, 1, 1) + timedelta(days=r.randint(0, 1300))
    part = Part(
        family=family,
        title=r.choice(TITLES[family][language]),
        drawing_number=DRAWING_NUMBER[layout_name](r),
        revision=rev_label(layout_name, 0),
        material=material,
        general_tolerance=r.choice(["m", "m", "m", "f", "c"]),
        scale="",
        mass_kg=_mass(family, geo, material),
        date=d0.isoformat(),
        envelope=env,
        dims=dims,
        notes=[NOTES[k][0][language] for k in notes_keys],
        requirements=[copy.copy(NOTES[k][1]) for k in notes_keys],
        geometry=geo,
    )
    first = {"en": "First release", "de": "Erstausgabe"}[language]
    part.revisions = [RevRow(part.revision, first, part.date)]
    if family == "assembly":
        part.bom = assembly_bom(r, part, language)
    return part


def assembly_bom(r: random.Random, part: Part, language: str) -> list[BomRow]:
    de = language == "de"
    plate_no = part.drawing_number + "-1"
    screw = r.choice([("ISO 4762 M8x25", "8.8"), ("ISO 4762 M6x20", "8.8"), ("ISO 4017 M10x30", "8.8")])
    rows = [
        BomRow(1, 1, "Grundplatte" if de else "Base plate", plate_no, part.material),
        BomRow(2, 2, "Lagerbuchse" if de else "Bearing bush", r.choice(["PAP 2015 P10", "PAP 2520 P10"]), "CuSn8"),
        BomRow(3, r.choice([4, 6]), "Zylinderschraube" if de else "Socket head cap screw", screw[0], screw[1]),
    ]
    if r.random() < 0.6:
        rows.append(BomRow(4, 2, "Zylinderstift" if de else "Dowel pin", "ISO 8734 8x30", "1.3505"))
    return rows


# ------------------------------------------------------------------ revisions

CHANGE_TEXT = {
    "en": {
        "dimension_changed": "Dimension {k} changed",
        "tolerance_changed": "Tolerance {k} tightened",
        "feature_added": "Hole added",
        "feature_removed": "Hole removed",
        "field_changed": "Material changed",
    },
    "de": {
        "dimension_changed": "Maß {k} geändert",
        "tolerance_changed": "Toleranz {k} eingeengt",
        "feature_added": "Bohrung ergänzt",
        "feature_removed": "Bohrung entfallen",
        "field_changed": "Werkstoff geändert",
    },
}


def revise(r: random.Random, prev: Part, layout_name: str, language: str) -> tuple[Part, list[Change]]:
    """The next revision of `prev` with one to three known changes."""
    cur = copy.deepcopy(prev)
    n_rev = len(prev.revisions)
    cur.revision = rev_label(layout_name, n_rev)
    changes: list[Change] = []
    kinds = r.sample(
        ["dimension_changed", "tolerance_changed", "feature_added", "feature_removed", "field_changed"], r.randint(1, 3)
    )
    if cur.family not in ("plate", "assembly"):
        kinds = [k for k in kinds if k not in ("feature_added", "feature_removed")] or ["dimension_changed"]
    for kind in kinds:
        if kind == "dimension_changed":
            d = r.choice([d for d in cur.dims if d.kind in ("linear", "diameter")])
            old = d.nominal
            d.nominal = round(old + r.choice([-10, -5, 5, 10, 2, -2]) * (1 if old > 15 else 0.5), 1)
            if d.nominal <= 1:
                d.nominal = old + 5
            changes.append(Change(kind, d.key, f"{old:g}", f"{d.nominal:g}"))
            if d.key in ("length", "width") and cur.family in ("plate", "assembly"):
                cur.geometry["L" if d.key == "length" else "W"] = d.nominal
        elif kind == "tolerance_changed":
            cands = [
                d
                for d in cur.dims
                if d.tol.kind in ("general", "sym")
                and d.kind in ("linear", "diameter")
                and not any(c.key == d.key for c in changes)
            ]
            if not cands:
                continue
            d = r.choice(cands)
            before = _tol_str(d.tol)
            d.tol = (
                Tol("sym", plus=0.05, minus=-0.05)
                if d.tol.kind == "general" or d.tol.plus > 0.05
                else Tol("sym", plus=0.02, minus=-0.02)
            )
            changes.append(Change(kind, d.key, before, _tol_str(d.tol)))
        elif kind == "feature_added":
            holes = cur.geometry["holes"]
            x = round(cur.geometry["L"] * 0.92, 0)
            if any(abs(h[0] - x) < 6 for h in holes):
                continue
            holes.append((x, holes[-1][1]))
            i = len(holes)
            cur.dims.append(Dim(f"hole_{i}.x", "linear", float(x), _general()))
            for d in cur.dims:
                if d.key == "holes.dia":
                    d.count += 1
            changes.append(Change(kind, f"hole_{i}.x", "", f"{x:g}"))
        elif kind == "feature_removed":
            holes = cur.geometry["holes"]
            if len(holes) < 3:
                continue
            i = len(holes)
            holes.pop()
            cur.dims = [d for d in cur.dims if not d.key.startswith(f"hole_{i}.")]
            for d in cur.dims:
                if d.key == "holes.dia":
                    d.count -= 1
            changes.append(Change(kind, f"hole_{i}.x", "", ""))
        elif kind == "field_changed":
            alts = [m for m in MATERIALS[cur.family] if m != cur.material]
            before, cur.material = cur.material, r.choice(alts)
            changes.append(Change(kind, "material", before, cur.material))
    if not changes:
        d = next(d for d in cur.dims if d.kind == "linear")
        old = d.nominal
        d.nominal = old + 5
        changes.append(Change("dimension_changed", d.key, f"{old:g}", f"{d.nominal:g}"))
    d1 = date.fromisoformat(prev.date) + timedelta(days=r.randint(20, 200))
    cur.date = d1.isoformat()
    text = "; ".join(CHANGE_TEXT[language][c.kind].format(k=c.key.split(".")[0]) for c in changes[:2])
    cur.revisions = [*prev.revisions, RevRow(cur.revision, text, cur.date)]
    cur.mass_kg = _mass(cur.family, cur.geometry, cur.material)
    if cur.mass_kg != prev.mass_kg:
        changes.append(Change("field_changed", "mass_kg", f"{prev.mass_kg:g}", f"{cur.mass_kg:g}"))
    return cur, changes


def _tol_str(t: Tol) -> str:
    if t.kind == "general":
        return "general"
    if t.kind == "fit":
        return t.fit
    if t.kind == "sym":
        return f"±{t.plus:g}"
    return f"+{t.plus:g}/{t.minus:g}"
