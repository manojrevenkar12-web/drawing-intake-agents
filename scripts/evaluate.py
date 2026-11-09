"""Score the reader against the truth.

    python scripts/evaluate.py dev       # any time; also prints the routing curve the threshold is chosen from
    python scripts/evaluate.py heldout   # once: checks config/heldout.lock, refuses a second run

Writes reports/<split>.json. The held-out customers' layouts were never used to build or tune anything."""

from __future__ import annotations

import hashlib
import json
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from dia.delivery.routing import choose_threshold
from dia.engineering.diff import compare
from dia.engineering.feasibility import decide
from dia.engineering.notes import RuleReader
from dia.engineering.tolerance import resolve
from dia.perceive.dimensions import ReadDim
from dia.perceive.fields import FIELDS, learn_profile, read_title_block, same_value
from dia.perceive.reader import Reader, Reading
from dia.perceive.regions import CLASSES, Template
from dia.settings import ROOT, load

DATA, VAR, REPORTS = ROOT / "data", ROOT / "var", ROOT / "reports"
MATCH_MM = 8.0


def truth(split: str, sid: str) -> dict:
    return json.loads((DATA / "truth" / split / f"{sid}.json").read_text())


def files(split: str) -> dict[str, Path]:
    return {p.stem: p for p in sorted((DATA / split).iterdir())}


def template() -> Template:
    ex = []
    for sid in files("dev"):
        t = truth("dev", sid)
        ex.append(({k: [tuple(b) for b in v] for k, v in t["regions"].items()}, tuple(t["page_mm"])))
    return Template.fit(ex)


def read_all(split: str, reader: Reader) -> dict[str, Reading]:
    cache = VAR / f"readings_{split}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    out = {}
    t0 = time.time()
    for i, (sid, p) in enumerate(files(split).items()):
        out[sid] = reader.read(p)
        if i % 20 == 0:
            print(f"  {i}/{len(files(split))} read, {time.time() - t0:.0f}s", flush=True)
    VAR.mkdir(exist_ok=True)
    cache.write_bytes(pickle.dumps(out))
    return out


# ------------------------------------------------------------------ metrics


def _grid_iou(pred: list, true: list, size) -> float | None:
    W, H = int(size[0]), int(size[1])
    a, b = np.zeros((H, W), bool), np.zeros((H, W), bool)
    for x0, y0, x1, y1 in pred:
        a[int(y0) : int(y1), int(x0) : int(x1)] = True
    for x0, y0, x1, y1 in true:
        b[int(y0) : int(y1), int(x0) : int(x1)] = True
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else None


def region_scores(readings: dict, split: str, tmpl: Template) -> dict:
    res: dict[str, dict[str, list]] = {"detector": defaultdict(list), "template": defaultdict(list)}
    for sid, r in readings.items():
        t = truth(split, sid)
        tb = t["regions"]
        tp = tmpl.detect(None, tuple(t["page_mm"]))
        for cls in CLASSES[1:]:
            true = tb.get(cls, [])
            if not true:
                continue
            for name, pred in (("detector", r.regions.get(cls, [])), ("template", tp.get(cls, []))):
                v = _grid_iou(pred, true, t["page_mm"])
                if v is not None:
                    res[name][cls].append(v)
    return {
        name: {
            cls: {"mean_iou": round(float(np.mean(v)), 3), "found_iou50": round(float(np.mean(np.array(v) >= 0.5)), 3)}
            for cls, v in per.items()
        }
        for name, per in res.items()
    }


def as_read(d: dict) -> ReadDim:
    t = d["tol"]
    return ReadDim(
        d["kind"],
        d["nominal"],
        t["kind"],
        t["plus"],
        t["minus"],
        t["fit"],
        d["count"],
        d["text"],
        d["x"],
        d["y"],
        d["vertical"],
    )


def match_dims(read: list[ReadDim], true: list[dict]) -> list[tuple[dict, ReadDim | None]]:
    out, used = [], set()
    for td in true:
        best = None
        for j, rd in enumerate(read):
            if j in used:
                continue
            dist = float(np.hypot(rd.x - td["x"], rd.y - td["y"]))
            if dist <= MATCH_MM and (best is None or dist < best[0]):
                best = (dist, j)
        if best:
            used.add(best[1])
            out.append((td, read[best[1]]))
        else:
            out.append((td, None))
    return out


def dim_scores(readings: dict, split: str) -> dict:
    by = defaultdict(lambda: Counter())
    for sid, r in readings.items():
        t = truth(split, sid)
        gcls_t = t["part"]["general_tolerance"]
        gcls_r = r.fields["general_tolerance"].value
        pairs = match_dims(r.dims, t["part"]["dims"])
        for med in (t["medium"], "all"):
            c = by[med]
            c["truth"] += len(t["part"]["dims"])
            c["read"] += len(r.dims)
            for td, rd in pairs:
                tr = as_read(td)
                if rd is None:
                    continue
                c["located"] += 1
                c["exact"] += rd.signature() == tr.signature()
                c["nominal"] += rd.nominal == tr.nominal
                lt, lr = resolve(tr, gcls_t), resolve(rd, gcls_r)
                if lt is not None:
                    c["limits_truth"] += 1
                    c["limits_right"] += lr is not None and (lr.lower, lr.upper) == (lt.lower, lt.upper)
    out = {}
    for med, c in by.items():
        out[med] = {
            "truth": c["truth"],
            "read": c["read"],
            "recall_exact": round(c["exact"] / c["truth"], 4),
            "precision_exact": round(c["exact"] / max(1, c["read"]), 4),
            "recall_nominal": round(c["nominal"] / c["truth"], 4),
            "limits_right": round(c["limits_right"] / max(1, c["limits_truth"]), 4),
        }
    return out


