# Journal de mise à niveau TriosSeconverter

Suivi des étapes du plan de mise à niveau (kit de départ : `LISEZ-MOI.md`).

---

## Étape 3 — Moteur de mesure de précision (2026-09-28)

Livré : `mesure_precision.py` (module pur) + `mesurer_precision.py` (CLI) + section
`MESURE_*` de `config.py`. Test doré `tests/test_mesurer_precision_golden.py` :
sortie v1.7 figée de l'extrait 223111PE011 (mode Claude) contre la vérité terrain
validée — aucun appel au pipeline.

### Chiffres mesurés — sortie v1.7 contre vérité terrain (extrait 223111PE011)

Relevé le 2026-09-28 avec `mesure_precision.mesurer` (stratégie d'alignement de cette
étape ; les totaux changeront si l'alignement évolue — le test doré ne les fige pas).

| Mesure | Valeur |
|--------|--------|
| Pages de la vérité | 10 (dont 104 sans ligne de données) |
| Blocs dans la sortie v1.7 | 8 (168 lignes de données) |
| Pages appariées | 8 — dont 122a ↔ « 128 » et 123 ↔ 123 |
| Pages absentes de la sortie | 2 : pages 9 et 104 |
| Blocs en trop dans la sortie | 0 |
| Cellules comparées | 656 |
| Cellules identiques | 419 → précision 63,9 % |
| Écarts « espacement » | 97 |
| Écarts « contenu différent » | 61 |
| Écarts « manquant » | 60 (les 60 ABOUTISSANT vides de la page 119) |
| Écarts « confusion de caractère » | 19 |
| Écarts « ajouté » | 0 |
| Lignes en trop | 4 (page 122) |
| Lignes manquantes | 0 |
| Écarts de pied de page | 19 |
| Écarts de position | 0 (référence Excel : pas de géométrie) |

Écarts nommés vérifiés par le test doré :
- page 1 : glissement de colonnes sur 4 lignes (TENANT réduit à « PH », « QTEL2 » passé
  en SIGNAL lu « CITEL2 » → contenu différent)
- page 3 : « BUBU » lu « BLEU » (contenu différent) ; SIGNAL de deux lignes fusionné
- page 52 : « 15B/M » lu « 15 M/J »
- page 119 : 60 ABOUTISSANT vides ; « ITIN » lu « ITTN » 4 fois et « TALONNAGE » lu
  « TALONAGE » (confusion de caractère)
- page 122 : 4 lignes en trop

Tests : 568 passent dans `tests/` (+ 1 échec attendu, + 1 test lent facultatif),
31 dans les fichiers de la racine.

Décisions prises pendant l'étape :
- Appariement des pages **sans contrainte d'ordre** (glouton sur la meilleure
  similarité) : la sortie v1.7 range la page 122a (nommée « 128 ») après la 123 ;
  un appariement monotone laissait la 123 orpheline des deux côtés.
- Table de confusions reprise à l'identique de `outils_reference/comparateur.py`
  (dont `T/I`, qui classe ITIN → ITTN en confusion de caractère).

### Constaté à l'étape 3, à corriger à l'étape 4

**Couche texte illisible mais présente → jamais de repli image (mode Tesseract).**

`223111PE011_extrait_10pages.pdf` porte une couche OCR invisible « Paper Capture »
illisible (ex. `SlQW, AEOJITSSANI'` pour `SIGNAL ABOUTISSANT`). En mode Tesseract,
`converter.py` passe par `_extraire_depuis_pdf()` → `PdfTableExtractor._extract_page()` :
la page a assez de mots pour sauter le repli OCR (`_MIN_WORDS`), l'analyse de cette
couche échoue (`success=False`), et aucune relecture de l'image n'est tentée.
Résultat : **5 pages sur 10 ne produisent aucune ligne** (pages 1, 2, 3, 9, 52).
Forcer Tesseract sur l'image de la page 52 donne bien des lignes.

Le mode Claude n'est pas touché : `_extraire_pdf_comme_images()` rasterise et
contourne la couche texte.

Correction prévue (étape 4) : image avec couche OCR invisible → ignorer la couche,
traiter comme un scan. Ne pas modifier `pdf_extractor.py` avant.

