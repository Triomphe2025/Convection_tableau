Visualise graphiquement la détection des colonnes OCR et la classification des lignes sur une image de bornier.

Tu es un ingénieur en vision par ordinateur qui génère des images annotées pour déboguer
les erreurs de détection de colonnes et de classification des lignes (en-tête, données, séparateur, pied).

## Contexte technique

La détection des colonnes dans `ocr_processor.py` fonctionne ainsi :
1. `_find_header()` : trouve la ligne d'en-tête en cherchant les mots-clés (BORNE, COULEUR, SIGNAL, etc.)
2. `_col_boundaries()` : calcule les frontières de colonnes à partir des positions pixel (`cx`) des mots de l'en-tête
3. `_classify_lines()` : classe chaque ligne en `data` / `section` / `footer`
4. `_assign_cells()` : affecte chaque mot à une colonne selon son bord gauche (`x`), pas son centre

## Étape 1 — Sélectionner l'image

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
images = sorted(Path('images_borniers').glob('*.jpg'))
print(f'{len(images)} images disponibles :')
for i, p in enumerate(images, 1):
    print(f'  {i:2}. {p.name}')
"
```

Demander à l'utilisateur quelle image analyser.

## Étape 2 — Reproduire la détection et annoter l'image

```powershell
env\Scripts\python.exe -c "
import cv2, numpy as np, pytesseract
from pathlib import Path
from config import Config

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH

# ── Choisir l'image ─────────────────────────────────────────────────
img_path = Path('images_borniers/[NOM_IMAGE]')
img_orig = cv2.imread(str(img_path))
gray = cv2.cvtColor(img_orig, cv2.COLOR_BGR2GRAY)

