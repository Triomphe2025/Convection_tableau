# /auditer-code-mort

## Objectif
Détecter les fonctions, classes, variables et imports définis dans le projet mais jamais appelés dans le code actif.

## Contexte — pourquoi ce skill existe
En v1.x, `claude_ocr.py` contenait `_parse_response()`, `_apply_post_corrections()`, `_fix_borne_in_signal()`, `_POST_CORRECTIONS` et `_COL_DESCRIPTIONS` — du code de l'ancienne implémentation JSON qui n'était plus appelé depuis la migration vers le format pipe-séparé. Ce code mort créait un risque d'erreur si quelqu'un le modifiait ou s'y fiait par accident.

## Fichiers à analyser
- `claude_ocr.py` — moteur Claude Vision
- `ocr_processor.py` — moteur Tesseract
- `converter.py` — orchestration
- `generer_classeur.py` — génération Excel
- `interface.py` — interface graphique
- `template.py` — modèles de tableau
- `data_dictionary.py` — corrections OCR

## Ce que fait ce skill

### Étape 1 — Recenser les définitions
Pour chaque fichier, lister :
- Fonctions `def` et méthodes privées `_xxx()`
- Variables module-level (dicts, listes, constantes)
- Classes et leurs méthodes publiques

### Étape 2 — Chercher les usages
Pour chaque élément recensé, rechercher dans **tout le projet** :
```
grep -rn "nom_fonction\|nom_variable" *.py
```
- Si aucun appel trouvé en dehors de la définition elle-même → candidat au code mort

### Étape 3 — Valider avant suppression
Avant de marquer comme "mort", vérifier :
- L'élément est-il exporté et utilisé depuis un autre module ?
- Est-il référencé dans un commentaire ou un test ?
- Est-il dans un chemin de code conditionnel rarement atteint (ex : `if Config.OCR_MODE == "..."`) ?

### Étape 4 — Rapport classé par priorité

**🔴 Suppression sûre** (non appelé, non importé, non testé)
```
claude_ocr.py:52  _COL_DESCRIPTIONS — dict jamais référencé
claude_ocr.py:169 _fix_borne_in_signal() — non appelée en dehors de _apply_post_corrections()
...
```

**🟡 À vérifier** (appelé conditionnellement ou dans un test)
```
ocr_processor.py:XXXX  _extract_page_ocr() — appelée seulement si mode PDF raster
...
```

**🟢 Actif** — ne pas toucher

### Étape 5 — Suppression (si validé par l'utilisateur)
Supprimer les éléments 🔴, vérifier que les tests passent, mettre à jour CLAUDE.md si une fonction documentée est supprimée.
