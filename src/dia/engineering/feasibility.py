"""Can the plant make this part, and how? Each toleranced feature needs a process that holds its ISO tolerance grade;
threads need a tap the plant has; the material must be in stock or be ordered; surface and heat treatment go to
partners. The decision is code reading the plant's settings (config/plant.yaml), with a reason for every line."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from dia.engineering.tolerance import resolve
from dia.perceive.dimensions import ReadDim
from dia.settings import ROOT
from dia.standards.iso286 import best_grade


@lru_cache
def plant(path: str | None = None) -> dict:
    return yaml.safe_load((ROOT / "config" / "plant.yaml").read_text() if path is None else open(path).read())


@dataclass
class Decision:
    route: str  # "in_house" | "with_partner" | "decline"
    processes: list[str] = field(default_factory=list)
    partners: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    extra_days: int = 0
    order_material: bool = False


def _feature(d: ReadDim) -> list[str]:
    if d.kind == "thread":
        return ["thread"]
    if d.kind == "diameter":
        if d.tol_kind == "fit":
            return ["hole"] if d.fit[0].isupper() else ["step"]
        return ["hole"] if d.count > 1 else ["hole", "step"]
    if d.kind == "linear":
        return ["length", "outline"]
    return []


def decide(
    dims: list[ReadDim],
    general_class: str | None,
    material: str | None,
    requirements: list[dict] | None = None,
    cfg: dict | None = None,
) -> Decision:
    p = cfg or plant()
    dec = Decision("in_house")
    procs: set[str] = set()
    partners: dict[str, int] = {}
    size = max((d.nominal for d in dims if d.kind in ("linear", "diameter")), default=0.0)
    if size > p["envelope_mm"][0]:
        dec.route = "decline"
        dec.reasons.append(f"largest dimension {size:g} mm exceeds the {p['envelope_mm'][0]} mm machine envelope")
    for d in dims:
        feats = _feature(d)
        if not feats:
            continue
        if d.kind == "thread":
            taps = p["processes"]["tapping"]["threads"]
            if int(d.nominal) in taps:
                procs.add("tapping")
            else:
                dec.route = "decline"
                dec.reasons.append(f"no M{d.nominal:g} tap in the plant")
            continue
        r = resolve(d, general_class)
        if r is None:
            dec.reasons.append(f"{d.text}: tolerance not resolvable, checked by an engineer")
            continue
        if d.nominal > 500:
            continue  # outside the ISO 286 table used here; the envelope check above covers such parts
        grade = best_grade(r.width, d.nominal)
        if grade is None:
            dec.route = "decline"
            dec.reasons.append(f"{d.text}: {r.width * 1000:.0f} µm is finer than IT6, beyond plant and partners")
            continue
        inhouse = [
            (n, c["it_grade"])
            for n, c in p["processes"].items()
            if c["it_grade"] and c["it_grade"] <= grade and set(c["features"]) & set(feats)
        ]
        if inhouse:
            procs.add(max(inhouse, key=lambda t: t[1])[0])  # the coarsest process that is good enough
            continue
        sub = [
            (n, c)
            for n, c in p["subcontract"].items()
            if c.get("it_grade") and c["it_grade"] <= grade and set(c["features"]) & set(feats)
        ]
        if sub:
            n, c = sub[0]
            partners[n] = c["extra_days"]
            dec.reasons.append(f"{d.text}: IT{grade} needs {n.replace('_', ' ')} at a partner")
        else:
            dec.route = "decline"
            dec.reasons.append(f"{d.text}: IT{grade} cannot be held in the plant or by partners")
    if material and material not in p["materials_in_stock"]:
        dec.order_material = True
        dec.reasons.append(f"{material} is not in stock and has to be ordered")
    for req in requirements or []:
        k, v = req.get("kind"), str(req.get("value", ""))
        name = None
        if k == "heat_treatment":
            name = "heat_treatment"
        elif k == "surface":
            name = "anodising" if "anodis" in v.lower() else "zinc_plating" if "Zn" in v else "powder_coating"
        if name:
            partners[name] = p["subcontract"][name]["extra_days"]
            dec.reasons.append(f"{k.replace('_', ' ')} {v} at a partner")
    dec.processes = sorted(procs)
    dec.partners = sorted(partners)
    dec.extra_days = sum(partners.values())
    if dec.route != "decline" and partners:
        dec.route = "with_partner"
    return dec
