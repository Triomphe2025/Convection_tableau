Analyse complète de la qualité OCR sur toutes les images du dossier bornier.

Tu es un ingénieur qualité qui évalue les résultats d'extraction. Exécute cette analyse en plusieurs étapes.

## Étape 1 — Inventaire des images

Lis `config.py` pour trouver `IMAGES_FOLDER_NAME` et `TESSERACT_PATH`.
Liste toutes les images dans le dossier `images_borniers/` (ou le dossier configuré).
Affiche le nombre total d'images trouvées.

## Étape 2 — Analyse OCR image par image

Pour chaque image, exécute :
```powershell
env\Scripts\activate
python -c "
from ocr_processor import BornierTableExtractor
from pathlib import Path
import json

ext = BornierTableExtractor()
images = sorted(Path('images_borniers').glob('*.jpg'))
rapport = []
for img in images:
    r = ext.extract(img)
    n_data = sum(1 for row in r.get('rows', []) if row.get('type') == 'data')
    rapport.append({
        'image': img.name,
        'success': r.get('success'),
        'blur_pct': r.get('blur_pct', 0),
        'lignes_data': n_data,
        'bornier': r.get('metadata', {}).get('BORNIER', '?'),
        'page': r.get('metadata', {}).get('PAGE', '?'),
        'erreur': r.get('error', '')
    })
print(json.dumps(rapport, ensure_ascii=False, indent=2))
"
```

## Étape 3 — Synthèse du rapport

À partir des résultats JSON, calcule et affiche :

**Statistiques globales :**
- Nombre d'images réussies / total
- Nombre d'images floues (blur_pct > 80%)
- Nombre d'images sans métadonnées BORNIER détectées
- Nombre d'images avec moins de 3 lignes de données (OCR probablement raté)

**Liste des problèmes par priorité :**

🔴 CRITIQUE — images échouées (success = false) → à retraiter manuellement
🟠 ATTENTION — images floues (blur > 80%) → vérifier la qualité du scan
🟡 VIGILANCE — borniers sans PAGE détectée → positionnement Excel incorrect
🟢 OK — images extraites proprement

**Tableau récapitulatif** (format texte) :
```
Image           | Bornier | Page | Flou% | Lignes | Statut
bornier_1.jpg   | B702A   | 92   | 12%   | 24     | ✓ OK
bornier_12.jpg  | ?       | ?    | 84%   | 3      | ⚠ FLOU
```

## Étape 4 — Recommandations concrètes

Pour chaque problème détecté, propose une action :
- Image floue → "Rescanner l'original en 300 DPI minimum"
- PAGE manquante → "Ajouter manuellement via /corriger-ocr"
- Moins de 3 lignes → "Vérifier si l'image est bien un tableau de bornier"
- Echec total → "Vérifier que l'image n'est pas corrompue"

Termine par : "Rapport de qualité OCR terminé. X images nécessitent une action."
