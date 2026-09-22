Alimente le dictionnaire de correction OCR depuis un fichier Excel corrigé manuellement.

Tu es un ingénieur données qui extrait les valeurs validées d'un Excel pour améliorer les futures extractions OCR.

## Contexte

Après une extraction, l'utilisateur corrige manuellement les erreurs OCR dans le fichier Excel.
Ce skill lit ces corrections et les mémorise dans `data_dictionary.json` pour que les prochaines extractions soient automatiquement plus précises.

## Étape 1 — Identifier le fichier source

Demande à l'utilisateur : "Quel est le nom du fichier Excel corrigé ?"
(Par défaut : `tous_les_borniers_corrigé.xlsx` dans le dossier courant)

Vérifie que le fichier existe avant de continuer.

## Étape 2 — État actuel du dictionnaire

```powershell
env\Scripts\python.exe -c "
from data_dictionary import get_dictionary
dico = get_dictionary()
stats = dico.stats()
print('Dictionnaire actuel:')
if not stats:
    print('  (vide — première utilisation)')
else:
    for col, n in stats.items():
        print(f'  {col}: {n} valeurs connues')
"
```

## Étape 3 — Import des corrections

```powershell
env\Scripts\python.exe -c "
from data_dictionary import get_dictionary
from pathlib import Path

fichier = Path('tous_les_borniers_corrige.xlsx')  # adapter le nom
dico = get_dictionary()
stats_avant = dico.stats()

ajouts = dico.update_from_excel(fichier)

print('Nouvelles valeurs ajoutées:')
if not ajouts:
    print('  Aucune nouvelle valeur (tout était déjà connu)')
else:
    for col, n in ajouts.items():
        print(f'  {col}: +{n} valeur(s)')

stats_apres = dico.stats()
print()
print('Dictionnaire mis à jour:')
for col, n in stats_apres.items():
    avant = stats_avant.get(col, 0)
    print(f'  {col}: {n} valeurs (+{n - avant})')
"
```

## Étape 4 — Vérification des données ajoutées

Affiche un échantillon de 5 valeurs par colonne pour que l'utilisateur puisse vérifier :

```powershell
env\Scripts\python.exe -c "
from data_dictionary import get_dictionary
dico = get_dictionary()
for col in ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']:
    vals = dico.get_all(col)
    print(f'{col} ({len(vals)} valeurs) — exemples: {vals[:5]}')
"
```

## Étape 5 — Confirmation

Indique à l'utilisateur :
- Combien de nouvelles valeurs ont été apprises au total
- Que le dictionnaire est sauvegardé dans `data_dictionary.json`
- Que ces corrections seront appliquées **automatiquement** lors de la prochaine conversion
- Conseil : "Plus vous corrigez d'extractions, plus le dictionnaire s'améliore."
