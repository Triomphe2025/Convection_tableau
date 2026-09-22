Génère un rapport de livraison complet avant de remettre le classeur au client ou à l'équipe.

Tu es un ingénieur chef de projet qui consolide tous les contrôles qualité en un seul rapport de livraison.

## Contexte

Ce skill enchaîne automatiquement tous les contrôles nécessaires avant livraison et produit un rapport structuré.

## Étape 1 — Collecter les informations du projet

Lis `config.py` pour obtenir : STATION_NAME, OCR_LANGUAGE, TESSERACT_PATH.
Demande à l'utilisateur :
- Numéro du plan : (ex: VD23111 PE 162)
- Date de livraison : (défaut : aujourd'hui)
- Destinataire : (ex: Bureau d'études)

## Étape 2 — Vérification de l'environnement

Lance les vérifications de base :
```powershell
env\Scripts\python.exe -c "
import pytesseract, cv2, openpyxl, docx
from config import Config
from pathlib import Path

print('=== ENVIRONNEMENT ===')
print('Tesseract:', pytesseract.get_tesseract_version())
print('OpenCV:', cv2.__version__)
print('openpyxl:', openpyxl.__version__)
print('Station:', Config.STATION_NAME)
print('PAGE_SIZE:', Config.PAGE_SIZE)
print()

# Fichiers de sortie
for f in ['tous_les_borniers.xlsx', 'tous_les_borniers.docx']:
    p = Path(f)
    if p.exists():
        size_ko = p.stat().st_size // 1024
        print(f'{f}: {size_ko} Ko')
    else:
        print(f'{f}: ABSENT')
"
```

## Étape 3 — Statistiques d'extraction

```powershell
env\Scripts\python.exe -c "
import openpyxl
from config import Config

wb = openpyxl.load_workbook('tous_les_borniers.xlsx', read_only=True)
ws_b = wb['Borniers']
n_borniers = ws_b.max_row // Config.PAGE_SIZE
n_lignes = ws_b.max_row

print(f'Feuille Borniers : {n_borniers} borniers, {n_lignes} lignes')
if 'tableaux word' in wb.sheetnames:
    ws_w = wb['tableaux word']
    n_w = ws_w.max_row // Config.PAGE_SIZE
    print(f'Feuille tableaux word : {n_w} tableaux')
else:
    print('Feuille tableaux word : absente')

from data_dictionary import get_dictionary
dico = get_dictionary()
stats = dico.stats()
total_vals = sum(stats.values())
print(f'Dictionnaire OCR : {total_vals} valeurs connues')
"
```

## Étape 4 — Vérification des sauts de page

```powershell
env\Scripts\python.exe -c "
import openpyxl
from config import Config

wb = openpyxl.load_workbook('tous_les_borniers.xlsx')
ws = wb['Borniers']
n_breaks = len(ws.row_breaks.brk)
n_borniers_attendus = ws.max_row // Config.PAGE_SIZE
print(f'Sauts de page: {n_breaks} (attendu: {n_borniers_attendus - 1})')
print('Zone impression:', ws.print_area)
print('Format papier: A4' if ws.page_setup.paperSize == 9 else 'AUTRE FORMAT')
print('Orientation: Portrait' if ws.page_setup.orientation == 'portrait' else 'PAYSAGE')
"
```

## Étape 5 — Générer le rapport texte

Produis un rapport structuré au format suivant :

```
╔══════════════════════════════════════════════════════════════╗
║           RAPPORT DE LIVRAISON — TRIOSSECONVERTER           ║
╚══════════════════════════════════════════════════════════════╝

DATE           : [date du jour]
PROJET / PLAN  : [numéro de plan]
STATION        : [STATION_NAME de config.py]
DESTINATAIRE   : [saisi par l'utilisateur]
GÉNÉRÉ PAR     : TriosSeconverter v1.2

══════════════════════════════════════════════════════════════
RÉSULTATS D'EXTRACTION
══════════════════════════════════════════════════════════════

  Borniers extraits (OCR)    : XX
  Tableaux Word importés     : XX (feuille "tableaux word")
  Lignes de données totales  : XXXX
  Valeurs OCR corrigées auto : XX (dictionnaire)

══════════════════════════════════════════════════════════════
FICHIERS LIVRÉS
══════════════════════════════════════════════════════════════

  tous_les_borniers.xlsx     : XX Ko — [statut]
  tous_les_borniers.docx     : XX Ko — [statut]

══════════════════════════════════════════════════════════════
CONTRÔLES QUALITÉ
══════════════════════════════════════════════════════════════

  Pagination A4 (48 lg/page) : [✓ OK / ✗ KO]
  Sauts de page Excel        : [✓ OK / ✗ KO]
  Zone d'impression définie  : [✓ OK / ✗ KO]
  Pieds de page complets     : [✓ XX/XX / ✗ XX manquants]
  Feuilles distinctes        : [✓ Borniers + tableaux word]

══════════════════════════════════════════════════════════════
OBSERVATIONS / POINTS D'ATTENTION
══════════════════════════════════════════════════════════════

  [liste des images floues ou borniers avec données manquantes]
  [ou "Aucune observation — extraction propre"]

══════════════════════════════════════════════════════════════
VALIDATION : [APPROUVÉ POUR LIVRAISON / À CORRIGER]
══════════════════════════════════════════════════════════════
```

Demande à l'utilisateur s'il veut sauvegarder ce rapport dans un fichier texte.
