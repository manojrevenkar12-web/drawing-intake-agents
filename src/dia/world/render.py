"""Draw a part onto a customer's sheet as a vector PDF (with a text layer, as CAD exports it), and degrade it into a
scan when the customer sends paper. Records where everything landed: region boxes, dimension text positions and
the exact printed title-block values, which is the truth the reader is scored against."""

from __future__ import annotations

import io
import itertools
import math
import random
from datetime import date
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from dia.world.layouts import Layout
from dia.world.model import Dim, Part, Sheet

MM = 72 / 25.4
FONT_DIRS = [Path("/usr/share/fonts")]
_REGISTERED: dict[str, str] = {}
SCALES = [(2, 1), (1, 1), (1, 2), (1, 2.5), (1, 5)]


def font(stem: str) -> str:
    """Register a TTF by file stem; fall back to DejaVuSans, then Helvetica."""
    if stem in _REGISTERED:
        return _REGISTERED[stem]
    for candidate in (stem, "DejaVuSans"):
        for d in FONT_DIRS:
            hits = list(d.rglob(f"{candidate}.ttf"))
            if hits:
                pdfmetrics.registerFont(TTFont(candidate, str(hits[0])))
                _REGISTERED[stem] = candidate
                return candidate
    _REGISTERED[stem] = "Helvetica"
    return "Helvetica"


def num(x: float, decimal: str) -> str:
    s = f"{x:.2f}".rstrip("0").rstrip(".") if not float(x).is_integer() else f"{int(x)}"
    return s.replace(".", decimal)


def dim_text(d: Dim, decimal: str) -> str:
    n = num(d.nominal, decimal)
    count = f"{d.count}x " if d.count > 1 and d.kind in ("diameter", "thread", "radius") else ""
    if d.kind == "diameter":
        core = f"Ø{n}"
    elif d.kind == "radius":
        core = f"R{n}"
    elif d.kind == "thread":
        core = f"M{n}"
    elif d.kind == "chamfer":
        core = f"{n}x45°"
        count = f"{d.count}x " if d.count > 1 else ""
    else:
        core = n
    t = d.tol
    if t.kind == "fit":
        tol = f" {t.fit}"
    elif t.kind == "sym":
        tol = f" ±{num(t.plus, decimal)}"
    elif t.kind == "asym":
        lo = "0" if t.minus == 0 else f"-{num(abs(t.minus), decimal)}"
        tol = f" +{num(t.plus, decimal)}/{lo}"
    else:
        tol = ""
    return f"{count}{core}{tol}"


def scale_text(s: tuple[float, float]) -> str:
    a, b = s
    return f"{num(a, '.')}:{num(b, '.')}"


# ------------------------------------------------------------------ views per family


