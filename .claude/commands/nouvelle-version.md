Prépare une nouvelle version de TriosSeconverter pour livraison.

L'utilisateur indique le numéro de version (ex : v1.3) et les changements effectués.

Étapes dans l'ordre :

1. Lis le fichier `CLAUDE.md` pour voir l'historique des versions existantes.

2. Vérifie l'état Git du projet :
   ```powershell
   git status
   git log --oneline -5
   ```

3. Mets à jour la section "Historique des améliorations majeures" dans `CLAUDE.md`
   avec la nouvelle version, la date du jour (2026-05-04) et les changements.

4. Met à jour le badge de version dans `interface.py` :
   - Cherche la ligne contenant `text=" v1.x "` dans le header de la fenêtre
   - Remplace par le nouveau numéro de version

5. Lance les tests pour s'assurer que rien n'est cassé :
   ```powershell
   env\Scripts\activate && pytest tests\ -v --tb=short
   ```

6. Si les tests passent, crée le commit Git :
   ```powershell
   git add -A
   git commit -m "Version vX.Y — [résumé des changements]"
   git tag vX.Y
   ```

7. Propose de compiler l'exe avec `/build-exe`.

8. Fournis la checklist de livraison tirée de `Contexte\GUIDE_CREATION_LOGICIEL.md`.
