# Règle 03 — Pipeline OCR et extraction de données

## Pipeline complet (7 étapes)

```
Source (Word/PDF/images/JSONL)
  ↓
1. Extraction images  → recuperer_image.py / pdf_extractor.py
  ↓
2. Prétraitement      → ocr_processor.py (OpenCV : binarisation, redressement)
  ↓
3. OCR               → Tesseract / Claude Vision / Ollama / Docling / Agent / Hybrid
  ↓
4. Détection colonnes → _col_boundaries() sur positions pixel des mots-clés en-tête
  ↓
5. Affectation cellules → bord gauche du mot (jamais le centre)
  ↓
6. Corrections OCR   → data_dictionary.py (whitelist de valeurs valides)
  ↓
7. Génération Excel  → generer_classeur.py (feuille "Borniers" + "tableaux word")
```

## Règles critiques OCR

### Frontières de colonnes
`_col_boundaries()` utilise les positions pixel (`cx`) des mots-clés de l'en-tête.
**Pas de clustering sur les données.** Plus robuste sur les scans déformés.

L'affectation utilise le **bord gauche** (`x`), pas le centre (`cx`) :
un mot large commençant dans SIGNAL ne doit pas aller dans JARRETIERES
parce que son centre dépasse la frontière.

### Indice OCR — confusion O/0
La confusion `O` ↔ `0` est normalisée automatiquement dans `_extract_meta()` :
```python
meta['INDICE'] = meta.get('INDICE', '0').replace('O', '0')
```

### Fidélité Claude Vision
`_fill_worksheet()` **ne doit PAS appliquer** `data_dictionary.correct()` si
`detection_method` est `claude-vision` ou `log-replay`.
Cela évite que "TC IDPO1" devienne "TC IDPO8".

```python
if row.get('detection_method') not in ('claude-vision', 'log-replay'):
    value = get_dictionary().correct(col_name, value)
```

### split_flags
Les cellules issues d'un split sont protégées contre la ré-analyse OCR.
Ne jamais re-OCR une cellule si `split_flags` est positionné.

## Modes OCR — isolation obligatoire

Chaque mode OCR (tesseract/claude/docling/log-replay) applique exactement
ses propres transformations. Aucune fuite entre modes.

Utiliser `/isoler-modes-ocr` pour vérifier l'isolation.

## Filtrage des borniers ratés

`MIN_DATA_ROWS` (config.py) : seuil minimal de lignes pour valider un bornier.
Un bornier avec moins de lignes que ce seuil est exclu du classeur Excel.

## data_dictionary.json

La structure est une **whitelist de valeurs valides** par colonne, pas des paires de corrections :
```json
{
  "BORNE": ["01", "01A", "02", ...],
  "COULEUR": ["BLANC", "ROUGE", ...],
  "SIGNAL": ["TC IDPO1", ...]
}
```
Utiliser `/corriger-ocr` pour ajouter des valeurs. Utiliser `/alimenter-dictionnaire`
pour charger depuis un Excel corrigé manuellement.