def views(part: Part) -> list[dict]:
    g, f = part.geometry, part.family
    if f in ("plate", "assembly"):
        L, W, T = g["L"], g["W"], g["T"]
        front = {"name": "front", "w": L, "h": W, "shapes": [("rect", 0, 0, L, W, g["radius"])], "place": {}}
        for x, y in g["holes"]:
            front["shapes"].append(("circle", x, y, g["dia"] / 2))
            front["shapes"].append(("cross", x, y, g["dia"] / 2 + 2))
        side = {"name": "side", "w": T, "h": W, "shapes": [("rect", 0, 0, T, W, 0)], "place": {}}
        front["place"]["length"] = ("h", 0, L, W, 1, 1)
        front["place"]["width"] = ("v", 0, W, 0, -1, 1)
        side["place"]["thickness"] = ("h", 0, T, W, 1, 1)
        level = 1
        for i, (x, y) in enumerate(g["holes"]):
            k = f"hole_{i + 1}"
            front["place"][f"{k}.x"] = ("h", 0, x, 0, -1, level)
            level += 1
            front["place"][f"{k}.y"] = ("v", 0, y, 0, -1, 1 + level - 1)
        hx, hy = g["holes"][0]
        front["place"]["holes.dia"] = ("leader", hx, hy, 18, -14)
        if g["radius"]:
            front["place"]["corner.radius"] = ("leader", L - g["radius"] * 0.3, W - g["radius"] * 0.3, 14, 10)
        return [front, side]
    if f == "shaft":
        dmax = max(g["dias"])
        front = {"name": "front", "w": sum(g["lens"]), "h": dmax, "shapes": [], "place": {}}
        x = 0.0
        for i, (ln, d) in enumerate(zip(g["lens"], g["dias"], strict=True)):
            front["shapes"].append(("rect", x, (dmax - d) / 2, ln, d, 0))
            front["place"][f"step_{i + 1}.dia"] = ("vin", (dmax - d) / 2, (dmax + d) / 2, x + ln / 2)
            if i < len(g["lens"]) - 1:
                front["place"][f"step_{i + 1}.len"] = ("h", x, x + ln, dmax, 1, 1)
            x += ln
        front["shapes"].append(("axis", 0, dmax / 2, x, dmax / 2))
        front["place"]["length"] = ("h", 0, x, dmax, 1, 2)
        dl = g["dias"][-1]
        front["place"]["end.chamfer"] = ("leader", x, (dmax - dl) / 2, 12, -12)
        if g["thread"]:
            front["place"]["end.thread"] = ("leader", x - g["lens"][-1] * 0.3, (dmax + dl) / 2, 14, 14)
        end = {
            "name": "end",
            "w": dmax,
            "h": dmax,
            "shapes": [("circle", dmax / 2, dmax / 2, d / 2) for d in g["dias"]],
            "place": {},
        }
        return [front, end]
    if f == "flange":
        od, bore, pcd, n, hole, t = g["od"], g["bore"], g["pcd"], g["n"], g["hole"], g["t"]
        c = od / 2
        front = {
            "name": "front",
            "w": od,
            "h": od,
            "shapes": [("circle", c, c, od / 2), ("circle", c, c, bore / 2), ("dashcircle", c, c, pcd / 2)],
            "place": {},
        }
        for k in range(n):
            a = 2 * math.pi * k / n + math.pi / n
            front["shapes"].append(("circle", c + pcd / 2 * math.cos(a), c + pcd / 2 * math.sin(a), hole / 2))
        front["place"]["bore.dia"] = ("leader", c + bore / 2 * 0.7, c - bore / 2 * 0.7, 30, -c + 6)
        a0 = 2 * math.pi * (n - 1) / n + math.pi / n
        front["place"]["holes.dia"] = ("leader", c + pcd / 2 * math.cos(a0), c + pcd / 2 * math.sin(a0), 22, 16)
        front["place"]["pcd.dia"] = ("leader", c - pcd / 2 * 0.71, c + pcd / 2 * 0.71, -26, 18)
        side = {
            "name": "section",
            "w": t,
            "h": od,
            "shapes": [
                ("rect", 0, 0, t, (od - bore) / 2, 0),
                ("rect", 0, (od + bore) / 2, t, (od - bore) / 2, 0),
                ("hatch", 0, 0, t, od),
            ],
            "place": {},
        }
        side["place"]["od.dia"] = ("v", 0, od, t, 1, 1)
        side["place"]["thickness"] = ("h", 0, t, od, 1, 1)
        return [front, side]
    a, b, w, t, hole = g["a"], g["b"], g["w"], g["t"], g["hole"]
    front = {
        "name": "front",
        "w": a,
        "h": b,
        "shapes": [("poly", [(0, 0), (t, 0), (t, b - t), (a, b - t), (a, b), (0, b), (0, 0)])],
        "place": {},
    }
    front["place"]["leg_a.len"] = ("h", 0, a, b, 1, 1)
    front["place"]["leg_b.len"] = ("v", 0, b, 0, -1, 1)
    front["place"]["thickness"] = ("leader", t / 2, b * 0.3, -18, -10)
    front["place"]["bend.radius"] = ("leader", t, b - t, 16, -16)
    top = {
        "name": "top",
        "w": a,
        "h": w,
        "shapes": [
            ("rect", 0, 0, a, w, 0),
            ("circle", a * 0.55, w / 2, hole / 2),
            ("circle", a * 0.85, w / 2, hole / 2),
        ],
        "place": {},
    }
    top["place"]["width"] = ("v", 0, w, a, 1, 1)
    top["place"]["holes.dia"] = ("leader", a * 0.55, w / 2, 14, -w / 2 - 8)
    return [front, top]


