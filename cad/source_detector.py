"""Détecte si une source est un PDF vectoriel, un scan raster ou une image."""
from pathlib import Path


_RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
_VECTOR_DRAWING_THRESHOLD = 5   # nb min de drawings pour qualifier un PDF de vectoriel


def detect_source_mode(path: Path, page_index: int = 0) -> str:
    """Retourne 'vector', 'raster' ou 'unknown'."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in _RASTER_EXTENSIONS:
        return 'raster'

    if suffix == '.pdf':
        try:
            import fitz
            doc = fitz.open(str(path))
            if page_index >= len(doc):
                doc.close()
                return 'raster'
            page = doc[page_index]
            drawings = page.get_drawings()
            if len(drawings) >= _VECTOR_DRAWING_THRESHOLD:
                doc.close()
                return 'vector'
            # PDF sans drawings mais avec texte positionné → vectoriel simple
            blocks = page.get_text('dict').get('blocks', [])
            doc.close()    # fermeture après toute lecture — évite l'accès à page fermée
            if len(blocks) >= 3:
                return 'vector'
            return 'raster'
        except Exception:
            return 'unknown'

    return 'unknown'


def count_pages(path: Path) -> int:
    """Retourne le nombre de pages d'un PDF (1 pour les images)."""
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        try:
            import fitz
            doc = fitz.open(str(path))
            n = len(doc)
            doc.close()
            return n
        except Exception:
            return 0
    return 1
