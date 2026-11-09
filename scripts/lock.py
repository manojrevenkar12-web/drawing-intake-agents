"""Pin the reader before the held-out run: hashes of everything that decides what it reads.

python scripts/lock.py "Step 1 (date): reason"   # appends a commented step and the current hashes
"""

from __future__ import annotations

import hashlib
import sys

from dia.settings import ROOT

PINNED = [
    "data/heldout_index.json",
    "src/dia/world/layouts.py",
    "src/dia/world/parts.py",
    "src/dia/world/render.py",
    "src/dia/perceive/page.py",
    "src/dia/perceive/ocr.py",
    "src/dia/perceive/regions.py",
    "src/dia/perceive/dimensions.py",
    "src/dia/perceive/fields.py",
    "src/dia/perceive/reader.py",
    "src/dia/engineering/tolerance.py",
    "src/dia/engineering/diff.py",
    "src/dia/engineering/feasibility.py",
    "src/dia/engineering/notes.py",
    "src/dia/standards/iso286.py",
    "src/dia/standards/iso2768.py",
    "models/regions.pt",
    "config/dia.toml",
    "config/plant.yaml",
]


def main() -> None:
    note = sys.argv[1] if len(sys.argv) > 1 else "pinned"
    lock = ROOT / "config" / "heldout.lock"
    lines = [f"# {note}"]
    for p in PINNED:
        lines.append(f"{hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}  {p}")
    with lock.open("a") as f:
        f.write("\n".join(lines) + "\n")
    print(lock.read_text())


if __name__ == "__main__":
    main()