# ------------------------------------------------------------------ sheet composition


class Painter:
    def __init__(self, c: canvas.Canvas, page_h: float, font_name: str):
        self.c, self.H, self.font = c, page_h, font_name

    def P(self, x: float, y: float) -> tuple[float, float]:
        return x * MM, (self.H - y) * MM

    def line(self, x0, y0, x1, y1, w=0.25, dash=None):
        self.c.setLineWidth(w)
        self.c.setDash(list(dash)) if dash else None
        self.c.line(*self.P(x0, y0), *self.P(x1, y1))
        self.c.setDash()

    def rect(self, x, y, w, h, lw=0.35, r=0.0):
        self.c.setLineWidth(lw)
        X, Y = self.P(x, y + h)
        if r:
            self.c.roundRect(X, Y, w * MM, h * MM, r * MM)
        else:
            self.c.rect(X, Y, w * MM, h * MM)

    def circle(self, cx, cy, r, lw=0.35, dash=None):
        self.c.setLineWidth(lw)
        self.c.setDash(list(dash)) if dash else None
        self.c.circle(*self.P(cx, cy), r * MM)
        self.c.setDash()

    def text(self, x, y, s, size, angle=0, bold=False):
        """x, y: baseline start in sheet mm."""
        self.c.saveState()
        self.c.setFont(self.font, size)
        self.c.translate(*self.P(x, y))
        if angle:
            self.c.rotate(angle)
        self.c.drawString(0, 0, s)
        self.c.restoreState()

    def width(self, s: str, size: float) -> float:
        return pdfmetrics.stringWidth(s, self.font, size) / MM


def _arrow(p: Painter, x, y, dx, dy):
    n = math.hypot(dx, dy) or 1
    ux, uy = dx / n, dy / n
    L, Wd = 2.5, 0.9
    pts = [(x, y), (x - ux * L - uy * Wd, y - uy * L + ux * Wd), (x - ux * L + uy * Wd, y - uy * L - ux * Wd)]
    path = p.c.beginPath()
    path.moveTo(*p.P(*pts[0]))
    for q in pts[1:]:
        path.lineTo(*p.P(*q))
    path.close()
    p.c.drawPath(path, fill=1, stroke=0)


