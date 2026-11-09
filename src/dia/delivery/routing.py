"""Which read values go straight into the ERP and which an engineer checks first.

A field is accepted automatically only if its confidence clears `routing.min_confidence`, a threshold chosen on the
development drawings so that wrong values among accepted fields stay under `routing.max_auto_error`
(scripts/evaluate.py prints the curve it was chosen from). Dimensions with repaired OCR text, and anything the
feasibility check could not resolve, always go to review."""

from __future__ import annotations

from dataclasses import dataclass, field

from dia.perceive.fields import FIELDS, FieldRead


@dataclass
class Routed:
    accepted: dict[str, str] = field(default_factory=dict)
    review: list[dict] = field(default_factory=list)


def route(fields: dict[str, FieldRead], min_confidence: float) -> Routed:
    out = Routed()
    for f in FIELDS:
        r = fields.get(f)
        if r is None or r.value is None:
            out.review.append({"field": f, "value": None, "reason": "not found", "conf": 0.0})
        elif r.conf >= min_confidence and not r.checks:
            out.accepted[f] = r.value
        else:
            why = "; ".join(r.checks) or f"confidence {r.conf:.2f} below {min_confidence:.2f}"
            out.review.append({"field": f, "value": r.value, "reason": why, "conf": r.conf})
    return out


def choose_threshold(scored: list[tuple[float, bool]], max_error: float) -> tuple[float, list[dict]]:
    """Lowest confidence threshold whose accepted set has an error rate at or below `max_error`.
    `scored` holds (confidence, correct) per field read on the development drawings."""
    curve = []
    best = 1.01
    for t in sorted({round(c, 2) for c, _ in scored} | {0.0}, reverse=True):
        acc = [ok for c, ok in scored if c >= t]
        if not acc:
            continue
        err = 1 - sum(acc) / len(acc)
        curve.append({"threshold": t, "accepted_share": round(len(acc) / len(scored), 4), "error": round(err, 4)})
        if err <= max_error:
            best = t
    return best, sorted(curve, key=lambda c: c["threshold"])
