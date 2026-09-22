Profile les performances du pipeline OCR pour identifier les goulets d'étranglement et accélérer les extractions.

Tu es un ingénieur performance qui mesure le temps de chaque étape du pipeline OCR
et propose des optimisations ciblées basées sur les données mesurées, pas des suppositions.

## Étape 1 — Profil de base : temps par image

```powershell
env\Scripts\python.exe -c "
import time, cv2
from pathlib import Path
from config import Config
import pytesseract, numpy as np

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH

dossier = Path('images_borniers')
if not dossier.exists():
    print('ERREUR : dossier images_borniers/ introuvable. Lancer une extraction d\abord.')
    exit()

images = sorted(dossier.glob('*.jpg'))[:10]
if not images:
    print('ERREUR : aucune image .jpg dans images_borniers/')
    exit()

resultats = []
for img_path in images:
    img = cv2.imread(str(img_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Mesurer prétraitement
    t0 = time.perf_counter()
    if gray.shape[1] < 1400:
        scale = 1400 / gray.shape[1]
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    t_pretraitement = time.perf_counter() - t0

    # Mesurer OCR
    t1 = time.perf_counter()
    data = pytesseract.image_to_data(binary, config='--oem 3 --psm 6 -l fra',
                                     output_type=pytesseract.Output.DICT)
    t_ocr = time.perf_counter() - t1

    # Mesurer analyse (groupement de lignes)
    t2 = time.perf_counter()
    mots_valides = [t for t,c in zip(data['text'], data['conf'])
                    if t.strip() and int(c) > 30]
    t_analyse = time.perf_counter() - t2

    total = t_pretraitement + t_ocr + t_analyse
    resultats.append({
        'nom': img_path.name,
        'prep': t_pretraitement,
        'ocr': t_ocr,
        'analyse': t_analyse,
        'total': total,
        'mots': len(mots_valides),
        'largeur': img.shape[1],
    })
    print(f'{img_path.name}: prep={t_pretraitement:.2f}s | ocr={t_ocr:.2f}s | analyse={t_analyse:.2f}s | TOTAL={total:.2f}s | {len(mots_valides)} mots')

print()
import statistics
totaux = [r['total'] for r in resultats]
print(f'Moyenne : {statistics.mean(totaux):.2f}s/image')
print(f'Max     : {max(totaux):.2f}s ({[r for r in resultats if r[\"total\"]==max(totaux)][0][\"nom\"]})')
print(f'Min     : {min(totaux):.2f}s')
print(f'Estimation {len(list(Path(\"images_borniers\").glob(\"*.jpg\")))} images : {statistics.mean(totaux)*len(list(Path(\"images_borniers\").glob(\"*.jpg\")))/60:.1f} minutes')
"
```

## Étape 2 — Identifier le goulot principal

Analyse les résultats :

| Proportion OCR | Interprétation | Action |
|---------------|----------------|--------|
| OCR > 80% du temps | Tesseract est le goulot | Réduire résolution ou changer PSM |
| Prétraitement > 30% | Redimensionnement excessif | Ajuster seuil 1400px |
| Analyse > 20% | Trop de mots parasites | Augmenter le seuil de confiance |

## Étape 3 — Test avec résolution réduite

Si OCR > 80% du temps, tester si réduire la résolution cible préserve la qualité :

```powershell
env\Scripts\python.exe -c "
import time, cv2, pytesseract, numpy as np
from pathlib import Path
from config import Config

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH

images = sorted(Path('images_borniers').glob('*.jpg'))[:5]
seuils = [1000, 1200, 1400, 1600, 1800]

for seuil in seuils:
    total_mots = 0
    total_temps = 0
    for img_path in images:
        img = cv2.imread(str(img_path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if gray.shape[1] < seuil:
            scale = seuil / gray.shape[1]
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        t = time.perf_counter()
        data = pytesseract.image_to_data(binary, config='--oem 3 --psm 6 -l fra',
                                         output_type=pytesseract.Output.DICT)
        total_temps += time.perf_counter() - t
        total_mots += len([t for t,c in zip(data['text'],data['conf']) if t.strip() and int(c)>30])
    print(f'Seuil {seuil}px : {total_temps:.1f}s total | {total_mots} mots détectés')
"
```

## Étape 4 — Test avec cache d'images prétraitées

Si les mêmes images sont traitées plusieurs fois (ex: debug), le cache évite le retraitement :

```powershell
env\Scripts\python.exe -c "
# Simuler un cache : sauvegarder les images binaires prétraitées
import cv2, numpy as np, time
from pathlib import Path

cache_dir = Path('images_borniers/_cache')
cache_dir.mkdir(exist_ok=True)

images = sorted(Path('images_borniers').glob('*.jpg'))[:5]

print('=== SANS CACHE ===')
t0 = time.perf_counter()
for img_path in images:
    img = cv2.imread(str(img_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] < 1400:
        gray = cv2.resize(gray, None, fx=1400/gray.shape[1], fy=1400/gray.shape[1], interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
print(f'Temps prétraitement : {time.perf_counter()-t0:.2f}s')

print()
print('=== AVEC CACHE ===')
# Écrire le cache
for img_path in images:
    img = cv2.imread(str(img_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] < 1400:
        gray = cv2.resize(gray, None, fx=1400/gray.shape[1], fy=1400/gray.shape[1], interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cv2.imwrite(str(cache_dir / img_path.name), binary)

# Lire depuis le cache
t1 = time.perf_counter()
for img_path in images:
    binary = cv2.imread(str(cache_dir / img_path.name), cv2.IMREAD_GRAYSCALE)
print(f'Temps avec cache : {time.perf_counter()-t1:.2f}s')

import shutil
shutil.rmtree(cache_dir)
"
```

## Étape 5 — Recommandations et application

Selon les résultats, propose les modifications dans `ocr_processor.py` :

**Si réduire le seuil à 1200px donne autant de mots avec 20%+ de gain :**
```python
# Dans _preprocess(), modifier la ligne :
if gray.shape[1] < 1400:   # → changer en 1200
```
→ Modifier via `/changer-config` si paramètre dans config.py, sinon éditer directement.

**Si seuil de confiance trop bas crée beaucoup de bruit :**
```python
# Dans _ocr_elements(), chercher la ligne avec conf > XX et augmenter :
if int(c) > 30:   # → tester avec 40 ou 50
```

**Si les images sont souvent traitées plusieurs fois :**
→ Proposer d'ajouter un paramètre `ENABLE_PREPROCESS_CACHE = False` dans `config.py`
  et implémenter via `/implementer-feature`.

## Étape 6 — Rapport de performance

```
RAPPORT DE PERFORMANCE — TriosSeconverter OCR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Images testées   : XX
Temps moyen      : XX.Xs/image (prétraitement XX% | OCR XX% | analyse XX%)
Goulot principal : [OCR Tesseract / Prétraitement / Analyse]
Estimation totale: XX.X min pour YY images

OPTIMISATION APPLIQUÉE : [description]
  Avant : XX.Xs/image
  Après : XX.Xs/image
  Gain  : XX%
```