def render(sheet: Sheet, lay: Layout, rng: random.Random) -> bytes:
    part = sheet.part
    W, H = lay.sheet
    sheet.page_mm = (W, H)
    left, m = 20.0, lay.border_margin
    dim_size = 9 if W > 300 else 7.5

    # ---- where things go (decided before anything is drawn)
    tw, nrows = sum(lay.col_w), 1 + max(r for _, r, _ in lay.cells.values())
    th, strip = nrows * lay.row_h, 7.0
    tx, ty = W - m - tw, H - m - th
    top_of_stack = ty - strip
    bom_rh, bom_y = 6.5, None
    if part.bom and lay.bom_labels:
        bom_y = top_of_stack - (len(part.bom) + 1) * bom_rh
        top_of_stack = bom_y
    rev_rh, rev_w = 6.0, (14, 70, 24)
    nr = len(part.revisions) + 1
    if lay.rev_position == "top_right":
        rx, ry = W - m - sum(rev_w), m
    else:
        rx, ry = W - m - sum(rev_w), top_of_stack - 4 - nr * rev_rh
    notes = [lay.notes_heading, *[f"{i + 1}. {n}" for i, n in enumerate(part.notes)]]
    nh = 5.2 * len(notes)
    nx, ny = left + 6, H - m - 6 - nh
    top = m + (nr * rev_rh + 28 if lay.rev_position == "top_right" else 30)
    area = (left + 30, top, W - m - 30, min(ny, top_of_stack) - 22)

    vs = views(part)
    gap = 45
    for s in SCALES:
        k = s[0] / s[1]
        need_w = sum(v["w"] * k for v in vs) + gap * (len(vs) - 1)
        need_h = max(v["h"] * k for v in vs)
        if need_w <= area[2] - area[0] and need_h <= area[3] - area[1]:
            break
    part.scale = scale_text(s)
    values = title_values(part, lay)
    sheet.title_values = values

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W * MM, H * MM))
    c.setTitle(f"{part.drawing_number} {part.revision}")
    p = Painter(c, H, font(lay.font))
    p.rect(left, m, W - left - m, H - 2 * m, lw=0.7)
    regions: dict[str, list] = {}

    # ---- title block
    p.rect(tx, ty - strip, tw, th + strip, lw=0.5)
    p.text(tx + 2, ty - 2.2, lay.company, 7)
    xs = [tx + sum(lay.col_w[:i]) for i in range(len(lay.col_w) + 1)]
    for fld, (col, row, span) in lay.cells.items():
        x0, y0 = xs[col], ty + row * lay.row_h
        p.rect(x0, y0, xs[col + span] - x0, lay.row_h, lw=0.25)
        p.text(x0 + 1.2, y0 + 0.8 + lay.label_size * 0.36, lay.labels[fld], lay.label_size)
        p.text(x0 + 2.0, y0 + lay.row_h - 2.2, values[fld], lay.value_size)
    regions["title_block"] = [(tx, ty - strip, W - m, H - m)]

    # ---- parts list above the title block
    if bom_y is not None:
        rest = tw - 22
        cw = [10, 12, rest * 0.34, rest * 0.38, rest * 0.28]
        cx = [tx + sum(cw[:i]) for i in range(6)]
        rows = [lay.bom_labels, *[(str(b.pos), str(b.qty), b.description, b.reference, b.material) for b in part.bom]]
        for r_i, row in enumerate(rows):
            yy = bom_y + r_i * bom_rh
            for j, cell in enumerate(row):
                p.rect(cx[j], yy, cw[j], bom_rh, lw=0.25)
                p.text(cx[j] + 1.2, yy + bom_rh - 2.0, str(cell), 6 if r_i == 0 else 7)
        regions["parts_list"] = [(tx, bom_y, W - m, ty - strip)]

    # ---- revision table
    rows = [lay.rev_labels, *[(rv.rev, rv.description, fmt_date(rv.date, lay)) for rv in part.revisions]]
    for r_i, row in enumerate(rows):
        x = rx
        for j, cell in enumerate(row):
            p.rect(x, ry + r_i * rev_rh, rev_w[j], rev_rh, lw=0.25)
            p.text(x + 1.2, ry + r_i * rev_rh + rev_rh - 1.9, str(cell)[:46], 6 if r_i == 0 else 6.5)
            x += rev_w[j]
    regions["revision_table"] = [(rx, ry, rx + sum(rev_w), ry + nr * rev_rh)]

    # ---- notes, bottom left
    for i, ln in enumerate(notes):
        p.text(nx, ny + 4 + i * 5.2, ln, 8 if i else 9)
    nw = max(p.width(ln, 8 if i else 9) for i, ln in enumerate(notes))
    regions["notes"] = [(nx - 1, ny, nx + nw + 1, ny + nh + 1.5)]

    # ---- views and dimensions
    total_w = sum(v["w"] * k for v in vs) + gap * (len(vs) - 1)
    max_h = max(v["h"] * k for v in vs)
    ox = area[0] + max(0, (area[2] - area[0] - total_w) / 2 + rng.uniform(-8, 8))
    oy = area[1] + max(0, (area[3] - area[1] - max_h) / 2 + rng.uniform(-6, 6))
    dims = {d.key: d for d in part.dims}
    regions["view"] = []
    for v in vs:
        vx, vy = ox, oy + (max_h - v["h"] * k) / 2
        box = [vx, vy, vx + v["w"] * k, vy + v["h"] * k]
        for sh in v["shapes"]:
            _shape(p, sh, vx, vy, k)
        for key, pl in v["place"].items():
            d = dims.get(key)
            if d is None:
                continue
            d.text = dim_text(d, lay.decimal)
            d.view = v["name"]
            bb = _dimension(p, d, pl, vx, vy, k, dim_size)
            box = [min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3])]
        regions["view"].append(tuple(box))
        ox += v["w"] * k + gap
    sheet.regions = {k2: [tuple(round(z, 2) for z in b) for b in v2] for k2, v2 in regions.items()}
    c.showPage()
    c.save()
    return buf.getvalue()