if gray.shape[1] < 1400:
    scale = 1400 / gray.shape[1]
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    img_orig = cv2.resize(img_orig, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
H, W = binary.shape

# ── OCR complet ──────────────────────────────────────────────────────
data = pytesseract.image_to_data(binary, config='--oem 3 --psm 6 -l fra',
                                 output_type=pytesseract.Output.DICT)

# ── Regrouper par lignes (mots dont le centre y est proche) ──────────
mots = []
for i in range(len(data['text'])):
    if not data['text'][i].strip() or int(data['conf'][i]) < 0:
        continue
    mots.append({
        'text': data['text'][i],
        'x':    data['left'][i],
        'y':    data['top'][i],
        'w':    data['width'][i],
        'h':    data['height'][i],
        'cx':   data['left'][i] + data['width'][i] // 2,
        'cy':   data['top'][i]  + data['height'][i] // 2,
        'conf': int(data['conf'][i]),
    })

if not mots:
    print('ERREUR : aucun mot OCR détecté sur cette image.')
    exit()

# Regrouper par ligne (cy similaires à ±10px)
mots.sort(key=lambda m: m['cy'])
lignes = []
ligne_courante = [mots[0]]
for mot in mots[1:]:
    if abs(mot['cy'] - ligne_courante[-1]['cy']) < 12:
        ligne_courante.append(mot)
    else:
        lignes.append(sorted(ligne_courante, key=lambda m: m['x']))
        ligne_courante = [mot]
lignes.append(sorted(ligne_courante, key=lambda m: m['x']))

# ── Trouver l'en-tête (ligne contenant les mots-clés de colonnes) ────
EN_TETE_MOTS = {'BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERE', 'JARRETIERES', 'SECTION'}
header_idx = None
for i, ligne in enumerate(lignes):
    mots_ligne = {m['text'].upper() for m in ligne}
    if len(mots_ligne & EN_TETE_MOTS) >= 2:
        header_idx = i
        break

if header_idx is None:
    print('AVERTISSEMENT : en-tête non détectée. Lignes disponibles :')
    for i, l in enumerate(lignes[:10]):
        print(f'  Ligne {i}: {\" | \".join(m[\"text\"] for m in l)}')
    exit()

header_ligne = lignes[header_idx]
print(f'En-tête trouvée à la ligne {header_idx}: {\" | \".join(m[\"text\"] for m in header_ligne)}')

# ── Calculer les frontières de colonnes ──────────────────────────────
# Frontière = milieu entre deux mots d'en-tête consécutifs
header_ligne_sorted = sorted(header_ligne, key=lambda m: m['cx'])
frontieres = []
for j in range(len(header_ligne_sorted) - 1):
    f = (header_ligne_sorted[j]['cx'] + header_ligne_sorted[j+1]['cx']) // 2
    frontieres.append(f)

print(f'Frontières de colonnes (px) : {frontieres}')

# ── Générer l'image annotée ──────────────────────────────────────────
annot = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

# Colonnes : lignes verticales bleues
for f in frontieres:
    cv2.line(annot, (f, 0), (f, H), (255, 100, 0), 2)

# En-tête : surlignage vert
for mot in header_ligne:
    x,y,w,h = mot['x'], mot['y'], mot['w'], mot['h']
    cv2.rectangle(annot, (x,y), (x+w,y+h), (0,200,0), 2)
    cv2.putText(annot, mot['text'], (x, y-4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,180,0), 1)

# Mots de données : couleur selon colonne assignée
couleurs_col = [(200,50,50),(50,100,200),(50,180,100),(180,100,50),(100,50,180)]
for ligne in lignes:
    if ligne == header_ligne:
        continue
    for mot in ligne:
        # Trouver la colonne selon bord gauche
        col_idx = len(frontieres)  # par défaut : dernière colonne
        for k, f in enumerate(frontieres):
            if mot['x'] < f:
                col_idx = k
                break
        couleur = couleurs_col[col_idx % len(couleurs_col)]
        x,y,w,h = mot['x'], mot['y'], mot['w'], mot['h']
        cv2.rectangle(annot, (x,y), (x+w,y+h), couleur, 1)

# Légende
for k, col_name in enumerate([m['text'] for m in header_ligne_sorted]):
    cv2.putText(annot, f'Col{k}: {col_name}', (10, 30+k*20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, couleurs_col[k % len(couleurs_col)], 1)

sortie = Path('images_borniers') / f'colonnes_{img_path.name}'
cv2.imwrite(str(sortie), annot)
print(f'Image annotée : {sortie}')
print()

# ── Résumé de l\affectation ──────────────────────────────────────────
print('=== AFFECTATION DES MOTS PAR COLONNE ===')
col_noms = [m['text'] for m in header_ligne_sorted]
for ligne in lignes[header_idx+1:header_idx+6]:  # 5 lignes de données
    print()
    for mot in ligne:
        col_idx = len(frontieres)
        for k, f in enumerate(frontieres):
            if mot['x'] < f:
                col_idx = k
                break
        col_nom = col_noms[col_idx] if col_idx < len(col_noms) else '???'
        print(f'  [{col_nom:12}] \"{mot[\"text\"]}\" (x={mot[\"x\"]}px)')
"
```

## Étape 3 — Diagnostic des problèmes d'affectation

Après l'exécution, analyser les résultats :

**Problème : un mot de la colonne SIGNAL se retrouve dans JARRETIERES**
→ Son bord gauche (`x`) dépasse la frontière entre SIGNAL et JARRETIERES.
→ Solution : ajuster `_col_boundaries()` pour décaler la frontière vers la droite.

**Problème : l'en-tête n'est pas détectée**
→ Les mots-clés ne correspondent pas (OCR a lu "B0RNE" au lieu de "BORNE").
→ Solution : ajouter une correction dans `data_dictionary.json` via `/corriger-ocr`.

**Problème : des mots sont dans la mauvaise colonne car le scan est en biais**
→ Les positions `x` sont décalées par l'inclinaison.
→ Solution : activer la correction d'inclinaison dans `/analyser-image-profonde`.

**Problème : une colonne n'est jamais détectée**
→ Son mot-clé d'en-tête n'a pas été lu par Tesseract.
→ Vérifier dans l'image annotée si la zone est présente mais mal lue.

## Étape 4 — Rapport visuel

```
VISUALISATION COLONNES — [NOM_IMAGE]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

En-tête détectée à la ligne : [N]
Colonnes trouvées : [BORNE | COULEUR | SIGNAL | JARRETIERES]
Frontières (px)   : [XXX | XXX | XXX]

Affectation 5 premières lignes de données :
  [tableau]

Problèmes détectés :
  ✗ [description du problème et ligne/mot concerné]
  ✓ Aucun problème — détection correcte

Image annotée sauvegardée : images_borniers/colonnes_[NOM].jpg
(Ouvrir avec l'Explorateur Windows pour visualiser)
```

Ouvrir l'image annotée automatiquement :
```powershell
Start-Process "images_borniers\colonnes_[NOM_IMAGE]"
```
