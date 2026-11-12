# Phase 1B — registre des types, détection, estimation, points à relire (branche `moteur-phase1`)

Prompt de référence, enregistré mot pour mot. À relire avant chaque commit.

---

Enregistre d'abord ce prompt mot pour mot dans docs/phases/phase1b.md (committé sur la branche) et relis-le avant chaque commit.  Contexte : suite de la phase 1, même branche moteur-phase1. Toujours rien de visible à l'écran,
aucun changement dans les Excel.

Étape 1 — Registre des types de documents : types_documents.py lit templates.json et y ajoute des
champs optionnels, les champs actuels ne bougent pas : famille (tableau, plan, mixte, excel,
journal), reconnaissance (mots du pied de page, marque du cartouche, en-tête des colonnes, format
de page), sorties, profil_lecture par défaut, ecran_attente, relecture. Les modèles existants
(Bornier standard, Répartiteur, REPARTITEUR, REPARTITEUR 2) reçoivent des valeurs par défaut
déduites de leurs champs (footer_detect_keywords, footer_left_label, columns). Ajoute aussi les
familles plan (PDF ou TIFF grand format vers DXF), excel (mise en forme) et journal (.jsonl).
Signale-moi les doublons (« Répartiteur » et « REPARTITEUR » ont les mêmes colonnes) sans les
supprimer.

Étape 2 — Détection : detecter_type(chemin) -> (type, confiance, preuves). D'abord l'extension et
le format de page, puis le texte des pieds de page des premières pages (texte natif, sinon
Tesseract rapide) comparé aux mots de reconnaissance. Fichier inconnu : type None, confiance 0,
preuves qui expliquent pourquoi. Tests sur de petits extraits déjà présents dans tests/ ;
n'ajoute aucun document client au dépôt sans me demander.

Étape 3 — Estimation avant lancement : estimer(chemin, type, profil, lot) -> pages par nature,
pages déjà en cache, tokens et coût estimés (CLAUDE_PRIX_MODELES, -50 % en lot), durée estimée.
Les moyennes de tokens par page viennent des journaux .jsonl existants quand il y en a, sinon
d'une constante documentée. Tests.

Étape 4 — Points à relire : à chaque conversion, écrire à côté de l'Excel un fichier
<nom>_points.json, une entrée par point : page, bornier, ligne, colonne, valeur, suggestion
éventuelle, raison, confiance, zone sur l'image de la page, cellule Excel. Sources : alertes
a_verifier, contrôle Claude / Tesseract, vérification de conversion, pages signalées. L'Excel
lui-même ne change pas. Émettre aussi ces points dans les événements page_alerte.

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
  faire à la main.Précisions :
- Étape 4 (points à relire) : la zone de chaque point est la boîte de la CELLULE (mots Tesseract de la ligne appariée, découpés par les bornes de colonnes de positions_scan), en 0–1 ; la boîte de la ligne entière seulement si la cellule n'est pas calculable, avec un indicateur qui le dit.
- Avant de toucher aux alertes, vérifie qu'un test couvre le coloriage orange des cellules « à vérifier » dans la feuille Borniers (aucun des 3 extraits du filet n'en a) ; sinon écris-le d'abord, vert sur le code actuel, et prouve-le par une mutation.
