# Règle 08 — Livraison et versionnement

## Processus de livraison

```
1. /tester              → 205+ tests passent
2. /nouvelle-version    → badge UI, CLAUDE.md, tag Git
3. /build-exe           → dist\TriosSeconverter.exe
4. Test exe sur machine sans Python
5. /rapport-livraison   → rapport complet
```

## Numérotation des versions

Format : `vMAJEUR.MINEUR`
- MAJEUR : changement d'architecture ou rupture de compatibilité
- MINEUR : nouvelle fonctionnalité ou correction significative

Historique actuel : v1.0 → v1.1 → v1.2 → v1.3 → v1.4 → v1.5 → v1.6 → v1.7

## Checklist avant livraison

- [ ] Badge version mis à jour dans `interface.py` (chercher `text=" vX.X "`)
- [ ] Historique des versions mis à jour dans `CLAUDE.md`
- [ ] 205+ tests pytest passent
- [ ] `TriosSeconverter.spec` inclut tous les modules dynamiques :
  - `agent_ocr`, `claude_ocr`, `ollama_ocr`, `hybrid_ocr`
  - `pdf_extractor`, `docling_ocr`
  - Package `cad/` (vérifier `hiddenimports`)
- [ ] Exe testé sur machine sans Python installé
- [ ] README mis à jour avec le bon nombre de tests

## Mise à jour PyInstaller spec

À chaque ajout d'un nouveau module chargé dynamiquement :
```python
# Dans TriosSeconverter.spec
hiddenimports=[
    'agent_ocr', 'claude_ocr', 'ollama_ocr', 'hybrid_ocr',
    'pdf_extractor', 'docling_ocr',
    'cad', 'cad.service', 'cad.vector_pdf_extractor',
    'cad.dxf_writer', 'cad.block_builder', 'cad.models',
    'cad.source_detector',
]
```

## Commit Git

```powershell
# Format du message (PowerShell here-string)
git commit -m @'
Version vX.Y - Description courte des changements

- Changement 1
- Changement 2

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
'@
```

**JAMAIS** de `git push --force` sur main.
**JAMAIS** de `git reset --hard` sans confirmation.

## Ce qu'il ne faut jamais faire avant livraison

- Modifier `env/` — recréer avec `install.bat` si besoin
- Supprimer `templates.json` — contient les modèles utilisateur
- Modifier directement la config PyInstaller sans tester l'exe
