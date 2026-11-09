"""Train the region detector on the development layouts only.

python scripts/train_regions.py loo     # leave one development layout out at a time: the dev estimate
python scripts/train_regions.py final   # train on all development layouts, write models/regions.pt
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np
import torch
from torch import nn

from dia.perceive.page import load
from dia.perceive.regions import CLASSES, UNet, masks_from_boxes, prepare
from dia.settings import ROOT
from dia.settings import load as settings

CACHE = ROOT / "var" / "regions_cache.npz"


def dataset(split: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    s = settings()
    cache = CACHE.with_name(f"regions_{split}.npz")
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        return z["x"], z["y"], list(z["layout"])
    xs, ys, lays = [], [], []
    for f in sorted((ROOT / "data" / split).iterdir()):
        t = json.loads((ROOT / "data" / "truth" / split / f"{f.stem}.json").read_text())
        page = load(f, dpi=100 if f.suffix == ".pdf" else s.render.scan_dpi)
        xs.append(prepare(page.image, s.render.detector_width))
        ys.append(
            masks_from_boxes(
                {k: [tuple(b) for b in v] for k, v in t["regions"].items()}, page.size_mm, s.render.detector_width
            )
        )
        lays.append(t["layout"])
    cache.parent.mkdir(exist_ok=True)
    np.savez_compressed(cache, x=np.stack(xs), y=np.stack(ys), layout=np.array(lays))
    return np.stack(xs), np.stack(ys), lays


def augment(x: torch.Tensor, y: torch.Tensor, g: torch.Generator) -> tuple[torch.Tensor, torch.Tensor]:
    """Shift by up to 6% of the page and vary contrast; the sheet's structure stays where ISO puts it."""
    _, _, h, w = x.shape
    dy = int(torch.randint(-h // 16, h // 16 + 1, (1,), generator=g))
    dx = int(torch.randint(-w // 16, w // 16 + 1, (1,), generator=g))
    x = torch.roll(x, (dy, dx), (2, 3))
    y = torch.roll(y, (dy, dx), (1, 2))
    gain = 0.85 + 0.3 * torch.rand(x.shape[0], 1, 1, 1, generator=g)
    return (1 - (1 - x) * gain).clamp(0, 1), y


def train(x: np.ndarray, y: np.ndarray, seed: int = 0) -> UNet:
    s = settings().regions
    torch.manual_seed(seed)
    g = torch.Generator().manual_seed(seed)
    net = UNet()
    counts = np.bincount(y.ravel(), minlength=len(CLASSES)).astype(np.float32)
    weight = torch.tensor((counts.sum() / (counts + 1)) ** 0.5)
    weight = weight / weight.mean()
    loss_fn = nn.CrossEntropyLoss(weight=weight)
    opt = torch.optim.AdamW(net.parameters(), lr=s.learning_rate, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, s.epochs)
    X, Y = torch.from_numpy(x), torch.from_numpy(y)
    for _ in range(s.epochs):
        net.train()
        perm = torch.randperm(len(X), generator=g)
        for i in range(0, len(X), s.batch):
            idx = perm[i : i + s.batch]
            xb, yb = augment(X[idx], Y[idx], g)
            opt.zero_grad()
            loss = loss_fn(net(xb), yb)
            loss.backward()
            opt.step()
        sched.step()
    net.eval()
    return net


@torch.no_grad()
def class_iou(net: UNet, x: np.ndarray, y: np.ndarray) -> dict[str, float]:
    pred = torch.cat([net(torch.from_numpy(x[i : i + 16])).argmax(1) for i in range(0, len(x), 16)]).numpy()
    out = {}
    for ci, cls in enumerate(CLASSES[1:], start=1):
        inter = np.logical_and(pred == ci, y == ci).sum()
        union = np.logical_or(pred == ci, y == ci).sum()
        out[cls] = round(float(inter / union), 3) if union else float("nan")
    return out


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "final"
    x, y, lays = dataset("dev")
    if mode == "loo":
        res = {}
        for lay in sorted(set(lays)):
            tr = np.array([lo != lay for lo in lays])
            t = time.time()
            net = train(x[tr], y[tr])
            res[lay] = class_iou(net, x[~tr], y[~tr])
            print(lay, res[lay], f"{time.time() - t:.0f}s", flush=True)
        out = ROOT / "reports" / "regions_dev_loo.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(res, indent=1))
        return
    net = train(x, y)
    (ROOT / "models").mkdir(exist_ok=True)
    torch.save(net.state_dict(), ROOT / "models" / "regions.pt")
    print("models/regions.pt", class_iou(net, x, y))


if __name__ == "__main__":
    main()
