Contexte : nouvelle interface en PySide6, construite À CÔTÉ de l'actuelle. L'exe actuel reste
celui de l'équipe. Maquettes et jetons de design : docs/maquettes/ (LISEZMOI.md, jetons.json,
01 à 10). Branche : interface-qt.

1. Installe PySide6 (version figée dans requirements) ; crée trios_qt/ et run_qt.py.
   interface.py ne change pas.
2. Thème : couleurs, polices, tailles, rayons et durées de docs/maquettes/jetons.json -> une
   feuille QSS générée par trios_qt/theme.py ; polices Inter et JetBrains Mono embarquées
   (QFontDatabase), licences OFL dans licences/.
3. Fenêtre principale (voir 01_convertir.png) : barre latérale (Convertir, Relecture avec son
   compteur, Mise en forme Excel, Plans -> DXF avec la mention bêta ; en bas Réglages, Aide, et
   l'état du modèle et de la clé) + QStackedWidget avec une page vide par écran, passage
   d'écran en fondu de 300 ms (jeton passage_ecran ; le 250 ms d'une version antérieure du
   prompt était une erreur).
4. Licence : réutilise la vérification existante (même fichier, même message) avant d'ouvrir la
   fenêtre.
5. Lis au démarrage le réglage Windows « réduire les animations » (SystemParametersInfo,
   SPI_GETCLIENTAREAANIMATION) dans un drapeau global que toutes les animations respecteront.
6. Empaquetage : spec PyInstaller séparé (TriosSeconverter_Qt.spec), en mode dossier et non
   fichier unique (licence LGPL de PySide6), texte de la licence LGPL joint. Vérifie que
   l'obfuscation actuelle accepte ce build ; sinon dis-le-moi avant de contourner quoi que ce soit.

Tests : pytest-qt pour la navigation (chaque bouton affiche la bonne page) et pour le thème
(aucune couleur en dur hors jetons).

Règles (valables à chaque étape) :
- branche dédiée, jamais de travail direct sur main ;
- interface.py et l'exe actuel restent inchangés ; le nouveau code va dans trios_qt/ ;
- avant chaque commit : suite de tests complète verte et flake8 propre sur les fichiers touchés ;
- rien n'est poussé sans mon accord ; jamais de git push --force ; jamais de git reset --hard
  sans me demander ;
- la clé API ne va jamais dans un fichier commité ; references/excels_valides/ reste hors de git ;
- ne lis pas cle_privee_ed25519.bin et ne touche pas au dossier TriosSeconverter_prive ;
  l'obfuscation ne modifie jamais les sources ;
- la conversion doit produire exactement les mêmes Excel ;
- commence par me montrer ton plan ; avance par petites étapes, un commit par étape ; termine
  par un rapport : fichiers touchés, tests ajoutés, résultat de la suite, vérifications à
  faire à la main, et une capture de chaque écran modifié.
