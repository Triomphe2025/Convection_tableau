Analyse approfondie d'une image de bornier spécifique : histogramme, prétraitements alternatifs, comparaison OCR.

Tu es un ingénieur en vision par ordinateur qui diagnostique en profondeur pourquoi une image
est mal lue par l'OCR et expérimente plusieurs chaînes de traitement pour trouver la meilleure.

## Étape 1 — Sélection de l'image

Demande à l'utilisateur le nom de l'image à analyser (ex: `bornier_05.jpg`).
Si pas précisé, prendre la première image dans `images_borniers/`.

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
images = sorted(Path('images_borniers').glob('*.jpg'))
print(f'{len(images)} images disponibles :')
for i, p in enumerate(images, 1):
    print(f'  {i:2}. {p.name}')
"
```

## Étape 2 — Métriques de qualité complètes

```powershell
env\Scripts\python.exe -c "
import cv2, numpy as np
from pathlib import Path

# Remplacer par le nom choisi
img_path = Path('images_borniers/[NOM_IMAGE]')
img = cv2.imread(str(img_path))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
h, w = gray.shape

print(f'=== MÉTRIQUES : {img_path.name} ===')
print(f'Dimensions     : {w} x {h} px')
print(f'Résolution     : {\"OK\" if w >= 1400 else \"FAIBLE (< 1400px)\"}')

# Flou
flou = cv2.Laplacian(gray, cv2.CV_64F).var()
print(f'Netteté (Laplacien) : {flou:.0f}  {\"✓ NET\" if flou > 200 else \"△ FLOU\" if flou > 80 else \"✗ TRÈS FLOU\"}')

# Contraste
print(f'Contraste (std) : {gray.std():.1f}  {\"✓ BON\" if gray.std() > 60 else \"△ FAIBLE\"}')

# Luminosité
print(f'Luminosité (moy): {gray.mean():.0f}  {\"✓ OK\" if 160 <= gray.mean() <= 230 else \"△ PROBLÈME\"}')

# Histogramme simplifié
bins = np.histogram(gray, bins=5, range=(0,255))[0]
labels = ['Noir', 'Sombre', 'Gris', 'Clair', 'Blanc']
print()
print('Histogramme :')
for label, count in zip(labels, bins):
    bar = '#' * int(count / max(bins) * 30)
    print(f'  {label:6}: {bar} ({count}px)')

# Détection d'inclinaison
edges = cv2.Canny(gray, 50, 150)
lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
if lines is not None:
    angles = [(np.degrees(line[0][1]) - 90) for line in lines[:20]]
    angle_moyen = np.mean(angles)
    print(f'\nInclinaison estimée : {angle_moyen:.1f}° {\"✓ OK\" if abs(angle_moyen) < 2 else \"△ À REDRESSER\"}')
else:
    print('\nInclinaison : non détectable (image trop peu contrastée)')
"
```

## Étape 3 — Comparaison de 5 chaînes de prétraitement

Tester 5 approches et mesurer le nombre de mots OCR détectés avec confiance > 30 :

```powershell
env\Scripts\python.exe -c "
import cv2, numpy as np, pytesseract
from pathlib import Path
from config import Config

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH

img_path = Path('images_borniers/[NOM_IMAGE]')
img = cv2.imread(str(img_path))
gray_orig = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

def ocr_count(binary, psm=6):
    data = pytesseract.image_to_data(binary, config=f'--oem 3 --psm {psm} -l fra',
                                     output_type=pytesseract.Output.DICT)
    mots = [t for t,c in zip(data['text'],data['conf']) if t.strip() and int(c)>30]
    conf_moy = np.mean([int(c) for c in data['conf'] if int(c) > 0]) if data['conf'] else 0
    return len(mots), conf_moy

def redim(gray, seuil=1400):
    if gray.shape[1] < seuil:
        s = seuil / gray.shape[1]
        return cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    return gray

gray = redim(gray_orig)

chaines = {}

# 1 — Standard actuel (Otsu)
_, b1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
chaines['1. Otsu standard (actuel)'] = b1

# 2 — CLAHE + Otsu (améliore le contraste local)
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
gray_clahe = clahe.apply(gray)
_, b2 = cv2.threshold(gray_clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
chaines['2. CLAHE + Otsu'] = b2

# 3 — Seuillage adaptatif (robuste aux ombres locales)
b3 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                            cv2.THRESH_BINARY, 15, 8)
chaines['3. Seuillage adaptatif'] = b3

