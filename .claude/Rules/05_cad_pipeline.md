# Règle 05 — Pipeline CAD PDF→DXF AutoCAD

## Architecture du module cad/

```
cad/
  __init__.py             → exports publics (convert_to_dxf, detect_source_mode, ...)
  models.py               → CadDocument, CadPage, CadEntity, EntityKind
  source_detector.py      → détection vectoriel/raster/image
  vector_pdf_extractor.py → PyMuPDF → géométrie (LIGNES, RECTS, COURBES, TEXTES)
  dxf_writer.py           → ezdxf → fichier .dxf avec offset par folio
  block_builder.py        → tableaux légende → BLOCK definitions AutoCAD
  service.py              → façade : convert_to_dxf() appelé par interface.py
```

**Règle absolue** : le module `cad/` est entièrement isolé. Aucun autre module du
projet ne connaît ezdxf. Aucune référence à `cad/` depuis converter.py ou ocr_processor.py.

## Formules de coordonnées — VALIDÉES VISUELLEMENT

`page.get_drawings()` retourne les coordonnées dans l'espace PHYSIQUE non-rotaté.
`page.rect` donne les dimensions VISUELLES correctes (après rotation).
`page.transformation_matrix` n'applique PAS la rotation — éviter pour les calculs.

```python
# Formules selon page.rotation
if rot == 270:    # VALIDÉ sur 717-6324-LL02.pdf ✓
    x_dxf, y_dxf = raw_y * PT, raw_x * PT

elif rot == 0:    # Standard
    x_dxf, y_dxf = raw_x * PT, (mh - raw_y) * PT

elif rot == 90:   # À valider sur PDF réel
    x_dxf, y_dxf = (mh - raw_y) * PT, (mw - raw_x) * PT

elif rot == 180:  # À valider sur PDF réel
    x_dxf, y_dxf = (mw - raw_x) * PT, (mh - raw_y) * PT
```

Où `PT = 25.4 / 72.0` (conversion points PDF → mm) et
`mw, mh = page.mediabox.width, page.mediabox.height` (dimensions physiques).

## Déduplication obligatoire

AutoCAD génère souvent des entités dupliquées dans le PDF :
```python
# Textes : supprimer si même contenu ET position < 1mm
cad_page.entities = _dedup_texts(cad_page.entities, tol_mm=1.0)

# Lignes : supprimer si mêmes points < 0.2mm
cad_page.entities = _dedup_lines(cad_page.entities, tol_mm=0.2)
```

## Offset folio dans le DXF

Toutes les pages dans le même modelspace, décalées horizontalement :
- Folio 0 : x_offset = 0
- Folio 1 : x_offset = folio0.width + 50mm
- Folio N : x_offset = somme(folios précédents) + N×50mm

## Génération DXF

Paramètres obligatoires :
```python
dxf.header['$INSUNITS'] = 4   # 4 = millimètres
```

Calque "CADRES" : rectangle de bordure de chaque folio.
Calque "TEXTES" : tous les textes extraits du PDF.
Calques d'origine : noms de calques AutoCAD d'origine depuis les OCGs du PDF.

## Blocs AutoCAD (block_builder.py)

1. Détecter les pages de légende (`detect_legend_pages()`)
2. Extraire les lignes de tableau (`extract_table_rows()`)
3. Créer les BLOCK definitions (`create_dxf_blocks()`)
4. Chaque bloc : rectangle 10×10mm + texte code + attribut ATT_DESC dynamique

## Processus de débogage CAD

```python
# 1. Rendre la page PDF comme image de référence
pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))

# 2. Extraire et tracer les entités en matplotlib (fond sombre, lignes blanches)
import matplotlib.pyplot as plt
fig, (ax1, ax2) = plt.subplots(1, 2)
# ax1: entités DXF reconstruites
# ax2: image PDF de référence

# 3. Comparer visuellement les 4 formules de rotation si besoin
```

## Technologies requises

| Bibliothèque | Version min | Usage |
|-------------|-------------|-------|
| pymupdf | 1.24.0 | Extraction géométrie vectorielle |
| ezdxf | 1.0.0 | Génération fichiers DXF |
| matplotlib | 3.0.0 | Débogage visuel (non embarqué dans le .exe) |
