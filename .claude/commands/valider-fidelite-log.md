# /valider-fidelite-log

## Objectif
Vérifier qu'un fichier `*_claude.jsonl` est complet et fidèle : toutes les entrées contiennent `rows_data`, et que rejouer le log produirait un Excel identique à l'original.

## Contexte — pourquoi ce skill existe
En v1.x, le log Claude ne stockait pas `rows_data` (les lignes déjà parsées). Lors d'un replay, `LogReplayer` re-parsait `raw` (la réponse brute), ce qui pouvait produire des différences si la logique de `_parse_pipe_response()` avait changé entre les deux exécutions. Le champ `rows_data` a été ajouté pour garantir un replay 100 % fidèle.

## Usage
```
/valider-fidelite-log
/valider-fidelite-log chemin/vers/mon_fichier_claude.jsonl
```
Sans argument : cherche automatiquement le log le plus récent (`*_claude.jsonl`).

## Ce que fait ce skill

### Étape 1 — Localiser le fichier log
- Argument fourni → utiliser ce chemin
- Sinon → chercher `*_claude.jsonl` dans le dossier courant et sous-dossiers

### Étape 2 — Analyser chaque entrée
Pour chaque ligne du JSONL :
```
✅ success=True, rows_data présent   → replay exact garanti
⚠️  success=True, rows_data absent   → fallback re-parsing (risque de différence)
❌ success=False                     → image non traitée (erreur API)
```

### Étape 3 — Détecter les incohérences
- Entrées avec `rows_data` vide (`[]`) mais `rows > 0` → données perdues
- Entrées où `len(rows_data) != entry['rows']` → comptage incohérent
- Entrées sans champ `image` → impossible d'identifier la source

### Étape 4 — Tester le re-parsing des entrées legacy
Pour les entrées sans `rows_data` (anciens logs) :
- Re-parser `raw` avec `_parse_pipe_response()`
- Comparer le nombre de lignes obtenu avec `entry['rows']`
- Si différence → signaler (le replay pourrait produire moins/plus de lignes)

### Étape 5 — Rapport synthétique
```
Fichier analysé : VD23111PE162_claude.jsonl
Entrées totales : 24
  ✅ Complètes (rows_data présent)  : 22 / 24
  ⚠️  Legacy (sans rows_data)        :  2 / 24  → lignes 8, 19
  ❌ Erreurs API                    :  0 / 24
Taux de fidélité garanti           : 92 %

Entrées à risque :
  Ligne 8  — bornier_8.jpg — 12 lignes — re-parse OK (12 lignes)
  Ligne 19 — bornier_19.jpg — 7 lignes  — re-parse OK (7 lignes)

Verdict : replay faisable, résultat probablement identique mais non garanti à 100 %.
Pour garantir 100 % : relancer l'extraction avec OCR_MODE="claude" pour régénérer le log.
```

### Action recommandée
Si des entrées legacy existent et que la fidélité est critique :
1. Relancer l'extraction depuis les images sources (`OCR_MODE = "claude"`)
2. Le nouveau log contiendra `rows_data` sur toutes les entrées
3. Replay garanti identique
