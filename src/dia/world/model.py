"""What a drawing *is*, as the simulated customer authored it. This is the truth side: the generator writes it, the
evaluation reads it, and nothing that serves (dia.perceive, dia.engineering, dia.delivery) imports it."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

TITLE_FIELDS = ("title", "drawing_number", "revision", "material", "general_tolerance", "scale", "mass_kg", "date")


@dataclass
class Tol:
    kind: str  # "general" | "sym" | "asym" | "fit"
    plus: float = 0.0
    minus: float = 0.0  # stored as a positive or negative deviation, as printed (e.g. -0.05)
    fit: str = ""


@dataclass
class Dim:
    key: str  # stable feature key, e.g. "length", "hole_2.dia", "hole_2.x"
    kind: str  # "linear" | "diameter" | "radius" | "thread" | "chamfer"
    nominal: float
    tol: Tol
    count: int = 1
    text: str = ""  # as printed on the drawing
    view: str = "front"
    x: float = 0.0  # text centre on the sheet, mm from the top-left corner
    y: float = 0.0
    vertical: bool = False


@dataclass
class BomRow:
    pos: int
    qty: int
    description: str
    reference: str  # part number or standard designation
    material: str


@dataclass
class RevRow:
    rev: str
    description: str
    date: str


@dataclass
class Requirement:
    kind: str  # "edge_break" | "surface" | "certificate" | "heat_treatment" | "compliance" | "deburr"
    value: str
    standard: str = ""


@dataclass
class Part:
    family: str
    title: str
    drawing_number: str
    revision: str
    material: str
    general_tolerance: str  # "f" | "m" | "c"
    scale: str
    mass_kg: float
    date: str
    envelope: tuple[float, float, float]  # mm, largest first
    dims: list[Dim] = field(default_factory=list)
    bom: list[BomRow] = field(default_factory=list)
    revisions: list[RevRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    geometry: dict = field(default_factory=dict)  # family-specific shape parameters for rendering


@dataclass
class Change:
    kind: str  # "dimension_changed" | "tolerance_changed" | "feature_added" | "feature_removed" | "field_changed"
    key: str
    before: str = ""
    after: str = ""


@dataclass
class Sheet:
    """One delivered drawing: the part, the customer layout it was drawn in, and how it arrived."""

    id: str
    layout: str
    split: str  # "dev" | "heldout"
    medium: str  # "vector" | "scan"
    part: Part
    page_mm: tuple[float, float]
    regions: dict[str, list[tuple[float, float, float, float]]] = field(default_factory=dict)  # x0, y0, x1, y1 mm
    title_values: dict[str, str] = field(default_factory=dict)  # field -> exact printed text
    previous: str | None = None  # id of the previous revision's sheet, if delivered with it
    changes: list[Change] = field(default_factory=list)  # truth changes from `previous`

    def to_dict(self) -> dict:
        return asdict(self)
