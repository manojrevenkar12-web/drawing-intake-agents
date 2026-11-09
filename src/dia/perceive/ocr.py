"""Read a registered scan region by region.

Tables (title block, parts list, revision table) are split into cells by their ruling lines, and each cell is read
as a block of text; notes are read as a block; views are read sparsely, once as is and once turned 90 degrees for
vertical dimension texts. Reading a cell on its own, enlarged, is what makes the 5 pt labels of a title block
legible to Tesseract at all."""

from __future__ import annotations

import cv2
import numpy as np
import pytesseract

from dia.perceive.page import Item, Page

TABLES = ("title_block", "parts_list", "revision_table")
UPSCALE = 2.0
LINE_PX = 40  # text-line height Tesseract reads best, in pixels


def _crop(page: Page, box, pad_mm: float) -> tuple[np.ndarray, float, float]:
    ppm = page.px_per_mm
    h, w = page.image.shape
    x0, y0 = max(0, int((box[0] - pad_mm) * ppm)), max(0, int((box[1] - pad_mm) * ppm))
    x1, y1 = min(w, int((box[2] + pad_mm) * ppm)), min(h, int((box[3] + pad_mm) * ppm))
    return page.image[y0:y1, x0:x1], x0 / ppm, y0 / ppm


def remove_lines(img: np.ndarray, ppm: float, min_len_mm: float) -> np.ndarray:
    """White out straight horizontal and vertical strokes longer than `min_len_mm` (table rules, dimension and
    extension lines), which otherwise run into the text and turn it into noise."""
    bw = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12)
    n = max(8, int(min_len_mm * ppm))
    lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (n, 1)))
    lines |= cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, n)))
    out = img.copy()
    out[cv2.dilate(lines, np.ones((3, 3), np.uint8)) > 0] = 255
    return out


