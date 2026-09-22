# Règle 06 — Configuration et paramètres

## Règle absolue : tout passe par config.py

**Ne jamais coder un paramètre en dur dans un autre fichier.**

```python
# INTERDIT
TESSERACT_PATH = r"C:\Tesseract\TesseractOCR\tesseract.exe"  # dans ocr_processor.py

# CORRECT
from config import Config
Config.TESSERACT_PATH   # référencer uniquement
```

## Paramètres actuels (config.py)

| Paramètre | Valeur actuelle | Rôle |
|-----------|----------------|------|
| `TESSERACT_PATH` | `C:\Tesseract\TesseractOCR\tesseract.exe` | Chemin Tesseract |
| `OCR_LANGUAGE` | `fra` | Langue Tesseract |
| `PAGE_SIZE` | `48` | Lignes par page A4 dans Excel |
| `STATION_NAME` | `EPEULE` | Nom P.E.T. de repli si OCR échoue |
| `MIN_DATA_ROWS` | `1` | Seuil minimal de lignes pour valider un bornier |
| `IMAGES_FOLDER_NAME` | `VD23111 PE 162` | Nom du dossier de sortie des images |
| `OCR_MODE` | `tesseract` | Mode OCR par défaut |
| `CLAUDE_API_KEY` | `""` | Clé API Anthropic |
| `CLAUDE_AGENT_SESSION_ID` | `""` | ID session agent |

## Vérification de conversion (section « VÉRIFICATION DE CONVERSION »)

| Paramètre | Valeur défaut | Rôle |
|-----------|--------------|------|
| `VERIF_SEUIL_PAGE` | `0.30` | Similarité minimale pour apparier deux pages |
| `VERIF_SEUIL_LIGNE` | `0.55` | Similarité minimale pour apparier deux lignes lues différemment |
| `VERIF_DISTANCE_BENIGNE` | `2` | Écart d'au plus N caractères bénin si la confiance reste sous `VERIF_CONFIANCE_SURE` |
| `VERIF_CONFIANCE_SURE` | `90` | Confiance OCR de la référence au-delà de laquelle un écart est suspect |
| `VERIF_FUSION_ECARTS` | `3` | Zones qui diffèrent séparées de moins de N caractères identiques = un seul écart |
| `VERIF_SEUIL_PAGE_EXACTE` | `0.9` | Similarité de lignes identiques au-delà de laquelle deux pages sont appariées directement |
| `VERIF_LIGNE_BRUIT_MIN_CARS` | `3` | En dessous de N caractères alphanumériques, une ligne orpheline est du bruit |
| `VERIF_CONFUSIONS_OCR` | `0O, 1IL, 5S, T7, 8B, 2Z` | Groupes de caractères repliés avant comparaison |
| `VERIF_SEUIL_CONCORDANCE` | `0.98` | Concordance au-dessus de laquelle la conversion est jugée fidèle |

La confiance basse réutilise `OCR_REOCR_THRESHOLD` (pas de paramètre dédié).

## Ajouter un nouveau paramètre

1. Ajouter dans `Config` (class dans config.py) avec valeur par défaut
2. Documenter dans le tableau ci-dessus
3. Mettre à jour CLAUDE.md section "Configuration"
4. Utiliser `/changer-config` pour modifier via Claude Code

## Paramètres de mise en forme Excel

| Paramètre | Valeur défaut |
|-----------|--------------|
| `FORMAT_ROW_HEIGHT` | `12.6` (pt) |
| `FORMAT_COL_WIDTH_DEFAULT` | `19` (car) |
| `FORMAT_COL_WIDTH_SIGNAL` | `33` (car) |
| `FORMAT_MARGIN_TOP/BOTTOM` | `0.9` (cm) |
| `FORMAT_MARGIN_LEFT/RIGHT` | `1.75` (cm) |
| `FORMAT_MARGIN_HEADER/FOOTER` | `0.0` (cm) |

## Ressources dans l'exe PyInstaller

```python
def _resource(name: str) -> Path:
    """Résout le chemin d'une ressource — fonctionne en mode dev et en exe."""
    if hasattr(sys, '_MEIPASS'):         # Mode exe PyInstaller
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name  # Mode dev
```

Toujours passer par cette fonction pour `icon.ico` et les ressources statiques.

## Variables d'environnement Python

Configurées dans `.claude/settings.json` :
- `PYTHONIOENCODING=utf-8` — encodage obligatoire pour les PDFs et logs
- `PYTHONPATH=.` — permet d'importer les modules locaux
- `PYTHONUTF8=1` — mode UTF-8 global Python 3.7+
