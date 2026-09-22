Revue d'architecture complète du projet — vérifie que chaque fichier respecte son rôle unique et les conventions du projet.

Tu es un architecte logiciel senior qui inspecte le code source pour détecter les violations des principes
établis dans CLAUDE.md avant qu'elles ne deviennent des bugs en production.

## Étape 1 — Lecture des fichiers à auditer

Lis dans l'ordre : `config.py`, `converter.py`, `interface.py`, `ocr_processor.py`,
`generer_classeur.py`, `word_table_importer.py`, `template.py`, `data_dictionary.py`.

## Étape 2 — Contrôle des 8 règles fondamentales

Pour chaque règle, inspecte le code et signale toute violation avec le fichier et la ligne exacte.

---

### Règle 1 — Séparation des responsabilités

Chaque fichier a UN rôle unique :
- `interface.py` : JAMAIS de logique métier (calculs, OCR, Excel)
- `converter.py` : JAMAIS de code Tkinter ni d'import `tkinter`
- `ocr_processor.py` : JAMAIS d'écriture fichier (openpyxl, docx write)
- `generer_classeur.py` : JAMAIS d'appel Tesseract ou OpenCV

```powershell
env\Scripts\python.exe -c "
import ast, sys
from pathlib import Path

interdits = {
    'interface.py':        ['openpyxl', 'pytesseract', 'cv2'],
    'converter.py':        ['tkinter', 'tk.'],
    'ocr_processor.py':    ['wb.save', 'wb.create_sheet', 'document.save'],
    'generer_classeur.py': ['pytesseract', 'tesseract'],
}

for fichier, mots in interdits.items():
    code = Path(fichier).read_text(encoding='utf-8')
    for mot in mots:
        if mot in code:
            # Trouver la ligne
            for i, line in enumerate(code.splitlines(), 1):
                if mot in line and not line.strip().startswith('#'):
                    print(f'VIOLATION {fichier}:{i} → \"{mot}\" interdit dans ce fichier')
print('Contrôle terminé.')
"
```

---

### Règle 2 — Paramètres dans config.py uniquement

Aucune valeur numérique ou chaîne de configuration ne doit être codée en dur
en dehors de `config.py`.

```powershell
env\Scripts\python.exe -c "
import re
from pathlib import Path

# Patterns suspects : nombres magiques, chemins absolus, noms de colonnes en dur
suspects = [
    (r'[\"\'](BORNE|COULEUR|SIGNAL|JARRETIERES)[\"\']\s*[,\]]', 'Nom de colonne en dur (devrait venir du template)'),
    (r'C:\\\\[A-Za-z]', 'Chemin absolu Windows en dur'),
    (r'(?<![A-Za-z_])(48|300|0\.82|1400)(?![A-Za-z_])', 'Constante magique (PAGE_SIZE/DPI/seuil/résolution)'),
]

fichiers = ['converter.py', 'ocr_processor.py', 'generer_classeur.py', 'interface.py']

for f in fichiers:
    code = Path(f).read_text(encoding='utf-8')
    lines = code.splitlines()
    for pattern, raison in suspects:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line) and not line.strip().startswith('#'):
                print(f'ATTENTION {f}:{i} → {raison}')
                print(f'  {line.strip()[:80]}')
print('Contrôle terminé.')
"
```

---

### Règle 3 — Thread safety Tkinter

Dans `interface.py`, aucune modification de widget ne doit avoir lieu en dehors du thread principal.
Vérifier que toutes les mises à jour passent par `self._queue.put()`.

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
code = Path('interface.py').read_text(encoding='utf-8')
lines = code.splitlines()

# Dans le callback du thread de travail (lambda passée à Converter),
# tout accès à self._log_area, self._progress_bar etc. doit passer par queue
for i, line in enumerate(lines, 1):
    if 'self._log_area' in line or 'self._progress' in line:
        # Vérifier que ce n'est pas dans _poll_queue
        context = '\n'.join(lines[max(0,i-10):i])
        if '_poll_queue' not in context and 'after(' not in context:
            print(f'RISQUE THREAD {i}: {line.strip()[:80]}')

