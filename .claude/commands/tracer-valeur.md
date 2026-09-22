# /tracer-valeur

## Objectif
Tracer une valeur précise depuis la réponse brute Claude (ou l'image Tesseract) jusqu'à la cellule Excel finale, pour détecter toute modification non voulue.

## Usage
```
/tracer-valeur TC IDPO1
/tracer-valeur EPL D113T 01A
/tracer-valeur +TCA11-31
```

## Ce que fait ce skill

### Étape 1 — Lire le log Claude
Chercher `$VALEUR` dans `*_claude.jsonl` (champ `raw` et champ `rows_data`).
- Si présent dans `raw` mais **absent** dans `rows_data` → problème de parsing `_parse_pipe_response()`
- Si présent dans `rows_data` mais **différent** dans l'Excel → problème dans `_fill_worksheet()`

### Étape 2 — Vérifier le champ `detection_method`
Dans l'entrée log correspondante, lire `metadata.detection_method` ou le champ du résultat.
- `claude-vision` ou `log-replay` → `_skip_dict` doit être `True` dans `_fill_worksheet()`
- `tesseract` / `header` / `tatr` / etc. → corrections dictionnaire autorisées

### Étape 3 — Chercher dans `data_dictionary.json`
Vérifier si la valeur (ou une variante proche) existe dans le dictionnaire :
```python
from data_dictionary import get_dictionary
d = get_dictionary()
result, changed = d.correct('NOM_COLONNE', '$VALEUR')
print(f"Avant: {repr('$VALEUR')} → Après: {repr(result)} — modifiée: {changed}")
```
Si `changed=True` et `detection_method` est `claude-vision` → bug de fuite de correction.

### Étape 4 — Simuler le chemin complet
```python
# Simuler _fill_worksheet() sur une seule cellule
val = '$VALEUR'
detection_method = 'claude-vision'   # ou 'tesseract'
skip_dict = detection_method in ('claude-vision', 'log-replay')
if not skip_dict:
    val, _ = dictionary.correct('NOM_COLONNE', val)
print(f"Valeur finale : {repr(val)}")
```

### Rapport
```
Valeur recherchée : "TC IDPO1"
Dans raw Claude   : ✅ trouvé ligne 42 — "TC IDPO1 | ... | ..."
Dans rows_data    : ✅ présent — cells[0] = "TC IDPO1"
detection_method  : claude-vision → _skip_dict = True
Correction dict   : ⏭ ignorée (mode protégé)
Valeur finale     : "TC IDPO1" ✅ IDENTIQUE
```
Si une étape montre une divergence, indiquer le fichier + fonction + ligne exacte.