def field_scores(readings: dict, split: str) -> tuple[dict, list[tuple[float, bool]]]:
    per = defaultdict(lambda: Counter())
    scored = []
    for sid, r in readings.items():
        t = truth(split, sid)
        for f in FIELDS:
            ok = same_value(f, r.fields[f].value, t["title_values"][f])
            for k in (f, f"medium:{t['medium']}", "all"):
                per[k]["n"] += 1
                per[k]["ok"] += ok
            if r.fields[f].value is not None:
                scored.append((r.fields[f].conf if not r.fields[f].checks else 0.0, ok))
    return {k: round(c["ok"] / c["n"], 4) for k, c in per.items()}, scored


def notes_scores(readings: dict, split: str) -> dict:
    tp = fp = fn = 0
    for sid, r in readings.items():
        t = truth(split, sid)
        true = {(q["kind"], q["value"]) for q in t["part"]["requirements"]}
        got = {(q.kind, q.value) for q in RuleReader().read(r.notes)}
        tp += len(true & got)
        fp += len(got - true)
        fn += len(true - got)
    return {
        "precision": round(tp / max(1, tp + fp), 4),
        "recall": round(tp / max(1, tp + fn), 4),
        "requirements": tp + fn,
    }


def bom_scores(readings: dict, split: str) -> dict:
    cells = ok = 0
    for sid, r in readings.items():
        t = truth(split, sid)
        for row in t["part"]["bom"]:
            got = next((b for b in r.bom if b["pos"] == row["pos"]), None)
            for k in ("qty", "description", "reference", "material"):
                cells += 1
                ok += got is not None and str(got[k]).strip() == str(row[k]).strip()
    return {"cells": cells, "cell_accuracy": round(ok / max(1, cells), 4)}


def _near(dims: list[dict], x: float, y: float) -> dict | None:
    best = min(dims, key=lambda d: np.hypot(d["x"] - x, d["y"] - y), default=None)
    return best if best is not None and np.hypot(best["x"] - x, best["y"] - y) <= MATCH_MM else None


def diff_scores(readings: dict, split: str) -> dict:
    """Changes reported as certain are scored for precision and recall; changes flagged for a look (possibly a
    reading error) count only towards 'found or flagged'."""
    tp = fp = fn = flagged_true = flagged_false = 0
    examples = []
    by_medium = Counter()
    for sid, r in readings.items():
        t = truth(split, sid)
        if not t["previous"] or t["previous"] not in readings:
            continue
        prev_t = truth(split, t["previous"])
        both_vector = t["medium"] == prev_t["medium"] == "vector"
        found = compare(readings[t["previous"]], r)
        true = {(c["kind"], c["key"]) for c in t["changes"]}
        companions = {
            (c["kind"], "holes.dia") for c in t["changes"] if c["kind"] in ("feature_added", "feature_removed")
        }
        hit: set = set()
        flagged: set = set()
        for f in found:
            if f.kind == "field_changed":
                key = (f.kind, f.what)
            else:
                d = _near(prev_t["part"]["dims"] if f.on_previous else t["part"]["dims"], f.x, f.y)
                key = (f.kind, d["key"] if d else "?")
            real = key in true or key in companions
            if not f.certain:
                flagged_true += real
                flagged_false += not real
                if key in true:
                    flagged.add(key)
                continue
            if key in true:
                hit.add(key)
            elif not real:
                fp += 1
                by_medium["fp_vector" if both_vector else "fp_scan"] += 1
                if len(examples) < 12:
                    examples.append(
                        {"sheet": sid, "found": f.kind, "what": f.what, "before": f.before, "after": f.after}
                    )
        tp += len(hit)
        fn += len(true - hit)
        by_medium["true_vector" if both_vector else "true_scan"] += len(true)
        by_medium["hit_vector" if both_vector else "hit_scan"] += len(hit)
        by_medium["found_or_flagged"] += len(hit | flagged)
    total = tp + fn
    return {
        "changes": total,
        "precision": round(tp / max(1, tp + fp), 4),
        "recall": round(tp / max(1, total), 4),
        "found_or_flagged": round(by_medium["found_or_flagged"] / max(1, total), 4),
        "flagged": flagged_true + flagged_false,
        "flagged_real": flagged_true,
        "recall_vector_pairs": round(by_medium["hit_vector"] / max(1, by_medium["true_vector"]), 4),
        "recall_with_a_scan": round(by_medium["hit_scan"] / max(1, by_medium["true_scan"]), 4),
        "false_examples": examples,
    }