Test à ajouter à l'étape 4 : l'extrait 10 pages en mode Tesseract doit produire des
lignes sur les 10 pages (aujourd'hui 5 sur 10).

---

## Étape 4 — Routage PDF par page, modes vision (2026-09-28)

Livré : `pdf_extractor.classer_page` / `grille_page` / `PdfTableExtractor.extract_page_grille`,
routage dans `Converter._extraire_pdf_comme_images`, paramètres `PDF_*` de `config.py`
(`PDF_ROUTAGE_VECTORIEL = False` rend la v1.7). Tests : `tests/test_routage_pdf.py`.
`ocr_processor.py` non modifié.

Classement (signaux mesurés sur les fixtures, pas supposés) :

| Page | Image pleine page | Texte | Classement | Traitement |
|------|-------------------|-------|------------|-----------|
| 223400PE137, 51 pages de texte | non (≤ 3 %) | visible, polices intégrées | vectoriel | grille, sans OCR |
| 223400PE137, pages 3 et 5 (gardes scannées en 4 bandes, ≈ 40 %) | non | aucun | vide | ignorée |
| 223111PE011 extrait, 8 pages Paper Capture | 100 % | invisible (rendu 3) | OCR invisible | rastérisée → vision |
| 223111PE011 extrait, pages 104 et 122a (TP3 refaites) | aucune | visible | vectoriel | grille |
| 6A23111PE102 scan | 100 % | aucun | scan | rastérisée → vision |

### Chiffres mesurés

| Mesure | v1.7 | Étape 4 |
|--------|------|---------|
| 223400PE137 (53 pages) en mode Claude : appels API | 53 | **0** |
| 223400PE137 : durée du routage (53 pages) | — | ≈ 1 s (hors génération Excel, ≈ 20 s) |
| 223400PE137 : tableaux extraits | — | 48 / 53 (47 dans l'Excel : page PAGE 36 n'a qu'une ligne, écartée par `MIN_DATA_ROWS = 3`) |
| Page 122a de l'extrait, lecture grille contre vérité terrain | 2 erreurs (TEL PBT, TEL PEP) | **56 / 56 cellules exactes** |

Écarts assumés par rapport à `outils_reference/grille.py` :
- lignes regroupées avec une tolérance en y (`PDF_GRILLE_TOLERANCE_Y = 2,0 pt`) au lieu de
  `round(y)` : sur PE137 page 38, « D_T 01B » est posé 0,7 pt plus haut que « 1847N » et
  formait sinon une ligne à part ;
- pages sans cadre (TP2 : pages 37, 38, 51) : les titres sont centrés au-dessus des colonnes
  (SIGNAL : titre en colonne 63, données en colonne 52). Couper au début des titres enverrait
  le SIGNAL dans ABOUTISSANT : entre deux titres, la coupure est posée après la plus large
  bande de colonnes vide sur toutes les lignes de données. La marge commune de chaque colonne
  est retirée (alignement relatif conservé).

### Dictionnaire : valeurs exactes réécrites — corrigé (autorisé le 2026-09-28)

`BornierTableExtractor._fill_worksheet` (`ocr_processor.py:3116-3117`) n'exemptait de
`data_dictionary.correct()` que `claude-vision`, `log-replay` et `hybrid`. Les pages
`pdf-grille` étaient « corrigées » vers des valeurs voisines : sur 223400PE137, **31 valeurs
exactes distinctes** faussées dans l'Excel, par exemple :
- « ALARME RUPTEURS Q1 » → « RU/ALARME RUPTEUR Q2 »
- « COMMUN TS GR4 315TS » → « COMMUN TS GR4 312TS »
- « BS NORMAL (105G26) » → « BS NORMAL (106B) »
- « -/+ CPA/ACM G26 » → « -/+ CPA/ACM G36 »

Correction : `'pdf-grille'` ajouté à la liste d'exemption (seule ligne modifiée dans
`ocr_processor.py`). `test_valeurs_exactes_non_corrigees_par_le_dictionnaire` est passé
d'échec attendu à test normal.

**À traiter à l'étape 9.** Le dictionnaire remplace par des valeurs VOISINES qui désignent un
AUTRE équipement (RUPTEURS Q1 → RUPTEUR Q2, 315TS → 312TS) : ce n'est pas une correction
d'OCR, c'est une substitution silencieuse. À l'étape 9, il ne remplacera plus rien en silence,
dans aucun mode (Tesseract compris).

### Mesure de 223400PE137 contre le PDF (après correction)

`mesurer_precision.py 223400PE137.xlsx 223400PE137.pdf --modele REPARTITEUR` (mode Claude,
routage actif, 0 appel API) :

| Mesure | Valeur |
|--------|--------|
| Pages appariées | 47 |
| Cellules identiques | 9 460 / 9 460 — **0 caractère faux** |
| Écarts de position | **0** |
| Écarts de pied de page | 0 |
| Lignes orphelines | 0 |
| Page de référence sans partenaire | 1 : PDF page 40 (PAGE 36, 1 ligne) — écartée par `MIN_DATA_ROWS = 3`, écart toléré, à traiter à l'étape 6 |

Corrections faites dans l'outil de mesure pour obtenir ce chiffre (défauts de l'outil,
pas de la conversion) :
- appariement des pages : la similarité fine (ligne à ligne) n'est calculée que sur les
  `MESURE_CANDIDATS_PAGE = 3` pages les plus proches en mots — la version précédente faisait
  ~7 millions de comparaisons sur 53 pages et dépassait 5 minutes ; maintenant ≈ 19 s ;