def cells(img: np.ndarray, ppm: float) -> list[tuple[int, int, int, int]]:
    """Cell rectangles (x0, y0, x1, y1 px) of a ruled table, from its horizontal and vertical lines."""
    bw = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12)
    span = max(10, int(6 * ppm))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (span, 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, int(3 * ppm)))))
    grid = cv2.dilate(horiz | vert, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(255 - grid, connectivity=4)
    out = []
    H, W = img.shape
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if w < 2.5 * ppm or h < 3 * ppm or area < 0.5 * w * h:
            continue
        if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:  # outside the table, between it and the crop edge
            continue
        out.append((x, y, x + w, y + h))
    return out


def binarize(img: np.ndarray) -> np.ndarray:
    """Clean a scan crop for Tesseract: upscale, remove speckle noise, threshold."""
    big = cv2.resize(img, None, fx=UPSCALE, fy=UPSCALE, interpolation=cv2.INTER_CUBIC)
    big = cv2.medianBlur(big, 3)
    _, bw = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = 255 - bw
    _, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    small = np.where(stats[:, cv2.CC_STAT_AREA] < 6)[0]
    ink[np.isin(lab, small[small > 0])] = 0
    return 255 - ink


def _lines(img: np.ndarray, psm: int, min_word_conf: float = 0.40) -> list[tuple[str, int, int, int, int, float]]:
    big = binarize(img)
    d = pytesseract.image_to_data(
        big, lang="deu+eng", config=f"--psm {psm} --oem 1", output_type=pytesseract.Output.DICT
    )
    groups: dict[tuple, list[int]] = {}
    for i, t in enumerate(d["text"]):
        if (t or "").strip() and float(d["conf"][i]) >= min_word_conf * 100:
            groups.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(i)
    out = []
    for idx in groups.values():
        text = " ".join(d["text"][i].strip() for i in idx)
        x0 = min(d["left"][i] for i in idx) / UPSCALE
        y0 = min(d["top"][i] for i in idx) / UPSCALE
        x1 = max(d["left"][i] + d["width"][i] for i in idx) / UPSCALE
        y1 = max(d["top"][i] + d["height"][i] for i in idx) / UPSCALE
        conf = float(np.mean([float(d["conf"][i]) for i in idx])) / 100
        out.append((text, int(x0), int(y0), int(x1), int(y1), conf))
    return out


def _words(img: np.ndarray, min_conf: float) -> list[tuple[str, int, int, int, int, float]]:
    big = binarize(img)
    d = pytesseract.image_to_data(big, lang="deu+eng", config="--psm 11 --oem 1", output_type=pytesseract.Output.DICT)
    out = []
    for t, c, x, y, w, h in zip(d["text"], d["conf"], d["left"], d["top"], d["width"], d["height"], strict=True):
        t = (t or "").strip()
        if t and float(c) >= min_conf * 100:
            out.append(
                (t, int(x / UPSCALE), int(y / UPSCALE), int((x + w) / UPSCALE), int((y + h) / UPSCALE), float(c) / 100)
            )
    return out


def text_lines(cell: np.ndarray) -> list[tuple[int, int]]:
    """Row bands (y0, y1) holding ink, from the horizontal projection of a binarised cell."""
    rows = ink(cell).sum(1) >= 2
    bands, start = [], None
    for y, on in enumerate([*rows, False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= 4:
                bands.append((start, y))
            start = None
    return bands


def ink(img: np.ndarray, min_area: int = 5) -> np.ndarray:
    """Binary ink mask without scan speckles."""
    _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab]


def segments(band: np.ndarray, gap_px: int) -> list[tuple[int, int]]:
    """Horizontal runs of ink in a text line, split where the gap is wider than `gap_px`."""
    cols = np.where(ink(band).any(0))[0]
    if cols.size == 0:
        return []
    out, start, prev = [], cols[0], cols[0]
    for c in cols[1:]:
        if c - prev > gap_px:
            out.append((max(0, start - 3), min(band.shape[1], prev + 4)))
            start = c
        prev = c
    out.append((max(0, start - 3), min(band.shape[1], prev + 4)))
    return out


def _ocr_line(img: np.ndarray) -> tuple[str, float]:
    """One text line, enlarged so that its height is what Tesseract reads best (~40 px)."""
    h = img.shape[0]
    k = float(np.clip(LINE_PX / max(h, 1), 1.5, 6.0))
    big = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    _, big = cv2.threshold(cv2.medianBlur(big, 3), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    big = cv2.copyMakeBorder(big, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    d = pytesseract.image_to_data(big, lang="deu+eng", config="--psm 7 --oem 1", output_type=pytesseract.Output.DICT)
    words = [(t.strip(), float(c)) for t, c in zip(d["text"], d["conf"], strict=True) if t and t.strip()]
    words = [(t, c) for t, c in words if c >= 25]
    if not words:
        return "", 0.0
    return " ".join(t for t, _ in words), float(np.mean([c for _, c in words])) / 100


def read_table(page: Page, box, kind: str) -> list[Item]:
    """Split the table into cells, each cell into text lines, and read every line at the size Tesseract likes:
    the 5 pt labels of a title block need about four times the enlargement of its values."""
    img, ox, oy = _crop(page, box, 1.5)
    ppm = page.px_per_mm
    items = []
    found = cells(img, ppm)
    if not found:  # no ruling found: read the region as one block
        found = [(0, 0, img.shape[1], img.shape[0])]
    inset = max(1, int(0.35 * ppm))
    clean = remove_lines(img, ppm, 4.0)
    for x0, y0, x1, y1 in found:
        cx0, cy0 = x0 + inset, y0 + inset
        cell = clean[cy0 : y1 - inset, cx0 : x1 - inset]
        if cell.size == 0 or cell.min() > 160:
            continue
        for b0, b1 in text_lines(cell):
            band = cell[max(0, b0 - 2) : b1 + 2]
            for a, b in segments(band, gap_px=int(2.5 * ppm)):
                text, conf = _ocr_line(band[:, a:b])
                if not text:
                    continue
                items.append(
                    Item(
                        text,
                        ox + (cx0 + a) / ppm,
                        oy + (cy0 + b0) / ppm,
                        ox + (cx0 + b) / ppm,
                        oy + (cy0 + b1) / ppm,
                        False,
                        conf,
                    )
                )
    del kind
    return items


def read_block(page: Page, box) -> list[Item]:
    img, ox, oy = _crop(page, box, 1.0)
    ppm = page.px_per_mm
    return [
        Item(t, ox + a / ppm, oy + b / ppm, ox + c / ppm, oy + d / ppm, False, conf)
        for t, a, b, c, d, conf in _lines(img, 6)
    ]


def text_blocks(img: np.ndarray, ppm: float) -> list[tuple[int, int, int, int, bool]]:
    """Boxes (x0, y0, x1, y1, vertical) of text in a view after lines are removed: ink that is neither a long
    stroke nor a large shape, grouped by closing small gaps, and called vertical when much taller than wide."""
    mask = ink(img).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    big = int(7 * ppm)
    keep = np.zeros(n, bool)
    keep[1:] = (stats[1:, cv2.CC_STAT_WIDTH] < big) & (stats[1:, cv2.CC_STAT_HEIGHT] < big)
    k = max(3, int(1.1 * ppm))
    grown = cv2.dilate(keep[lab].astype(np.uint8), np.ones((k, k), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(grown, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _area = stats[i]
        if max(w, h) < 2.0 * ppm or min(w, h) < 1.2 * ppm:
            continue  # an arrowhead or a speck, not text
        out.append((x, y, x + w, y + h, h > 1.4 * w))
    return out


def read_view(page: Page, box) -> list[Item]:
    """Two passes: Tesseract's sparse-text mode over the whole view (as is and turned 90 degrees), then every text
    block the sparse pass did not read confidently is cut out and read on its own as one line. Sparse mode is fast
    and good next to straight dimension lines; it loses text among circles, which the second pass recovers."""
    img, ox, oy = _crop(page, box, 3.0)
    ppm = page.px_per_mm
    img = remove_lines(img, ppm, 5.0)
    horiz = [
        Item(t, ox + a / ppm, oy + b / ppm, ox + c / ppm, oy + d / ppm, False, conf)
        for t, a, b, c, d, conf in _words(img, 0.30)
    ]
    rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    H0 = img.shape[0]
    vert = []
    for t, a, b, c, d, conf in _words(rot, 0.50):
        x0, y0, x1, y1 = b, H0 - c, d, H0 - a  # rotated clockwise: (x, y) here is (y, H0 - x) in the original
        # a vertical reading counts only if it is taller than wide and has a digit (a "±" read sideways is "I+")
        if y1 - y0 > x1 - x0 and any(ch.isdigit() for ch in t):
            vert.append(Item(t, ox + x0 / ppm, oy + y0 / ppm, ox + x1 / ppm, oy + y1 / ppm, True, conf))
    keep_h = [h for h in horiz if not any(_overlap(h, v) > 0.3 and v.conf >= h.conf for v in vert)]
    keep_v = [v for v in vert if not any(_overlap(v, h) > 0.3 and h.conf > v.conf for h in keep_h)]
    items = keep_h + keep_v
    for x0, y0, x1, y1, vertical in text_blocks(img, ppm):
        blk = Item("", ox + x0 / ppm, oy + y0 / ppm, ox + x1 / ppm, oy + y1 / ppm, vertical)
        if any(_overlap(blk, i) > 0.3 and i.conf >= 0.6 for i in items):
            continue
        crop = img[y0:y1, x0:x1]
        text, conf = _ocr_line(cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE) if vertical else crop)
        if text:
            items = [i for i in items if _overlap(blk, i) <= 0.3]
            blk.text, blk.conf = text, conf
            items.append(blk)
    return items


def _overlap(a: Item, b: Item) -> float:
    ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    small = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0)) or 1e-9
    return ix * iy / small


def read_scan(page: Page, regions: dict[str, list]) -> list[Item]:
    items: list[Item] = []
    for kind in TABLES:
        for box in regions.get(kind, []):
            items += read_table(page, box, kind)
    for box in regions.get("notes", []):
        items += read_block(page, box)
    for box in regions.get("view", []):
        items += read_view(page, box)
    return items
