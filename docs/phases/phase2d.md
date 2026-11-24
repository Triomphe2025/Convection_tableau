Contexte : nouvelle interface PySide6, branche interface-qt. Écrans d'après
docs/maquettes/03_termine.png et 04_relecture.png. Les points viennent de <nom>_points.json
(phase 1B).

Préambule — 3 finitions de l'écran lot (09_attente_lot.png), vérifiées par capture :
a. Lot rapatrié : la pastille verte roule sur la piste « retour » en haut, l'étiquette
   « retour des résultats » est à droite de cette piste (comme la maquette), et la taille
   « xx Mo » ne touche plus la pastille.
b. Anneau « pages lues » : « sur 116 » en petit (taille du libellé secondaire de la maquette),
   le nombre seul en grand.
c. Carte « Pendant ce temps » : lignes à la taille de texte normale, chacune sur un léger fond
   de ligne comme la maquette.

Écran Terminé : chiffres clés (tableaux, pages par nature, points à relire, coût et durée,
pages servies par le cache) ; « Ce qui demande ton attention » (pages signalées, cellules qui
s'écartent, résultat du contrôle Claude / Tesseract) ; bouton principal « Relire les N points » ;
Ouvrir l'Excel, Dossier ; outils d'après (auditer, comparer au scan, enrichir le lexique,
mettre en forme) qui appellent le code existant.
Branchements : le bouton « Voir le résumé » de l'écran Traitement ouvre Terminé ; le lien
« Relire » de la carte « Pendant ce temps » (écran lot) ouvre Relecture sur ce document ; le
compteur de Relecture dans la barre latérale = nombre de points encore « À voir ».

Écran Relecture :
- liste des points (QListView) avec leur état : À voir, Gardé, Corrigé, Passé ; compteur et
  barre « n sur N traités » ;
- au centre, l'extrait du scan zoomé sur la cellule (QGraphicsView, image de la page du dossier
  de travail, cadre orange sur la cellule, cadre bleu pointillé sur la ligne de comparaison),
  miniature de la page avec la zone, zoom - / + ; si l'image de la page n'existe plus dans le
  dossier de travail, la régénérer depuis le PDF (sans bloquer l'interface) ou afficher un
  message clair, jamais un écran vide ;
- la ligne en champs modifiables, la cellule douteuse en orange, l'explication et la confiance ;
- Garder (Entrée), Remplacer par la suggestion (R), Passer (Échap), Tab = cellule suivante,
  Ctrl+flèche bas = point suivant ; case « Retenir dans le lexique » (code du lexique existant) ;
- « Enregistrer dans l'Excel » : écrit les valeurs corrigées dans le classeur (openpyxl, mise en
  forme conservée), retire l'orange des points traités, ajoute un commentaire « Relu le <date> »,
  et garde la première fois une copie <nom>_avant_relecture.xlsx. Si l'Excel est ouvert dans
  Excel (fichier verrouillé), le dire clairement et ne rien perdre de la relecture en cours.
- l'état de la relecture (points traités) est conservé si on ferme l'appli et qu'on revient.
Le mode « page par page pendant la conversion » réutilise ce même écran.

Tests (tests d'abord, 3 preuves par test comme d'habitude) : un classeur et un points.json de
test (fabriqués pour le test, aucune donnée client) ; garder / remplacer / passer modifient le
classeur comme prévu ; la mise en forme des autres cellules est intacte ; la copie de
sauvegarde existe et n'est créée qu'une fois ; les raccourcis clavier marchent ; classeur
verrouillé = message, pas de plantage ; état de relecture retrouvé après redémarrage.
Essai réel en plus (sans le committer) : ouvre la Relecture sur un vrai couple Excel +
points.json déjà produit (par exemple PE142 ou PE143) sur une COPIE du classeur, et
joins la capture au rapport.

Captures : pour chaque écran, une image côte à côte maquette / rendu (dans captures/, non
commité), comme pour la 2C.

Règles (valables à chaque étape) :
- branche dédiée, jamais de travail direct sur main ;
- interface.py et l'exe actuel restent inchangés ; le nouveau code va dans trios_qt/ ;
- avant chaque commit : suite de tests complète verte et flake8 propre sur les fichiers touchés ;
- tu peux pousser la branche interface-qt en sauvegarde après chaque étape ; jamais main sans mon
  accord ; jamais de git push --force ; jamais de git reset --hard sans me demander ;
- la clé API ne va jamais dans un fichier commité ; references/excels_valides/ reste hors de git ;
  aucune donnée client dans le dépôt ;
- ne lis pas cle_privee_ed25519.bin et ne touche pas au dossier TriosSeconverter_prive ;
  l'obfuscation ne modifie jamais les sources ;
- la conversion produit toujours les mêmes Excel ; seule la relecture, sur mon action, modifie
  un classeur (avec sa copie de sauvegarde) ; ne modifie jamais un de mes originaux pendant tes
  essais, travaille sur des copies ;
- commence par me montrer ton plan ; avance par petites étapes, un commit par étape ; termine
  par un rapport : fichiers touchés, tests ajoutés, résultat de la suite, vérifications à
  faire à la main, et les captures côte à côte.
