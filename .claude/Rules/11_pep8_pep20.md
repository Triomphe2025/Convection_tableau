# Règle 11 — PEP 8 et PEP 20 (Zen of Python)

## PEP 8 — Style de code Python (conformité obligatoire)

Référence officielle : https://peps.python.org/pep-0008/

### Indentation
```python
# CORRECT — 4 espaces (jamais de tabulations)
def ma_fonction():
    if condition:
        return valeur

# INTERDIT
def ma_fonction():
  if condition:    # 2 espaces → interdit
      return valeur
```

### Longueur de ligne
```python
# Maximum 99 caractères (configuré dans .flake8)
# Couper les longues expressions avec parenthèses
result = (
    valeur_longue_1
    + valeur_longue_2
    + valeur_longue_3
)

# Couper les appels de fonctions
widget = tk.Label(
    parent,
    text="Mon texte long",
    font=FONT_BOLD,
    fg=FG_TEXT,
)
```

### Espaces autour des opérateurs
```python
# CORRECT
x = 1
y = x + 2
liste[0] = valeur
dico['cle'] = 'valeur'
fonction(arg1, arg2, kwarg=valeur)

# INTERDIT
x=1          # pas d'espaces autour de =
y = x+2      # pas d'espaces autour de +
liste [0]    # espace avant [
```

### Imports
```python
# ORDRE OBLIGATOIRE (isort) :
# 1. Bibliothèques standard
import math
import os
from pathlib import Path

# 2. Bibliothèques tierces
import fitz
import ezdxf
import numpy as np

# 3. Modules locaux
from .models import CadDocument
from config import Config

# RÈGLES :
# - 1 import par ligne (sauf from ... import a, b)
# - Pas de import *
# - Imports inutilisés → supprimer (cf. /auditer-code-mort)
```

### Nommage
```python
# Fonctions et variables → snake_case
def extraire_geometrie():
    page_index = 0
    all_entities = []

# Classes → PascalCase
class CadDocument:
    pass

class BornierTableExtractor:
    pass

# Constantes → UPPER_SNAKE_CASE (dans config.py)
PAGE_SIZE = 48
TESSERACT_PATH = r"C:\Tesseract\..."

# Attributs privés → _prefixe
self._nav_frame = None
self._result = None

# Méthodes privées → _prefixe
def _build_nav(self):
    ...
```

### Espaces dans les fonctions
```python
# CORRECT
def fonction(a, b, c=None):
    ...

# INTERDIT
def fonction( a, b, c = None ):  # espaces superflus
    ...
```

### Docstrings
```python
# CORRECT — une seule ligne si évident
def _pt(v: float) -> float:
    """Convertit des points PDF en millimètres."""
    return v * 25.4 / 72.0

# INTERDIT — docstring inutile qui répète le nom
def _pt(v: float) -> float:
    """
    This function converts points to millimeters.
    It takes a float v and returns a float.
    """
    ...
```

### Comparaisons
```python
# CORRECT
if value is None:        # pas if value == None
if value is not None:    # pas if value != None
if items:                # pas if len(items) > 0
if not items:            # pas if len(items) == 0

# Types booléens
if flag:                 # pas if flag == True
if not flag:             # pas if flag == False
```

### Retours de fonction
```python
# CORRECT — cohérent
def trouver(items, cible):
    for item in items:
        if item == cible:
            return item
    return None  # retour explicite

# INTERDIT — retour implicite None mélangé avec retour valeur
def trouver(items, cible):
    for item in items:
        if item == cible:
            return item
    # retour implicite None → peu clair
```

---

## PEP 20 — Le Zen de Python (principes directeurs)

Référence : `import this` dans Python

### Les 19 principes appliqués au projet

| Principe | Application concrète dans TriosSeconverter |
|----------|-------------------------------------------|
| **Beau vaut mieux que laid** | Code lisible, nommage explicite, pas de one-liners obscurs |
| **Explicite vaut mieux qu'implicite** | `return None` explicite, type hints sur les APIs publiques |
| **Simple vaut mieux que complexe** | 1 fichier = 1 responsabilité, pas de surarchitecture |
| **Complexe vaut mieux que compliqué** | Un module cad/ structuré vaut mieux que tout dans ocr_processor.py |
| **Plat vaut mieux qu'imbriqué** | Maximum 3 niveaux d'indentation — extraire en sous-fonctions sinon |
| **Épars vaut mieux que dense** | 1 idée par ligne, pas de `;` pour chaîner des instructions |
| **La lisibilité compte** | Noms de variables/fonctions en français ou anglais cohérent |
| **Les cas spéciaux ne sont pas assez spéciaux** | Pas d'exceptions à l'architecture sans discussion |
| **Les erreurs ne devraient jamais passer silencieusement** | Jamais de `except: pass` — toujours logger l'erreur |
| **Face à l'ambiguïté, résiste à deviner** | Si le comportement est incertain, demander ou documenter |
| **Il devrait y avoir une façon évidente de faire** | Utiliser les fonctions existantes avant d'en créer |
| **Maintenant vaut mieux que jamais** | Écrire les tests maintenant, pas "plus tard" |
| **Jamais vaut mieux que maintenant, si c'est compliqué** | Ne pas implémenter une feature non demandée |
| **Si l'implémentation est difficile à expliquer, c'est une mauvaise idée** | Code qui ne peut pas être expliqué simplement = à revoir |
| **Les espaces de nommage sont une bonne idée** | Modules séparés (cad/, tests/) plutôt que tout dans un seul fichier |

### Applications directes

```python
# PEP 20 : "Explicite vaut mieux qu'implicite"
# BIEN
def extract_vector_pdf(path: Path, page_indices: list = None) -> CadDocument:
    ...

# MAL
def extract(p, idx=None):  # noms opaques
    ...

# PEP 20 : "Plat vaut mieux qu'imbriqué"
# BIEN — max 3 niveaux
def _process(items):
    for item in items:
        if item.valid:
            return _transform(item)
    return None

# MAL — trop imbriqué
def _process(items):
    for item in items:
        if item:
            if item.valid:
                if item.value:
                    for sub in item.subs:
                        if sub.ok:
                            ...

# PEP 20 : "Les erreurs ne devraient jamais passer silencieusement"
# BIEN
try:
    result = process(data)
except ValueError as e:
    _log(f"✗ Erreur traitement page {i}: {e}", 'err')
    continue  # on continue avec la prochaine page

# MAL
try:
    result = process(data)
except:
    pass  # erreur silencieuse — interdit
```

---

## Vérification automatique PEP 8

Le fichier `.flake8` à la racine du projet configure la vérification :

```ini
[flake8]
max-line-length = 99
exclude = env/, .claude/, __pycache__/
ignore = E124  # closing bracket indentation (style acceptable)
```

Pour vérifier manuellement :
```powershell
env\Scripts\python.exe -m flake8 interface.py converter.py ocr_processor.py cad/
```

L'agent Auditeur exécute cette vérification automatiquement sur tout code soumis.
