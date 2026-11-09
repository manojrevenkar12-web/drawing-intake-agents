"""Turn whatever the customer sent into one Page: a list of text items with boxes in sheet millimetres, plus a page
image for the region detector.

* A CAD-exported PDF has a text layer: read it directly, with each item's writing direction.
* A scan (JPEG/PNG, or a PDF without text) is registered to its drawing frame (which undoes skew and shift), then
  read with Tesseract twice: once as is, and once turned 90 degrees for the vertical dimension texts.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pymupdf

MM_PER_PT = 25.4 / 72
# ISO 5457 drawing frame: 20 mm filing margin on the left, 10 mm elsewhere. Scans are registered to it.
FRAME_LEFT, FRAME_OTHER = 20.0, 10.0
SHEETS = {(420.0, 297.0): "A3", (297.0, 210.0): "A4"}


@dataclass
class Item:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    vertical: bool = False
    conf: float = 1.0  # 1.0 for a text layer, Tesseract's confidence / 100 for a scan

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return (self.x1 - self.x0) if self.vertical else (self.y1 - self.y0)


@dataclass
class Page:
    source: str  # "vector" | "scan"
    size_mm: tuple[float, float]
    items: list[Item]
    image: np.ndarray  # grayscale, registered, at `px_per_mm`
    px_per_mm: float
    registration_error_mm: float | None = None
    notes: list[str] = field(default_factory=list)

    def within(self, box: tuple[float, float, float, float], pad: float = 0.0) -> list[Item]:
        x0, y0, x1, y1 = box
        return [i for i in self.items if x0 - pad <= i.cx <= x1 + pad and y0 - pad <= i.cy <= y1 + pad]


def load(path: str | Path | None = None, data: bytes | None = None, name: str = "", dpi: int = 200) -> Page:
    name = str(path or name)
    raw = data if data is not None else Path(path).read_bytes()  # type: ignore[arg-type]
    if name.lower().endswith(".pdf") or raw[:4] == b"%PDF":
        doc = pymupdf.open(stream=raw, filetype="pdf")
        page = doc[0]
        if page.get_text("text").strip():
            return _vector(page, dpi)
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
        return _scan(img, dpi)
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"{name or 'upload'} is neither a PDF nor an image")
    return _scan(img, dpi)


def _sheet_size(w_mm: float, h_mm: float) -> tuple[float, float]:
    best = min(SHEETS, key=lambda s: abs(s[0] - w_mm) + abs(s[1] - h_mm))
    return best


def _vector(page: pymupdf.Page, dpi: int) -> Page:
    w, h = page.rect.width * MM_PER_PT, page.rect.height * MM_PER_PT
    items = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            vertical = abs(line["dir"][1]) > 0.5
            for span in line["spans"]:
                t = span["text"].strip()
                if not t:
                    continue
                x0, y0, x1, y1 = (v * MM_PER_PT for v in span["bbox"])
                items.append(Item(t, x0, y0, x1, y1, vertical))
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
    return Page("vector", (round(w, 1), round(h, 1)), items, img, dpi / 25.4)


# ------------------------------------------------------------------ scans


def frame_corners(img: np.ndarray) -> np.ndarray | None:
    """Corners of the drawing frame (the largest rectangle on the page), ordered TL, TR, BR, BL, in pixels."""
    small_k = 1600 / max(img.shape)
    small = cv2.resize(img, None, fx=small_k, fy=small_k, interpolation=cv2.INTER_AREA)
    bw = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.4 * small.shape[0] * small.shape[1]:
        return None
    rect = cv2.minAreaRect(c)
    box = cv2.boxPoints(rect) / small_k
    s, d = box.sum(1), np.diff(box, axis=1).ravel()
    return np.array([box[np.argmin(s)], box[np.argmin(d)], box[np.argmax(s)], box[np.argmax(d)]], np.float32)


def register(img: np.ndarray, dpi: int) -> tuple[np.ndarray, tuple[float, float], float, float | None]:
    """Warp a scan so that sheet millimetres map linearly to pixels; returns the image, sheet size, px/mm and the
    residual of the frame fit (mm), or None if no frame was found (then the page is used as scanned)."""
    ppm = dpi / 25.4
    h_px, w_px = img.shape
    W, H = _sheet_size(w_px / ppm, h_px / ppm)
    corners = frame_corners(img)
    if corners is None:
        return img, (W, H), ppm, None
    dst = (
        np.array(
            [
                [FRAME_LEFT, FRAME_OTHER],
                [W - FRAME_OTHER, FRAME_OTHER],
                [W - FRAME_OTHER, H - FRAME_OTHER],
                [FRAME_LEFT, H - FRAME_OTHER],
            ],
            np.float32,
        )
        * ppm
    )
    M, _ = cv2.estimateAffine2D(corners, dst)
    out = cv2.warpAffine(img, M, (round(W * ppm), round(H * ppm)), borderValue=255)
    fitted = cv2.transform(corners[None], M)[0]
    resid = float(np.abs(fitted - dst).max() / ppm)
    return out, (W, H), ppm, resid


def _scan(img: np.ndarray, dpi: int) -> Page:
    """Register the scan; text is read later, region by region (dia.perceive.ocr), once the regions are known."""
    reg, size, ppm, resid = register(img, dpi)
    notes = [] if resid is not None else ["no drawing frame found; page read as scanned"]
    return Page("scan", size, [], reg, ppm, resid, notes)


def as_png(page: Page) -> bytes:
    ok, enc = cv2.imencode(".png", page.image)
    return enc.tobytes() if ok else b""


__all__ = ["Item", "Page", "as_png", "io", "load", "register"]
