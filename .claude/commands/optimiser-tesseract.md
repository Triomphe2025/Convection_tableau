Analyse et optimise les paramètres Tesseract pour améliorer la qualité OCR sur les images de borniers.

Tu es un ingénieur spécialisé en traitement d'image qui ajuste finement les paramètres OCR pour ce type de document industriel.

## Contexte technique

Les borniers électriques ont des caractéristiques spécifiques :
- Texte en majuscules principalement
- Grilles avec lignes noires bien définies
- Fond blanc, encre noire
- Parfois scanné en biais ou avec contraste insuffisant
- Codes alphanumériques courts (BORNE, COULEUR) + texte long (SIGNAL)

## Étape 1 — Diagnostic des images existantes

```powershell
env\Scripts\python.exe -c "
import cv2, numpy as np
from pathlib import Path

dossier = Path('images_borniers')
if not dossier.exists():
    print('Dossier images_borniers/ introuvable. Lancer une extraction d\'abord.')
    exit()

stats = []
for img_path in sorted(dossier.glob('*.jpg'))[:10]:  # 10 premières images
    img = cv2.imread(str(img_path))
    if img is None: continue
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    
    # Score de flou (variance Laplacienne)
    flou = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    # Contraste (écart-type)
    contraste = gray.std()
    
    # Luminosité moyenne
    luminosite = gray.mean()
    
    print(f'{img_path.name}: {w}x{h}px | flou={flou:.0f} | contraste={contraste:.1f} | lum={luminosite:.0f}')
"
```

## Étape 2 — Interprétation des métriques

Analyse les valeurs et identifie les problèmes :

| Métrique | Valeur idéale | Problème si |
|----------|--------------|-------------|
| Flou (variance Laplacien) | > 200 | < 100 → image floue, rescanner |
| Contraste (écart-type) | > 60 | < 40 → scan trop grisâtre |
| Luminosité | 180-220 | < 150 → trop sombre / > 240 → surexposé |
| Résolution | > 1400px largeur | < 1000px → agrandissement dégradé |

## Étape 3 — Test de différentes configurations Tesseract

```powershell
env\Scripts\python.exe -c "
import pytesseract, cv2, numpy as np
from pathlib import Path
from config import Config

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH

# Prendre la première image du dossier
images = sorted(Path('images_borniers').glob('*.jpg'))
if not images:
    print('Aucune image disponible.')
    exit()

img_path = images[0]
print(f'Image test: {img_path.name}')

img = cv2.imread(str(img_path))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
if gray.shape[1] < 1400:
    scale = 1400 / gray.shape[1]
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

configs = [
    ('PSM 6 (défaut actuel)', '--oem 3 --psm 6'),
    ('PSM 4 (colonne unique)', '--oem 3 --psm 4'),
    ('PSM 11 (texte épars)',   '--oem 3 --psm 11'),
]

for nom, cfg in configs:
    data = pytesseract.image_to_data(binary, config=cfg + ' -l fra', output_type=pytesseract.Output.DICT)
    mots = [t for t, c in zip(data['text'], data['conf']) if t.strip() and int(c) > 30]
    print(f'{nom}: {len(mots)} mots détectés avec confiance > 30%')
"
```

## Étape 4 — Recommandations personnalisées

Selon les résultats, propose des actions concrètes :

**Si images floues (flou < 100) :**
→ "Rescanner les originaux en 300 DPI. Les scans actuels sont insuffisants."
→ "Alternative : utiliser PSM 11 qui tolère mieux le flou (modifier dans `ocr_processor.py`, ligne `_ocr_elements()`)."

**Si contraste faible :**
→ "Activer le prétraitement CLAHE avant Otsu. Modifier `_preprocess()` pour ajouter :
```python
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
gray = clahe.apply(gray)
```"

**Si résolution trop basse :**
→ "Le seuil d'agrandissement est 1400px. Pour les images très petites, augmenter à 2000px dans `_preprocess()`."

**Si PSM 4 donne plus de mots que PSM 6 :**
→ "Essayer PSM 4 pour ce type de document. Modifier `--psm 6` en `--psm 4` dans `_ocr_elements()`."

## Étape 5 — Application des modifications

Si l'utilisateur valide une modification, effectue-la dans `ocr_processor.py`.
Teste immédiatement sur la même image et compare le nombre de mots détectés avant/après.
