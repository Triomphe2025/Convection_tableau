Valide l'intégrité complète du classeur Excel généré par TriosSeconverter.

Tu es un ingénieur de validation qui s'assure que le fichier Excel est conforme aux exigences avant livraison.

## Étape 1 — Localiser le classeur

Cherche `tous_les_borniers.xlsx` dans le dossier courant ou dans le dossier de sortie.
Si introuvable, demande à l'utilisateur d'indiquer le chemin.

## Étape 2 — Analyse structurelle

```powershell
env\Scripts\activate
python -c "
import openpyxl
from pathlib import Path

wb = openpyxl.load_workbook('tous_les_borniers.xlsx')
print('Feuilles:', wb.sheetnames)

for ws_name in wb.sheetnames:
    ws = wb[ws_name]
    print(f'\n=== Feuille: {ws_name} ===')
    print(f'Dimensions: {ws.dimensions}')
    print(f'Lignes utilisées: {ws.max_row}')
    print(f'Colonnes utilisées: {ws.max_column}')
    print(f'Sauts de page: {len(ws.row_breaks.brk)}')
    print(f'Zone impression: {ws.print_area}')
"
```

## Étape 3 — Vérifications métier

Exécute ces vérifications et signale chaque anomalie :

```powershell
python -c "
import openpyxl, re
from config import Config

wb = openpyxl.load_workbook('tous_les_borniers.xlsx')
ws = wb['Borniers']
page_size = Config.PAGE_SIZE
problemes = []

# 1. Vérifier que chaque bloc de PAGE_SIZE lignes a un pied de page
for row_idx in range(page_size - 1, ws.max_row, page_size):
    cell_val = str(ws.cell(row=row_idx, column=2).value or '')
    if 'NO PLAN' not in cell_val.upper() and 'INDICE' not in cell_val.upper():
        problemes.append(f'Ligne {row_idx}: pied de page manquant ou mal positionné')

# 2. Vérifier que la première ligne de chaque bornier est un en-tête
for row_idx in range(1, ws.max_row, page_size):
    cell = ws.cell(row=row_idx, column=1)
    if not cell.font or not cell.font.bold:
        problemes.append(f'Ligne {row_idx}: en-tête attendu mais non trouvé')

# 3. Compter les borniers
n_borniers = ws.max_row // page_size
print(f'Borniers détectés: {n_borniers}')
print(f'Problèmes: {len(problemes)}')
for p in problemes[:20]:
    print(f'  - {p}')
"
```

## Étape 4 — Vérification de la feuille "tableaux word"

Si la feuille "tableaux word" est présente :
- Vérifier qu'elle n'est pas vide
- Vérifier que ses données ne se retrouvent PAS dans la feuille "Borniers" (pas de doublon)

## Étape 5 — Rapport de validation

Affiche un bilan clair :

✅ Structure : X feuilles présentes (Borniers + tableaux word)
✅ Pagination : X borniers, X sauts de page
✅ Pieds de page : X/X borniers ont un pied complet
⚠️ ou ❌ pour chaque anomalie détectée

Conclus par : "Classeur VALIDE pour livraison" ou "Classeur INVALIDE — X corrections nécessaires."
