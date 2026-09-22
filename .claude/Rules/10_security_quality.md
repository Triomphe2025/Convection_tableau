# Règle 10 — Sécurité et qualité du code

## Injections et vulnérabilités

- **Pas d'eval()** sur du contenu utilisateur
- **Pas de subprocess** avec des chemins non validés
- **Valider les chemins** avant de les ouvrir :
  ```python
  path = Path(user_input).resolve()
  if not path.exists():
      raise FileNotFoundError(f"Introuvable : {path}")
  ```
- **Limiter les extensions** acceptées pour les fichiers source :
  ```python
  ACCEPTED_EXTENSIONS = {'.docx', '.pdf', '.jsonl', '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
  ```

## Secrets et clés API

- **Jamais committer** de clés API dans le code source
- La clé API Claude est entrée par l'utilisateur dans l'interface et stockée en mémoire de session uniquement
- `Config.CLAUDE_API_KEY` est lu depuis l'interface — jamais hardcodé
- Le fichier `.env` est dans `.gitignore`

## Qualité du code — vérifications automatiques

Le hook PostToolUse dans `settings.json` vérifie la syntaxe après chaque édition :
```json
{
  "matcher": "Edit",
  "hooks": [{"type": "command", "command": "python -m py_compile $file"}]
}
```

Avant chaque commit :
```powershell
# Vérification syntaxe tous les fichiers Python modifiés
env\Scripts\python.exe -m py_compile converter.py
env\Scripts\python.exe -m py_compile ocr_processor.py
env\Scripts\python.exe -m py_compile interface.py
env\Scripts\python.exe -m py_compile cad\vector_pdf_extractor.py

# Suite de tests complète
env\Scripts\python.exe -m pytest tests\ -v --tb=short
```

## Permissions git (configurées dans settings.json)

| Commande | Statut |
|---------|--------|
| `git add`, `git commit`, `git tag` | Autorisé |
| `git log`, `git diff`, `git status` | Autorisé |
| `git push --force` | **INTERDIT** |
| `git reset --hard` | **INTERDIT** |

## Taille des fichiers

Surveiller la croissance des fichiers principaux :
- `interface.py` : ~6 400 lignes actuellement — surveiller la complexité
- `ocr_processor.py` : ~3 300 lignes — envisager une extraction si > 4 000
- `converter.py` : ~600 lignes — en bonne santé

Si un fichier dépasse 4 000 lignes, utiliser `/revoir-architecture` pour
identifier une décomposition en modules.

## Audit de code mort

Utiliser `/auditer-code-mort` régulièrement pour détecter :
- Fonctions définies mais jamais appelées
- Imports inutilisés
- Variables locales non utilisées

## Bordures de cellules fusionnées (openpyxl)

```python
# INTERDIT — openpyxl ne propage pas automatiquement
ws.merge_cells('A1:D1')
ws['A1'].border = Border(...)  # seulement A1 a la bordure

# CORRECT — poser les bordures sur chaque cellule de bord individuellement
for col in range(1, 5):
    cell = ws.cell(row=1, column=col)
    cell.border = Border(
        left=Side(style='thin') if col == 1 else None,
        right=Side(style='thin') if col == 4 else None,
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )
```
