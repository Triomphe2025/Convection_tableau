Agent d'implémentation du pipeline CAD vectoriel : extrait la géométrie de PDFs vectoriels (PyMuPDF) et génère des fichiers DXF ouvrable dans AutoCAD (ezdxf), sans modifier le pipeline OCR existant.

Tu es un ingénieur CAD/Python senior. Ta mission : implémenter le module cad/ isolé, connecter la page "Transformation dessins" de l'interface existante, sans toucher au pipeline tableaux.

---

## Règle absolue

Ne jamais modifier converter.py, ocr_processor.py, generer_classeur.py, data_dictionary.py.
Seuls les fichiers créés dans cad/ et les modifications minimales de interface.py, config.py, requirements.txt sont autorisés.

---

## Étape 1 — Vérification de l'environnement

```powershell
env\Scripts\python.exe -c "import fitz; print('PyMuPDF OK:', fitz.__version__)"
env\Scripts\python.exe -c "import ezdxf; print('ezdxf OK:', ezdxf.__version__)"
```

Si ezdxf manque :
```powershell
env\Scripts\pip.exe install ezdxf
```

---

## Étape 2 — Créer la structure cad/

```
cad/
  __init__.py
  models.py            ← CadDocument, CadPage, CadEntity
  source_detector.py   ← détection vectoriel/scan/image
  vector_pdf_extractor.py  ← extraction géométrie via PyMuPDF
  dxf_writer.py        ← génération DXF via ezdxf
  service.py           ← façade appelée par interface.py
```

---

## Étape 3 — Implémenter cad/models.py

Dataclasses légères :

```python
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
    geometry: dict          # coords brutes (x1,y1,x2,y2 ou points ou center+radius)
    layer: str = "0"
    color: tuple = (0, 0, 0)
    lineweight: float = 0.25
    confidence: float = 1.0

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
```

---

## Étape 4 — Implémenter cad/source_detector.py

```python
from pathlib import Path
import fitz

def detect_source_mode(path: Path, page_index: int = 0) -> str:
    """Retourne 'vector', 'raster' ou 'image'."""
    suffix = path.suffix.lower()
    if suffix in ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'):
        return 'raster'
    if suffix == '.pdf':
        doc = fitz.open(str(path))
        if page_index >= len(doc):
            return 'raster'
        page = doc[page_index]
        drawings = page.get_drawings()
        texts = page.get_text("dict").get("blocks", [])
        # PDF vectoriel = présence de drawings OU texte positionné
        if len(drawings) > 10:
            return 'vector'
        if len(texts) > 5:
            return 'vector'
        return 'raster'
    return 'unknown'
```

---

## Étape 5 — Implémenter cad/vector_pdf_extractor.py

Points clés :
- Utiliser `page.get_drawings()` (pas get_cdrawings)
- Inversion axe Y : `y_dxf = page_height_mm - y_pdf_mm`
- Conversion points PDF → mm : `mm = pt * 25.4 / 72`
- Conserver le nom de calque si disponible

