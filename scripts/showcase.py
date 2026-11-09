"""The sheet shown on the dashboard: one held-out scan as received and as read, from the readings the evaluation
cached (nothing is read again). Writes reports/showcase.json and the two images under web/public/data/."""

from __future__ import annotations

import json
import pickle
import sys

import cv2

from dia.delivery.routing import route
from dia.engineering.diff import compare
from dia.engineering.feasibility import decide
from dia.engineering.notes import RuleReader
from dia.engineering.tolerance import resolve
from dia.perceive.fields import FIELDS, same_value
from dia.perceive.page import load
from dia.settings import ROOT
from dia.settings import load as settings

sys.path.insert(0, str(ROOT / "scripts"))
from evaluate import as_read, files, match_dims, truth

WEB = ROOT / "web" / "public" / "data"
WIDTH_PX = 1600


def _limits(d, gcls):
    r = resolve(d, gcls)
    return None if r is None else f"{r.lower:g} to {r.upper:g} mm ({r.source})"


def main() -> None:
    split = sys.argv[1] if len(sys.argv) > 1 else "heldout"
    readings = pickle.loads((ROOT / "var" / f"readings_{split}.pkl").read_bytes())
    s = settings()
    # a scan of a held-out customer that came with its previous revision
    sid = next(
        k
        for k in sorted(readings)
        if truth(split, k)["medium"] == "scan"
        and truth(split, k)["previous"]
        and truth(split, k)["part"]["family"] in ("plate", "assembly")
    )
    r, t = readings[sid], truth(split, sid)
    path = files(split)[sid]
    raw = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    k = WIDTH_PX / raw.shape[1]
    WEB.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(
        str(WEB / "sheet_received.jpg"),
        cv2.resize(raw, None, fx=k, fy=k, interpolation=cv2.INTER_AREA),
        [cv2.IMWRITE_JPEG_QUALITY, 82],
    )
    page = load(path, dpi=s.render.scan_dpi)
    k2 = WIDTH_PX / page.image.shape[1]
    cv2.imwrite(
        str(WEB / "sheet_registered.jpg"),
        cv2.resize(page.image, None, fx=k2, fy=k2, interpolation=cv2.INTER_AREA),
        [cv2.IMWRITE_JPEG_QUALITY, 82],
    )
    gcls = r.fields["general_tolerance"].value
    dims = []
    used = set()
    for td, rd in match_dims(r.dims, t["part"]["dims"]):
        if rd is None:
            dims.append(
                {
                    "text": "",
                    "truth": td["text"],
                    "x": td["x"],
                    "y": td["y"],
                    "vertical": td["vertical"],
                    "status": "missed",
                    "limits": None,
                }
            )
            continue
        used.add(id(rd))
        ok = rd.signature() == as_read(td).signature()
        dims.append(
            {
                "text": rd.text,
                "truth": td["text"],
                "x": round(rd.x, 1),
                "y": round(rd.y, 1),
                "vertical": rd.vertical,
                "status": "right" if ok else "wrong",
                "limits": _limits(rd, gcls),
            }
        )
    for rd in r.dims:
        if id(rd) not in used:
            dims.append(
                {
                    "text": rd.text,
                    "truth": None,
                    "x": round(rd.x, 1),
                    "y": round(rd.y, 1),
                    "vertical": rd.vertical,
                    "status": "extra",
                    "limits": None,
                }
            )
    routed = route(r.fields, s.routing.min_confidence)
    fields = [
        {
            "field": f,
            "value": r.fields[f].value,
            "truth": t["title_values"][f],
            "right": same_value(f, r.fields[f].value, t["title_values"][f]),
            "conf": r.fields[f].conf,
            "routed": "accepted" if f in routed.accepted else "review",
        }
        for f in FIELDS
    ]
    reqs = [{"kind": q.kind, "value": q.value} for q in RuleReader().read(r.notes)]
    dec = decide(r.dims, gcls, r.fields["material"].value, reqs)
    found = compare(readings[t["previous"]], r)
    out = {
        "id": sid,
        "layout": t["layout"],
        "medium": t["medium"],
        "size_mm": t["page_mm"],
        "received": "sheet_received.jpg",
        "registered": "sheet_registered.jpg",
        "regions": {k3: [list(b) for b in v] for k3, v in r.regions.items()},
        "dims": dims,
        "fields": fields,
        "decision": {"route": dec.route, "reasons": dec.reasons, "partners": dec.partners, "processes": dec.processes},
        "changes": {
            "found": [{"kind": f.kind, "what": f.what, "before": f.before, "after": f.after} for f in found],
            "truth": t["changes"],
        },
    }
    (ROOT / "reports" / "showcase.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(sid, sum(d["status"] == "right" for d in dims), "of", len(t["part"]["dims"]), "dims right")


if __name__ == "__main__":
    main()
