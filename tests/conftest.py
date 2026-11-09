import random
from pathlib import Path

import pytest

from dia.world.dataset import generate


@pytest.fixture(scope="session")
def sample(tmp_path_factory) -> Path:
    """A few vector drawings from two development layouts, one with a previous revision, plus one scan."""
    root = tmp_path_factory.mktemp("data")
    generate("t", ["acme_rail", "boltwerk"], 2, 7, root=root, scan_share=0.0, revision_share=1.0)
    generate("s", ["sitec"], 1, 3, root=root, scan_share=1.0, revision_share=0.0)
    return root


@pytest.fixture
def rng():
    return random.Random(1)
