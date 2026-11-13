# Essais à la main sur l'exe

Les essais que je fais **moi-même** sur l'exe (`dist\TriosSeconverter\TriosSeconverter.exe`)
**avant** de fusionner `moteur-phase1` dans `main` et **avant** de donner un exe à l'équipe.

- Une case à cocher par essai, les étapes, le résultat attendu.
- À compléter au fil des phases : chaque phase ajoute ses essais ici.
- La clé API se saisit dans l'interface (jamais dans un fichier). Pour distribuer : copier
  tout le dossier `dist\TriosSeconverter\` ; Tesseract reste à installer sur la machine.

---

## Phase 0 — refonte de l'interface

Les 6 vérifications visuelles du rapport final de la phase 0 (points 3, 7, 9, 10, 11, 12 de
`docs/phases/phase0.md`), puis une vraie conversion Claude qui couvre le point 8 (clignotement + son).

- [ ] **P0.1 — Point 3 : page « Formater Excel » lisible.**
  - Ouvrir l'appli à sa taille d'ouverture (1060 × 760), aller sur « Formater Excel ».
  - Attendu : les boutons **Reformater** et **Espacements PDF** et le **journal** restent visibles
    (page défilable à la molette si besoin) ; le libellé « Marges (cm) » ne chevauche pas
    « Nombre de colonnes ».

- [ ] **P0.2 — Point 7 : tableau de bord pendant la conversion.**
  - Lancer une conversion et regarder le tableau de bord.
  - Attendu : « page n / total », le **temps écoulé** et le **temps restant estimé** s'affichent ;
    il n'y a **plus** de bouton « Voir onglet Mode OCR ».

- [ ] **P0.3 — Point 9 : barre du haut au repos.**
  - Ouvrir l'appli sans rien convertir.
  - Attendu : **Excel, Dossier, Audit, Observer** et la barre de progression vide **n'apparaissent
    pas** ; ils n'apparaissent qu'une fois une conversion terminée. « Ajouter au lexique » n'est
    **pas** dans la barre du haut (il est dans Options).

- [ ] **P0.4 — Point 10 : fenêtre de validation de page.**
  - Pendant une conversion qui demande une validation de page, observer la fenêtre.
  - Attendu : le **vrai numéro de page** est dans le titre ; l'image du scan est **agrandissable**
    (clic = vue 100 % défilable, molette = zoom) ; la **croix demande confirmation** (elle ne vaut
    plus « accepter ») ; « Valider et continuer » **n'est plus rouge** ; **Entrée** valide,
    **Échap** ferme avec confirmation.

- [ ] **P0.5 — Point 11 : animation d'accueil.**
  - Rester sur l'Accueil, puis changer de page et revenir.
  - Attendu : animation « trios » (la boîte, une feuille entre, un petit tableau sort),
    **sans** le personnage Minion ; l'animation **s'arrête** quand l'Accueil est caché et
    **repart** quand il revient.

- [ ] **P0.6 — Point 12 : page Aide et Ctrl+O.**
  - Ouvrir la page Aide ; appuyer sur **Ctrl+O**.
  - Attendu : le texte correspond à l'interface réelle (plus d'onglets « Documents » / « Modèles »,
    plus de renvoi à CLAUDE.md) ; **Ctrl+O** ouvre le choix du fichier source.

- [ ] **P0.7 — Point 8 : conversion Claude, fenêtre en arrière-plan (clignotement + son).**
  - Mode OCR **Claude**, convertir un PDF de **3 à 5 pages**. Pendant le traitement, **mettre la
    fenêtre de l'appli en arrière-plan** (cliquer sur une autre fenêtre).
  - Attendu : à la fin, l'**icône clignote** dans la barre des tâches et le **son système** est joué ;
    le tableau de bord propose **Ouvrir l'Excel**, **Dossier**, **Audit** ; l'**Excel est produit**.

---

## Phase 1A — moteur prêt pour la future interface (mode lot + reprise)

- [ ] **1A.1 — PE082 en mode lot, avec reprise après fermeture.**
  - **Avant de lancer** : ouvrir la console Anthropic → **Batches** et **noter l'état** (nombre de
    lots existants) pour pouvoir comparer après.
  - Ouvrir l'exe, mode OCR **Claude**, cocher **« Mode lot »** (économique). Choisir **PE082.pdf**,
    un **dossier de sortie** et un **modèle** — **noter le modèle** choisi. Saisir la clé API.
  - **Lancer.** Pendant l'**attente du lot** (journal « en attente du lot »), **fermer l'appli**.
    (Vérifier au passage qu'un lot est bien apparu dans la console Anthropic et qu'un fichier
    `lot_<id>.json` est présent dans le dossier de sortie — ne pas le supprimer.)
  - **Relancer** l'exe avec **le même PDF**, **le même dossier de sortie** et **le même modèle** ;
    relancer la conversion.
  - Attendu :
    - le journal affiche **« Reprise »** (reprise de N page(s)) ;
    - dans la console Anthropic → Batches, **aucun nouveau lot** n'est créé à la relance (le lot
      d'origine est repris, donc **pas re-facturé**) ;
    - l'**Excel est produit** à la fin, complet.

---

## Phase 1B — moteur préparé (détection, estimation, points à relire)

Rien ne change à l'écran : ces essais portent sur ce que le moteur **produit** (fichiers,
estimations, reconnaissance). Les points 1.B.3 et 1.B.4 se lancent par un petit script Python
(`env\Scripts\python.exe`), le reste depuis l'exe.

- [ ] **1B.1 — `<nom>_points.json` écrit à côté de l'Excel (vrai scan + Claude).**
  - Mode OCR **Claude**, convertir un PDF **scanné** de 2–3 pages qui a des cases douteuses.
  - Attendu : à côté de l'Excel, un fichier **`<nom>_points.json`** ; l'ouvrir et vérifier que
    chaque **cellule colorée** de la feuille Borniers y a **un point** (sorte, `cellule_excel`,
    `page_imprimee`, `bornier`), et que les **zones** de cellule (0–1) tombent sur les bonnes cases.

- [ ] **1B.2 — Points d'une conversion arrêtée.**
  - Lancer une conversion, puis **Arrêter** en cours.
  - Attendu : `<nom>_points.json` est **quand même écrit**, avec `"arrete": true` et seulement les
    points des **pages déjà lues** ; aucune erreur, l'appli reste utilisable.

- [ ] **1B.3 — Estimation : ordre de grandeur sur un document connu.**
  - Dans un terminal, à la racine du projet :
    `env\Scripts\python.exe -c "import estimation,types_documents as t; print(estimation.estimer(r'CHEMIN.pdf', None, profil='claude', modele='claude-opus-5-5'))"`
  - Attendu : `pages` par nature plausibles, `cout_usd` et `duree` du **bon ordre de grandeur** pour
    ce document ; `approche` vaut `True`. (Les moyennes s'affinent si `ESTIMATION_JOURNAUX_DOSSIER` /
    `ESTIMATION_STATS_FICHIER` pointent sur tes vraies conversions.)

- [ ] **1B.4 — Détection de type sur des fichiers clients.**
  - `env\Scripts\python.exe -c "import types_documents as t; print(t.detecter_type(r'CHEMIN'))"`
    sur un PDF de tableaux, un scan, un `.jsonl`, un `.xlsx`, un plan grand format.
  - Attendu : famille correcte (tableau / plan / journal / excel) ; pour un modèle indiscernable,
    « à préciser » avec le modèle le plus proche ; fichier inconnu → `(None, 0)`.

- [ ] **1B.5 — `points_relire` embarqué dans l'exe.**
  - Reconstruire l'exe (`build_exe.bat`) puis vérifier dans le journal de build qu'il n'y a **pas**
    d'avertissement « module not found: points_relire » ; une conversion depuis l'exe écrit bien
    `<nom>_points.json`.

- [ ] **1B.6 — Modèle réel du scan 6A23111PE102 (facultatif).**
  - Vérifier sur le document d'origine **quel modèle** est le scan PE102. S'il est bien un
    **Bornier standard**, me le dire pour resserrer le test de détection sur ce nom.
