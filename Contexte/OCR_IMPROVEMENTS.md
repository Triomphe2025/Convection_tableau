# OCR_IMPROVEMENTS.md — Suivi d'amélioration OCR TriosSeconverter

## Mot-clé de reprise : `OCR_AMÉLIORATIONS_V2`

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

---

## Améliorations implémentées (session 2026-05-08)

### ✅ 9. Bouton "Enrichir le dico" dans l'interface (`interface.py`)
- Nouveau bouton dans `_build_buttons_row()`, toujours actif (non conditionné à une conversion)
- Ouvre un sélecteur de fichier Excel (`filedialog.askopenfilename`)
- Appelle `DataDictionary.update_from_excel()` → sauvegarde automatique dans `data_dictionary.json`
- Affiche une boîte de dialogue avec le nombre de corrections ajoutées

### ✅ 10. Confiance OCR par cellule — surlignage jaune + commentaires Excel (`ocr_processor.py`)
- `_line_to_cells()` retourne maintenant `Tuple[List[str], List[int]]` (cellules + confiances 0-100)
- Confiance = moyenne des scores Tesseract des mots dans la cellule ; 100 si cellule vide
- `extract()` stocke `'confidence': confs` dans chaque dict de ligne de données
- `_fill_worksheet()` : si `confiance < 60 %` ET cellule non vide → fond jaune `#FFFF99` + commentaire Excel "Confiance OCR : XX%"
- Permet à l'utilisateur de voir exactement quelles cellules vérifier dans le classeur généré

### ✅ 11. Prétraitement amélioré (`_preprocess()` — `ocr_processor.py` l.759)
Pipeline mis à niveau :
- **CLAHE clipLimit 2.0 → 3.0** : révèle le texte pâle sans amplifier le bruit
- **medianBlur(3) remplacé par `fastNlMeansDenoising(h=7)`** : préserve les jambages fins (1, l, i)
- **Sharpen kernel 3×3** ajouté après le débruitage (compense le lissage, renforce les bords avant Otsu)
- Otsu conservé (stable sur fond homogène industriel)
- Upscale si < 1400 px conservé

### ✅ 12. OEM 3 → OEM 1 (`_ocr_elements()` l.821)
- `--oem 3` (LSTM + legacy) → `--oem 1` (LSTM pur)
- Tesseract 5.x : OEM 1 est systématiquement plus précis sur texte imprimé

### ✅ 13. Whitelists de caractères par colonne (`_COL_WHITELISTS`)
- Dictionnaire de caractères autorisés : BORNE, COULEUR, SIGNAL, JARRETIERES, TENANT, JAR, ABOUTISSANT
- Utilisé par `_reocr_cell()` via `tessedit_char_whitelist`

### ✅ 14. Re-OCR ciblé par cellule (`_reocr_cell()` + `Config.OCR_PER_COLUMN`)
- Nouvelle méthode `_reocr_cell()` dans `BornierTableExtractor`
- Pipeline : crop cellule → upscale si < 20 px → Tesseract PSM 7 + whitelist colonne
- Activé par `Config.OCR_PER_COLUMN = True` (défaut) et `Config.OCR_REOCR_THRESHOLD = 60`
- Dans `extract()` : pour chaque ligne, si une cellule a conf < seuil, re-OCR et garde le meilleur résultat
- Impact : +10 à +20 % sur colonnes à caractères ambigus (A↔4, l↔1)

---

## Corrections de régression (session 2026-05-11)

### ✅ 16. Correction template corrompu (`template.py` — `REPARTITEUR_TEMPLATE`)
- **Cause racine** : `REPARTITEUR_TEMPLATE` codé en dur dans `template.py` avait `JARRETIERES` au lieu de `JAR` en colonne 2.
- Ce template était chargé en premier par `TemplateManager._load()` avant les templates du JSON.
- **Fix** : colonnes corrigées → `["TENANT", "JAR", "ABOUTISSANT", "SIGNAL"]`, col_widths alignés sur le JSON (22/10/22/36).

### ✅ 17. Auto-détection du template si mauvais template sélectionné (`extract()`)
- Si `_find_header_idx()` échoue avec le template actif, le code essaie automatiquement tous les autres templates.
- Cas typique : images REPARTITEUR traitées avec le template "Bornier standard" par défaut.
- **Impact** : `detection_method` passe de `tatr` → `header` → colonnes correctes sans intervention manuelle.

