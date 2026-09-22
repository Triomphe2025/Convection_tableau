Compile TriosSeconverter en exécutable Windows autonome (.exe) avec PyInstaller.

Étapes à suivre dans l'ordre :

1. Vérifie que le fichier `TriosSeconverter.spec` existe à la racine du projet.

2. Active l'environnement virtuel et lance la compilation :
   ```powershell
   env\Scripts\activate
   pyinstaller TriosSeconverter.spec --clean
   ```

3. Vérifie que `dist\TriosSeconverter.exe` a bien été créé.

4. Affiche la taille du fichier généré.

5. Rappelle à l'utilisateur :
   - Tester l'exe sur une machine SANS Python installé avant de livrer
   - L'exe se trouve dans le dossier `dist\`
   - Toutes les ressources (icon.ico, templates.json) sont incluses dans l'exe

Si la compilation échoue, affiche l'erreur complète et propose une solution.