def feasibility_scores(readings: dict, split: str) -> dict:
    agree = n = 0
    routes = Counter()
    for sid, r in readings.items():
        t = truth(split, sid)
        p = t["part"]
        oracle = decide([as_read(d) for d in p["dims"]], p["general_tolerance"], p["material"], p["requirements"])
        reqs = [{"kind": q.kind, "value": q.value} for q in RuleReader().read(r.notes)]
        got = decide(r.dims, r.fields["general_tolerance"].value, r.fields["material"].value, reqs)
        n += 1
        agree += got.route == oracle.route
        routes[oracle.route] += 1
    return {"drawings": n, "route_agreement": round(agree / max(1, n), 4), "true_routes": dict(routes)}


def review_time(readings: dict, split: str, threshold: float) -> dict:
    s = load().review
    fields_total = accepted = wrong_accepted = 0
    minutes = 0.0
    for sid, r in readings.items():
        t = truth(split, sid)
        to_review = 0
        for f in FIELDS:
            fr = r.fields[f]
            fields_total += 1
            if fr.value is not None and fr.conf >= threshold and not fr.checks:
                accepted += 1
                wrong_accepted += not same_value(f, fr.value, t["title_values"][f])
            else:
                to_review += 1
        to_review += sum(1 for d in r.dims if d.repairs)
        minutes += s.minutes_per_drawing_check + to_review * s.minutes_per_field_review
    n = len(readings)
    return {
        "threshold": threshold,
        "fields": fields_total,
        "auto_accepted_share": round(accepted / fields_total, 4),
        "wrong_among_auto_accepted": wrong_accepted,
        "error_among_auto_accepted": round(wrong_accepted / max(1, accepted), 4),
        "minutes_per_drawing_manual_assumed": s.minutes_per_drawing_manual,
        "minutes_per_drawing_with_desk": round(minutes / n, 2),
    }


def onboarding(readings: dict, split: str, ks=(0, 1, 3)) -> dict:
    """Title-block accuracy on a customer's later drawings after learning from their first k drawings."""
    out: dict[str, dict] = {}
    by_layout = defaultdict(list)
    for sid in sorted(readings):
        by_layout[truth(split, sid)["layout"]].append(sid)
    for k in ks:
        ok = n = 0
        for lay, sids in by_layout.items():
            learn, test = sids[:k], sids[max(k, 3) :]  # the same test drawings for every k
            prof = (
                learn_profile(
                    lay,
                    [(readings[s].items, truth(split, s)["title_values"]) for s in learn],
                    [(readings[s].regions.get("title_block") or [None])[0] for s in learn],
                )
                if k
                else None
            )
            for s in test:
                r, t = readings[s], truth(split, s)
                tb = [
                    i
                    for b in r.regions.get("title_block", [])
                    for i in r.items
                    if b[0] - 1 <= i.cx <= b[2] + 1 and b[1] - 1 <= i.cy <= b[3] + 1
                ]
                box = (r.regions.get("title_block") or [None])[0]
                fields = read_title_block(tb, prof, load().fields.max_value_distance_mm, r.revisions, box)
                for f in FIELDS:
                    n += 1
                    ok += same_value(f, fields[f].value, t["title_values"][f])
        out[str(k)] = {"field_accuracy": round(ok / max(1, n), 4), "fields": n}
    return out


# ------------------------------------------------------------------ the held-out procedure


def check_lock() -> list[str]:
    bad = []
    for ln in (ROOT / "config" / "heldout.lock").read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        digest, path = ln.split(maxsplit=1)
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            bad.append(path)
    return bad


def main() -> None:
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    out = REPORTS / f"{split}.json"
    if split == "heldout":
        if out.exists():
            sys.exit("the held-out set has been run; its result is in reports/heldout.json and is not re-run")
        bad = check_lock()
        if bad:
            sys.exit(f"changed since the held-out lock: {', '.join(bad)}")
    s = load()
    reader = Reader()
    t0 = time.time()
    readings = read_all(split, reader)
    fields, scored = field_scores(readings, split)
    report = {
        "split": split,
        "drawings": len(readings),
        "media": dict(Counter(truth(split, sid)["medium"] for sid in readings)),
        "layouts": sorted({truth(split, sid)["layout"] for sid in readings}),
        "regions": region_scores(readings, split, template()),
        "fields": fields,
        "dimensions": dim_scores(readings, split),
        "parts_list": bom_scores(readings, split),
        "notes": notes_scores(readings, split),
        "revisions": diff_scores(readings, split),
        "feasibility": feasibility_scores(readings, split),
        "onboarding": onboarding(readings, split),
        "seconds": round(time.time() - t0, 1),
    }
    if split == "dev":
        thr, curve = choose_threshold(scored, s.routing.max_auto_error)
        report["routing_curve"] = curve
        report["chosen_threshold"] = thr
    report["review"] = review_time(readings, split, s.routing.min_confidence)
    REPORTS.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(
        json.dumps({k: v for k, v in report.items() if k not in ("routing_curve",)}, indent=1, ensure_ascii=False)[
            :6000
        ]
    )


if __name__ == "__main__":
    main()
