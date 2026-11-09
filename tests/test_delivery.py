import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dia.api import create_app
from dia.delivery.erp import LegacyErp, bom_records, idempotency_key, material_record
from dia.delivery.routing import choose_threshold, route
from dia.delivery.service import Desk
from dia.perceive.fields import FIELDS, FieldRead, same_value
from dia.perceive.reader import Reader
from dia.settings import ROOT, load

VALUES = {
    "title": "Base plate",
    "drawing_number": "AR-407-9724",
    "revision": "B",
    "material": "1.4301",
    "general_tolerance": "m",
    "scale": "1:1",
    "mass_kg": "2.24",
    "date": "2025-06-11",
}


def test_routing_sends_low_confidence_and_failed_checks_to_review():
    fields = {f: FieldRead(VALUES[f], conf=0.97) for f in FIELDS}
    fields["material"] = FieldRead("1.43O1", conf=0.97, checks=["value check failed"])
    fields["date"] = FieldRead("2025-06-11", conf=0.5)
    r = route(fields, 0.8)
    assert set(r.accepted) == set(FIELDS) - {"material", "date"}
    assert {x["field"] for x in r.review} == {"material", "date"}


def test_threshold_is_the_lowest_that_keeps_errors_under_the_limit():
    scored = [(0.99, True)] * 95 + [(0.95, False)] + [(0.6, True)] * 3 + [(0.6, False)] * 3
    t, curve = choose_threshold(scored, 0.02)
    assert t == 0.95 and curve[0]["threshold"] == 0.0


def test_erp_records_are_fixed_width_and_idempotent():
    key = idempotency_key("AR-407-9724", "B", b"pdf")
    line = material_record(VALUES, "1000", "HALB", key)
    erp = LegacyErp()
    assert erp.import_file([line]) == {"status": "ok", "created": 1}
    assert erp.import_file([line]) == {"status": "ok", "created": 0}
    assert erp.import_file([line[:-1]])["status"] == "rejected"
    rows = [{"pos": 1, "qty": 4, "reference": "ISO 4762 M8x25", "description": "Screw"}]
    erp.import_file(bom_records("AR-407-9724", rows))
    erp.import_file(bom_records("AR-407-9724", rows))
    assert len(erp.boms["AR-407-9724"]) == 1
    with pytest.raises(ValueError):
        material_record({**VALUES, "material": "x" * 21}, "1000", "HALB", key)


@pytest.fixture(scope="module")
def desk():
    return Desk(Reader())


def test_desk_reads_compares_and_exports_a_vector_drawing(sample, desk):
    truth = json.loads(next((sample / "truth" / "t").glob("acme_rail-000.json")).read_text())
    prev = desk.submit((sample / "t" / f"{truth['previous']}.pdf").read_bytes(), "prev.pdf", "acme")
    job = desk.submit((sample / "t" / "acme_rail-000.pdf").read_bytes(), "cur.pdf", "acme", previous=prev.id)
    for f in FIELDS:
        assert same_value(f, job.reading.fields[f].value, truth["title_values"][f])
    assert job.changes, "a revision with known changes shows changes"
    assert job.decision["route"] in ("in_house", "with_partner", "decline")
    for f in FIELDS:
        if f not in job.accepted:
            desk.approve(job.id, {f: job.reading.fields[f].value})
    first = desk.export(job.id)
    assert first["status"] == "ok" and first["created"] == 1
    assert desk.export(job.id)["created"] == 0


def test_export_is_blocked_until_required_fields_are_approved(sample, desk):
    job = desk.submit((sample / "t" / "boltwerk-000.pdf").read_bytes(), "x.pdf")
    job.accepted.pop("material", None)
    assert desk.export(job.id) == {"status": "blocked", "missing": ["material"]}


def test_a_scan_is_registered_and_read(sample, desk):
    scan = next((sample / "s").glob("*.jpg"))
    truth = json.loads((sample / "truth" / "s" / f"{scan.stem}.json").read_text())
    job = desk.submit(scan.read_bytes(), scan.name)
    assert job.reading.source == "scan"
    right = sum(same_value(f, job.reading.fields[f].value, truth["title_values"][f]) for f in FIELDS)
    assert right >= 6
    assert len(job.reading.dims) >= len(truth["part"]["dims"]) // 2


def test_http_api(sample, desk):
    c = TestClient(create_app(desk))
    assert c.get("/api/health").json() == {"ok": True}
    p = sample / "t" / "boltwerk-001.pdf"
    r = c.post("/api/drawings", files={"file": (p.name, p.read_bytes(), "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["fields"]["drawing_number"]["value"].startswith("BW")
    assert c.get(f"/api/drawings/{body['id']}").status_code == 200
    assert c.get("/api/drawings/nope").status_code == 404
    assert c.post("/api/drawings", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 422
    assert c.post(f"/api/drawings/{body['id']}/approve", json={"colour": "red"}).status_code == 422


def test_nothing_that_serves_reads_the_truth():
    for p in (ROOT / "src" / "dia").rglob("*.py"):
        if "world" in p.parts:
            continue
        text = p.read_text()
        assert "dia.world" not in text and '"truth"' not in text and "data/truth" not in text, p


def test_settings_load():
    s = load()
    assert 0 < s.routing.min_confidence <= 1 and Path(ROOT / "config" / "plant.yaml").exists()
