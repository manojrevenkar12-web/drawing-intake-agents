import json

import httpx
import pytest

from dia.engineering.diff import compare
from dia.engineering.feasibility import decide
from dia.engineering.notes import LLMReader, RuleReader, read_notes, validate
from dia.engineering.tolerance import resolve
from dia.perceive.dimensions import ReadDim, parse
from dia.perceive.fields import FIELDS, FieldRead
from dia.perceive.reader import Reading


def d(text, x=0.0, y=0.0):
    r = parse(text)
    r.x, r.y = x, y
    return r


def test_limits_from_each_source():
    assert resolve(d("Ø25 H7"), "m").upper == pytest.approx(25.021)
    assert (resolve(d("50 ±0.1"), "m").lower, resolve(d("50 ±0.1"), "m").upper) == (49.9, 50.1)
    g = resolve(d("50"), "m")
    assert (g.lower, g.upper, g.source) == (49.7, 50.3, "ISO 2768-m")
    assert resolve(d("50"), None) is None and resolve(d("M8"), "m") is None


def test_feasibility_routes():
    assert decide([d("120"), d("4x Ø9")], "m", "S235JR").route == "in_house"
    fine = decide([d("Ø20 g6")], "m", "C45E")
    assert fine.route == "with_partner" and fine.partners == ["cylindrical_grinding"]
    assert decide([d("50 ±0.002")], "m", "S235JR").route == "decline"
    assert decide([d("M14")], "m", "S235JR").route == "decline"
    assert decide([d("700")], "c", "S235JR").route == "decline"
    order = decide([d("100")], "m", "1.4404")
    assert order.order_material and order.route == "in_house"
    coated = decide([d("100")], "m", "S235JR", [{"kind": "surface", "value": "Fe//Zn8//C"}])
    assert coated.partners == ["zinc_plating"] and coated.extra_days > 0


def test_note_rules_in_both_languages():
    en = RuleReader().read(
        [
            "Break all sharp edges 0.5 x 45°",
            "Zinc plated Fe//Zn8//C to ISO 2081",
            "Material certificate EN 10204 3.1 required",
            "Hardened and tempered 28-32 HRC",
        ]
    )
    de = RuleReader().read(
        [
            "Alle scharfen Kanten 0,5 x 45° brechen",
            "Galvanisch verzinkt Fe//Zn8//C nach ISO 2081",
            "Abnahmeprüfzeugnis EN 10204 3.1 erforderlich",
            "Vergütet auf 28-32 HRC",
        ]
    )
    pairs = {(r.kind, r.value, r.standard) for r in en}
    assert pairs == {(r.kind, r.value, r.standard) for r in de}
    assert ("surface", "Fe//Zn8//C", "ISO 2081") in pairs and ("certificate", "3.1", "EN 10204") in pairs


def test_llm_requirements_pass_the_validator_or_are_rejected():
    notes = ["Powder coated RAL 7035", "Salt spray tested 480 h"]
    reply = {
        "requirements": [
            {"kind": "surface", "value": "RAL 7035", "standard": "", "quote": "Powder coated RAL 7035"},
            {
                "kind": "surface",
                "value": "salt spray 480 h",
                "standard": "ISO 9227",
                "quote": "Salt spray tested 480 h",
            },
            {"kind": "heat_treatment", "value": "58 HRC", "standard": "", "quote": "case hardened 58 HRC"},
        ]
    }

    def handler(request):
        assert json.loads(request.content)["model"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(reply)}]})

    llm = LLMReader(api_key="test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = read_notes(notes, llm)
    reasons = sorted(r["reason"] for r in out["rejected"])
    assert [r["value"] for r in out["requirements"]] == ["RAL 7035"]
    assert reasons == ["quoted text is not in the notes", "standard 'ISO 9227' not known or not cited"]
    kept, _ = validate([], notes)
    assert kept == []


def _reading(dims: list[ReadDim], material="S235JR") -> Reading:
    fields = {f: FieldRead(None) for f in FIELDS}
    fields["material"] = FieldRead(material, conf=1)
    return Reading("vector", (420, 297), {}, fields, dims, [], [], [])


def test_revision_compare_aligns_sheets_then_pairs_dimensions():
    prev = [d("180", 100, 200), d("60", 50, 120), d("3x Ø9", 150, 80), d("40 ±0.1", 120, 60)]
    shift = 7.0  # the CAD system re-centred the views
    cur = [
        d("185", 100 + shift, 200),
        d("60", 50 + shift, 120),
        d("4x Ø9", 150 + shift, 80),
        d("40 ±0.05", 120 + shift, 60),
        d("170", 160 + shift, 60),
    ]
    found = {(f.kind, f.after or f.before) for f in compare(_reading(prev), _reading(cur, "S355J2"))}
    assert found == {
        ("field_changed", "S355J2"),
        ("dimension_changed", "185"),
        ("feature_added", "4x Ø9"),
        ("tolerance_changed", "40 ±0.05"),
        ("feature_added", "170"),
    }
