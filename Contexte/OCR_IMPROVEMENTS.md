# OCR_IMPROVEMENTS.md — Suivi d'amélioration OCR TriosSeconverter

## Mot-clé de reprise : `OCR_AMÉLIORATIONS_V1`

Si la session s'interrompt, relancer avec : **`@Contexte/OCR_IMPROVEMENTS.md`** pour reprendre ici.

---

## Diagnostic (2026-05-07)

### Deux types d'images dans le corpus

| Type | Colonnes réelles | Header détecté ? | Fallback |
|------|-----------------|-----------------|---------|
| **Répartiteur** (bornier_2, _3…) | TENANT / JAR. / ABOUTISSANT / SIGNAL | ❌ Non (mots-clés template absents) | morpho → whitespace → weighted |
| **Bornier standard** (bornier_100…) | BORNE / COULEUR / SIGNAL / JARRETIERES | ✅ Oui | `header` (précis) |

### Problèmes identifiés

1. **Attribution colonne (répartiteur)** : l'en-tête OCR ne correspond jamais aux mots-clés du template (`BORNE`, `COULEUR`, `SIGNAL`, `JARRETIERES`). Conséquence : on tombe toujours en repli morpho/weighted.
   - Morpho fonctionne bien si les lignes verticales sont nettes.
   - Weighted utilise les proportions du template → SIGNAL obtient 59 % de la largeur, raisonnable.
   - **Point faible** : `_detect_col_bounds_morpho()` utilisait un noyau unique (h//5 = 20 %) → ratait les lignes partielles.

2. **Confusions OCR (toutes images)** :
   - `€` → `E` (tres fréquent) : non corrigé
   - `l` (L minuscule) → `1` : non corrigé (sauf `_fix_o0` partiel)
   - `A` ↔ `4` : ambiguë sans vocabulaire ; corrigé uniquement pour mots SIGNAL commençant par `4` + préfixe électrique connu
   - `O` → `0` : déjà géré dans `_clean_cell()`

3. **COULEUR sans dictionnaire** : `data_dictionary.json` n'existait pas → aucune correction floue activée.

---

## Améliorations implementées (session 2026-05-07)

### ✅ 1. `_fix_common_ocr()` — corrections universelles dans `_clean_cell()`
- `€`→`E`, `£`→`E`, `¢`→`C`
- `\xa0`→` ` (espace insécable)
- `l` (L minuscule) → `1` entre/après chiffres

### ✅ 2. `data_dictionary.json` pré-rempli
- Vocabulaire COULEUR initial : ROUGE, VERT, BLEU, NOIR, BLANC, JAUNE, ORANGE, VIOLET, MARRON, GRIS, ROSE, BRUN, BEIGE, CYAN
- La correction floue `DataDictionary.correct()` est maintenant opérationnelle pour COULEUR

### ✅ 3. `_correct_by_col()` — corrections par colonne
- COULEUR : correspondance floue (Levenshtein ≤ 2) sur le vocabulaire restreint
- SIGNAL : `4` en tête de mot → `A` pour les termes électriques connus (ARRET, ALARME, ALIM, etc.)

### ✅ 4. `_line_to_cells()` améliorée
- Nouveau paramètre `col_names` (optionnel, rétrocompatible)
- Appel de `_correct_by_col()` après `_clean_cell()` quand `col_names` est fourni

### ✅ 5. `_detect_col_bounds_morpho()` multi-hauteur
- Essaie 4 hauteurs de noyau : h//3, h//4, h//5, h//6
- S'arrête dès que n_cols-1 séparateurs sont trouvés
- Seuil abaissé de 0.30 → 0.25 (capture les lignes plus légères)

### ✅ 6. `_detect_col_bounds_whitespace()` — nouveau fallback
- Histogramme de densité de texte horizontal
- Détecte les n_cols-1 vallées les plus profondes
- Inséré entre morpho et weighted dans la chaîne de repli

### ✅ 7. `extract()` mis à jour
- Passe `col_names` à `_line_to_cells()` → corrections par colonne actives
- Nouveau fallback : `whitespace` entre `morpho` et `weighted`
- Méthode de détection `'whitespace'` reconnue dans les logs

---

### ✅ 8. Template REPARTITEUR corrigé dans `templates.json`
- Colonnes : TENANT / JAR / ABOUTISSANT / SIGNAL
- `col_widths` réalistes : 22 / 10 / 22 / 36 (avant : 20/20/20/20 = tranches égales)
- Template "Bornier standard" ajouté explicitement dans le JSON
- **Impact** : avec ce template sélectionné, la méthode de détection passe de `tatr`/`weighted` → **`header`** (colonne TENANT correcte dès la 1ère ligne)

### ⚠️ Découverte critique — Sélection du template dans l'interface
Les images du corpus se divisent en 2 types :
- **Bornier standard** (bornier_100+…) : template "Bornier standard" → header détecté ✅
- **Répartiteur** (bornier_2/3…) : template "REPARTITEUR" → header détecté ✅

**L'utilisateur doit sélectionner le bon template dans l'interface avant de lancer la conversion.**  
Sans ça, le système utilise toujours "Bornier standard" pour les documents répartiteur → colonnes décalées.

---

## Améliorations en attente / pistes futures

### Moyen terme
- [ ] **A/4 en BORNE/JARRETIERES** : requiert un vocabulaire de codes électriques. Solution : alimenter `data_dictionary.json` depuis un Excel corrigé manuellement (`/alimenter-dictionnaire`).
- [ ] **OCR par colonne (deux passes)** : extraire chaque colonne comme sous-image, relancer Tesseract avec PSM 4. Impact fort mais +3× temps de traitement. Désactivable via `config.py`.
- [ ] **Template "Répartiteur"** : créer un 2e template avec colonnes TENANT/JAR./ABOUTISSANT/SIGNAL et les bons mots-clés pour détecter ces en-têtes. Sélectionnable depuis l'interface.
- [ ] **`fra+eng` en langue OCR** : tester si la langue mixte améliore les codes alphanumériques (B702A, etc.).

### Long terme
- [ ] **Entraîner Tesseract** sur les polices monospace des borniers Matra/VAL.
- [ ] **Modèle DL A/4** : collecte d'échantillons `A` vs `4` de la police cible, entraîner un classifieur binaire léger (EfficientNet-B0).

---

## Comment reprendre après interruption

1. Lire ce fichier : `@Contexte/OCR_IMPROVEMENTS.md`
2. Vérifier l'état git : `git status`
3. Les modifications sont dans `ocr_processor.py` (méthodes listées ci-dessus)
4. Pour tester : `env\Scripts\python.exe generer_classeur.py`
5. Pour valider un changement : lancer sur quelques images et comparer l'Excel avant/après

## Commandes utiles
```powershell
# Tester sur une seule image
env\Scripts\python.exe -c "
from pathlib import Path
from ocr_processor import BornierTableExtractor
ext = BornierTableExtractor(tesseract_path=r'C:\Tesseract\TesseractOCR\tesseract.exe')
r = ext.extract(Path('images_repartiteur/bornier_100.jpg'))
print(r['detection_method'], r['metadata'])
for row in r['rows'][:5]: print(row)
"

# Générer le classeur complet
env\Scripts\python.exe generer_classeur.py
```