- lecteur de référence PDF : ignorait mal l'en-tête et le soulignement « °°°° » des pages à
  cadre (88 lignes orphelines), ne lisait pas les pages sans cadre, ne reconnaissait pas le
  pied « PET : » des pages TP2.

**Limite de la mesure** : sur les pages sans cadre (TP2), la référence est découpée en
colonnes par le même découpeur que la conversion (`extract_page_grille`). La mesure y vérifie
les caractères et la chaîne d'écriture (routage, dictionnaire, Excel), pas le découpage.

### Étape 4 (suite) — routage étendu à tous les modes, images cumulées

Décisions du 2026-09-28 :
- **Tous les modes** : le routage dépend de la nature de la page, pas du moteur. En mode
  tesseract/docling, `PdfTableExtractor._extract_page_routee` : vectoriel → grille ; couche OCR
  invisible → couche ignorée, repli image `_extract_page_ocr` ; scan → chemin v1.7.
  Ollama reste dans le routage des modes vision.
- **Nouvelle règle** (ordre) : texte vectoriel exploitable → grille ; sinon images CUMULÉES ≥
  `PDF_SEUIL_IMAGE` (0,10) → pipeline scan ; sinon page ignorée, avec dans le journal
  « page N ignorée : <raison>, images = X % de la page ». Les gardes 3 et 5 de 223400PE137
  (4 bandes de 10 %) repassent donc en scan : **2 appels API en mode Claude** (pages classées
  non-listing par Claude), **0 en mode Tesseract**. Choix complémentaire : une page en police
  non intégrée avec ≥ 20 caractères visibles va au pipeline scan plutôt que d'être ignorée.
- **Lignes de section dans la grille** : « NOM DU CABLE : … » (6A23111PE102, export Excel)
  était pris pour un pied de page (« CABLE : ») et vidait les pages 7 à 12 ; il est désormais
  reconnu comme ligne de section, comme dans le lecteur v1.7. Régression détectée par
  `test_lecture_du_pdf_final_par_le_converter` (5 pages avec tableau au lieu de 11).

Contrôles mesurés :

| Contrôle | Résultat |
|----------|----------|
| 223111PE011 complet (129 pages, Paper Capture), classement | **25 vectoriel** (pages 2, 16, 24, 26, 28, 35, 37, 38, 39, 40, 46, 50, 51, 52, 108, 109, 111, 116, 117, 118, 119, 120, 123, 126, 128) + **104 couche OCR invisible** — conforme à la liste attendue, aucune page en désaccord |
| Extrait 10 pages en mode Tesseract (réel, 49 s) | **9 pages sur 10 avec lignes** (étape 3 : 5 sur 10) ; la 10ᵉ est la page 104, câble « RESERVE », sans ligne de données ni dans le PDF ni dans la vérité terrain |
| Page 52 de l'extrait redécoupée en 4 bandes de 10 % | routée en pipeline scan (faux moteur vision appelé une fois) |
| 6A23111PE102 final (export Excel), grille contre lecteur v1.7 | mêmes nombres de lignes sur les 13 pages ; la grille ne coupe plus les mots (v1.7 : « R » │ « ESERVE NON CABLEE ») |

