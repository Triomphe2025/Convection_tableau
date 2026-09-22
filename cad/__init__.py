"""Package CAD — pipeline PDF vectoriel/scan → DXF AutoCAD."""
from .service import convert_to_dxf
from .source_detector import detect_source_mode, count_pages
from .models import CadDocument, CadPage, CadEntity, EntityKind

__all__ = [
    'convert_to_dxf', 'detect_source_mode', 'count_pages',
    'CadDocument', 'CadPage', 'CadEntity', 'EntityKind',
]
