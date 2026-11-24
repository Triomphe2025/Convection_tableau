Contexte : nouvelle interface PySide6, branche interface-qt. Écrans d'attente d'après
docs/maquettes/02_traitement_tableau_a/b/c.png, 09_attente_lot.png, 10_mini_fenetre.png et le
tableau « Mouvement » de 07_systeme_visuel.png. Les événements viennent de service_conversion
(phase 1). Règle d'or : rien d'inventé à l'écran, chaque animation montre un vrai état.

Traitement d'un tableau :
- rail des 4 étapes (analyse, lecture, contrôles, Excel) avec sa barre ;
- « Lecture en direct » : QGraphicsView avec l'image de la page en cours. Pendant que Claude lit,
  une bande rose descend la page. À l'événement page_lue, les zones apparaissent ligne par ligne
  (bleu = vu, vert = lu, rose = ligne courante, orange = doute), une loupe montre la ligne lue
  agrandie et suit la lecture sans retard, le tableau extrait (QTableView, 9 dernières lignes)
  se remplit ligne par ligne, les valeurs lues s'affichent en puces sous la loupe. Sans zones,
  seules la bande et le tableau s'animent ;
- anneau d'avancement (widget peint, pourcentage), temps restant, heure de fin estimée,
  tableaux extraits, pages à relire, coût en direct ;
- astuces qui changent toutes les 7 s ; messages d'étape en bas à droite (chaque centaine de
  tableaux, « plus que 10 pages », fin), 3 s chacun, sans masquer l'en-tête ;
- mosaïque : une case par page, peinte en une seule passe (pas un widget par case) : attente,
  en lecture (pulsation), lue, texte natif, à relire ; infobulle par case ;
- journal technique replié en bas, une ligne visible ;
- Pause / Reprendre / Arrêter ; à la fin : anneau vert, coche dessinée, un seul bouton
  « Voir le résumé », notification Windows (QSystemTrayIcon) et clignotement de la barre des
  tâches si la fenêtre n'a pas le focus.

Attente du mode lot :
- une piste par lot : envoi (pastille qui avance, taille en Mo), chez Anthropic (pages lues sur
  total), retour, rapatrié ; anneau des pages lues ; « dernière vérification il y a n s,
  prochaine dans n s » ;
- carte « Tu peux fermer l'appli » avec l'interrupteur « Me prévenir à la fin » ; carte
  « Pendant ce temps » (relire un autre document, lancer le fichier suivant de la file) ;
- mosaïque par état de lot (texte natif, dans un lot, lue mais pas rapatriée, rapatriée) ;
- à la réouverture de l'appli, un lot en cours rouvre cet écran et reprend (phase 1A).

Mini-fenêtre : fenêtre outil toujours au premier plan (environ 440 x 150) avec anneau, pages,
temps restant, barre avec repères des pages à relire, Pause, Agrandir. Progression aussi dans
le bouton de la barre des tâches (ITaskbarList3, optionnel, sans planter si indisponible).

Contraintes : l'interface reste fluide (aucun travail lourd dans le fil de l'interface) ; toutes
les animations s'arrêtent quand leur écran est caché ou si les animations sont réduites ;
durées du tableau « Mouvement » (350 ms au plus hors boucles d'attente).

Tests : un faux service rejoue une suite d'événements enregistrée (JSON dans tests/) ; vérifier
l'état des widgets à plusieurs instants et à la fin, et l'arrêt des minuteurs quand l'écran
est caché.

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
  faire à la main, et une courte vidéo ou plusieurs captures de chaque écran d'attente.

Précisions issues des phases 1 et 2B :
- Les événements page_debut / page_lue existent maintenant aussi en Tesseract ; les zones peuvent
  être absentes (None) : la bande de lecture et le tableau extrait s'animent quand même.
- La pause n'agit pas pendant l'attente d'un lot : pas de bouton Pause sur l'écran du lot.
- Remplace l'écran Traitement provisoire de la 2B ; garde « Arrêter » réactif (message immédiat)
  et « Ouvrir l'Excel / le dossier » à la fin.
- Toute animation s'arrête si l'écran est caché ou si les animations sont réduites ; aucun travail
  lourd dans le fil de l'interface.
- Test final avec l'exe sur un vrai scan avant de rendre la main (temps réel, captures à
  3 instants).

## Retouches 3

Contexte : vérification visuelle de eb03d20 contre docs/maquettes/09 (écran lot) et 10 (mini-fenêtre), scénario 141 pages dont 25 vectorielles, 5 lots, lot 0 récupéré, LOT_ETAT lues 24/14/8/4/2. Règle tests d'abord habituelle (rouge avant, rouge sur mutation, vert à la fin) pour les points marqués [test].

1. [test] Mosaïque : les pages vectorielles (texte natif, sans Claude) doivent être coloriées en bleu (couleur de la légende « texte natif ») à leur rang réel, dès l'événement ANALYSE, et rester bleues jusqu'à la fin. Aujourd'hui aucune case n'est bleue. Test : après ANALYSE avec 25 pages vectorielles, exactement 25 cases ont l'état « natif ».
2. [test] Mosaïque : l'état « lue, pas encore rapatriée » utilise la couleur lavande de la maquette (jeton violet clair de jetons.json), pas le rose. Attribue les états par plage de pages de chaque lot (pages du lot N) et non par rang agrégé : les cases du lot 0 récupéré passent au vert, les lues de chaque lot en lavande, le reste du lot en violet foncé.
3. Diagramme : les blocs « Ce PC » et « Anthropic » ont une largeur fixe suffisante (au moins 120 px) pour que « prépare, puis récupère » et « lit les pages du lot » tiennent sur 2 lignes maximum sans chevaucher les étiquettes « xx Mo » ni « lu x / y ». L'icône est dans un carré arrondi encadré (50 px environ) comme sur la maquette.
4. Pastilles de lot : contour fin visible comme sur la maquette ; le texte « lu x / y » est placé juste sous sa pastille, aligné à droite sur elle.
5. Barre d'étapes : l'étape en cours « Lecture chez Anthropic » est en violet (pas rose) et remplie au prorata (52/116 ≈ 45 %).
6. Carte « pages lues par Anthropic » : anneau violet ; « Dernière vérification il y a … · prochaine dans … » en gris normal (pas orange gras) avec une fine barre de décompte dessous qui se vide jusqu'à la prochaine vérification.
7. Carte « Tu peux fermer l'appli » : ajoute l'icône bouclier (Lucide shield-check) devant le titre.
8. Carte « Pendant ce temps » : remplace les deux gros boutons par deux lignes comme la maquette, texte à gauche (« Relire les N points de <document> », « Lancer le fichier suivant de la file ») et lien d'action rose à droite (« Relire », « Lancer »). Si rien à relire ou pas de fichier suivant, la ligne est masquée.
9. Mini-fenêtre : barre de progression fine (6 px environ, comme la maquette) ; bouton pause = icône pause Lucide dans un bouton arrondi encadré de 32 px environ.

Ne touche pas au moteur ni au test « mêmes cellules ». À la fin : tous les tests verts, capture offscreen de l'écran lot et de la mini-fenêtre avec le même scénario, sauvegardées dans captures/ (non commité), commit sur interface-qt, push de la branche (jamais main), et ton rapport avec la liste des points faits.