Le test « 10 pages sur 10 » demandé à l'étape 3 est écrit en « 9 pages sur 10, la page 104
n'ayant pas de ligne » (`test_extrait_toutes_les_pages_a_tableau_produisent_des_lignes`).

### Grille : défaut hérité de outils_reference/grille.py — corrigé (2026-09-28)

Signalé en construisant la vérité TP2 v3 ; présent aussi dans `pdf_extractor.grille_page`.
`grille.py` posait chaque span à sa colonne de départ puis comptait ses caractères :
- un espace isolé dans son propre span était absorbé : « VERSPCC », « DUPCC »,
  « COURSCYCL » (lignes 1769N, 1829N, 1843N) ;
- un span en police 10,08 au lieu de 11,04 (« D_T 02A », « D_T 01B », « D_S 01B ») gardait
  ses 8 espaces alors que son 2e champ est visuellement en colonne 10.

Correction : chaque mot placé d'après sa propre x, pas mesuré sur la page. Le placement
tout-absolu demandé (colonne = round((x - x0) / pas) pour chaque mot) créait deux
régressions mesurées, faute de grille commune aux champs (ABOUTISSANT à 34,50 colonnes du
TENANT, JAR à 24,51) : « PHONIE RAME G21DU PCC » (espace perdu) et « D_S 01B » désaligné
d'une colonne. Retenu : 1er mot d'un span en absolu, mots suivants du span à partir du début
du span avec le pas de la page, et au moins un espace entre deux spans séparés d'un
demi-caractère ou plus.

| Contrôle | Résultat |
|----------|----------|
| 45 pages à cadre de 223400PE137 (8 796 cellules de données) | aucune cellule changée |
| 6A23111PE102 final (13 pages) | aucune cellule changée |
| Pages TP2 (32, 33, 49) | 6 lignes changées, toutes voulues : 3 espaces retrouvés, « D_T 02A », « D_T 01B », « D_S 01B » au pas de la page |
| 223400PE137 contre le PDF | 9 460 / 9 460 cellules, 0 position fausse (PAGE 36 écartée par `MIN_DATA_ROWS`) |

**Vérité TP2 v3 (2026-09-28)** — `tests/fixtures/223400PE137_TP2_verite.xlsx`, méthode
indépendante (chaque mot à sa x réelle, bornes de colonnes en points). Vérifié : 167 lignes
(55 + 56 + 56), 2e champ du TENANT en colonne 10 sur les 167, 7 espaces dans « D_T 02A »,
« D_T 01B », « D_S 01B ».

Positions : une vérité xlsx fait désormais foi aussi pour les positions — ses lignes sont
`exact`, les colonnes de début des sous-champs sont comparées (comme contre un PDF).

| Mesure 223400PE137, pages TP2, contre la vérité v3 | Résultat |
|----------------------------------------------------|----------|
| Cellules | **668 / 668** identiques |
| Positions fausses | **0** |
| Pieds de page faux | 0 |
| Lignes orphelines | 0 |

Test doré `tests/test_mesurer_precision_tp2_golden.py` (grille → Excel → relecture → mesure,
sans OCR) : il échoue si « D_T       02A » devient « D_T        02A » (écart de position
TENANT (0, 10) → (0, 11)). Sur 223111PE011, la comparaison des positions n'ajoute aucun écart.

Fixtures : `223400PE135.pdf` et `223400PE136.pdf` étaient inversés ; noms échangés. PE135 :
189 pages (FIL / TENANT / ABOUTISSANT) ; PE136 : 389 pages (BORNE / COULEUR / JARRETIERES) ;
tous deux exportés de Word, texte vectoriel.

### Reste ouvert

- **Qualité du repli image Tesseract** sur les pages Paper Capture : lignes lues en réel,
  page 52 (60 lignes dans la vérité) → 8 lignes, page 119 (60) → 42. Le routage n'y est pour
  rien : c'est la lecture Tesseract de ces scans qu'il faudra mesurer et améliorer.
- **Numéro de page « 122a »** lu « 122 » dans les métadonnées : `_extract_meta` ne retient que
  les chiffres de PAGE (comportement v1.7, non modifié).

---

## Étape 5 — Modèle Claude et campagne de mesure (2026-09-28)

