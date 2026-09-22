Lance la suite de tests automatisés du projet TriosSeconverter.

Étapes :

1. Active l'environnement virtuel :
   ```powershell
   env\Scripts\activate
   ```

2. Lance les tests avec pytest :
   ```powershell
   pytest tests\ -v --tb=short
   ```

3. Si le dossier `tests\` n'existe pas encore, signale-le et propose de le créer avec les fichiers de test de base tirés du guide `Contexte\GUIDE_CREATION_LOGICIEL.md`.

4. Analyse les résultats :
   - Affiche combien de tests passent / échouent
   - Pour chaque test en échec, explique en français ce qui ne fonctionne pas
   - Propose une correction si le problème est identifiable

5. Si tous les tests passent, confirme que le projet est prêt pour une livraison.
