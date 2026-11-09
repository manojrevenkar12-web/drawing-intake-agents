"""Read the title block: find each field's label, take the value that belongs to it, check it, and say how sure we
are.

Labels come from a vocabulary of title-block terms (ISO 7200's field names in English and German, and the labels of
the development customers), matched loosely so that "Werkst." still finds "Werkstoff". A customer profile, learnt
from a few of that customer's drawings with known values, adds the customer's own labels: that is how a new
customer's template is onboarded without code changes. Fields whose label is not found are looked for by the shape
of their value (a scale, a date, an ISO 2768 class, a material from the material master)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from difflib import SequenceMatcher

from dia.perceive.page import Item
from dia.standards.iso2768 import parse_class

FIELDS = ("title", "drawing_number", "revision", "material", "general_tolerance", "scale", "mass_kg", "date")

VOCABULARY: dict[str, list[str]] = {
    # ISO 7200 terms (EN/DE) and the development customers' labels; nothing from the held-out customers.
    "title": ["title", "titel", "benennung", "bezeichnung", "description", "part name", "designation"],
    "drawing_number": [
        "drawing no",
        "drawing number",
        "drawing",
        "document number",
        "identification number",
        "zeichnungsnummer",
        "zeichnungs nr",
        "sachnummer",
        "dokumentnummer",
        "teilenummer",
        "part no",
    ],
    "revision": ["rev", "revision", "revision index", "issue", "index", "anderungsindex", "anderungsstand"],
    "material": ["material", "werkstoff"],
    "general_tolerance": [
        "general tolerances",
        "general tol",
        "tolerances unless stated",
        "allgemeintoleranzen",
        "freimasstoleranz",
        "toleranz",
    ],
    "scale": ["scale", "massstab"],
    "mass_kg": ["mass", "mass kg", "weight", "weight kg", "gewicht", "gewicht kg", "masse", "masse kg"],
    "date": ["date", "datum", "date of issue", "ausgabedatum", "released", "erstellt"],
}

MATERIAL_MASTER = [
    "S235JR",
    "S355J2",
    "1.4301",
    "1.4305",
    "1.4404",
    "EN AW-6082-T6",
    "DC01",
    "C45E",
    "42CrMo4",
    "EN-GJS-400-15",
    "CuSn8",
    "1.3505",
    "8.8",
]

POSITION_MM = 4.0
ANCHOR = "general_tolerance"  # found by its shape alone on every layout, so positions are measured from it

DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d %b %Y", "%d/%m/%Y", "%d-%b-%Y", "%d/%m/%y", "%m/%d/%Y")


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().replace("ß", "ss"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def label_score(text: str, label: str) -> float:
    """How well an item's text matches a label: exact, abbreviation ("werkst" for "werkstoff") or fuzzy."""
    a, b = fold(text), fold(label)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 3 and (b.startswith(a) or b.replace(" ", "").startswith(a.replace(" ", ""))):
        return 0.85 * min(1.0, len(a) / 5)
    return SequenceMatcher(None, a, b).ratio() * 0.9


# ------------------------------------------------------------------ value checks


def normalise(fld: str, text: str) -> tuple[str | None, bool]:
    """(normalised value, passes the field's check)."""
    t = re.sub(r"\s+", " ", text.strip().strip("|").strip())
    if fld == "general_tolerance":
        c = parse_class(t)
        return (c, True) if c else (None, False)
    if fld == "scale":
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*[:;]\s*(\d+(?:[.,]\d+)?)", t)
        return (f"{m[1]}:{m[2]}".replace(",", "."), True) if m else (None, False)
    if fld == "mass_kg":
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:kg)?", t)
        return (str(float(m[1].replace(",", "."))), True) if m else (None, False)
    if fld == "date":
        for f in DATE_FORMATS:
            try:
                return datetime.strptime(t, f).date().isoformat(), True
            except ValueError:
                continue
        return None, False
    if fld == "revision":
        ok = bool(re.fullmatch(r"[A-Z]|\d{1,2}", t))
        return t, ok
    if fld == "material":
        best = max(MATERIAL_MASTER, key=lambda m: SequenceMatcher(None, m.lower(), t.lower()).ratio())
        if best.lower() == t.lower():
            return best, True
        # OCR confusions in material codes ($ for S, O for 0, ) or | or / for J), checked against the master
        fixed = re.sub(r"^[$5](?=\d{3})", "S", t).replace(")", "J").replace("|", "J").replace("]", "J")
        fixed = re.sub(r"(?<=[A-Z])O(?=\d)", "0", fixed).replace("GIS", "GJS")
        fixed = re.sub(r"(?<=\d)/(?=R)", "J", fixed)
        for m in MATERIAL_MASTER:
            if m.lower() == fixed.lower():
                return m, True
        return t, False
    if fld == "drawing_number":
        ok = len(re.sub(r"\D", "", t)) >= 4 and 5 <= len(t) <= 24 and not normalise("date", t)[1]
        return t, ok
    if fld == "title":
        ok = bool(re.search(r"[A-Za-zÄÖÜäöü]{3,}", t)) and not any(ch.isdigit() for ch in t[:2])
        return t, ok
    return t, True