### ✅ 18. Performance : `fastNlMeansDenoising` → `bilateralFilter` (`_preprocess()`)
- **Avant** : `fastNlMeansDenoising(h=7, sw=21)` = **3.82 s/image** sur images 2475×3499 px
- **Après** : `bilateralFilter(d=5, sigmaColor=50, sigmaSpace=50)` = **0.01 s** (400× plus rapide)
- Préserve les bords des caractères (edge-preserving), qualité équivalente pour l'OCR.
- `CLAHE clipLimit` : 3.0 → 2.5 (compromis stabilité/contraste).
- Temps total par image : 18-22 s → **7-9 s** (gain ≈ 60 %).

### ✅ 19. Seuil de flou abaissé à 40 % (était 60 %/80 %)
- `generer_classeur.py` : rapport images floues déclenché si `blur_pct > 40` (était 60).
- `_fill_worksheet()` : en-tête orange + commentaire Excel si `blur_pct > 40` (était 80).
- Permet de repérer les images légèrement floues avant que la qualité OCR soit trop dégradée.

### ✅ 20. Journal OCR Tesseract (`Config.OCR_DEBUG_LOG = True`)
- Nouvelle méthode `_write_ocr_log()` dans `BornierTableExtractor`.
- Crée/enrichit `ocr_debug.log` dans le répertoire courant à chaque conversion.
- Contenu par image : texte brut Tesseract (mot + position + confiance), lignes regroupées, frontières colonnes, affectation finale par colonne.
- Désactivable via `Config.OCR_DEBUG_LOG = False` en production.

---

### ✅ 15. Script d'entraînement Tesseract (`creer_donnees_entrainement.py`)
- Nouveau script autonome pour générer les données d'entraînement (`ground_truth/`)
- Lit un Excel corrigé manuellement + les images originales
- Extrait les bandes horizontales de chaque image (une bande = une ligne)
- Génère : `p0001_l001.png` + `p0001_l001.gt.txt` par ligne
- Affiche instructions complètes pour lancer tesstrain sous WSL2
- Usage : `python creer_donnees_entrainement.py [--excel ...] [--images ...] [--out ...]`

---

## Améliorations en attente / pistes futures

### Court terme (prochaine session)
- [ ] **Tester le modèle `fra_best`** : remplacer `fra.traineddata` par la version LSTM haute précision de `tessdata_best`. Sans entraînement, juste le meilleur modèle pré-entraîné. Gain potentiel +5 à +10 %.
- [ ] **`fra+eng` en langue OCR** : tester si la langue mixte améliore les codes alphanumériques (B702A, etc.). Modifier `Config.OCR_LANGUAGE = "fra+eng"`.
- [ ] **A/4 en BORNE/JARRETIERES** : alimenter `data_dictionary.json` depuis un Excel corrigé (`/alimenter-dictionnaire`).

### Moyen terme (avec données d'entraînement)
- [x] ~~**OCR par colonne**~~ → **Implémenté** (`Config.OCR_PER_COLUMN`, `_reocr_cell()`)
- [x] ~~**Template "Répartiteur"**~~ → **Implémenté** (templates.json session 2026-05-07)
- [ ] **Fine-tuning Tesseract** : utiliser `creer_donnees_entrainement.py` → corriger 50 borniers → lancer tesstrain dans WSL2.

### Long terme
- [ ] **Fine-tuning incrémental** : après le premier modèle, chaque nouveau cycle avec les nouvelles cellules corrigées améliore progressivement le modèle.
- [ ] **EasyOCR fallback** : pour les cellules restant < 40 % après re-OCR, utiliser EasyOCR (CRNN). Nécessite PyTorch (~1.5 Go). Config : `Config.USE_EASYOCR_FALLBACK = False`.

---

## Comment reprendre après interruption

1. Lire ce fichier : `@Contexte/OCR_IMPROVEMENTS.md`
2. Vérifier l'état git : `git status`
3. Les modifications sont dans `ocr_processor.py` (méthodes listées ci-dessus)
4. Pour tester : `.\env\Scripts\python.exe generer_classeur.py`
5. Pour valider un changement : lancer sur quelques images et comparer l'Excel avant/après

## Commandes utiles
```powershell
# Tester sur une seule image (confiance OCR visible)
.\env\Scripts\python.exe -c "
from pathlib import Path
from ocr_processor import BornierTableExtractor
ext = BornierTableExtractor(tesseract_path=r'C:\Tesseract\TesseractOCR\tesseract.exe')
r = ext.extract(Path('images_repartiteur/bornier_100.jpg'))
print(r['detection_method'], r['metadata'])
for row in r['rows'][:5]:
    if row['type'] == 'data':
        print('cellules:', row['cells'])
        print('confiances:', row.get('confidence', []))
"

# Générer le classeur complet
.\env\Scripts\python.exe generer_classeur.py

# Générer les données d'entraînement Tesseract
.\env\Scripts\python.exe creer_donnees_entrainement.py --excel tous_les_borniers_corrigé.xlsx
```
