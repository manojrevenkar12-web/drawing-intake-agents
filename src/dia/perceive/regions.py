"""Find the parts of a drawing sheet: title block, parts list, revision table, notes and the views.

A small U-Net segments a downscaled page into these classes; connected components become boxes in sheet
millimetres. It is trained only on the development customers' layouts (scripts/train_regions.py) and judged on
layouts it has never seen, against a baseline that assumes every customer's sheet looks like the average one."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn

CLASSES = ("background", "title_block", "parts_list", "revision_table", "notes", "view")
Box = tuple[float, float, float, float]


def _block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
    )


class UNet(nn.Module):
    def __init__(self, widths: tuple[int, ...] = (12, 24, 48, 64), n_classes: int = len(CLASSES)):
        super().__init__()
        self.down = nn.ModuleList()
        cin = 1
        for w in widths:
            self.down.append(_block(cin, w))
            cin = w
        self.up = nn.ModuleList()
        self.merge = nn.ModuleList()
        for w_hi, w_lo in zip(widths[::-1][:-1], widths[::-1][1:], strict=True):
            self.up.append(nn.ConvTranspose2d(w_hi, w_lo, 2, stride=2))
            self.merge.append(_block(w_lo * 2, w_lo))
        self.head = nn.Conv2d(widths[0], n_classes, 1)
        self.pool = nn.MaxPool2d(2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skips = []
        for i, blk in enumerate(self.down):
            x = blk(x)
            if i < len(self.down) - 1:
                skips.append(x)
                x = self.pool(x)
        for up, merge in zip(self.up, self.merge, strict=True):
            x = up(x)
            s = skips.pop()
            x = merge(torch.cat([x[..., : s.shape[2], : s.shape[3]], s], 1))
        return self.head(x)


def input_size(width: int) -> tuple[int, int]:
    """(height, width) of the detector input; sheets are landscape ISO A-series (aspect sqrt 2), height a multiple
    of 8 for the three poolings."""
    h = round(width / 2**0.5 / 8) * 8
    return h, width


def prepare(image: np.ndarray, width: int) -> np.ndarray:
    h, w = input_size(width)
    small = cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA)
    # dilate the ink so thin lines and small text survive the downscale
    small = 255 - cv2.dilate(255 - small, np.ones((2, 2), np.uint8))
    return (small.astype(np.float32) / 255.0)[None]


def masks_from_boxes(regions: dict[str, list[Box]], size_mm: tuple[float, float], width: int) -> np.ndarray:
    h, w = input_size(width)
    sx, sy = w / size_mm[0], h / size_mm[1]
    m = np.zeros((h, w), np.int64)
    for cls in ("view", "notes", "revision_table", "parts_list", "title_block"):  # later classes win
        for x0, y0, x1, y1 in regions.get(cls, []):
            m[int(y0 * sy) : int(np.ceil(y1 * sy)), int(x0 * sx) : int(np.ceil(x1 * sx))] = CLASSES.index(cls)
    return m


class Detector:
    def __init__(self, weights: str | Path | None = None, width: int = 256, min_area_fraction: float = 0.002):
        self.width, self.min_area = width, min_area_fraction
        self.net = UNet()
        if weights and Path(weights).exists():
            self.net.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
        self.net.eval()

    @torch.no_grad()
    def probabilities(self, image: np.ndarray) -> np.ndarray:
        x = torch.from_numpy(prepare(image, self.width))[None]
        return torch.softmax(self.net(x), 1)[0].numpy()

    def detect(self, image: np.ndarray, size_mm: tuple[float, float]) -> dict[str, list[Box]]:
        return boxes_from_labels(self.probabilities(image).argmax(0), size_mm, self.min_area)


def boxes_from_labels(labels: np.ndarray, size_mm: tuple[float, float], min_area: float) -> dict[str, list[Box]]:
    h, w = labels.shape
    sx, sy = size_mm[0] / w, size_mm[1] / h
    out: dict[str, list[Box]] = {}
    for ci, cls in enumerate(CLASSES[1:], start=1):
        mask = (labels == ci).astype(np.uint8)
        if cls == "view":
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        boxes = []
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if area < min_area * h * w:
                continue
            boxes.append((round(x * sx, 1), round(y * sy, 1), round((x + bw) * sx, 1), round((y + bh) * sy, 1)))
        if cls != "view" and len(boxes) > 1:  # one of each table per sheet: keep the largest
            boxes = [max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))]
        if boxes:
            out[cls] = boxes
    return out


class Template:
    """Baseline: every customer's sheet is assumed to look like the average development sheet (boxes as fractions
    of the sheet, median over the development layouts)."""

    def __init__(self, fractions: dict[str, list[Box]]):
        self.fractions = fractions

    @classmethod
    def fit(cls, examples: list[tuple[dict[str, list[Box]], tuple[float, float]]]) -> Template:
        acc: dict[str, list[np.ndarray]] = {}
        for regions, (W, H) in examples:
            for k, boxes in regions.items():
                if k == "view":
                    xs0, ys0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
                    xs1, ys1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
                    boxes = [(xs0, ys0, xs1, ys1)]
                for b in boxes:
                    acc.setdefault(k, []).append(np.array(b) / [W, H, W, H])
        return cls({k: [tuple(np.median(np.stack(v), 0).round(4))] for k, v in acc.items()})

    def detect(self, image: np.ndarray, size_mm: tuple[float, float]) -> dict[str, list[Box]]:
        W, H = size_mm
        return {k: [(b[0] * W, b[1] * H, b[2] * W, b[3] * H) for b in v] for k, v in self.fractions.items()}


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0