@dataclass
class FieldRead:
    value: str | None
    raw: str = ""
    how: str = "missing"  # label | label_fuzzy | profile | pattern | missing
    conf: float = 0.0
    checks: list[str] = field(default_factory=list)
    box: tuple[float, float, float, float] | None = None


@dataclass
class Profile:
    """What was learnt about one customer's title block from a few of their drawings: their labels, and where each
    value sits relative to the general-tolerance value (which holds even where a label is illegible)."""

    customer: str
    labels: dict[str, list[str]] = field(default_factory=dict)
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)  # offset from the anchor value, mm
    anchor: str = ANCHOR

    def vocabulary(self) -> dict[str, list[str]]:
        return {f: [*VOCABULARY[f], *self.labels.get(f, [])] for f in FIELDS}


def _is_label_like(it: Item, vocab: dict[str, list[str]]) -> tuple[str, float] | None:
    best = None
    for fld, labels in vocab.items():
        for lab in labels:
            s = label_score(it.text, lab)
            if s >= 0.72 and (best is None or s > best[1]):
                best = (fld, s)
    return best


def _candidates(label: Item, items: list[Item], max_dist: float) -> list[tuple[float, Item]]:
    """Items that could be this label's value: below it in the same cell, or to its right on the same line."""
    out = []
    for it in items:
        if it is label:
            continue
        dy = it.cy - label.cy
        dx = it.x0 - label.x0
        if 0.8 < dy < 12 and -2 < dx < 40:  # below, starting near the label's left edge
            out.append((dy + 0.3 * abs(dx), it))
        elif abs(dy) < 1.5 and 0 < it.x0 - label.x1 < max_dist:  # same line, to the right
            out.append((0.5 * (it.x0 - label.x1), it))
    return sorted(out, key=lambda t: t[0])


def read_title_block(
    items: list[Item],
    profile: Profile | None = None,
    max_dist: float = 60.0,
    revision_rows: list[tuple[str, str]] | None = None,
    box: tuple[float, float, float, float] | None = None,
) -> dict[str, FieldRead]:
    vocab = profile.vocabulary() if profile else VOCABULARY
    labelled: list[tuple[Item, str, float]] = []
    for it in items:
        hit = _is_label_like(it, vocab)
        if hit:
            labelled.append((it, *hit))
        elif ":" in it.text:  # "Material: S235JR" on one line
            lab, _, val = it.text.partition(":")
            hit = _is_label_like(Item(lab, it.x0, it.y0, it.x1, it.y1), vocab)
            if hit and val.strip():
                labelled.append((Item(val.strip(), it.x0, it.y0, it.x1, it.y1, conf=it.conf), hit[0], -hit[1]))
    label_items = {id(i) for i, _, s in labelled if s > 0}
    values = [i for i in items if id(i) not in label_items]
    out: dict[str, FieldRead] = {}
    taken: set[int] = set()
    # best label per field first
    for it, fld, score in sorted(labelled, key=lambda t: -abs(t[2])):
        if fld in out:
            continue
        if score < 0:  # inline "label: value"
            v, ok = normalise(fld, it.text)
            out[fld] = FieldRead(
                v,
                it.text,
                "label",
                0.9 if ok else 0.5,
                [] if ok else ["value check failed"],
                (it.x0, it.y0, it.x1, it.y1),
            )
            continue
        for _, cand in _candidates(it, values, max_dist):
            if id(cand) in taken:
                continue
            v, ok = normalise(fld, cand.text)
            if v is None and fld in ("general_tolerance", "scale", "mass_kg", "date"):
                continue
            how = (
                "profile"
                if profile and any(label_score(it.text, x) >= 0.95 for x in profile.labels.get(fld, []))
                else ("label" if score >= 0.95 else "label_fuzzy")
            )
            base = {"label": 0.95, "profile": 0.95, "label_fuzzy": 0.8}[how]
            conf = base * (1.0 if ok else 0.55) * min(1.0, cand.conf / 0.85)
            out[fld] = FieldRead(
                v,
                cand.text,
                how,
                round(conf, 3),
                [] if ok else ["value check failed"],
                (cand.x0, cand.y0, cand.x1, cand.y1),
            )
            taken.add(id(cand))
            break
    _pattern_rescue(out, values, taken, revision_rows or [])
    if profile:
        _position_rescue(out, values, taken, profile)
    _cross_check(out, revision_rows or [])
    for f in FIELDS:
        out.setdefault(f, FieldRead(None))
    return out


