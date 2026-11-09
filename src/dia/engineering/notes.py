"""Turn a drawing's notes into requirements the plant acts on (surface treatment, heat treatment, certificates,
edge breaks, compliance).

Two readers, one gate:
* `RuleReader` knows the common phrasings in English and German.
* `LLMReader` asks a language model (Anthropic Messages API) for the same structure, for phrasings no rule covers.
* `validate` keeps an LLM requirement only if the text it quotes is really in the note and its standard is one the
  plant knows; anything else goes to an engineer instead of into the order. The model reads; code decides.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass

import httpx

from dia.settings import load as settings

KINDS = ("edge_break", "deburr", "surface", "certificate", "heat_treatment", "compliance", "unmarked_radius")
KNOWN_STANDARDS = ("ISO 2081", "ISO 4042", "EN 10204", "2011/65/EU", "ISO 2768", "ISO 13715", "DIN 6784")


@dataclass
class Req:
    kind: str
    value: str
    standard: str = ""
    quote: str = ""
    source: str = "rules"


RULES: list[tuple[str, str, callable]] = [  # type: ignore[valid-type]
    (
        "edge_break",
        r"(?=.*(?:break|brechen|gefast|chamfer|kanten)).*?(\d+[.,]?\d*)\s*[xX×]\s*45",
        lambda m: f"{_n(m[1])}x45°",
    ),
    ("deburr", r"\b(?:deburr|entgraten)", lambda m: "yes"),
    ("surface", r"(Fe//Zn\d+//[A-Z])", lambda m: m[1]),
    ("surface", r"RAL\s*(\d{4})", lambda m: f"RAL {m[1]}"),
    ("surface", r"(?:anodi[sz]ed|eloxiert)[^0-9]*(\d+)\s*[µu]m", lambda m: f"anodised {m[1]} µm"),
    ("certificate", r"EN\s*10204\s*[- ]?\s*(\d\.\d)", lambda m: m[1]),
    ("heat_treatment", r"(\d{2}\s*-\s*\d{2})\s*HRC", lambda m: re.sub(r"\s", "", m[1]) + " HRC"),
    ("compliance", r"\bRoHS\b", lambda m: "RoHS"),
    ("unmarked_radius", r"(?:unmarked radii|nicht bemaßte radien)\s*R\s*(\d+[.,]?\d*)", lambda m: _n(m[1])),
]
STANDARD_OF = {"surface": r"ISO\s*2081", "certificate": r"EN\s*10204", "compliance": r"2011/65/EU"}


def _n(s: str) -> str:
    return s.replace(",", ".")


class RuleReader:
    def read(self, notes: list[str]) -> list[Req]:
        out = []
        for note in notes:
            for kind, pat, value in RULES:
                m = re.search(pat, note, re.I)
                if not m:
                    continue
                std = ""
                if kind in STANDARD_OF and (sm := re.search(STANDARD_OF[kind], note)):
                    std = re.sub(r"\s+", " ", sm[0])
                out.append(Req(kind, value(m), std, m[0]))
        return out


PROMPT = """You read the general notes of a mechanical engineering drawing and list the requirements they state.
Return only JSON: {{"requirements": [{{"kind": one of {kinds}, "value": short normalised value,
"standard": the standard it cites or "", "quote": the exact words of the note you took it from}}]}}.
Do not add requirements the notes do not state.

Notes:
{notes}"""


class LLMReader:
    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None, model: str | None = None):
        cfg = settings().notes
        self.model = model or cfg.llm_model
        self.max_tokens = cfg.llm_max_tokens
        self.key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = client or httpx.Client(timeout=cfg.llm_timeout_s)

    def read(self, notes: list[str]) -> list[Req]:
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": PROMPT.format(kinds=", ".join(KINDS), notes="\n".join(notes))}],
        }
        r = self.client.post(
            "https://api.anthropic.com/v1/messages",
            json=body,
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json()["content"])
        m = re.search(r"\{.*\}", text, re.S)
        raw = json.loads(m[0]) if m else {"requirements": []}
        return [
            Req(x.get("kind", ""), str(x.get("value", "")), x.get("standard", "") or "", x.get("quote", ""), "llm")
            for x in raw.get("requirements", [])
        ]


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace(",", ".")).strip()


def validate(reqs: list[Req], notes: list[str]) -> tuple[list[Req], list[tuple[Req, str]]]:
    """Keep a requirement only if its kind is known, its quote is in the notes, and its standard is known and
    appears in the quoted note. Returns (kept, rejected with reason)."""
    text = _fold(" ".join(notes))
    kept, rejected = [], []
    for r in reqs:
        if r.kind not in KINDS:
            rejected.append((r, f"unknown kind {r.kind!r}"))
        elif not r.quote or _fold(r.quote) not in text:
            rejected.append((r, "quoted text is not in the notes"))
        elif r.standard and (r.standard not in KNOWN_STANDARDS or _fold(r.standard) not in text):
            rejected.append((r, f"standard {r.standard!r} not known or not cited"))
        else:
            kept.append(r)
    return kept, rejected


def read_notes(notes: list[str], llm: LLMReader | None = None) -> dict:
    """Rules first; the LLM, if given, may add requirements the rules missed, through the validator."""
    rules = RuleReader().read(notes)
    out = {"requirements": [asdict(r) for r in rules], "rejected": []}
    if llm is not None:
        kept, rejected = validate(llm.read(notes), notes)
        have = {(r.kind, r.value) for r in rules}
        out["requirements"] += [asdict(r) for r in kept if (r.kind, r.value) not in have]
        out["rejected"] = [{**asdict(r), "reason": why} for r, why in rejected]
    return out
