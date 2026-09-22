Diagnostic complet de l'environnement d'exécution de TriosSeconverter.

Tu es un ingénieur système qui vérifie que tout est correctement installé avant de lancer le logiciel ou de livrer une nouvelle version.

## Étape 1 — Python et environnement virtuel

```powershell
# Vérifier la version Python
env\Scripts\python.exe --version

# Vérifier que l'environnement virtuel est intact
env\Scripts\python.exe -c "import sys; print('Env Python OK:', sys.executable)"
```

## Étape 2 — Dépendances Python

```powershell
env\Scripts\python.exe -c "
imports_requis = [
    ('cv2', 'opencv-python'),
    ('pytesseract', 'pytesseract'),
    ('numpy', 'numpy'),
    ('openpyxl', 'openpyxl'),
    ('docx', 'python-docx'),
    ('PIL', 'Pillow'),
    ('fpdf', 'fpdf2'),
    ('pandas', 'pandas'),
]
ok, ko = [], []
for module, package in imports_requis:
    try:
        m = __import__(module)
        version = getattr(m, '__version__', '?')
        ok.append(f'  ✓ {package} ({version})')
    except ImportError:
        ko.append(f'  ✗ {package} MANQUANT')

print('DÉPENDANCES OK:')
for line in ok: print(line)
if ko:
    print('DÉPENDANCES MANQUANTES:')
    for line in ko: print(line)
    print()
    print('Corriger avec: env\Scripts\pip install -r requirements.txt')
"
```

## Étape 3 — Tesseract OCR

```powershell
env\Scripts\python.exe -c "
from config import Config
from pathlib import Path
import subprocess

path = Path(Config.TESSERACT_PATH)
print('Chemin configuré:', path)

if not path.exists():
    print('ERREUR: Tesseract introuvable à ce chemin.')
    print('Solutions:')
    print('  1. Installer Tesseract depuis: https://github.com/UB-Mannheim/tesseract/wiki')
    print('  2. Mettre à jour TESSERACT_PATH dans config.py')
else:
    result = subprocess.run([str(path), '--version'], capture_output=True, text=True)
    print('Version Tesseract:', result.stderr.split()[1] if result.stderr else '?')
    
    # Vérifier le fichier de langue française
    tessdata = path.parent / 'tessdata' / 'fra.traineddata'
    if tessdata.exists():
        print('Langue française (fra): OK')
    else:
        print('ERREUR: fra.traineddata absent de', tessdata.parent)
        print('Télécharger depuis: https://github.com/tesseract-ocr/tessdata')
"
```

## Étape 4 — Fichiers de configuration critiques

Vérifie que ces fichiers existent et sont lisibles :
- `config.py` — configuration principale
- `templates.json` — modèles de tableau
- `TriosSeconverter.spec` — fichier de compilation PyInstaller
- `requirements.txt` — liste des dépendances
- `Contexte\PROCESSUS_OCR.md` — documentation technique

## Étape 5 — Rapport de diagnostic

Présente un tableau récapitulatif :

```
COMPOSANT               | STATUT  | DÉTAIL
Python (env\)           |   ✓ OK  | Python 3.11.x
opencv-python           |   ✓ OK  | 4.8.0
pytesseract             |   ✓ OK  | 0.3.13
Tesseract OCR           |   ✓ OK  | v5.3.0
Langue française (fra)  |   ✓ OK  | fra.traineddata présent
templates.json          |   ✓ OK  | 2 modèles
```

Conclus par : "Environnement PRÊT" ou liste précise des actions à effectuer.
