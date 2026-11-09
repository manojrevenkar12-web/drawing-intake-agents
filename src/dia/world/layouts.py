"""Customer drawing layouts: how each simulated customer's CAD template prints a title block, a parts list, a
revision table and notes. Five are used for development; three are held out, with labels and arrangements the
reader has not seen (abbreviations, other languages, a parts list above the title block, a different sheet size).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Title block cells: field -> (column, row, column span) on a grid; labels print small at the top-left of the cell,
# values larger below them.


@dataclass(frozen=True)
class Layout:
    name: str
    company: str
    language: str  # "en" | "de"
    sheet: tuple[float, float]  # mm, landscape
    font: str  # TTF file stem in /usr/share/fonts, DejaVu as fallback
    labels: dict[str, str]
    cells: dict[str, tuple[int, int, int]]  # field -> (col, row, colspan)
    col_w: tuple[float, ...]  # mm per title block column
    row_h: float
    label_size: float  # pt
    value_size: float
    decimal: str  # "." or ","
    date_format: str  # strftime
    tol_phrase: str  # how the general tolerance is printed; {cls} is replaced
    bom_labels: tuple[str, str, str, str, str] | None = None  # pos, qty, description, reference, material
    bom_above_title: bool = True
    rev_labels: tuple[str, str, str] = ("Rev", "Description", "Date")
    rev_position: str = "top_right"  # "top_right" | "above_bom"
    notes_heading: str = "Notes"
    scale_style: str = "1:{n}"
    border_margin: float = 10.0
    label_inline: bool = False  # label and value on one line ("Material: S235JR")
    extra: dict = field(default_factory=dict)


def _grid(*rows: list[tuple[str, int]]) -> dict[str, tuple[int, int, int]]:
    out = {}
    for r, row in enumerate(rows):
        c = 0
        for name, span in row:
            out[name] = (c, r, span)
            c += span
    return out


LAYOUTS: dict[str, Layout] = {
    "acme_rail": Layout(
        name="acme_rail",
        company="ACME Rail Systems",
        language="en",
        sheet=(420, 297),
        font="DejaVuSansCondensed",
        labels={
            "title": "TITLE",
            "drawing_number": "DRAWING NO.",
            "revision": "REV",
            "material": "MATERIAL",
            "general_tolerance": "GENERAL TOLERANCES",
            "scale": "SCALE",
            "mass_kg": "MASS (kg)",
            "date": "DATE",
        },
        cells=_grid(
            [("title", 4)],
            [("drawing_number", 3), ("revision", 1)],
            [("material", 2), ("general_tolerance", 2)],
            [("scale", 1), ("mass_kg", 1), ("date", 2)],
        ),
        col_w=(40, 40, 40, 30),
        row_h=11,
        label_size=5,
        value_size=9,
        decimal=".",
        date_format="%Y-%m-%d",
        tol_phrase="ISO 2768-{cls}",
        bom_labels=("ITEM", "QTY", "DESCRIPTION", "PART NO. / STANDARD", "MATERIAL"),
        notes_heading="NOTES",
    ),
    "boltwerk": Layout(
        name="boltwerk",
        company="Boltwerk Antriebstechnik GmbH",
        language="de",
        sheet=(420, 297),
        font="LiberationSans-Regular",
        labels={
            "title": "Benennung",
            "drawing_number": "Zeichnungsnummer",
            "revision": "Index",
            "material": "Werkstoff",
            "general_tolerance": "Allgemeintoleranzen",
            "scale": "Maßstab",
            "mass_kg": "Gewicht kg",
            "date": "Datum",
        },
        cells=_grid(
            [("drawing_number", 2), ("revision", 1), ("scale", 1)],
            [("title", 4)],
            [("material", 3), ("mass_kg", 1)],
            [("general_tolerance", 3), ("date", 1)],
        ),
        col_w=(45, 45, 25, 25),
        row_h=10,
        label_size=5,
        value_size=8.5,
        decimal=",",
        date_format="%d.%m.%Y",
        tol_phrase="DIN ISO 2768-{cls}K",
        bom_labels=("Pos.", "Menge", "Benennung", "Sachnummer / Norm", "Werkstoff"),
        rev_labels=("Index", "Änderung", "Datum"),
        notes_heading="Hinweise",
    ),
    "nordlicht": Layout(
        name="nordlicht",
        company="Nordlicht Leuchten AG",
        language="de",
        sheet=(297, 210),
        font="FreeSans",
        labels={
            "title": "Bezeichnung",
            "drawing_number": "Zeichnungs-Nr.",
            "revision": "Änderungsstand",
            "material": "Material",
            "general_tolerance": "Freimaßtoleranz",
            "scale": "Maßstab",
            "mass_kg": "Masse [kg]",
            "date": "Erstellt",
        },
        cells=_grid(
            [("title", 3)],
            [("drawing_number", 2), ("revision", 1)],
            [("material", 2), ("scale", 1)],
            [("general_tolerance", 1), ("mass_kg", 1), ("date", 1)],
        ),
        col_w=(38, 38, 34),
        row_h=9,
        label_size=4.5,
        value_size=7.5,
        decimal=",",
        date_format="%d.%m.%Y",
        tol_phrase="ISO 2768-{cls}",
        bom_labels=None,
        rev_labels=("Stand", "Änderung", "Datum"),
        notes_heading="Anmerkungen",
    ),
    "sitec": Layout(
        name="sitec",
        company="SiTec Industrial Automation",
        language="en",
        sheet=(420, 297),
        font="LiberationSans-Regular",
        labels={
            "title": "Description",
            "drawing_number": "Document number",
            "revision": "Revision",
            "material": "Material",
            "general_tolerance": "Tolerances unless stated",
            "scale": "Scale",
            "mass_kg": "Weight [kg]",
            "date": "Released",
        },
        cells=_grid(
            [("title", 2), ("scale", 1)],
            [("drawing_number", 2), ("revision", 1)],
            [("material", 2), ("mass_kg", 1)],
            [("general_tolerance", 2), ("date", 1)],
        ),
        col_w=(55, 45, 40),
        row_h=10,
        label_size=5,
        value_size=8.5,
        decimal=".",
        date_format="%d %b %Y",
        tol_phrase="ISO 2768-{cls}",
        bom_labels=("Pos", "Qty", "Description", "Reference", "Material"),
        rev_position="above_bom",
        notes_heading="Technical notes",
    ),
    "vanderhoek": Layout(
        name="vanderhoek",
        company="Van der Hoek Machinebouw",
        language="en",
        sheet=(420, 297),
        font="DejaVuSans",
        labels={
            "title": "Part name",
            "drawing_number": "Drawing",
            "revision": "Issue",
            "material": "Material",
            "general_tolerance": "General tol.",
            "scale": "Scale",
            "mass_kg": "Mass kg",
            "date": "Date",
        },
        cells=_grid(
            [("drawing_number", 2), ("revision", 1)],
            [("title", 3)],
            [("material", 1), ("general_tolerance", 1), ("mass_kg", 1)],
            [("scale", 1), ("date", 2)],
        ),
        col_w=(50, 45, 35),
        row_h=11,
        label_size=5,
        value_size=9,
        decimal=".",
        date_format="%d/%m/%Y",
        tol_phrase="ISO 2768-{cls}",
        bom_labels=("No", "Qty", "Name", "Article / standard", "Material"),
        rev_labels=("Issue", "Change", "Date"),
        label_inline=False,
    ),
    # ---- held out: never seen while building or tuning the reader ----
    "kranich": Layout(
        name="kranich",
        company="Kranich Fördertechnik",
        language="de",
        sheet=(420, 297),
        font="DejaVuSans",
        labels={
            "title": "Benennung",
            "drawing_number": "Zchn.-Nr.",
            "revision": "Ausg.",
            "material": "Werkst.",
            "general_tolerance": "Tol. n.",
            "scale": "M",
            "mass_kg": "Gew.",
            "date": "Dat.",
        },
        cells=_grid(
            [("title", 3), ("scale", 1)],
            [("drawing_number", 2), ("revision", 1), ("date", 1)],
            [("material", 2), ("general_tolerance", 1), ("mass_kg", 1)],
        ),
        col_w=(45, 45, 30, 30),
        row_h=12,
        label_size=5,
        value_size=9,
        decimal=",",
        date_format="%d.%m.%y",
        tol_phrase="ISO 2768-{cls}",
        bom_labels=("Pos", "Stk", "Bezeichnung", "Ident-Nr. / Norm", "Werkst."),
        rev_labels=("Ausg.", "Änderung", "Dat."),
        notes_heading="Hinweise",
    ),
    "meridian": Layout(
        name="meridian",
        company="Meridian Rail Components Ltd",
        language="en",
        sheet=(420, 297),
        font="LiberationSans-Regular",
        labels={
            "title": "Title",
            "drawing_number": "Dwg No",
            "revision": "Iss",
            "material": "Matl",
            "general_tolerance": "Unless otherwise specified",
            "scale": "Scale",
            "mass_kg": "Wt (kg)",
            "date": "Date",
        },
        cells=_grid(
            [("drawing_number", 2), ("revision", 1)],
            [("title", 3)],
            [("material", 2), ("scale", 1)],
            [("general_tolerance", 2), ("mass_kg", 1)],
            [("date", 3)],
        ),
        col_w=(50, 50, 35),
        row_h=9,
        label_size=4.5,
        value_size=8,
        decimal=".",
        date_format="%d-%b-%Y",
        tol_phrase="TOLERANCES TO ISO 2768-{cls}",
        bom_labels=("Item", "No off", "Description", "Part / Std", "Matl"),
        rev_position="above_bom",
        notes_heading="NOTES",
    ),
    "tessaro": Layout(
        name="tessaro",
        company="Tessaro Meccanica S.r.l.",
        language="en",
        sheet=(297, 210),
        font="DejaVuSansCondensed",
        labels={
            "title": "Denomination",
            "drawing_number": "Code",
            "revision": "Rev.",
            "material": "Material",
            "general_tolerance": "Gen. tolerances",
            "scale": "Scale",
            "mass_kg": "Weight",
            "date": "Date",
        },
        cells=_grid(
            [("title", 2), ("drawing_number", 2)],
            [("material", 2), ("revision", 1), ("scale", 1)],
            [("general_tolerance", 2), ("mass_kg", 1), ("date", 1)],
        ),
        col_w=(30, 30, 25, 25),
        row_h=10,
        label_size=4.5,
        value_size=7.5,
        decimal=",",
        date_format="%d/%m/%Y",
        tol_phrase="ISO 2768-{cls}",
        bom_labels=None,
        notes_heading="Notes",
    ),
}


def layout(name: str) -> Layout:
    return LAYOUTS[name]
