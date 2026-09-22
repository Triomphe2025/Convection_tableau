"""Modèles de données communs pour le pipeline CAD (vectoriel et scan)."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class EntityKind(str, Enum):
    LINE = "LINE"
    POLYLINE = "POLYLINE"
    SPLINE = "SPLINE"
    CIRCLE = "CIRCLE"
    ARC = "ARC"
    TEXT = "TEXT"
    RECT = "RECT"


@dataclass
class CadEntity:
    kind: EntityKind
    geometry: dict
    layer: str = "0"
    color: tuple = (0, 0, 0)
    lineweight: float = 0.25
    confidence: float = 1.0
    linetype: str = 'CONTINUOUS'   # 'CONTINUOUS' | 'DASHED' | 'DASHED2' | 'HIDDEN'
    ltscale: float = 1.0           # LTSCALE AutoCAD (1.0 = par défaut)


@dataclass
class CadPage:
    width: float            # en mm
    height: float           # en mm
    source_mode: str        # "vector" | "raster"
    entities: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    page_index: int = 0


@dataclass
class CadDocument:
    source_path: Path
    pages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