```python
import fitz
from pathlib import Path
from .models import CadDocument, CadPage, CadEntity, EntityKind

PT_TO_MM = 25.4 / 72.0

def _pt(v): return v * PT_TO_MM

def extract_vector_pdf(path: Path, page_indices: list = None) -> CadDocument:
    doc_cad = CadDocument(source_path=path)
    pdf = fitz.open(str(path))
    if page_indices is None:
        page_indices = list(range(len(pdf)))

    for idx in page_indices:
        if idx >= len(pdf):
            continue
        page = pdf[idx]
        pw_mm = _pt(page.rect.width)
        ph_mm = _pt(page.rect.height)

        cad_page = CadPage(
            width=pw_mm, height=ph_mm,
            source_mode='vector', page_index=idx,
        )

        # Extraction des drawings
        for d in page.get_drawings():
            layer = d.get('layer') or '0'
            col = d.get('color') or (0, 0, 0)
            if isinstance(col, (int, float)):
                col = (col, col, col)
            col_rgb = tuple(int(c * 255) for c in col[:3]) if col else (0, 0, 0)

            for item in d.get('items', []):
                kind_code = item[0]

                if kind_code == 'l':          # ligne simple
                    p1, p2 = item[1], item[2]
                    cad_page.entities.append(CadEntity(
                        kind=EntityKind.LINE,
                        geometry={
                            'x1': _pt(p1.x), 'y1': ph_mm - _pt(p1.y),
                            'x2': _pt(p2.x), 'y2': ph_mm - _pt(p2.y),
                        },
                        layer=layer, color=col_rgb,
                    ))

                elif kind_code == 're':       # rectangle
                    r = item[1]
                    pts = [
                        (_pt(r.x0), ph_mm - _pt(r.y0)),
                        (_pt(r.x1), ph_mm - _pt(r.y0)),
                        (_pt(r.x1), ph_mm - _pt(r.y1)),
                        (_pt(r.x0), ph_mm - _pt(r.y1)),
                    ]
                    cad_page.entities.append(CadEntity(
                        kind=EntityKind.RECT,
                        geometry={'points': pts},
                        layer=layer, color=col_rgb,
                    ))

                elif kind_code == 'c':        # courbe Bézier → polyligne approx
                    points = [(_pt(p.x), ph_mm - _pt(p.y)) for p in item[1:]]
                    if len(points) >= 2:
                        cad_page.entities.append(CadEntity(
                            kind=EntityKind.POLYLINE,
                            geometry={'points': points},
                            layer=layer, color=col_rgb,
                        ))

        # Extraction des textes
        blocks = page.get_text('dict').get('blocks', [])
        for block in blocks:
            if block.get('type') != 0:
                continue
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    txt = span.get('text', '').strip()
                    if not txt:
                        continue
                    origin = span.get('origin', (0, 0))
                    cad_page.entities.append(CadEntity(
                        kind=EntityKind.TEXT,
                        geometry={
                            'x': _pt(origin[0]),
                            'y': ph_mm - _pt(origin[1]),
                            'text': txt,
                            'size': _pt(span.get('size', 10)),
                            'angle': 0.0,
                        },
                        layer='TEXTES',
                    ))

        doc_cad.pages.append(cad_page)
    pdf.close()
    return doc_cad
```

---

## Étape 6 — Implémenter cad/dxf_writer.py

```python
import ezdxf
from pathlib import Path
from .models import CadDocument, EntityKind

def write_dxf(doc_cad: CadDocument, output_path: Path, version: str = "R2010"):
    """Génère un fichier DXF depuis un CadDocument. Chaque page = un layout."""
    dxf = ezdxf.new(version)
    dxf.header['$INSUNITS'] = 4   # mm

    for i, page in enumerate(doc_cad.pages):
        layout_name = f"Folio_{page.page_index + 1}"
        if i == 0:
            msp = dxf.modelspace()
        else:
            try:
                msp = dxf.new_layout(layout_name)
            except Exception:
                msp = dxf.modelspace()

        _ensure_layers(dxf, page)

        for ent in page.entities:
            try:
                _write_entity(msp, ent)
            except Exception:
                pass

    dxf.saveas(str(output_path))
    return output_path

def _ensure_layers(dxf, page):
    for ent in page.entities:
        name = ent.layer or '0'
        if name not in dxf.layers:
            layer = dxf.layers.new(name)
            r, g, b = ent.color[:3] if ent.color else (0, 0, 0)
            # ezdxf utilise ACI color — 7 = blanc/noir
            layer.color = 7

def _write_entity(msp, ent):
    if ent.kind == EntityKind.LINE:
        g = ent.geometry
        msp.add_line(
            (g['x1'], g['y1'], 0),
            (g['x2'], g['y2'], 0),
            dxfattribs={'layer': ent.layer},
        )

    elif ent.kind in (EntityKind.POLYLINE, EntityKind.RECT):
        pts = ent.geometry.get('points', [])
        if len(pts) >= 2:
            pts3d = [(x, y, 0) for x, y in pts]
            if ent.kind == EntityKind.RECT:
                pts3d.append(pts3d[0])   # fermer le rectangle
            msp.add_lwpolyline(
                [(x, y) for x, y, _ in pts3d],
                dxfattribs={'layer': ent.layer,
                            'closed': ent.kind == EntityKind.RECT},
            )

    elif ent.kind == EntityKind.TEXT:
        g = ent.geometry
        msp.add_text(
            g.get('text', ''),
            dxfattribs={
                'layer': ent.layer,
                'insert': (g['x'], g['y'], 0),
                'height': max(g.get('size', 3.0), 1.0),
            },
        )
```