SCALE_DIGITS = {"11": "1:1", "12": "1:2", "21": "2:1", "15": "1:5"}


def _position_rescue(out: dict[str, FieldRead], values: list[Item], taken: set[int], profile: Profile) -> None:
    """Fields still missing are taken from where this customer prints them, measured from the anchor value."""
    anchor = out.get(profile.anchor)
    if anchor is None or anchor.box is None:
        return
    ax, ay = (anchor.box[0] + anchor.box[2]) / 2, (anchor.box[1] + anchor.box[3]) / 2
    for fld, (dx, dy) in profile.positions.items():
        if fld in out and out[fld].value:
            continue
        px, py = ax + dx, ay + dy
        near = sorted(
            (abs(i.cx - px) + abs(i.cy - py), n, i)
            for n, i in enumerate(values)
            if id(i) not in taken and abs(i.cx - px) < POSITION_MM * 3 and abs(i.cy - py) < POSITION_MM
        )
        for _, _, it in near:
            v, ok = normalise(fld, it.text)
            others = any(normalise(f, it.text)[1] for f in FIELDS if f not in (fld, "title", "drawing_number"))
            if v is None or not ok or others:
                continue
            out[fld] = FieldRead(
                v,
                it.text,
                "profile_position",
                round(0.85 * min(1.0, it.conf / 0.85), 3),
                [],
                (it.x0, it.y0, it.x1, it.y1),
            )
            taken.add(id(it))
            break


def _pattern_rescue(
    out: dict[str, FieldRead], values: list[Item], taken: set[int], rows: list[tuple[str, str]] | None = None
) -> None:
    """Fields whose label was not found, looked for by the shape of their value."""
    for fld in ("general_tolerance", "scale", "date", "material", "mass_kg"):
        if fld in out and out[fld].value:
            continue
        hits = []
        for it in values:
            if id(it) in taken:
                continue
            v, ok = normalise(fld, it.text)
            if ok and v:
                hits.append((it, v))
        if fld == "mass_kg":
            hits = [h for h in hits if "." in h[0].text or "," in h[0].text]
        if not hits and fld == "scale":  # OCR often drops the colon of a scale
            hits = [
                (it, SCALE_DIGITS[it.text.strip()])
                for it in values
                if id(it) not in taken and it.text.strip() in SCALE_DIGITS
            ]
        if hits:
            it, v = hits[0]
            out[fld] = FieldRead(
                v,
                it.text,
                "pattern",
                round(0.6 * min(1.0, it.conf / 0.85) * (1.0 if len(hits) == 1 else 0.7), 3),
                [] if len(hits) == 1 else ["several candidates"],
                (it.x0, it.y0, it.x1, it.y1),
            )
            taken.add(id(it))
    if rows and not (out.get("revision") and out["revision"].value):
        last = rows[-1][0]
        it = next((i for i in values if id(i) not in taken and i.text.strip() == last), None)
        if it is not None:
            out["revision"] = FieldRead(
                last,
                it.text,
                "revision_table",
                round(0.85 * min(1.0, it.conf / 0.85), 3),
                [],
                (it.x0, it.y0, it.x1, it.y1),
            )
            taken.add(id(it))
    if not (out.get("drawing_number") and out["drawing_number"].value):
        cands = []
        for it in values:
            if id(it) in taken:
                continue
            v, ok = normalise("drawing_number", it.text)
            others = any(
                normalise(f, it.text)[1] for f in ("date", "scale", "mass_kg", "material", "general_tolerance")
            )
            if ok and not others:
                cands.append((sum(ch.isdigit() for ch in it.text), it))
        if cands:
            cands.sort(key=lambda c: -c[0])
            it = cands[0][1]
            out["drawing_number"] = FieldRead(
                it.text.strip(),
                it.text,
                "pattern",
                round(0.55 * min(1.0, it.conf / 0.85), 3),
                [] if len(cands) == 1 else ["several candidates"],
                (it.x0, it.y0, it.x1, it.y1),
            )
            taken.add(id(it))