# 4 — Débruitage + Otsu (pour images bruitées)
denoised = cv2.fastNlMeansDenoising(gray, h=10)
_, b4 = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
chaines['4. Débruitage + Otsu'] = b4

# 5 — Correction gamma + Otsu (pour images sombres)
gamma = 1.5
lut = np.array([((i/255.0)**(1.0/gamma))*255 for i in range(256)]).astype(np.uint8)
gray_gamma = cv2.LUT(gray, lut)
_, b5 = cv2.threshold(gray_gamma, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
chaines['5. Gamma 1.5 + Otsu'] = b5

print(f'=== COMPARAISON OCR : {img_path.name} ===')
print(f'{\"Chaîne\":<35} {\"Mots (>30%)\">12} {\"Confiance moy.\">15}')
print('-' * 65)
meilleure = None
meilleur_score = 0
for nom, binary in chaines.items():
    n_mots, conf = ocr_count(binary)
    print(f'{nom:<35} {n_mots:>12} {conf:>14.1f}%')
    if n_mots > meilleur_score:
        meilleur_score = n_mots
        meilleure = nom

print()
print(f'Recommandation : {meilleure}')
"
```

## Étape 4 — Comparaison des modes PSM Tesseract

```powershell
env\Scripts\python.exe -c "
import cv2, numpy as np, pytesseract
from pathlib import Path
from config import Config

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH
img_path = Path('images_borniers/[NOM_IMAGE]')
img = cv2.imread(str(img_path))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
if gray.shape[1] < 1400:
    gray = cv2.resize(gray, None, fx=1400/gray.shape[1], fy=1400/gray.shape[1], interpolation=cv2.INTER_CUBIC)
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

psm_modes = {
    4: 'Colonne de texte unique',
    6: 'Bloc de texte uniforme (défaut)',
    11: 'Texte épars (tolérant au bruit)',
    12: 'Texte épars + OSD',
}

print(f'=== COMPARAISON PSM : {img_path.name} ===')
for psm, desc in psm_modes.items():
    data = pytesseract.image_to_data(binary, config=f'--oem 3 --psm {psm} -l fra',
                                     output_type=pytesseract.Output.DICT)
    mots = [t for t,c in zip(data['text'],data['conf']) if t.strip() and int(c)>30]
    print(f'PSM {psm:2} ({desc:<35}): {len(mots):3} mots')
"
```

## Étape 5 — Visualisation (sauvegarde une image annotée)

```powershell
env\Scripts\python.exe -c "
import cv2, numpy as np, pytesseract
from pathlib import Path
from config import Config

pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH
img_path = Path('images_borniers/[NOM_IMAGE]')
img = cv2.imread(str(img_path))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
if gray.shape[1] < 1400:
    scale = 1400 / gray.shape[1]
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

# OCR avec boîtes
data = pytesseract.image_to_data(binary, config='--oem 3 --psm 6 -l fra',
                                 output_type=pytesseract.Output.DICT)

annotee = img.copy()
for i in range(len(data['text'])):
    if not data['text'][i].strip(): continue
    conf = int(data['conf'][i])
    x,y,w,h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
    couleur = (0,200,0) if conf > 60 else (0,165,255) if conf > 30 else (0,0,255)
    cv2.rectangle(annotee, (x,y), (x+w,y+h), couleur, 1)

sortie = Path('images_borniers') / f'annote_{img_path.name}'
cv2.imwrite(str(sortie), annotee)
print(f'Image annotée sauvegardée : {sortie}')
print('Légende : vert=confiance>60% | orange=30-60% | rouge=<30%')
"
```

## Étape 6 — Recommandations

Selon les résultats des étapes 3 et 4, propose les modifications à apporter à `ocr_processor.py` :

**Si CLAHE + Otsu donne +15% de mots :**
→ Ajouter CLAHE dans `_preprocess()` avant le seuillage Otsu.

**Si PSM 4 ou PSM 11 donne plus de mots que PSM 6 :**
→ Modifier `--psm 6` en `--psm X` dans `_ocr_elements()`.

**Si inclinaison > 2° :**
→ Ajouter correction de biais avant le seuillage :
```python
# Redressement automatique
coords = np.column_stack(np.where(binary > 0))
angle = cv2.minAreaRect(coords)[-1]
if abs(angle) > 1:
    (h, w) = binary.shape
    M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
    binary = cv2.warpAffine(binary, M, (w, h))
```

Si l'utilisateur valide une modification, l'appliquer dans `ocr_processor.py`
et relancer le test pour confirmer l'amélioration.