---

## Étape 7 — Implémenter cad/service.py

```python
from pathlib import Path
from .source_detector import detect_source_mode
from .vector_pdf_extractor import extract_vector_pdf
from .dxf_writer import write_dxf

def convert_to_dxf(
    source_path: Path,
    output_dir: Path,
    page_indices: list = None,
    on_log=None,
    on_progress=None,
) -> Path:
    """
    Convertit un PDF vectoriel ou une image en DXF.
    Retourne le chemin du fichier DXF produit.
    """
    def _log(msg):
        if on_log: on_log(msg)

    def _progress(pct, msg=""):
        if on_progress: on_progress(pct, msg)

    source_path = Path(source_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _log(f"Analyse de la source : {source_path.name}")
    mode = detect_source_mode(source_path, page_index=0)
    _log(f"Mode détecté : {mode}")
    _progress(0.1, "Détection mode…")

    if mode == 'vector':
        _log("Pipeline vectoriel — PyMuPDF")
        _progress(0.2, "Extraction géométrie…")
        doc_cad = extract_vector_pdf(source_path, page_indices)
        n_ent = sum(len(p.entities) for p in doc_cad.pages)
        _log(f"✓ {n_ent} entités extraites sur {len(doc_cad.pages)} page(s)")
        _progress(0.7, f"{n_ent} entités extraites")

    elif mode == 'raster':
        raise NotImplementedError(
            "Le mode scan (raster) sera disponible en Phase 2.\n"
            "Ce PDF/image nécessite OpenCV — non implémenté dans cette version."
        )
    else:
        raise ValueError(f"Source non reconnue : {source_path.suffix}")

    output_path = output_dir / (source_path.stem + ".dxf")
    _log(f"Génération DXF : {output_path.name}")
    _progress(0.85, "Écriture DXF…")

    write_dxf(doc_cad, output_path)
    _log(f"✓ DXF généré : {output_path}")
    _progress(1.0, "Terminé")
    return output_path
```

---

## Étape 8 — Créer cad/__init__.py

```python
from .service import convert_to_dxf
from .source_detector import detect_source_mode
from .models import CadDocument, CadPage, CadEntity, EntityKind
```

---

## Étape 9 — Connecter à interface.py (page dessins)

Dans `_build_page_dessins()`, remplacer le squelette statique par un vrai formulaire d'extraction. Ajouter :
- Champ source (PDF/image)
- Champ dossier de sortie
- Bouton "Analyser & Exporter DXF"
- Journal de progression

Appeler `cad.convert_to_dxf()` dans un thread secondaire via la queue existante.

---

## Étape 10 — Mettre à jour requirements.txt

Ajouter `ezdxf>=1.0.0` si absent.

---

## Étape 11 — Tests

```python
# tests/test_cad_vectoriel.py
def test_source_detector_pdf_vectoriel():
def test_source_detector_image():
def test_extract_vector_pdf_page_count():
def test_entity_count_page3():
def test_y_inversion():
def test_write_dxf_creates_file():
def test_dxf_readable_by_ezdxf():
```

---

## Étape 12 — Mémoriser les leçons

Appeler `/apprendre-interface` en fin de session.