print('Contrôle thread terminé.')
"
```

---

### Règle 4 — Bordures openpyxl sur cellules fusionnées

Dans `generer_classeur.py`, vérifier que les bordures sont posées cellule par cellule,
pas via `merged_cells` directement.

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
code = Path('generer_classeur.py').read_text(encoding='utf-8')
lines = code.splitlines()
for i, line in enumerate(lines, 1):
    if 'merge_cells' in line:
        # Chercher si une bordure est appliquée dans les 5 lignes suivantes
        suivantes = '\n'.join(lines[i:i+5])
        if 'border' not in suivantes.lower():
            print(f'ATTENTION ligne {i}: merge_cells sans bordure explicite après')
            print(f'  {line.strip()}')
print('Contrôle bordures terminé.')
"
```

---

### Règle 5 — Ressources PyInstaller

Dans tous les fichiers qui chargent des ressources (icônes, JSON),
vérifier l'utilisation de `_resource()` ou équivalent `sys._MEIPASS`.

```powershell
env\Scripts\python.exe -c "
import re
from pathlib import Path

for f in Path('.').glob('*.py'):
    if f.name.startswith('test_') or 'env\\\\' in str(f):
        continue
    code = f.read_text(encoding='utf-8')
    # Chercher des open() ou Path() sur des fichiers .ico, .json, .png
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r'open\([\"\']\w+\.(ico|json|png)', line):
            if '_resource' not in line and '_MEIPASS' not in line:
                print(f'RISQUE EXE {f.name}:{i} → ressource sans _resource()')
                print(f'  {line.strip()[:80]}')
print('Contrôle ressources terminé.')
"
```

---

### Règle 6 — Pas de mélange word_results / ocr_results

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
code = Path('converter.py').read_text(encoding='utf-8')
# Chercher toute concaténation des deux listes
import re
for i, line in enumerate(code.splitlines(), 1):
    if re.search(r'ocr_results\s*\+\s*word_results|word_results\s*\+\s*ocr_results', line):
        print(f'BUG CRITIQUE {i}: fusion des deux listes détectée (corrompt les pieds de page)')
        print(f'  {line.strip()}')
print('Contrôle séparation terminé.')
"
```

---

### Règle 7 — Rétrocompatibilité des signatures de fonctions

Toute fonction publique ajoutée récemment doit avoir des paramètres optionnels.

```powershell
env\Scripts\python.exe -c "
import ast
from pathlib import Path

for f in ['generer_classeur.py', 'converter.py', 'ocr_processor.py']:
    tree = ast.parse(Path(f).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
            args = node.args
            n_args = len(args.args)
            n_defaults = len(args.defaults)
            n_required = n_args - n_defaults
            if n_required > 4:
                print(f'ATTENTION {f}:{node.lineno} → {node.name}() a {n_required} paramètres obligatoires')
print('Contrôle signatures terminé.')
"
```

---

### Règle 8 — Gestion des erreurs récupérables

Vérifier que les boucles de traitement d'images/borniers ont des try/except
pour qu'une image ratée ne stoppe pas le traitement global.

```powershell
env\Scripts\python.exe -c "
from pathlib import Path
code = Path('converter.py').read_text(encoding='utf-8')
lines = code.splitlines()
in_loop = False
try_count = 0
for i, line in enumerate(lines, 1):
    if 'for ' in line and ('image' in line or 'bornier' in line or 'result' in line):
        in_loop = True
        loop_line = i
        try_count = 0
    if in_loop and 'try:' in line:
        try_count += 1
    if in_loop and (line.strip() == '' or (i > loop_line + 30)):
        if try_count == 0:
            print(f'ATTENTION ligne {loop_line}: boucle de traitement sans try/except')
        in_loop = False
print('Contrôle gestion erreurs terminé.')
"
```

## Étape 3 — Rapport final

```
REVUE D'ARCHITECTURE — TriosSeconverter
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VIOLATIONS CRITIQUES (à corriger avant tout nouveau développement)
  ✗ [fichier:ligne] — [règle violée] — [correction]

POINTS D'ATTENTION (risques potentiels)
  △ [fichier:ligne] — [description]

CONFORMITÉ
  ✓ [règle N] — Respectée dans tous les fichiers
  ...

Score global : X/8 règles respectées
```

Pour chaque violation, propose la correction minimale et demande si l'utilisateur
veut l'appliquer immédiatement.
