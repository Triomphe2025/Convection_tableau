Contexte : nouvelle interface PySide6, branche interface-qt. Écran Convertir d'après
docs/maquettes/01_convertir.png. Les fonctions detecter_type et estimer viennent de la phase 1.

- Zone de dépôt : glisser-déposer de fichiers et de dossiers, bouton Choisir, Ctrl+O ; formats :
  PDF, TIFF, JPG/PNG, dossier d'images, Word .docx, Excel .xlsx, journal .jsonl. Petite
  animation « trios » (une feuille entre, un tableau sort, 3,6 s), arrêtée si l'écran est caché
  ou si les animations sont réduites.
- File de fichiers (QAbstractListModel) : pour chaque fichier, sigle de famille, nom, pages et
  natures, type détecté et sa preuve, sortie, estimation ; « Inconnu > à préciser » en orange.
  Retirer un fichier, changer l'ordre par glisser.
- Ligne dépliée : pour un tableau, les trois profils Rapide (Tesseract) / Précis (Sonnet 5.5) /
  Difficile (Opus 5.5) avec leur estimation, et l'interrupteur Mode économique (lot), proposé
  d'office au-delà de 100 pages ; pour un plan, la finesse Rapide / Standard / Précis ; pour un
  inconnu, « Choisir un type » et « Créer un type à partir de cette page » (écran Types,
  phase 2E). Changer le type d'un fichier recalcule son estimation.
- Panneau « Types reconnus » à droite, lu dans le registre, lien « Gérer » vers Types.
- Bas de page : résumé (fichiers, prêts, à préciser, coût et durée totaux) et bouton
  « Lancer les N fichiers prêts » (Ctrl+Entrée) : la file part via service_conversion, un
  fichier après l'autre, et l'écran Traitement s'ouvre.

Tests pytest-qt : dépôt de 3 fichiers de types différents (petits fichiers de test), types
affichés, bouton désactivé tant qu'aucun fichier n'est prêt, profil et lot modifient
l'estimation.

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

Précisions issues des phases 1A/1B :
- detecter_type et estimer tournent dans un fil à part au dépôt (jamais dans le fil de l'interface) ;
  le fichier s'affiche tout de suite avec « analyse… », puis se complète.
- « à préciser » (a_preciser) s'affiche en orange avec le modèle le plus proche proposé et les
  preuves en infobulle.
- Le coût affiché vient de estimer : « au plus » quand cache_connu est faux, « ~ » devant les
  montants (approche: True).
