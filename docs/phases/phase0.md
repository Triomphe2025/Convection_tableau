# Phase 0 — refonte de l'interface (branche `interface-phase0`)

Spécification durable des 14 points UX. À relire avant chaque commit (une compaction du
contexte ne doit plus faire disparaître le détail). Aucune donnée client ici.

## Contraintes permanentes

- Ne pas changer `converter.py`, `claude_ocr.py`, `claude_lot.py`, ni rien qui produise les Excel.
  La conversion doit produire **exactement** les mêmes classeurs (`test_non_regression_xlsx`).
- Tests d'abord pour tout changement de comportement (règle `.claude/CLAUDE.md`) ; captures
  avant/après pour ce qui est purement visuel.
- La clé API ne va jamais dans un fichier commité ; `references/excels_valides/` reste hors de git ;
  ne pas lire `cle_privee_ed25519.bin` ni toucher au dossier `TriosSeconverter_prive` ;
  l'obfuscation ne modifie jamais les sources.
- Un commit par groupe logique ; avant chaque commit : suite complète verte + flake8 propre sur
  les fichiers touchés. Rien n'est poussé sans accord. Jamais `git push --force` ni `git reset --hard`.
- Logique pure dans `interface_helpers.py` (zéro import tkinter), testée ; `interface.py` = câblage.

## Points déjà traités

| Point | Objet | Commit |
|-------|-------|--------|
| 1 | Retour Accueil en quittant une page Dev (`page_apres_bascule_dev`) | commit 4 `20db77d` |
| 2 | Lisibilité combobox readonly (styles `TCombobox`, Listbox popup) | commit 2 `bbb7060` |
| 2b | 3 défauts du commit 2 : couleur en dur `#7878a0`→FG_MUTED, FG_MUTED en fond (bouton désactivé `BG_BTN_OFF`/FG_MUTED, pastille texte `FG_PASTILLE_FOND_MUTED`), flèche `arrowcolor=FG_TEXT` | commit 2b `08cafc3` |
| 5 | Liste moteur « socle » hors Dev (`moteurs_visibles`) | commit 4 `20db77d` |
| 13 | Netteté DPI (`Config.DPI_NET` défaut False, `_activer_dpi`, `dpi_a_activer`) | commit 3 `5305bf7` |
| 14 | Contraste FG_MUTED ≥ 4,5:1 sur tous ses fonds | commit 2 + 2b |

## Points restants (texte exact)

**3. Page Formater Excel (`_build_page_format`)** : à la taille d'ouverture 1060 x 760, les boutons
Reformater et Espacements PDF et le journal sont sous le bord. Rendre la page défilable
(Canvas + Scrollbar + molette) ou la réorganiser pour que les boutons restent visibles ;
corriger le chevauchement du libellé « Marges (cm) » avec « Nombre de colonnes ».

**4. Étape 2 du parcours (`_build_stepper_step2`)** : quand Claude est choisi, afficher sous le
choix du moteur le modèle Claude avec des noms lisibles (« Sonnet 5.5 — recommandé »,
« Opus 5.5 — documents difficiles »…, d'après `CLAUDE_CAPACITES_MODELES`, l'identifiant en
infobulle), la case « Mode économique (lot) », la case « Relire même les pages en cache » et
l'état de la clé API (configurée / absente). Mêmes variables que la page Mode OCR
(`_claude_model`, `_claude_mode_lot`, `_claude_forcer`) pour rester synchronisé.

**6. Étape 3** : un seul bouton de lancement, désactivé avec un message clair tant que la source
ou la destination manque ; retirer « Le journal de progression apparaît dans l'onglet Mode OCR ».

**7. Tableau de bord (`_build_page_dashboard`)** : afficher « page n / total », le temps écoulé et
le temps restant estimé, calculés à partir des messages « Page n/total » déjà émis (fonction pure
testée). Supprimer le bouton « Voir onglet Mode OCR ».

**8. Fin de conversion** : si la fenêtre n'a pas le focus, faire clignoter l'icône dans la barre des
tâches (FlashWindowEx via ctypes, Windows seulement, sans erreur ailleurs) et jouer le son
système ; afficher dans le tableau de bord Ouvrir l'Excel, Dossier, Audit.

**9. Barre du haut** : Excel, Dossier, Audit, Observer et la barre de progression vide n'apparaissent
qu'une fois une conversion terminée ; « Ajouter au lexique » quitte la barre du haut (il reste dans
Options).

**10. ValidationPageDialog** : vrai numéro de page dans le titre (`page_done` si META PAGE est vide) ;
image du scan agrandissable (clic = vue à 100 % défilable, molette = zoom) ; la croix ne vaut plus
« accepter », elle demande confirmation ; « Valider et continuer » n'est plus rouge ; Entrée = valider,
Échap = fermer avec confirmation.

**11. WelcomeAnimation** : l'arrêter quand l'Accueil est caché et la relancer quand il revient
(`_show_page`) ; retirer le personnage Minion (`_minion`) : garder la boîte « trios », une feuille
entre, un petit tableau sort.

**12. Page Aide** : réécrire le texte d'après l'interface réelle (plus d'onglets « Documents » /
« Modèles », plus de renvoi à CLAUDE.md) ; brancher Ctrl+O sur le choix du fichier source.

## Précisions déjà convenues

- **Point 7** : estimation depuis le premier message « Page n/total » ; en mode lot, pas de temps
  restant mais « en attente du lot » puis « récupération des pages » (helpers déjà testés).
- **Point 8** : tout l'appel (FlashWindowEx, son) dans un try/except : un échec ne fait jamais échouer
  la fin de conversion, au pire une ligne dans le journal.
- **Point 6** : bouton désactivé = le couple de couleurs « inactif » du commit 2b (`BG_BTN_OFF` /
  FG_MUTED).

## Porte de fin de phase 0

`build_exe.bat`, ouvrir l'exe, convertir un vrai PDF, confirmer l'Excel identique
(`test_non_regression_xlsx` vert). Rapport final : tableau des commits, les 3 preuves par test,
captures avant/après, vérifications à faire à la main, résultat de `build_exe.bat` et de l'essai de
l'exe sur un vrai PDF.
