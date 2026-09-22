# /optimiser-prompt-claude

Agent interactif pour tester et affiner le prompt Claude Vision sur une image réelle, jusqu'à obtenir un résultat satisfaisant.

## Objectif

Permettre à l'utilisateur de voir exactement ce que Claude Vision extrait d'une image, comparer avec le résultat attendu, et itérer sur le prompt jusqu'à ce que l'extraction soit correcte — sans relancer toute la conversion.

## Déclenchement

L'utilisateur lance : `/optimiser-prompt-claude`

Il peut préciser une image : `/optimiser-prompt-claude exemple traitement\repartiteur 2\page_pdf_019.png`

## Protocole de l'agent

### Étape 1 — Identifier l'image à tester

Si l'utilisateur a fourni un chemin d'image, l'utiliser.
Sinon, chercher dans cet ordre :
1. `exemple traitement\` — images de test
2. `images_repartiteur\` — premières 5 images
3. `images_borniers\` — premières 5 images

Afficher la liste et demander à l'utilisateur quelle image tester.

### Étape 2 — Identifier le template applicable

Lire `templates.json` et afficher les templates disponibles avec leurs colonnes.
Demander à l'utilisateur quel template correspond à l'image choisie.

Si l'utilisateur ne sait pas, inspecter le nom de l'image ou du dossier pour déduire :
- `repartiteur` → template avec FIL/TENANT/SIGNAL/ABOUTISSANT
- `borniers` → template avec BORNE/COULEUR/SIGNAL/JARRETIERES

### Étape 3 — Afficher le prompt actuel

Lire `claude_ocr.py`, extraire la fonction `_build_prompt()`, et générer le prompt tel qu'il sera envoyé à l'API avec ce template.

Afficher le prompt complet. Demander si l'utilisateur veut le voir avant de tester.

### Étape 4 — Lancer le test via test_vision.py

Vérifier que `test_vision.py` existe. Si non, le créer selon le modèle ci-dessous.

Lancer :
```
.\env\Scripts\python.exe test_vision.py "<chemin_image>" "<nom_template>" <cle_api>
```

La clé API est récupérée depuis :
1. `Config.CLAUDE_API_KEY` dans `config.py`
2. Sinon demander à l'utilisateur de la fournir (elle ne sera pas stockée)

Capturer et afficher la sortie complète.

### Étape 5 — Analyser le résultat

Comparer le résultat obtenu avec ce que l'image devrait donner (en demandant à l'utilisateur si nécessaire).

Identifier les problèmes de la liste suivante :
- **Distribution colonnes** : une valeur dans la mauvaise colonne (ex: code borne dans SIGNAL)
- **Valeur perdue** : une cellule non-vide dans l'image qui est vide dans le résultat
- **Valeur inventée** : une cellule dans le résultat qui n'existe pas dans l'image
- **Erreur OCR** : valeur présente mais mal lue (ex: JTAAG107 → JrAJIG107)
- **Ligne manquante** : une ligne de données absente du résultat
- **Ligne fantôme** : une ligne dans le résultat qui n'est pas dans l'image (pied de page mal filtré)
- **Métadonnées incorrectes** : PAGE, BORNIER, PET mal extraites

Pour chaque problème identifié, diagnostiquer la cause probable dans le prompt actuel.

### Étape 6 — Proposer des améliorations au prompt

Pour chaque problème diagnostiqué :
1. Citer la section du prompt actuel responsable du problème (ou son absence)
2. Proposer une formulation améliorée — courte, précise, avec exemple concret
3. Justifier pourquoi cette formulation fonctionne mieux

Principes d'un bon prompt Claude Vision pour des tableaux industriels :
- **Exemple concret > règle abstraite** : montrer le bon et le mauvais résultat avec les valeurs exactes de l'image
- **Peu de règles, claires** : trop de restrictions contradictoires confusent le modèle
- **Nommer les valeurs problématiques** : si `01B` cause un problème, le citer explicitement
- **Priorité explicite** : si deux règles peuvent entrer en conflit, dire laquelle prime
- **Pas de règle qui s'annule** : vérifier que les règles ajoutées ne contredisent pas les précédentes

### Étape 7 — Appliquer et re-tester

Proposer d'appliquer les modifications au fichier `claude_ocr.py` (fonction `_build_prompt()`).

Avant d'appliquer :
- Montrer le diff exact (ancienne version → nouvelle version)
- Demander confirmation

Après application :
- Relancer le test sur la même image
- Comparer le nouveau résultat avec l'ancien
- Si le problème est résolu : confirmer et proposer de tester d'autres images
- Si un nouveau problème apparaît : itérer depuis l'étape 5

### Étape 8 — Valider sur plusieurs images

Quand le résultat est satisfaisant sur l'image cible, proposer de tester sur 2 autres images du même type pour vérifier qu'on n'a pas créé de régression.

Si une régression est détectée sur une autre image, diagnostiquer le conflit et trouver une formulation qui satisfait les deux cas.

## Règles de conduite de l'agent

- Ne jamais modifier `claude_ocr.py` sans montrer le diff et obtenir confirmation
- Ne jamais stocker la clé API dans un fichier
- Toujours tester après chaque modification — ne pas enchainer plusieurs modifications sans tester
- Si après 3 itérations le problème persiste, envisager une approche différente (ex: changer le format de sortie demandé à Claude)
- Rester concis dans les explications — l'utilisateur est ingénieur, pas développeur

## Format de rapport final

À la fin des itérations, produire un résumé :

```
RÉSUMÉ OPTIMISATION PROMPT
===========================
Image testée       : <chemin>
Template           : <nom>
Problèmes résolus  : <liste>
Problèmes restants : <liste ou "aucun">
Modifications faites dans claude_ocr.py :
  - <section modifiée> : <description du changement>
Recommandation     : <tester sur l'ensemble / ajuster data_dictionary / autre>
```
