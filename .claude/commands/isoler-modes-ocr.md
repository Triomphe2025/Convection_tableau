# /isoler-modes-ocr

## Objectif
Vérifier que chaque mode OCR (`tesseract`, `claude`, `docling`, `log-replay`) applique exactement les bonnes transformations — et aucune autre.

## Contexte — pourquoi ce skill existe
En v1.x, `_fill_worksheet()` dans `ocr_processor.py` appliquait `data_dictionary.correct()` (correction fuzzy Levenshtein, seuil 0.82) à **toutes** les cellules, y compris celles issues de Claude Vision.  
Résultat : "TC IDPO1" (exact Claude) → "TC IDPO8" (dans l'Excel). Perte de fidélité invisible.

**Règle d'or :**
- `tesseract` → corrections dictionnaire activées, re-OCR par colonne, whitelist Tesseract
- `claude` → **zéro correction post-API**, insertion purement positionnelle
- `docling` → **zéro correction post-API**
- `log-replay` → **zéro correction**, données issues du champ `rows_data` du log

## Ce que fait ce skill

### Étape 1 — Vérifier `_fill_worksheet()` dans `ocr_processor.py`
- Chercher la ligne `_skip_dict = result.get('detection_method') in ('claude-vision', 'log-replay')`
- Vérifier que `dictionary.correct()` n'est appelé que quand `not _skip_dict`
- Si absent ou mal positionné : alerter et indiquer la ligne exacte à corriger

### Étape 2 — Vérifier `ClaudeVisionExtractor.extract()` dans `claude_ocr.py`
- Confirmer que `_parse_pipe_response()` est la seule fonction de parsing appelée
- Confirmer qu'aucun appel à `_apply_post_corrections()`, `_fix_borne_in_signal()` ou `data_dictionary` n'existe dans le chemin Claude

### Étape 3 — Vérifier `LogReplayer.replay_all()` dans `claude_ocr.py`
- Confirmer la priorité : `rows_data` d'abord, `raw` re-parsé en fallback
- Confirmer que `detection_method = 'log-replay'` est bien positionné sur chaque résultat

### Étape 4 — Vérifier `BornierTableExtractor` dans `ocr_processor.py`
- Confirmer que `detection_method` dans le résultat est différent de `'claude-vision'` et `'log-replay'`
- Confirmer que `data_dictionary.correct()` est bien appliqué pour ce mode

### Rapport final
```
MODE            CORRECTIONS DICT   RE-OCR COLONNE   SOURCE DONNÉES
tesseract       ✅ activées        ✅ activé         Tesseract local
claude          ✅ désactivées     ✅ désactivé       API Anthropic
docling         ✅ désactivées     ✅ désactivé       Docling IBM
log-replay      ✅ désactivées     ✅ désactivé       rows_data du log
```
Toute divergence est signalée avec fichier + numéro de ligne.
