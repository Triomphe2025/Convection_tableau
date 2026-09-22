Agent d'implémentation des blocs AutoCAD réutilisables : détecte les tableaux de légende dans un PDF, extrait les définitions de blocs et les crée dans le DXF via ezdxf.

Tu travailles exclusivement dans le module cad/ sans modifier le pipeline OCR existant.

## Règle absolue
Ne jamais modifier converter.py, ocr_processor.py, generer_classeur.py.
Seuls cad/ et interface.py (page dessins) sont modifiables.

## Étape 1 — Lire le code actuel
Lire cad/vector_pdf_extractor.py, cad/dxf_writer.py, cad/service.py pour comprendre l'état.

## Étape 2 — Corriger l'orientation des annotations

Dans cad/vector_pdf_extractor.py, section extraction textes :
```python
import math
direction = span.get('dir', (1.0, 0.0))
# PDF a Y vers le bas, DXF a Y vers le haut — inverser le signe de sin
angle_dxf = math.degrees(math.atan2(-direction[1], direction[0]))
```
Remplacer 'angle': 0.0 par 'angle': angle_dxf.

## Étape 3 — Améliorer l'extraction des calques PDF

Dans cad/vector_pdf_extractor.py, construire la map des calques OCG au début de extract_vector_pdf() :
```python
# Map xref OCG -> nom de calque AutoCAD
ocg_names = {}
try:
    for cfg in pdf.layer_ui_configs():
        ocg_names[cfg.get('number', -1)] = cfg.get('text', '0')
except Exception:
    pass
```
Puis utiliser ce mapping pour enrichir le layer name des drawings.

## Étape 4 — Créer cad/block_builder.py

Ce module :
1. Détecte les pages de type "tableau de légende" dans le PDF
   - Critère : page avec ≥ 3 colonnes de texte alignées et ≥ 5 lignes
2. Extrait les lignes du tableau : {code, libellé, description}
3. Crée des définitions de BLOCK dans le DXF ezdxf

Structure d'un bloc créé :
- Rectangle de 10×10 mm (emprise du symbole)
- Texte du code en centre
- Attribut ATT_LIBELLE (ezdxf ATTDEF) pour la description dynamique

```python
def detect_legend_pages(pdf) -> list[int]:
def extract_table_rows(page) -> list[dict]:
def create_dxf_blocks(dxf_doc, rows: list[dict], on_log=None) -> int:
```

## Étape 5 — Intégrer dans cad/service.py

Après l'extraction vectorielle, appeler block_builder si des pages de légende sont détectées :
```python
from .block_builder import detect_legend_pages, extract_table_rows, create_dxf_blocks

legend_pages = detect_legend_pages(pdf)
if legend_pages:
    all_rows = []
    for idx in legend_pages:
        all_rows.extend(extract_table_rows(pdf[idx]))
    n_blocks = create_dxf_blocks(dxf_doc, all_rows, on_log=_log)
    _log(f"✓ {n_blocks} blocs AutoCAD créés depuis {len(legend_pages)} page(s) de légende")
```

## Étape 6 — Tests

```python
# tests/test_cad_blocs.py
def test_extract_table_rows_returns_dicts()
def test_create_dxf_blocks_inserts_block_defs()
def test_block_has_name_and_attrib()
def test_angle_extraction_from_span_dir()
```