def _shape(p: Painter, sh: tuple, vx: float, vy: float, k: float):
    kind = sh[0]
    if kind == "rect":
        _, x, y, w, h, r = sh
        p.rect(vx + x * k, vy + y * k, w * k, h * k, lw=0.5, r=r * k)
    elif kind == "circle":
        _, x, y, r = sh
        p.circle(vx + x * k, vy + y * k, r * k, lw=0.5)
    elif kind == "dashcircle":
        _, x, y, r = sh
        p.circle(vx + x * k, vy + y * k, r * k, lw=0.18, dash=(6, 2, 1, 2))
    elif kind == "cross":
        _, x, y, r = sh
        p.line(vx + (x - r) * k, vy + y * k, vx + (x + r) * k, vy + y * k, w=0.18, dash=(6, 2, 1, 2))
        p.line(vx + x * k, vy + (y - r) * k, vx + x * k, vy + (y + r) * k, w=0.18, dash=(6, 2, 1, 2))
    elif kind == "axis":
        _, x0, y0, x1, y1 = sh
        p.line(vx + x0 * k - 4, vy + y0 * k, vx + x1 * k + 4, vy + y1 * k, w=0.18, dash=(6, 2, 1, 2))
    elif kind == "poly":
        pts = sh[1]
        for (a, b), (c2, d) in itertools.pairwise(pts):
            p.line(vx + a * k, vy + b * k, vx + c2 * k, vy + d * k, w=0.5)
    elif kind == "hatch":
        _, x, y, w, h = sh
        step = 3.0
        t = 0.0
        while t < w * k + h * k:
            x0, y0 = vx + min(t, w * k), vy + max(0, t - w * k)
            x1, y1 = vx + max(0, t - h * k), vy + min(t, h * k)
            p.line(x0, y0, x1, y1, w=0.13)
            t += step


