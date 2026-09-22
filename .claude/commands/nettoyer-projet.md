Nettoie les fichiers temporaires et intermédiaires du projet TriosSeconverter.

Tu es un ingénieur de maintenance qui fait le ménage après une série d'extractions pour repartir sur une base propre.

## Étape 1 — Inventaire de ce qui sera supprimé

Avant de supprimer quoi que ce soit, liste les fichiers concernés et demande confirmation :

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
import os

categories = {
    'Images extraites (images_borniers/)': list(Path('images_borniers').glob('*')) if Path('images_borniers').exists() else [],
    'Fichiers Excel générés': list(Path('.').glob('tous_les_borniers*.xlsx')),
    'Fichiers Word générés': list(Path('.').glob('tous_les_borniers*.docx')),
    'Logs (*.log, *.txt temporaires)': list(Path('.').glob('*_log.txt')),
    'Cache pytest (__pycache__)': list(Path('.').glob('**/__pycache__')),
    'Rapports JSON': list(Path('.').glob('analysis_summary.json')),
}

total = 0
for cat, files in categories.items():
    if files:
        taille = sum(f.stat().st_size for f in files if f.is_file()) // 1024
        print(f'{cat}: {len(files)} éléments ({taille} Ko)')
        total += len(files)

print(f'\nTotal: {total} éléments à supprimer')
"
```

## Étape 2 — Confirmation obligatoire

Affiche ce message et attends la réponse de l'utilisateur :

"⚠️ ATTENTION : Cette opération va supprimer les fichiers listés ci-dessus.

Les fichiers suivants sont CONSERVÉS automatiquement :
  ✓ config.py, templates.json, data_dictionary.json
  ✓ Tous les fichiers .py (code source)
  ✓ Contexte\ (documentation)
  ✓ CLAUDE.md et fichiers .md
  ✓ .claude\ (commandes)
  ✓ requirements.txt, install.bat, build_exe.bat

Confirmez-vous le nettoyage ? (oui/non)"

**Ne pas continuer sans confirmation explicite.**

## Étape 3 — Nettoyage sélectif selon la réponse

Si l'utilisateur confirme, propose 3 niveaux :

**Niveau 1 — Nettoyage léger (recommandé)**
Supprime uniquement : __pycache__, *.pyc, logs temporaires
```powershell
env\Scripts\python.exe -c "
import shutil
from pathlib import Path
for p in Path('.').rglob('__pycache__'):
    if 'env\\' not in str(p):
        shutil.rmtree(p, ignore_errors=True)
for p in Path('.').glob('*_log.txt'):
    p.unlink()
print('Nettoyage léger terminé.')
"
```

**Niveau 2 — Nettoyage complet**
En plus du niveau 1 : supprime images_borniers/, tous_les_borniers.xlsx/.docx, analysis_summary.json

**Niveau 3 — Remise à zéro totale**
En plus du niveau 2 : supprime data_dictionary.json (perte des corrections OCR apprises)
⚠️ Déconseillé — avertir l'utilisateur que les corrections seront perdues.

## Étape 4 — Confirmation finale

Affiche les éléments supprimés et l'espace libéré.
Rappelle : "Le projet est prêt pour une nouvelle extraction depuis zéro."
