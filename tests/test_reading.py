import json

import pytest

from dia.perceive.dimensions import join, parse
from dia.perceive.fields import FIELDS, Profile, learn_profile, read_title_block, same_value
from dia.perceive.page import Item, load
from dia.perceive.reader import parse_bom, parse_notes, parse_revisions


@pytest.mark.parametrize(
    ("text", "expect"),
    [
        ("Ø25 js6", ("diameter", 25.0, "fit", 0.0, 0.0, "js6", 1)),
        ("2x Ø8 ±0.1", ("diameter", 8.0, "sym", 0.1, -0.1, "", 2)),
        ("53 +0.2/-0.05", ("linear", 53.0, "asym", 0.2, -0.05, "", 1)),
        ("12,5 ±0,1", ("linear", 12.5, "sym", 0.1, -0.1, "", 1)),
        ("4x R8", ("radius", 8.0, "general", 0.0, 0.0, "", 4)),
        ("M10", ("thread", 10.0, "general", 0.0, 0.0, "", 1)),
        ("2x 1x45°", ("chamfer", 1.0, "general", 0.0, 0.0, "", 2)),
        ("@8", ("diameter", 8.0, "general", 0.0, 0.0, "", 1)),
        ("173 #0.1", ("linear", 173.0, "sym", 0.1, -0.1, "", 1)),
    ],
)
def test_dimension_grammar_and_repairs(text, expect):
    d = parse(text)
    assert d is not None and d.signature() == expect


def test_repaired_text_is_marked():
    assert parse("@8").repairs and not parse("Ø8").repairs


def test_rejects_non_dimensions():
    assert parse("FOR QUOTATION") is None and parse("4x 20") is None


def test_join_splits_and_rejoins_pieces():
    items = [Item("173", 10, 10, 15, 13), Item("±0.1", 16, 10, 22, 13), Item("60", 40, 10, 44, 13)]
    texts = sorted(t for t, *_ in join(items, 2.5))
    assert texts == ["173 ±0.1", "60"]


def test_vector_title_block_reads_every_field(sample):
    for p in sorted((sample / "t").glob("*.pdf")):
        t = json.loads((sample / "truth" / "t" / f"{p.stem}.json").read_text())
        page = load(p, dpi=40)
        tb = t["regions"]["title_block"][0]
        res = read_title_block(page.within(tuple(tb)))
        for f in FIELDS:
            assert same_value(f, res[f].value, t["title_values"][f]), (p.stem, f, res[f].value)


def _block(labels: dict[str, str], values: dict[str, str]) -> list[Item]:
    items, y = [], 0.0
    for f in FIELDS:
        items += [Item(labels[f], 0, y, 10, y + 2), Item(values[f], 1, y + 4, 30, y + 7)]
        y += 10
    return items


def test_a_customer_profile_learns_unknown_labels():
    odd = {
        "title": "Objekt",
        "drawing_number": "Ref.",
        "revision": "Stufe",
        "material": "Mat.-Kz.",
        "general_tolerance": "Tolerierung",
        "scale": "Abb.",
        "mass_kg": "kg/Stk",
        "date": "Freigabe",
    }
    vals = {
        "title": "Halter",
        "drawing_number": "QX-55102",
        "revision": "C",
        "material": "S355J2",
        "general_tolerance": "ISO 2768-m",
        "scale": "1:2",
        "mass_kg": "0.41",
        "date": "2026-01-12",
    }
    before = read_title_block(_block(odd, vals))
    prof = learn_profile("new customer", [(_block(odd, vals), vals)])
    vals2 = {**vals, "title": "Lasche", "drawing_number": "QX-55993", "revision": "A"}
    after = read_title_block(_block(odd, vals2), prof)
    assert isinstance(prof, Profile) and prof.labels["drawing_number"] == ["Ref."]
    assert before["title"].value is None and before["drawing_number"].how == "pattern"
    assert all(same_value(f, after[f].value, vals2[f]) for f in FIELDS)


def test_tables_and_notes():
    rev = [
        Item("Rev", 0, 0, 5, 3),
        Item("Date", 60, 0, 70, 3),
        Item("A", 0, 6, 3, 9),
        Item("First release", 10, 6, 40, 9),
        Item("2025-01-02", 60, 6, 80, 9),
        Item("B", 0, 12, 3, 15),
        Item("2025-03-04", 60, 12, 80, 15),
    ]
    assert parse_revisions(rev) == [("A", "2025-01-02"), ("B", "2025-03-04")]
    bom = [
        Item("Pos", 0, 0, 3, 3),
        Item("1", 0, 6, 2, 9),
        Item("4", 10, 6, 12, 9),
        Item("Screw", 20, 6, 30, 9),
        Item("ISO 4762 M8x25", 40, 6, 60, 9),
        Item("8.8", 70, 6, 75, 9),
    ]
    assert parse_bom(bom) == [
        {"pos": 1, "qty": 4, "description": "Screw", "reference": "ISO 4762 M8x25", "material": "8.8"}
    ]
    notes = [
        Item("NOTES", 0, 0, 10, 3),
        Item("1. Deburr all edges", 0, 5, 40, 8),
        Item("2. RoHS compliant", 0, 10, 40, 13),
    ]
    assert parse_notes(notes) == ["Deburr all edges", "RoHS compliant"]
