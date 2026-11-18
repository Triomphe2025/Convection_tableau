# Phase 1a — préparation du moteur (branche `moteur-phase1`)

Prompt enregistré mot pour mot. À relire avant chaque commit.

---

Contexte : je vais construire une nouvelle interface PySide6 à côté de l'actuelle. La phase 1
prépare le moteur, sans rien changer à l'écran ni aux Excel. Branche : moteur-phase1.

Étape 1 — Filet de sécurité, avant tout le reste : un test de non-régression « mêmes cellules ».
Il rejoue sans appel API les journaux .jsonl de conversions déjà validées (mode rejeu existant)
et compare cellule par cellule l'Excel produit à l'Excel validé de references/excels_valides/
(valeurs et pieds de page ; ignorer les métadonnées du fichier). Liste-moi d'abord les paires
journal / Excel disponibles ; s'il en manque, dis-le-moi au lieu d'en fabriquer. Ce test peut
être hors de la suite rapide (marqueur), mais je dois pouvoir le lancer en une commande.

Étape 2 — Événements structurés : module evenements.py avec une dataclass Evenement (type,
horodatage, page, total, nature de page, état, bornier, lignes extraites, zones, alertes, coût,
lot) et un rappel optionnel on_evenement dans Converter, émis EN PLUS de on_progress et on_log
(rien ne change pour l'interface actuelle). Types au minimum : analyse (nature de chaque page),
phase (analyse, lecture, contrôles, excel), page_debut, page_lue (lignes extraites + zones),
page_alerte, lot_cree, lot_etat, lot_recupere, fin, erreur. Les zones sont les boîtes des mots
Tesseract déjà appariées par positions_scan quand elles existent, en coordonnées relatives à la
page (0 à 1) ; sinon None.

Étape 3 — Service : service_conversion.py lance Converter dans un fil et expose démarrer, pause,
reprendre, arrêter, en relayant les événements. Pause = attente entre deux pages
(threading.Event), sans perte. L'interface actuelle peut continuer d'appeler Converter.

Étape 4 — Reprise automatique du mode lot : à la relance d'un même document, si le dossier de
sortie contient des lot_*.json non terminés, les reprendre (LecteurLot.reprendre sur le dossier)
au lieu de renvoyer les pages ; marquer chaque lot_*.json « termine » une fois ses résultats
récupérés, pour qu'il ne soit plus repris. Corrige aussi l'anti-doublon : l'heure de départ qui
sert à repérer un doublon est prise au début de chaque lot (_creer), pas une fois pour tout le
document.

Tests : un test par type d'événement (avec le faux client déjà utilisé pour le lot), pause et
reprise, reprise automatique, suite complète verte. Le test « mêmes cellules » passe avant et
après tes changements.

Règles (valables à chaque étape) :
- branche dédiée, jamais de travail direct sur main ;
- avant chaque commit : suite de tests complète verte et flake8 propre sur les fichiers touchés ;
- rien n'est poussé sans mon accord ; jamais de git push --force ; jamais de git reset --hard
  sans me demander ;
- la clé API ne va jamais dans un fichier commité ; references/excels_valides/ reste hors de git ;
- ne lis pas cle_privee_ed25519.bin et ne touche pas au dossier TriosSeconverter_prive ;
  l'obfuscation ne modifie jamais les sources ;
- la conversion doit produire exactement les mêmes Excel (valeurs, pieds, mise en forme) ;
- commence par me montrer ton plan ; avance par petites étapes, un commit par étape ; termine
  par un rapport : fichiers touchés, tests ajoutés, résultat de la suite, vérifications à
  faire à la main.Enregistre d'abord ce prompt mot pour mot dans docs/phases/phase1a.md (committé sur la branche) et relis-le avant chaque commit.

---

## Étape 1 — le filet « mêmes cellules »

Le filet est dans la suite normale (~5 s) : il protège chaque commit sans qu'on pense à le
lancer. Il part avec `pytest tests\`. Pour le lancer seul :

```powershell
env\Scripts\python.exe -m pytest tests/test_memes_cellules.py -v
```

Régénérer l'instantané (seulement sur un changement voulu du moteur) :

```powershell
env\Scripts\python.exe -m tests.test_memes_cellules --regenerer
```

Déterminisme vérifié : le rejeu `.jsonl` ne lance ni OCR (pas de Tesseract) ni appel API ; le
lexique est neutralisé (dossier vide) — l'instantané ne dépend donc que du code.

---

## Limites connues pour la phase 2

- La pause n'agit pas pendant l'attente d'un lot (le lot continue chez Anthropic) :
  l'écran d'attente du lot ne propose pas Pause.
- Les zones d'une page lue avant sa lecture Tesseract (page en cache) n'arrivent qu'au
  placement, par l'événement `page_zones`.
- Pas de boîtes de cellule, seulement de ligne : à ajouter en phase 1B (points à relire).