def _dimension(p: Painter, d: Dim, pl: tuple, vx: float, vy: float, k: float, size: float) -> tuple:
    """Draw one dimension; set d.x, d.y (text centre) and d.vertical; return its bounding box."""
    text = d.text
    tw = p.width(text, size)
    th = size / MM * 0.72
    kind = pl[0]
    if kind == "h":
        _, x1, x2, ye, side, level = pl
        X1, X2, YE = vx + x1 * k, vx + x2 * k, vy + ye * k
        yl = YE + side * (8 + 8 * (level - 1))
        p.line(X1, YE + side * 1.5, X1, yl + side * 1.5, w=0.18)
        p.line(X2, YE + side * 1.5, X2, yl + side * 1.5, w=0.18)
        p.line(X1, yl, X2, yl, w=0.18)
        _arrow(p, X1, yl, -1, 0)
        _arrow(p, X2, yl, 1, 0)
        cx = (X1 + X2) / 2
        if tw + 6 > X2 - X1:
            cx = X2 + tw / 2 + 3
        p.text(cx - tw / 2, yl - 1.2, text, size)
        d.x, d.y, d.vertical = cx, yl - 1.2 - th / 2, False
        return (min(X1, cx - tw / 2), min(YE, yl - 1.2 - th), max(X2, cx + tw / 2), max(YE, yl + 1))
    if kind in ("v", "vin"):
        if kind == "v":
            _, y1, y2, xe, side, level = pl
            XE = vx + xe * k
            xl = XE + side * (8 + 8 * (level - 1))
            p.line(XE + side * 1.5, vy + y1 * k, xl + side * 1.5, vy + y1 * k, w=0.18)
            p.line(XE + side * 1.5, vy + y2 * k, xl + side * 1.5, vy + y2 * k, w=0.18)
        else:
            _, y1, y2, xm = pl
            xl = vx + xm * k
        Y1, Y2 = vy + y1 * k, vy + y2 * k
        p.line(xl, Y1, xl, Y2, w=0.18)
        _arrow(p, xl, Y1, 0, -1)
        _arrow(p, xl, Y2, 0, 1)
        cy = (Y1 + Y2) / 2
        p.text(xl - 1.2, cy + tw / 2, text, size, angle=90)
        d.x, d.y, d.vertical = xl - 1.2 - th / 2, cy, True
        return (
            min(xl - 1.2 - th, vx + (pl[3] if kind == "v" else xm) * k),
            min(Y1, cy - tw / 2),
            xl + 1,
            max(Y2, cy + tw / 2),
        )
    _, px, py, dx, dy = pl
    X, Y = vx + px * k, vy + py * k
    tx, ty = X + dx, Y + dy
    p.line(X, Y, tx, ty, w=0.18)
    _arrow(p, X, Y, X - tx, Y - ty)
    end = tx + (tw + 2 if dx >= 0 else -(tw + 2))
    p.line(tx, ty, end, ty, w=0.18)
    x0 = tx + 1 if dx >= 0 else end + 1
    p.text(x0, ty - 1.0, text, size)
    d.x, d.y, d.vertical = x0 + tw / 2, ty - 1.0 - th / 2, False
    return (min(X, tx, end), min(Y, ty - 1 - th), max(X, tx, end), max(Y, ty))


def fmt_date(iso: str, lay: Layout) -> str:
    return date.fromisoformat(iso).strftime(lay.date_format)


def title_values(part: Part, lay: Layout) -> dict[str, str]:
    return {
        "title": part.title,
        "drawing_number": part.drawing_number,
        "revision": part.revision,
        "material": part.material,
        "general_tolerance": lay.tol_phrase.format(cls=part.general_tolerance),
        "scale": lay.scale_style.format(n=part.scale.split(":")[1]) if part.scale.startswith("1:") else part.scale,
        "mass_kg": num(part.mass_kg, lay.decimal),
        "date": fmt_date(part.date, lay),
    }


# ------------------------------------------------------------------ scans


def rasterize(pdf: bytes, dpi: int) -> np.ndarray:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def degrade(img: np.ndarray, rng: random.Random, language: str) -> tuple[np.ndarray, dict]:
    """A plausible office scan: slight skew and shift, blur, noise, a stamp, JPEG artefacts."""
    h, w = img.shape
    angle = rng.uniform(-0.9, 0.9)
    dx, dy = rng.uniform(-12, 12), rng.uniform(-12, 12)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    M[:, 2] += (dx, dy)
    out = cv2.warpAffine(img, M, (w, h), borderValue=255)
    out = cv2.GaussianBlur(out, (0, 0), rng.uniform(0.5, 0.9))
    nrng = np.random.default_rng(rng.randint(0, 2**31))
    out = np.clip(
        out.astype(np.float32) * rng.uniform(0.92, 1.0) + nrng.normal(0, 7, out.shape) + rng.uniform(0, 12), 0, 255
    )
    speck = nrng.random(out.shape) < 0.0004
    out[speck] = 40
    out = out.astype(np.uint8)
    stamp = {"en": ["RECEIVED", "COPY", "FOR QUOTATION"], "de": ["EINGANG", "KOPIE", "ZUR ANFRAGE"]}[language]
    sx, sy = rng.randint(int(w * 0.3), int(w * 0.6)), rng.randint(int(h * 0.05), int(h * 0.2))
    cv2.rectangle(out, (sx, sy), (sx + 420, sy + 90), 110, 3)
    cv2.putText(out, rng.choice(stamp), (sx + 18, sy + 62), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 110, 3)
    ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(60, 82)])
    assert ok
    return cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE), {"angle": angle, "dx": dx, "dy": dy}