Livré : modes claude et hybrid sur Claude Opus 5 puis Opus 5.5 (table
`CLAUDE_CAPACITES_MODELES`, champ thinking omis pour Opus 5.5 / Fable 5.1), refus journalisé
avec sa catégorie, garde-fou de troncature (64 000 tokens à effort xhigh/max, réponse
tronquée = page en erreur), SDK anthropic 1.8, `campagne_mesure.py`.

**Décision : `claude-opus-5-5`, effort `medium`** — le réglage par défaut, inchangé.

### Campagne du 2026-09-28 (commit 2d522c5)

Extrait 223111PE011 (10 pages : 8 relues par Claude, 2 vectorielles lues en grille), mesuré
contre la vérité terrain validée ; 656 cellules comparées.

| Réglage | Passages | Cellules fausses (moy.) | Écart entre passages | Positions | Pieds faux* | Coût moyen / passage | Durée |
|---------|----------|-------------------------|----------------------|-----------|-------------|----------------------|-------|
| Haiku 4.5, sans effort | 2 | 442 | 4 | 0 | 21 / 19 | 0,042 $ | ~58 s |
| Opus 5.5, medium | 2 | **2** | 0 | 0 | 8 / 9 | 0,301 $ | ~79 s |
| Opus 5.5, high | 1 | **2** | — | 0 | 7 | 0,314 $ | 84 s |

\* Remesurés après la séparation du complément de pied de page (commit 75985e2) ; le CSV de
campagne garde les valeurs de l'outil au moment du passage (18, 9, 9).

223400PE137 avec Opus 5.5 medium : **2 appels API** (les 2 gardes scannées, classées
non-listing), **0 cellule fausse sur 9 460**, 0,053 $. Seule page sans correspondance : PAGE 36
(1 ligne, `MIN_DATA_ROWS`).

**Coût réel total : 1,05 $** (6 passages ; tokens renvoyés par l'API × prix de `config.py`).
**Aucune page en erreur** : ni refus, ni réponse tronquée ; modèle servi conforme au modèle
demandé sur toutes les pages.

Constats :
- Haiku décale les colonnes (TENANT coupé en « PH » + « QTEL2 09 » envoyé dans SIGNAL :
  ~145 écarts chacun sur TENANT, SIGNAL, ABOUTISSANT), ajoute 4 à 8 lignes, fausse les pieds
  (223111PE011 lu « PB011 », « WFHA104 », « TE203 »).
- Opus 5.5 : high ne corrige rien par rapport à medium (+4 % de coût) ; les deux passages
  medium sont identiques cellule pour cellule. Coût réel 0,30 $ / passage (estimé ~1,2 $) :
  la réflexion reste courte (185 à 2 800 tokens de sortie par page).
- Pieds faux restants d'Opus (medium 1) : 6 compléments perdus (pages 2, 3, 119, 122, 122a,
  123), PAGE « 122a » lu « 122 », TYPE de 122a perdu. Le complément perdu varie d'un passage à
  l'autre (page 52 au passage medium 2, page 122 retrouvée en high). À corriger à l'étape 7.
- Pages 9 et 104 absentes de l'Excel dans tous les passages : lues par le modèle (page 9 :
  2 lignes) mais écartées par `MIN_DATA_ROWS = 3` (page 104 : 0 ligne). Étape 6.

### Cas de référence pour les étapes 8 et 9 — erreurs d'Opus à signaler

Page 119, colonne SIGNAL, les 2 cellules fausses d'Opus 5.5 (medium et high) :

| Ligne | Vérité | Opus 5.5 |
|-------|--------|----------|
| 5 M (PH QC 05) | OC FS 14 50 + OCFSCS | CC FS 14 50 + CCFSCS |
| 6 BC (PH QC 06) | OC FS 14 50 | CC FS 14 50 |

Vérifié à 400 DPI : la première lettre est un O fermé, identique au O de « OCC ZONE ». La vérité
a raison, Opus se trompe (confusion O/C dans cette police). **Ces 2 cellules devront porter une
alerte** aux étapes 8 (double lecture) et 9 (plus aucune substitution silencieuse).

Passage Haiku du matin (`mesures/haiku_passage1/`) : non retenu — document complet (129 pages)
interrompu après 20 pages, avant les commits Opus, sans tokens journalisés.

## Étape 6 — Pages, numéros, caractères illisibles (2026-09-29)

