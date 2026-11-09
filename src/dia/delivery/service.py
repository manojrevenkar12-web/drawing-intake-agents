"""The intake desk: a drawing comes in, is read, checked against the plant, compared with its previous revision,
routed field by field, reviewed where needed, and exported to the ERP only from approved values."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field

from dia.delivery.erp import LegacyErp, bom_records, idempotency_key, material_record
from dia.delivery.routing import route
from dia.engineering.diff import compare
from dia.engineering.feasibility import decide
from dia.engineering.notes import LLMReader, read_notes
from dia.engineering.tolerance import resolve
from dia.perceive.fields import FIELDS, Profile, learn_profile
from dia.perceive.reader import Reader, Reading
from dia.settings import load as settings

REQUIRED_FOR_EXPORT = ("drawing_number", "revision", "title", "material", "date")


@dataclass
class Job:
    id: str
    name: str
    customer: str | None
    reading: Reading
    content: bytes = field(repr=False, default=b"")
    accepted: dict[str, str] = field(default_factory=dict)
    review: list[dict] = field(default_factory=list)
    requirements: list[dict] = field(default_factory=list)
    decision: dict = field(default_factory=dict)
    changes: list[dict] = field(default_factory=list)
    previous: str | None = None
    exported: dict | None = None

    def summary(self) -> dict:
        r = self.reading
        return {
            "id": self.id,
            "name": self.name,
            "customer": self.customer,
            "source": r.source,
            "fields": {
                f: {
                    "value": r.fields[f].value,
                    "conf": r.fields[f].conf,
                    "how": r.fields[f].how,
                    "checks": r.fields[f].checks,
                }
                for f in FIELDS
            },
            "accepted": self.accepted,
            "review": self.review,
            "dimensions": [
                {
                    "text": d.text,
                    "kind": d.kind,
                    "nominal": d.nominal,
                    "count": d.count,
                    "tolerance": d.tol_kind,
                    "fit": d.fit,
                    "limits": _limits(d, r),
                    "conf": round(d.conf, 3),
                    "repairs": d.repairs,
                }
                for d in r.dims
            ],
            "parts_list": r.bom,
            "revisions": r.revisions,
            "notes": r.notes,
            "requirements": self.requirements,
            "decision": self.decision,
            "previous": self.previous,
            "changes": self.changes,
            "warnings": r.warnings,
            "exported": self.exported,
        }


def _limits(d, r: Reading):
    res = resolve(d, r.fields["general_tolerance"].value)
    return None if res is None else {"lower": res.lower, "upper": res.upper, "source": res.source}


class Desk:
    def __init__(self, reader: Reader | None = None, llm: LLMReader | None = None, erp: LegacyErp | None = None):
        self.s = settings()
        self.reader = reader or Reader()
        self.llm = llm
        self.erp = erp or LegacyErp()
        self.jobs: dict[str, Job] = {}
        self.profiles: dict[str, Profile] = {}

    def submit(self, data: bytes, name: str, customer: str | None = None, previous: str | None = None) -> Job:
        reading = self.reader.read(data=data, name=name, profile=self.profiles.get(customer or ""))
        job = Job(uuid.uuid4().hex[:12], name, customer, reading, data)
        routed = route(reading.fields, self.s.routing.min_confidence)
        job.accepted, job.review = routed.accepted, routed.review
        for d in reading.dims:
            if d.repairs:
                job.review.append(
                    {
                        "dimension": d.text,
                        "reason": "OCR text repaired: " + ", ".join(d.repairs),
                        "conf": round(d.conf, 3),
                    }
                )
        job.requirements = read_notes(reading.notes, self.llm)["requirements"]
        dec = decide(
            reading.dims, reading.fields["general_tolerance"].value, reading.fields["material"].value, job.requirements
        )
        job.decision = asdict(dec)
        if previous and previous in self.jobs:
            job.previous = previous
            job.changes = [asdict(c) for c in compare(self.jobs[previous].reading, reading)]
        self.jobs[job.id] = job
        return job

    def approve(self, job_id: str, values: dict[str, str]) -> Job:
        """An engineer confirms or corrects fields; confirmed values join the accepted set."""
        job = self.jobs[job_id]
        for f, v in values.items():
            if f not in FIELDS:
                raise KeyError(f"unknown field {f}")
            job.accepted[f] = v
        job.review = [r for r in job.review if r.get("field") not in values]
        return job

    def export(self, job_id: str) -> dict:
        job = self.jobs[job_id]
        missing = [f for f in REQUIRED_FOR_EXPORT if f not in job.accepted]
        if missing:
            return {"status": "blocked", "missing": missing}
        key = idempotency_key(job.accepted["drawing_number"], job.accepted["revision"], job.content)
        lines = [material_record(job.accepted, self.s.erp.plant, self.s.erp.material_type, key)]
        lines += bom_records(job.accepted["drawing_number"], job.reading.bom)
        result = self.erp.import_file(lines)
        job.exported = {**result, "lines": lines}
        return job.exported

    def onboard(self, customer: str, examples: list[tuple[bytes, str, dict[str, str]]]) -> Profile:
        """Learn a customer's title-block labels from a few of their drawings with known values."""
        readings = [(self.reader.read(data=d, name=n), known) for d, n, known in examples]
        prof = learn_profile(
            customer,
            [(r.items, k) for r, k in readings],
            [(r.regions.get("title_block") or [None])[0] for r, _ in readings],
        )
        self.profiles[customer] = prof
        return prof
