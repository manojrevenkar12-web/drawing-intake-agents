"""Turn a read dimension into its limits of size: an explicit tolerance, an ISO 286 fit class, or the general
tolerance class from the title block (ISO 2768-1)."""

from __future__ import annotations

from dataclasses import dataclass

from dia.perceive.dimensions import ReadDim
from dia.standards import iso286, iso2768


@dataclass(frozen=True)
class Resolved:
    lower: float  # mm, absolute limits of size
    upper: float
    source: str  # "explicit" | "ISO 286 <class>" | "ISO 2768-<cls>" | "none"

    @property
    def width(self) -> float:
        return round(self.upper - self.lower, 4)


def resolve(d: ReadDim, general_class: str | None) -> Resolved | None:
    n = d.nominal
    if d.kind in ("thread", "chamfer"):
        return None  # threads follow ISO 965; chamfers are not toleranced here
    if d.tol_kind in ("sym", "asym"):
        return Resolved(round(n + d.minus, 4), round(n + d.plus, 4), "explicit")
    if d.tol_kind == "fit":
        try:
            lim = iso286.fit_limits(d.fit, n)
        except (KeyError, ValueError):
            return None
        return Resolved(round(n + lim.lower, 4), round(n + lim.upper, 4), f"ISO 286 {d.fit}")
    if general_class:
        try:
            dev = iso2768.deviation(general_class, n)
        except (KeyError, ValueError):
            return None
        return Resolved(round(n - dev, 4), round(n + dev, 4), f"ISO 2768-{general_class}")
    return None
