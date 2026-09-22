Compare deux extractions Excel pour détecter les régressions ou mesurer l'impact d'une modification OCR.

Tu es un ingénieur qualité qui compare deux classeurs Excel produits à des moments différents
pour identifier ce qui a changé : nouvelles erreurs, corrections, données manquantes ou gagnées.

## Contexte

Utile dans ces situations :
- Après une modification de `ocr_processor.py` : a-t-on amélioré ou dégradé ?
- Après ajout de corrections dans `data_dictionary.json` : combien d'erreurs corrigées ?
- Avant livraison : comparer avec la version précédente pour valider la régression zéro.

## Étape 1 — Identifier les deux fichiers à comparer

Demander à l'utilisateur :
- **Fichier référence** (ancienne version) : ex: `tous_les_borniers_v1.xlsx`
- **Fichier courant** (nouvelle version) : ex: `tous_les_borniers.xlsx`

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
xlsx = list(Path('.').glob('*.xlsx'))
print('Fichiers Excel disponibles :')
for f in xlsx:
    taille = f.stat().st_size // 1024
    print(f'  {f.name} ({taille} Ko)')
"
```

Si un seul fichier existe, proposer de comparer avec le Git précédent :
```powershell
git show HEAD~1:tous_les_borniers.xlsx > tous_les_borniers_ref.xlsx 2>$null
```

## Étape 2 — Comparaison cellule par cellule

```powershell
env\Scripts\python.exe -c "
import openpyxl
from pathlib import Path

REF   = 'tous_les_borniers_ref.xlsx'   # Ancienne version
ACTUEL = 'tous_les_borniers.xlsx'       # Nouvelle version

if not Path(REF).exists():
    print(f'ERREUR : fichier référence \"{REF}\" introuvable.')
    print('Copier l\ancienne version et la renommer en tous_les_borniers_ref.xlsx')
    exit()

wb_ref   = openpyxl.load_workbook(REF,    read_only=True)
wb_act   = openpyxl.load_workbook(ACTUEL, read_only=True)

ws_ref = wb_ref['Borniers']
ws_act = wb_act['Borniers']

print(f'Référence : {ws_ref.max_row} lignes | Actuel : {ws_act.max_row} lignes')
print()

differences = []
n_identiques = 0
n_vides_ref  = 0  # cellule vide dans ref, remplie dans actuel → gain OCR
n_vides_act  = 0  # cellule remplie dans ref, vide dans actuel → régression

max_row = min(ws_ref.max_row, ws_act.max_row)
for row in range(1, max_row + 1):
    for col in range(1, 6):  # Colonnes BORNE à JARRETIERES
        v_ref = str(ws_ref.cell(row, col).value or '').strip()
        v_act = str(ws_act.cell(row, col).value or '').strip()
        if v_ref == v_act:
            n_identiques += 1
        elif not v_ref and v_act:
            n_vides_ref += 1
            differences.append(('GAIN',   row, col, v_ref, v_act))
        elif v_ref and not v_act:
            n_vides_act += 1
            differences.append(('PERTE',  row, col, v_ref, v_act))
        else:
            differences.append(('MODIF',  row, col, v_ref, v_act))

print(f'Cellules identiques : {n_identiques}')
print(f'Gains OCR (vide→texte) : {n_vides_ref}')
print(f'Pertes OCR (texte→vide): {n_vides_act}')
print(f'Modifications          : {len([d for d in differences if d[0]==\"MODIF\"])}')
print()

if differences:
    print('=== 20 PREMIÈRES DIFFÉRENCES ===')
    for typ, row, col, avant, apres in differences[:20]:
        print(f'  {typ:6} L{row:04}C{col} | AVANT: \"{avant[:25]:<25}\" | APRÈS: \"{apres[:25]}\"')
else:
    print('Aucune différence — les deux fichiers sont identiques.')

wb_ref.close()
wb_act.close()
"
```

## Étape 3 — Comparaison des pieds de page (métadonnées)

```powershell
env\Scripts\python.exe -c "
import openpyxl, re
from pathlib import Path
from config import Config

REF    = 'tous_les_borniers_ref.xlsx'
ACTUEL = 'tous_les_borniers.xlsx'

if not Path(REF).exists():
    print('Fichier référence introuvable. Voir étape 1.')
    exit()

PAGE_SIZE = Config.PAGE_SIZE

def extraire_meta(wb_path):
    wb = openpyxl.load_workbook(wb_path, read_only=True)
    ws = wb['Borniers']
    meta = []
    for i in range(0, ws.max_row, PAGE_SIZE):
        pied = str(ws.cell(row=i + PAGE_SIZE - 1, column=2).value or '')
        bornier = re.search(r'BORNIER\s*:\s*([A-Z0-9\-]+)', pied)
        page    = re.search(r'PAGE\s*:\s*(\d+)', pied)
        meta.append({
            'bornier': bornier.group(1) if bornier else '?',
            'page':    page.group(1)    if page    else '?',
        })
    wb.close()
    return meta

meta_ref = extraire_meta(REF)
meta_act = extraire_meta(ACTUEL)

print(f'Borniers référence : {len(meta_ref)} | Borniers actuel : {len(meta_act)}')
borniers_ref = {m['bornier'] for m in meta_ref}
borniers_act = {m['bornier'] for m in meta_act}

perdus   = borniers_ref - borniers_act
nouveaux = borniers_act - borniers_ref

if perdus:
    print(f'BORNIERS PERDUS : {sorted(perdus)}')
if nouveaux:
    print(f'BORNIERS GAGNÉS : {sorted(nouveaux)}')
if not perdus and not nouveaux:
    print('Même liste de borniers dans les deux versions.')
"
```

## Étape 4 — Rapport de comparaison

```
RAPPORT DE COMPARAISON — TriosSeconverter
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Référence : [fichier_ref.xlsx] — XX lignes — XX borniers
Actuel    : [fichier_actuel.xlsx] — XX lignes — XX borniers

DONNÉES
  Cellules identiques : XXXX (XX%)
  Gains OCR           : XX cellules (texte apparu dans la nouvelle version)
  Pertes OCR          : XX cellules (texte disparu — régression potentielle)
  Modifications       : XX cellules (valeur différente)

BORNIERS
  Perdus   : [liste] ou Aucun
  Gagnés   : [liste] ou Aucun

VERDICT
  ✓ AMÉLIORATION — XX gains pour XX pertes
  △ NEUTRE — aucune différence significative
  ✗ RÉGRESSION — XX pertes pour XX gains → investiguer avant livraison
```

## Étape 5 — Actions selon le verdict

**Si régression détectée :**
→ Identifier les cellules perdues et vérifier si les images correspondantes
  existent toujours dans `images_borniers/`
→ Comparer les paramètres OCR entre les deux versions (git diff ocr_processor.py)
→ Utiliser `/analyser-image-profonde` sur les images régressées

**Si amélioration confirmée :**
→ Sauvegarder les nouvelles corrections dans `data_dictionary.json`
→ Documenter le changement dans l'historique CLAUDE.md
→ Archiver le fichier de référence : `copy tous_les_borniers.xlsx tous_les_borniers_v[X.Y].xlsx`
