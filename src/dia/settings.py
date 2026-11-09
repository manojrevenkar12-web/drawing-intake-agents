"""Typed access to config/dia.toml. Every threshold lives there."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class World(_S):
    seed: int
    dev_layouts: list[str]
    heldout_layouts: list[str]
    drawings_per_layout_dev: int = Field(ge=1)
    drawings_per_layout_heldout: int = Field(ge=1)
    scan_share: float = Field(ge=0, le=1)
    revision_share: float = Field(ge=0, le=1)


class Render(_S):
    scan_dpi: int = Field(ge=100, le=600)
    detector_width: int = Field(ge=128, le=1024)


class Regions(_S):
    epochs: int = Field(ge=1)
    learning_rate: float = Field(gt=0)
    batch: int = Field(ge=1)
    min_area_fraction: float = Field(ge=0, lt=1)


class Fields(_S):
    max_value_distance_mm: float = Field(gt=0)


class Dimensions(_S):
    max_join_gap_mm: float = Field(gt=0)


class Routing(_S):
    max_auto_error: float = Field(gt=0, lt=1)
    min_confidence: float = Field(ge=0, le=1)


class Review(_S):
    minutes_per_drawing_manual: float = Field(gt=0)
    minutes_per_field_review: float = Field(gt=0)
    minutes_per_drawing_check: float = Field(ge=0)


class Notes(_S):
    llm_model: str
    llm_max_tokens: int = Field(ge=100, le=4000)
    llm_timeout_s: float = Field(gt=0)


class Erp(_S):
    plant: str
    material_type: str


class Settings(_S):
    world: World
    render: Render
    regions: Regions
    fields: Fields
    dimensions: Dimensions
    routing: Routing
    review: Review
    notes: Notes
    erp: Erp


@lru_cache
def load(path: str | None = None) -> Settings:
    p = Path(path) if path else ROOT / "config" / "dia.toml"
    return Settings.model_validate(tomllib.loads(p.read_text()))