Mesure avant/après chaque commit **sans appel API** : la conversion complète est relancée
(routage, grille, génération Excel), le client Anthropic étant remplacé par un faux qui renvoie
les réponses enregistrées dans les journaux de la campagne (`mesures/claude-opus-5-5_medium_1`
pour l'extrait 223111PE011, `…_medium_3` pour 223400PE137). Seul le code après l'OCR change.

### Commit 1 — MIN_DATA_ROWS = 1, pages écartées journalisées, tableau vide conservé

| Mesure | Avant | Après |
|--------|-------|-------|
| Extrait 223111PE011 : pages appariées / 10 | 8 (9 et 104 absentes) | 10 |
| Extrait : cellules fausses | 2 / 656 | 2 / 664 (les mêmes, page 119) |
| Extrait : pieds faux | 8 | 8 |
| 223400PE137 contre son PDF : pages appariées | 47 (1 absente) | 48 |
| 223400PE137 : cellules fausses | 0 / 9 460 | 0 / 9 464 |
| 223400PE137 contre la vérité TP2 | 0 écart | 0 écart |

- Page 9 (2 lignes) écartée par `MIN_DATA_ROWS = 3` : retrouvée.
- Page 104 (CABLE : RESERVE, 0 ligne) : la grille rendait `success=False` faute de ligne ;
  un en-tête reconnu suffit désormais à en faire un tableau, conservé vide.
- Chaque page écartée écrit « page ignorée : <numéro> <raison> » dans le journal de
  l'interface (5 pages de garde dans PE137, raisons : pas d'en-tête du modèle / pas un
  tableau de câblage). Aucune page de tableau écartée sur les deux documents.

### Commit 2 — numéros de page à suffixe, jamais renumérotés ni retriés

| Mesure | Avant | Après |
|--------|-------|-------|
| Extrait 223111PE011 : pieds faux | 8 | 7 (page 122a lue « 122a », plus « 122 ») |
| Extrait : cellules fausses / pages | 2 / 10 pages | 2 / 10 pages |
| 223400PE137 (vérité TP2 et PDF) | 0 écart, 48 pages | 0 écart, 48 pages |
| Alertes de séquence | — | aucune (les deux documents sont croissants) |

- Lecture du numéro : lettre isolée après les chiffres gardée (`122a`, `44B`) ; « 92PET »
  reste 92. PDF (grille et couche texte) : casse d'origine. Docling et Tesseract
  (`ocr_processor.py`, ligne autorisée le 2026-09-29) : le texte y est passé en majuscules
  avant lecture, le suffixe sort donc en majuscule (`122A`) — limite connue.
- `generer_excel` ne trie plus par PAGE et ne remplit plus un PAGE vide depuis le nom
  d'image : ordre du document conservé, alerte au journal pour un recul, une répétition ou
  un numéro illisible. Idem pour la feuille « tableaux word ».
- Prompt Claude : « PAGE : recopie le numéro exactement comme imprimé, lettre finale
  comprise ». **Non mesuré** : le rejeu renvoie les réponses déjà enregistrées ; à vérifier au
  prochain passage réel (Opus lisait « 122 » pour 122a).
- `tests/test_non_regression_xlsx.py` : entrée remise dans l'ordre 1-2-3 (elle testait le tri
  par un ordre 3-1-2) ; instantané **non régénéré**, identique.

### Commit 3 — « ?? » pour un caractère illisible, gardé et coloré

- Prompt Claude (règles) : « Si un caractère est illisible, écris ?? à sa place. Ne devine
  jamais, ne corrige jamais un mot, recopie exactement. » (marqueur `MARQUEUR_ILLISIBLE`).
- Le parseur et l'Excel gardent « ?? » tel quel (dictionnaire déjà sauté en mode Claude) ;
  `generer_excel` colore chaque cellule qui le contient (`COULEUR_ILLISIBLE`, rouge clair,
  commentaire « vérifier sur le document d'origine ») et compte ces cellules au journal.
  `ocr_processor.py` non modifié : le marquage est fait après remplissage de la feuille.
- Mesure (rejeu) : inchangée — extrait 2 cellules fausses / 664, 7 pieds faux, 10 pages ;
  PE137 0 écart, 48 pages. Attendu : les réponses rejouées sont antérieures à la consigne.
  **L'effet de la consigne (et de celle sur PAGE) reste à mesurer au prochain passage réel**,
  en particulier sur le cas de référence page 119 (« OC » lu « CC »).