def _cross_check(out: dict[str, FieldRead], rows: list[tuple[str, str]]) -> None:
    """Agreement with the revision table raises confidence; disagreement lowers it."""
    if not rows:
        return
    last_rev, last_date = rows[-1]
    r = out.get("revision")
    if r and r.value:
        if r.value == last_rev:
            r.conf = round(min(0.99, r.conf + 0.1), 3)
        else:
            r.conf = round(r.conf * 0.6, 3)
            r.checks.append(f"revision table ends at {last_rev}")
    d = out.get("date")
    if d and d.value and last_date:
        ld, _ = normalise("date", last_date)
        if ld == d.value:
            d.conf = round(min(0.99, d.conf + 0.05), 3)


def learn_profile(
    customer: str,
    examples: list[tuple[list[Item], dict[str, str]]],
    boxes: list[tuple[float, float, float, float] | None] | None = None,
) -> Profile:
    """From a few drawings with known title-block values: for each field, the label printed in the same cell just
    above or left of the value, and where the value sits relative to the title block's bottom-right corner."""
    prof = Profile(customer)
    offsets: dict[str, list[tuple[float, float]]] = {}
    for items, known in examples:
        anchor = next((i for i in items if fold(i.text) == fold(known.get(ANCHOR, "")) and known.get(ANCHOR)), None)
        for fld, value in known.items():
            target = fold(value)
            hits = [i for i in items if fold(i.text) == target]
            if not hits:
                continue
            v = hits[0]
            if anchor is not None and fld != ANCHOR:
                offsets.setdefault(fld, []).append((v.cx - anchor.cx, v.cy - anchor.cy))
            values_here = {fold(x) for x in known.values()}
            near = [
                i
                for i in items
                if i is not v
                and fold(i.text) not in values_here
                and i.conf >= 0.6
                and not any(
                    normalise(f, i.text)[1] for f in ("general_tolerance", "scale", "date", "material", "mass_kg")
                )
                and (
                    (0.8 < v.cy - i.cy < 8 and abs(v.x0 - i.x0) < 4)
                    or (abs(v.cy - i.cy) < 1.5 and 0 < v.x0 - i.x1 < 15)
                )
            ]
            if not near:
                continue
            lab = min(near, key=lambda i: (v.cy - i.cy) + 0.3 * abs(v.x0 - i.x0))
            if not re.search(r"[A-Za-zÄÖÜäöü]", lab.text) or len(lab.text) > 40:
                continue
            labels = prof.labels.setdefault(fld, [])
            if fold(lab.text) not in (fold(x) for x in labels):
                labels.append(lab.text)
    for fld, offs in offsets.items():
        xs, ys = sorted(o[0] for o in offs), sorted(o[1] for o in offs)
        prof.positions[fld] = (xs[len(xs) // 2], ys[len(ys) // 2])
    return prof


def same_value(fld: str, predicted: str | None, expected: str) -> bool:
    """Does a read value equal the expected printed value, in the field's normal form?"""
    if predicted is None:
        return False
    tv, _ = normalise(fld, expected)
    if fld in ("title", "drawing_number"):
        return fold(predicted) == fold(expected) and predicted.replace(" ", "") == expected.replace(" ", "")
    return (tv or expected) == predicted


__all__ = ["FIELDS", "FieldRead", "Profile", "date", "learn_profile", "read_title_block", "same_value"]
