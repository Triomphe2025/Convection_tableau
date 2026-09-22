# Règle 02 — Standards de code Python

## Style général

- **Langue des logs et messages** : français uniquement
- **Commentaires** : sur le POURQUOI uniquement, jamais sur le QUOI
- **Docstrings** : une ligne max — jamais de docstrings multi-paragraphes
- **Nommage** : snake_case pour fonctions/variables, PascalCase pour classes
- **Longueur de ligne** : 99 caractères maximum (config flake8 `.flake8`)

## Ce qu'il ne faut jamais écrire

```python
# INTERDIT — commentaire qui dit le quoi
def calculate_sum(a, b):
    # Add a and b together
    return a + b

# AUTORISÉ — commentaire qui dit le pourquoi
def calculate_sum(a, b):
    # Les négatifs sont permis car les corrections OCR peuvent être négatives
    return a + b
```

## Paramètres et rétrocompatibilité

Tout nouveau paramètre de fonction **doit** avoir une valeur par défaut :

```python
# BON
def extract_vector_pdf(path: Path, page_indices: list = None) -> CadDocument:
    ...

# MAUVAIS — casse les appels existants
def extract_vector_pdf(path: Path, page_indices: list) -> CadDocument:
    ...
```

## Gestion des erreurs

- **Erreurs récupérables** : une image ratée ne stoppe pas le traitement global
- **Pas de `except Exception: pass`** sauf dans les boucles de dessin (CAD)
- **Logger l'erreur** avant de continuer : `_log(f"✗ Erreur page {i}: {e}", 'err')`
- **Pas de validation à l'intérieur** — valider uniquement aux frontières (input utilisateur, API externe)

## Imports

```python
# Ordre : stdlib → third-party → local
import math
import os
from pathlib import Path

import fitz
import ezdxf

from .models import CadDocument
```

## Encodage

Toujours spécifier `encoding='utf-8'` lors de l'ouverture de fichiers texte :
```python
with open(path, 'r', encoding='utf-8') as f:
    ...
```

## Variables d'environnement

Toujours définir `PYTHONIOENCODING=utf-8` et `PYTHONUTF8=1` dans l'environnement
(configuré dans `.claude/settings.json`).

## Anti-patterns à éviter

- Pas de `globals()` ou `locals()` dynamiques
- Pas de `eval()` ou `exec()`
- Pas de chemins absolus hardcodés — toujours via `config.py` ou `Path(__file__).parent`
- Pas de `import *`
- Pas de print() en production — utiliser les callbacks `on_log`
