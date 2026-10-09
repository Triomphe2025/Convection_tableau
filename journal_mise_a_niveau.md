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

### Décisions et constats de fin d'étape 6 (2026-09-29)

- **Limite connue, non corrigée (décision du 2026-09-29)** : en modes Tesseract et Docling,
  le suffixe de page sort en majuscule (« 122a » → « 122A ») car le pied est passé en
  majuscules avant lecture. Ces modes ne servent pas en production.
- **Reporté à l'étape 7** : nom de bornier inventé depuis le nom de fichier (« BORNIER :
  bornier_57 », repli `meta.get('BORNIER') or img_stem` dans `generer_excel`). Règle retenue :
  un champ absent du pied reste vide avec une alerte, jamais une valeur tirée du nom de fichier.
- Test du nouveau comportement d'ordre :
  `tests/test_numeros_page.py::TestGenererExcelOrdreEtNumeros::test_pages_3_1_2_restent_en_3_1_2_avec_alerte_de_recul`
  (commit 714c801) — vérifié par mutation.

**Les 7 pieds faux restants de l'extrait (rejeu Opus medium 1) : 6 compléments + 1 TYPE**

| Page | Libellé | Vérité | Sortie | Moteur |
|------|---------|--------|--------|--------|
| 2 | COMPLEMENT | REF CE 8707905 | vide | Claude (TYPE lu « 3PC200 ») |
| 3 | COMPLEMENT | REF CE 8707905 | vide | Claude (TYPE lu « 3PC200 ») |
| 119 | COMPLEMENT | CORDON TYPE 40 | vide | Claude (TYPE lu « 30P887 ») |
| 122 | COMPLEMENT | 8/10 | vide | Claude (TYPE lu « 2P.279 ») |
| 122a | TYPE | 7P.279 | **vide** | grille PDF |
| 122a | COMPLEMENT | 6/10 | vide | grille PDF |
| 123 | COMPLEMENT | 8/10 | vide | Claude (TYPE lu « 4PK13 ») |

Page 122a (vectorielle, lue sans OCR) : la grille contient bien `TYPE : 7P.279      6/10`, mais
`PdfTableExtractor._extract_meta` (champs de `footer_extract_fields`) a une classe de caractères
sans « . » (`[A-Z0-9/][A-Z0-9\s\-/]`) — « 7P.279 » ne correspond pas, le TYPE est perdu en
entier — et retire volontairement un « n/n » final, pris pour un compteur de pages, alors que
c'est ici le complément. Défaut de lecture du pied PDF, pas de Claude. À traiter à l'étape 7
avec les compléments.

### Étape 6 — passage réel (2026-09-30, commit 84cab76)

Opus 5.5 medium sur l'extrait 223111PE011, dossier
`mesures/223111PE011_extrait_10pages_claude-opus-5-5_medium_1`, 8 pages envoyées à Claude,
0 page en erreur.

| Mesure | Étape 5 (medium 1) | Rejeu étape 6 | Passage réel |
|--------|--------------------|---------------|--------------|
| Pages présentes | 8 / 10 | 10 / 10 | 10 / 10 |
| Cellules fausses | 2 / 656 | 2 / 664 | 2 / 664 |
| Pieds faux | 9 | 7 | 8 |
| Lignes manquantes / en trop | 0 / 0 | 0 / 0 | 0 / 0 |
| Coût | 0,301 $ | — | 0,304 $ |

- Pages 9 et 104 présentes ; aucune page écartée, aucune alerte de séquence.
- Cellules fausses : les 2 de la page 119 (« OC » lu « CC »), inchangées.
- Aucun « ?? » dans les 8 réponses, donc aucune cellule colorée.
- Prompt plus long : +112 tokens d'entrée par page (+0,003 $ par passage).
- 8 pieds faux = 7 compléments perdus (pages 2, 3, 52, 119, 122, 122a, 123) + TYPE de 122a
  perdu en entier (lecteur de pied PDF). L'écart de plus qu'au rejeu est le complément de la
  page 52 (« CORDON TYPE 60 ») : lu au passage rejoué, pas cette fois — variation déjà notée à
  l'étape 5, pas un effet du code. Étape 7.

**Limite connue — consigne « lettre du numéro de page » non testable.** 122a est la seule
page à suffixe de 223111PE011 (audit) et elle est vectorielle : lue dans le PDF sans Claude,
elle sort bien « 122a ». Ni l'extrait ni le document complet ne peuvent donc montrer l'effet de
la consigne. Filet de sécurité : si Claude lisait « 122 » pour une page 122a scannée, suivant
la page 122, `alertes_sequence_pages` écrirait « page 122 répétée » dans le journal.

**Consigne « ?? » conservée** (coût quasi nul). Elle ne protège pas contre une erreur commise
avec assurance : page 119, Opus lit « CC » sans hésiter et n'écrit pas « ?? ». Détecter ces
erreurs est le rôle des étapes 8 (double lecture) et 9 (plus aucune substitution silencieuse).

## Étape 7 — Pied de page lu tel quel, rien d'inventé (2026-09-30)

Choix validés le 2026-09-30 : complément découpé par une table en config ; P.E.T. « EPEULE » et
INDICE « 0 » supprimés comme « bornier_57 » ; pied de l'Excel = lignes brutes ; révisions lues
sur les gardes vectorielles et demandées à Claude sur les gardes scannées.

- `pied_page.py` (nouveau, module pur) : nettoyage des lignes (cadre, séparateurs, logo),
  toutes les paires `LIBELLÉ :` sans liste figée, COMPLEMENT pour le texte libre, indices de
  révision. Libellés à valeur d'un mot : `PIED_LIBELLES_UN_MOT` (TYPE, CABLE, INDICE, PAGE,
  BORNIER) ; « n/m » compteur seulement après PAGE/FOLIO (`PIED_LIBELLES_COMPTEUR`).
- Grille PDF et `_extract_meta` PDF passent par ce module (fini « TYPE : 7P.279 » perdu et
  « 6/10 » supprimé ; plus de O→0 silencieux sur l'INDICE lu en couche texte).
- Claude : bloc `PIED_BRUT:` recopié ligne à ligne, structuré localement ; le JSON META ne
  complète que les libellés absents du pied recopié, un désaccord devient une alerte.
  Pages de garde : ligne `REVISIONS:`.
- Excel : le pied affiche les lignes brutes (dernière ligne en ligne 2, les précédentes bout à
  bout en ligne 1) ; les formats du modèle ne servent plus que sans pied brut (Tesseract,
  anciens journaux). Plus de nom de bornier tiré du fichier, de P.E.T. de repli ni d'INDICE 0.
- Contrôles, en alerte seulement : champ de `footer_extract_fields` absent (groupé par champ),
  INDICE absent des révisions des gardes, N° PLAN différent de la majorité, désaccords du
  lecteur. Aucune valeur modifiée.

### Mesure par rejeu (sans API)

| Mesure | Avant (fin étape 6) | Après |
|--------|---------------------|-------|
| Extrait : pages / cellules fausses | 10 / 2 | 10 / 2 |
| Extrait : pieds faux | 7 | **5** (122a : TYPE 7P.279 et COMPLEMENT 6/10 retrouvés) |
| 223400PE137 contre son PDF | 48 pages, 0 écart | 48 pages, 0 écart |
| Alertes PE137 | — | BORNIER absent (48 pages, modèle REPARTITEUR) ; aucune alerte INDICE |

Les 5 pieds faux restants sont les compléments des pages lues par Claude (2, 3, 119, 122, 123) :
les réponses rejouées n'ont pas de bloc PIED_BRUT. **Seul le passage réel mesurera le nouveau
prompt** (cible : 0 pied faux).

### Outil de mesure ajusté (pas le produit)

Le pied brut garde l'espacement du document (« N°   PLAN », « INDICE        : ») : le lecteur de
mesure (`mesurer_precision._est_pied`, `mesure_precision._LABEL_PIED_RE`) tolère désormais
tout nombre d'espaces dans ses mots-clés. Sans cela la page 104 n'était plus appariée. La
comparaison, elle, ignorait déjà les espaces : sa sévérité ne change pas.

### Limites connues

- « JARRETIERAGE » (texte fixe du modèle REPARTITEUR) est écarté des valeurs par
  `mots_decor` ; il reste visible dans le pied brut.
- Logo : une ligne d'un seul mot en lettres (SIEMENS, MATRA) ou en lettres espacées
  (M A T R A) est prise pour le bloc gauche, pas pour du COMPLEMENT.
- Révisions de la garde de PE137 : quelques faux indices ramassés sous le tableau (AL2, 53,
  A4) ; ils élargissent la liste et ne peuvent pas masquer un INDICE absent.
- ~~Cellule gauche du pied = libellé du modèle~~ et ~~INDICE « 0 » du mode Tesseract~~ → corrigés le
  2026-09-30 (voir « Logo du pied » ci-dessous).
- ~~PE137 : alerte « BORNIER absent » sur les 48 pages~~ → remplacée le 2026-09-30 (voir ci-dessous).

### Suite de l'étape 7 (2026-09-30)

- **Alerte de champ absent** : un champ absent de TOUTES les pages donne une seule ligne,
  « BORNIER absent de tout le document : vérifier le modèle » (PE137 : 1 ligne au lieu de 48).
  L'alerte par page ne reste que si le champ manque sur une partie des pages seulement.
- **Tests dorés des étapes 3 et 4 inchangés** après l'ajustement du lecteur de mesure :
  recalculés sur e62b552 (avant l'étape 7, arbre de travail séparé) et sur l'étape 7, sorties
  identiques ligne à ligne (258 lignes, chaque écart détaillé). Étape 3 : 8 pages appariées,
  pages 9 et 104 orphelines, 419/656 cellules identiques (19 confusions, 61 contenus
  différents, 97 espacements, 60 manquants), 19 pieds faux, 4 lignes orphelines. Étape 4 :
  3 pages, 668/668, 0 pied faux, 0 position fausse.

### Logo du pied et INDICE Tesseract (2026-09-30, `ocr_processor.py` autorisé)

- La cellule gauche du pied prend le texte du document au format « M A T R A » ; vide si le
  document n'en montre pas. Plus jamais le libellé du modèle (« M  T  I » était inventé : les
  Excel corrigés à la main de PE135, PE136, PE137 portent « M A T R A »).
- Formes lues (`pied_page.logo_pied`) : lettres espacées (PE137), mot seul (« MATRA », pages
  TP2 de PE137), une lettre par ligne (logo vertical des scans de 223111PE011), avec ou sans
  cadre. Claude : ligne `LOGO:` demandée dans le prompt (un logo n'est pas une ligne de texte,
  Claude pourrait l'omettre du PIED_BRUT) ; à défaut, lettres relevées dans le PIED_BRUT ;
  désaccord = alerte.
- `ocr_processor.py`, lignes modifiées : 2144-2146 (INDICE absent = pas de clé, O→0 conservé
  pour un INDICE lu), 3259 (cellule gauche Excel = `meta.get('LOGO', '')`), 3367 (même chose
  dans l'ancienne sortie Word).
- Tests : `test_methods.py` vérifiait l'INDICE « 0 » inventé (2 tests réécrits : absent = pas
  de clé) ; l'instantané Excel (`test_non_regression_xlsx`) reste **non régénéré** : ses données
  fabriquées portent désormais le logo qu'un lecteur aurait relevé (`LOGO: 'M  T  I'`).
- Rejeu : PE137 0 écart, 48 pages, « M A T R A » sur les 48 pieds ; extrait inchangé (10 pages,
  2 cellules, 5 pieds faux). Cellule gauche des 8 pages Claude de l'extrait vide au rejeu (les
  réponses rejouées n'ont pas de ligne LOGO) : à vérifier au passage réel.
- **À confirmer** : les pages vectorielles de 223111PE011 (122a, 104) portent « SIEMENS »
  (horizontal) et non MATRA ; au format demandé la cellule vaut « S I E M E N S ».

### Champs constants d'un document (2026-10-01)

- Réglage par modèle `champs_constants` (P.E.T. par défaut ; éditeur de modèle, section
  « Champs constants du document » ; saisie « P.E.T., N° PLAN » acceptée). Anciens modèles de
  `templates.json` sans ce réglage : P.E.T. par défaut, fichier non modifié.
- Case vide d'un champ constant reprise des autres pages du MÊME document, à trois
  conditions : case vide (une valeur lue n'est jamais remplacée) ; toutes les pages qui portent
  le champ concordent (sinon case vide + alerte « non complété … ne concordent pas ») ; cellule
  du pied colorée (`COULEUR_DEDUIT`, bleu clair) avec le commentaire « déduit des autres pages
  du document ». La valeur est posée après son libellé vide dans le pied brut, ou ajoutée en fin
  de 1re ligne si le libellé n'y figure pas.
- Jamais repris : INDICE et PAGE (`PIED_CHAMPS_JAMAIS_DEDUITS`), même listés dans le modèle.
  `STATION_NAME` ne sert toujours à rien dans le pied.
- Rejeu : inchangé (aucun P.E.T. vide sur l'extrait ni sur PE137). Test : PE137 avec le P.E.T.
  vidé sur 1 page sur 48 → GRAND-BUT repris, coloré, commenté, autres pages intactes.

### Logo recopié tel qu'imprimé (2026-10-01, décision de l'utilisateur)

- Aucune conversion de forme : « SIEMENS » compact sur 122a et 104 (seule forme présente dans
  les PDF), « M A T R A » là où MATRA est imprimé espacé, « MATRA » là où il est imprimé
  compact (pages TP2 de 223400PE137 : pages 32, 33, 49). Le MATRA vertical des scans (une
  lettre par ligne) s'écrit « M A T R A ». Remplace la règle précédente (tout au format espacé).
- Claude : la ligne `LOGO:` demande le texte tel qu'imprimé, et pour un logo vertical les
  lettres séparées par une espace ; le parseur ne reformate plus. Désaccord avec le pied
  recopié jugé sans les espaces.
- Tests dorés des étapes 3 et 4 : identiques.

### Champs constants revus (2026-10-01, règles de l'utilisateur) — remplace la section précédente

- Liste dans `config.py` : `CHAMPS_CONSTANTS_DEFAUT = ("PET",)`, `CHAMPS_CONSTANTS_PAR_MODELE`
  par nom de modèle. Le réglage ajouté à l'éditeur de modèle et à `template.py` au commit
  eeba8cb est retiré (les deux fichiers reviennent à leur état antérieur).
- Jamais repris : INDICE, PAGE, TYPE, CABLE (`PIED_CHAMPS_JAMAIS_DEDUITS`), même listés.
- Case vide : reprise seulement si TOUTES les autres pages du document qui portent le champ
  donnent la même valeur ; cellule colorée, commentaire « déduit des autres pages du
  document ». Sinon case vide + une alerte ; pas de vote majoritaire.
- Valeur lue jamais remplacée ; si toutes les autres pages donnent une autre valeur : gardée +
  alerte « P.E.T. … différent des autres pages ».
- Jamais d'un document à l'autre : la déduction ne voit que les pages d'une même conversion
  (fonction pure, sans état ; testé).
- Tests : 47 EPEULE + 1 vide → remplie, colorée, commentée ; 46 EPEULE + 1 GRAND-BUT + 1 vide
  → vide + alerte ; 47 EPEULE + 1 EPEULF → EPEULF conservé + alerte ; INDICE vide → reste vide.
  Contre-épreuves (vote, remplacement, INDICE repris, alerte supprimée) : chacune fait échouer
  un test. Suite complète verte, tests dorés des étapes 3 et 4 identiques, rejeu inchangé.

### Pages de garde de 223111PE011 : fixture et page tournée (2026-10-01)

- `tests/fixtures/223111PE011_garde.pdf` : pages 1 (garde scannée, cartouche « Modifications »
  01 02 R R1 R2 TP1 03 TP2 TP3), 2 (tableau des révisions vectoriel, **tourné de 90°**), 3
  (tableau scanné, PAGE 1, INDICE R) et 16 (tableau vectoriel, PAGE 14, INDICE TP3) du document
  complet. Extrait de 10 pages et vérité inchangés.
- La page 2 était illisible en grille : `get_text` donne les positions de la page non tournée,
  chaque ligne y devenait verticale. `grille_page` ramène désormais les caractères au sens de
  lecture (`page.rotation_matrix`). Seule page tournée des 6 PDF de test et du document
  complet : aucune mesure existante ne change (tests dorés identiques, rejeu identique).
  Révisions lues : 01 02 R R1 R2 TP1 03 TP2 TP3 (+ « 08 », pris d'une ligne de suite :
  élargit la liste, ne masque rien).
- **Correction du journal de l'étape 6** : 122a n'est pas la seule page à suffixe du document
  complet ; les pages 34b et 34c existent (vectorielles, lues « 34b », « 34c »).

## Vérification de conversion : cahier des charges atteint (2026-10-02)

Test `test_criteres_du_cahier_des_charges` (6A 23111PE102, cibles ≤ 20 alertes et ≥ 98 %, non
baissées) : il échouait à 57 alertes et 93,5 %. Écart analysé avant correction.

### D'où venait l'écart avec outils_reference/pdf_table_compare.py

1. **Pas le même couple** : le prototype compare le scan au PDF final ; le test comparait le scan
   au journal Claude (vraies erreurs de Claude comprises). Relancé le 2026-10-02 : 98,76 %, 19
   cellules (98,89 %, 17 relevés auparavant, autre version de Tesseract).
2. **Le prototype compte plus large** : 546 cases vides comptées « identiques » (98,76 → 98,08 %),
   écart toléré si similarité ≥ 0,90 (→ 96,87 %, 31 alertes ; tolérance qui classerait « 48V »
   lu « 4H » en simple artefact), 31 lignes orphelines ni comptées ni vérifiées (→ 62 alertes).
3. **Lecture de référence bruitée** : notre relecture du scan passait par le moteur de
   conversion (rendu ×3, ~216 DPI) ; ~30 alertes = mots non lus (« RESERVE » devant « CABLEE »,
   « EP. » devant « STAT/TS »), 7 = lignes de pied lues comme données (« MATRA fe mm »).
   Remplacer seulement la lecture par celle du prototype donnait pire (73 alertes) : ponctuation
   parasite (« | 0038B », « ‘C14 », « EP, ») et pas de confiance par mot.

### Décisions (2026-10-02)

Cible sur les deux couples ; lignes orphelines comptées comme alertes ; lecture figée
`scan_lecture_tesseract.json` régénérée. Non repris du prototype : tolérance 0,90, cases vides
« identiques », lignes orphelines ignorées.

### Corrections

- `relecture_scan.py` (nouveau) : Tesseract psm 6 à 300 DPI, confiance par mot, colonnes sur
  les traits du cadre, lignes à clé de borne (clé repliée O→0, I/L→1 pour le seul test du
  motif : « AO1 », « col », « Pl »), en-tête et pied écartés. Appelé par
  `Converter.verifier_conversion` pour le scan de référence.
- `verificateur.py` : ponctuation parasite de l'OCR ignorée, virgule repliée sur le point ; une
  case que la relecture n'a pas lue (ou lue à confiance basse) est bénigne aussi dans le chemin
  par zones, comme elle l'était déjà pour une cellule seule.

| Couple | Avant | Après |
|--------|-------|-------|
| Scan / journal Claude | 57 alertes, 93,48 % | **7 alertes, 98,93 %** |
| Scan / PDF final | 56 alertes, 92,65 % | **4 alertes, 99,62 %** |

Les 7 alertes restantes (journal Claude) : 48V lu « 4H », DISCORDANCE lu DISCONTINUOSITE,
3 alertes pour deux lignes fusionnées par Claude page 13, et « CABLEE » lu sur sa propre ligne
page 11 (2 alertes, défaut de la relecture). Divergence DISCORDANCE trouvée sur les deux couples.
Test lent de bout en bout : 31 s au lieu de ~5 min. Tests dorés de la mesure de précision
identiques (`normaliser` sert aussi à ses signatures de ligne).

## Contrôle du banc de mesure avant l'étape 8 (2026-10-02, sans appel API)

**1. Compteurs non affichés, 4 passages réels de l'étape 7 (medium 2 à 5)** : 10 pages
appariées sur 10 ; par page (1, 2, 3, 9, 52, 104, 119, 122, 122a, 123) : 0 ligne absente, 0 ligne
en trop, 0 cellule « manquant », partout.

**2. Thermomètre** (`tests/test_mesure_thermometre.py`, graine 20261002) : copie en mémoire de
la vérité de l'extrait, fautes injectées sur des lignes distantes d'au moins deux lignes :
10 valeurs déplacées dans la colonne voisine, 10 mots supprimés, 5 lignes supprimées, 3 lignes
dupliquées, 2 paires de lignes inversées. Toutes retrouvées au bon endroit (cellule, ligne,
page) et aucun autre écart. Ajouts au banc :
- catégorie `GLISSEMENT_COLONNE` : les mots perdus par une cellule sont exactement les mots
  gagnés par sa voisine de la même ligne (multiensemble de mots), sans autre changement ;
- `LigneDeplacee` : ligne absente à sa place et en trop ailleurs, contenu identique (inversion) ;
- colonnes `glissement` et `lignes_deplacees` dans `mesures/campagne.csv` et `mesures.csv` ;
  un historique à l'ancien en-tête est réécrit avec les nouvelles colonnes (vides) pour que
  les valeurs ne glissent pas.
Contrôles : 30 autres graines, toutes vertes ; trois mutations du banc (glissement non détecté,
lignes déplacées non appariées, cellules jamais comparées) font chacune échouer le test.
Tests dorés des étapes 3 et 4 : chiffres identiques (la sortie v1.7 n'a ni glissement strict
ni ligne déplacée).

**3. « Positions fausses » sur l'extrait : ne mesure rien d'utile.** La vérité de l'extrait
n'a aucune cellule à double espace ou à retrait (0 sur les 10 pages, 104 et 122a comprises) ;
le marqueur `exact` est posé sur toutes ses lignes, la comparaison se réduit donc à « la
conversion n'a pas ajouté d'espaces ». Les positions ne sont réellement mesurées que contre
une référence en grille vectorielle (vérité TP2 de 223400PE137, ou un PDF vectoriel).

## Étape 7 — passage réel (2026-10-02, commit 51ec9c2) — document complet reporté à l'étape 10

### Extrait 223111PE011, Opus 5.5 medium (passages 6 et 7)

| Passage | Pages | Cellules fausses | Pieds faux | Lignes absentes / en trop | Glissements / déplacées | Coût |
|---------|-------|------------------|------------|---------------------------|-------------------------|------|
| 6 | 10/10 | 2 / 664 | 0 | 0 / 0 | 0 / 0 | 0,333 $ |
| 7 | 10/10 | 2 / 664 | 0 | 0 / 0 | 0 / 0 | 0,333 $ |

- Vrais appels : 16 identifiants de réponse distincts (`msg_011Cfdc…`), aucun vide, horodatages
  successifs (~50 s pour les 2 111 tokens de la page 52). Les réponses sont pourtant identiques
  au caractère près d'un passage à l'autre, et identiques à celles des passages 4 et 5 : le
  modèle rend la même réponse pour la même image et le même prompt. Ce n'est pas un rejeu.
- Les 2 cellules fausses restent celles de la page 119 (« OC » lu « CC »), cas des étapes 8 et 9.
- Avec les passages 2 à 5 : 0 ligne absente, 0 en trop, 0 cellule « manquant » sur toutes les pages.

### Contrôle INDICE — `tests/fixtures/223111PE011_garde.pdf` (2 appels, ~0,06 $)

- Page 1 (garde scannée) : Claude rend `REVISIONS: 01 02 R R1 R2 TP1 03 TP2 TP3`, conforme au
  cartouche imprimé. Page 2 (révisions vectorielles tournées de 90°) : mêmes indices, lus en
  grille sans appel (+ « 08 » parasite).
- Page 3 (scan, PAGE 1) : INDICE R ; page 4 (vectorielle, PAGE 14) : INDICE TP3 ; tous deux dans
  les révisions. Journal de conversion : aucune ligne « contrôle INDICE impossible » ni
  « INDICE absent des révisions » — contrôle fait, sans fausse alerte. Limite : le contrôle
  réussi ne laisse aucune ligne positive dans le journal, seulement l'absence d'alerte.
- Logo des pages Claude : « M A T R A » (ligne LOGO:), conforme au scan vertical.

## Positions des pages vectorielles contre la grille du PDF (2026-10-02)

`mesurer_precision.positions_contre_pdf` : les pages **vectorielles** du PDF source (classées
comme au routage ; scans et couches OCR invisibles exclus) sont lues en grille et appariées par
contenu à la sortie ; pour ces pages, leurs positions remplacent celles mesurées contre l'Excel
de vérité. Ligne de commande : `--pdf <source.pdf>` ; campagne : automatique.

Rappel de ce qu'est une position : l'écart entre les mots **à l'intérieur** d'une cellule, à
partir de son premier mot (`_decalages`) — pas le retrait de la cellule dans sa colonne.

| Sortie | Avant (contre la vérité) | Après (contre le PDF) | Pages vectorielles mesurées |
|--------|--------------------------|-----------------------|------------------------------|
| Extrait 223111PE011, passages réels 1 à 7 | 0 | 0 | 104 (0 ligne) et 122a (56 cellules) |
| Extrait 223111PE011, sortie v1.7 | 0 | 0 | 122a seule (v1.7 a perdu 104) |

Sur 223111PE011, la mesure reste presque vide de matière : 122a n'a aucune cellule à
espacement interne (« PH QTELMG 13 », un espace entre les mots). Nouveaux extraits, mesurés en
lecture seule (grille → Excel → relecture, comme PE137 TP2 ; fichiers non modifiés, tests à
venir avec leur intégration) : 223111PE012 pages 5, 9, 10 (« Bornier standard », 302 cellules,
1 à espacement interne) et 6A23111PE133 pages 7, 8 (« REPARTITEUR », 272 cellules dont **142** à
espacement interne, « RM       11B ») : 0 écart de position. Les 4 autres pages vectorielles de
ces extraits sont des gardes ou des pages de révisions (sans en-tête de tableau).
Contre-épreuve (test) : sur PE137, un espacement interne réduit à un espace dans la sortie est
retrouvé, à la bonne cellule.

## Vérité des positions des scans : feuille « Verite_positions » (2026-10-02)

Feuille facultative d'un Excel de vérité terrain, lue par `mesurer_precision.lire_verite_excel`.
**À remplir à la main** : la générer depuis Tesseract mesurerait le commit A avec son propre outil.

| Colonne | Contenu |
|---------|---------|
| Page | même valeur que la 1re colonne de `Verite_tableaux` (« Page extrait ») |
| Ligne | même valeur que la colonne « Ligne » de `Verite_tableaux` |
| Colonne | nom de colonne du tableau (FIL, TENANT, …), comme dans l'en-tête de `Verite_tableaux` |
| Sous-champ | n° du mot dans la cellule, à partir de 1 (un mot = suite de caractères sans espace) |
| Début | colonne, en caractères, du 1er caractère du sous-champ |

- Seuls les **écarts entre sous-champs** d'une même cellule comptent : l'origine du comptage
  (0 ou 1, bord de la cellule ou de la ligne) est libre. Exemple « PH  QTEL2   09 » :
  sous-champs 1, 2, 3 aux colonnes 1, 5, 13 (ou 0, 4, 12).
- Une cellule saisie n'est comparée en position que si son contenu est identique (une erreur de
  contenu est déjà comptée comme telle). Les cellules non saisies gardent la règle actuelle.
- Saisie contrôlée à la lecture : page, ligne ou colonne inconnue → erreur qui cite la ligne de
  la feuille ; colonne de feuille manquante → erreur qui la nomme. En-têtes reconnus sans
  tenir compte des accents ni de la casse (« Début », « debut »).
- Tests : `TestVeritePositions` (vérité fabriquée) — conformité, écart à sa cellule, origine et
  ordre libres, erreurs de saisie.

## Positions : début absolu, retrait compris (2026-10-05)

Définition validée : le début d'un mot est sa colonne en caractères, la **colonne 0 étant le
caractère le plus à gauche de cette colonne du tableau sur la page** ; le retrait d'une cellule
compte (exemple de l'original : 6A23111PE133 p. 15, TENANT « RM 03B » a son 2e mot une colonne
plus à droite que « DA 22 »). Avant : écarts entre mots d'une même cellule, retrait ignoré.

- `mesure_precision.origines_colonnes` : colonne 0 de chaque colonne, par page et de chaque
  côté (référence, sortie) ; `_debuts` remplace `_decalages`. S'applique à la grille vectorielle
  comme aux vérités `exact`.
- Feuille `Verite_positions` : « Début » est désormais **absolu** (colonne 0 = caractère le plus à
  gauche de la colonne sur la page), plus seulement l'écart entre sous-champs (section du
  2026-10-02 remplacée sur ce point).

| Mesure | Avant (retrait ignoré) | Après (début absolu) |
|--------|------------------------|----------------------|
| PE137 TP2 contre la vérité v3 | 0 | 0 |
| PE137 TP2 contre la grille du PDF | 0 | 0 |
| PE137 complet (48 pages) contre la grille du PDF | 0 | 0 |
| Extrait 223111PE011 (passage 7) contre vérité + PDF | 0 | 0 |

Inchangé, et c'est attendu : PE137 n'a qu'une cellule en retrait (« AAG 22-24 »), aucune dans les
pages TP2, et la chaîne grille → Excel la recopie à l'identique. Tests : un retrait d'une seule
cellule est détecté ; un retrait commun à toute la colonne ne l'est pas (même colonne 0) ;
tests dorés des étapes 3 et 4 identiques.

## Vérités des positions copiées dans les vérités validées (2026-10-05)

Source : `tests/fixtures/*_extrait_verite_positions.xlsx` (fournis). Feuille `Verite_positions`
copiée telle quelle (valeurs, largeurs, en-tête) dans la vérité validée de chaque extrait ;
empreinte des autres feuilles (valeurs, couleurs, commentaires, fusions, largeurs, validations,
mises en forme conditionnelles, images) identique avant / après ; copie refaite à l'identique
ligne à ligne.

| Extrait | Page | Positions | Cellules | Contrôle « Mot » |
|---------|------|-----------|----------|------------------|
| 223111PE011 | 52 | 549 | 240 (60 lignes) | 0 désaccord |
| 6A23111PE133 | 15 | 467 | 220 (56 lignes) | 0 désaccord |
| 223111PE012 | 39 | 211 | 140 (44 lignes) | 0 désaccord |

Contrôles avant copie : le mot de chaque ligne est bien le n-ième mot de la cellule visée dans
`Verite_tableaux`, chaque cellule saisie a tous ses mots, les débuts croissent d'un sous-champ au
suivant — aucune erreur de saisie à signaler. La lecture vérifie désormais « Mot » à chaque fois
(désaccord = erreur de saisie, citée avec sa ligne de feuille) et prend la page dans « Page
extrait » quand la feuille a aussi « Page document ».

Les vérités de 223111PE012 et 6A23111PE133 sont modifiées sur le disque mais **non commitées** :
elles restent hors de git avec le reste de leur jeu d'essai, en attendant leur intégration.

Effets sur les tests : le thermomètre retire les positions de sa référence (il éprouve les
fautes de contenu) ; la sortie v1.7 figée montre maintenant **120 écarts de position sur la page
52** (lecture Tesseract à un espace), première mesure réelle sur un scan.

## Chiffres de référence des positions pour le commit A (2026-10-05)

Positions fausses sur les pages à vérité des positions, sortie actuelle.

| Extrait | Page | Sortie mesurée | Cellules à vérité de position | Positions fausses |
|---------|------|----------------|-------------------------------|-------------------|
| 223111PE011 | 52 | rejeu (sans API) du passage réel 7, code au commit 58cb2d4 | 240 | **120** (TENANT 60, ABOUTISSANT 60 ; FIL, SIGNAL 0) |
| 6A23111PE133 | 15 | à mesurer après le 1er passage réel du nouvel extrait | 220 | — |
| 223111PE012 | 39 | à mesurer après le 1er passage réel du nouvel extrait | 140 | — |

223111PE011 page 52 : 0 cellule fausse en contenu ; la sortie n'a **aucun double espace** sur
240 cellules — Claude recopie « PH A104 01 » à un espace là où l'original aligne les mots en
colonnes 0, 6 et 16 (TENANT) ou 0, 6, 16 (ABOUTISSANT, 2e mot une colonne plus loin dans la
sortie : (0, 3, 9)). Les autres pages de l'extrait : 0 écart (pages vectorielles 104 et 122a
mesurées contre la grille du PDF).

## Contrôle INDICE réussi visible au journal (2026-10-05)

`generer_classeur.bilan_controle_indice` : quand des révisions ont été lues et que tous les
INDICE des pages y figurent, le journal porte « ✓ contrôle INDICE : OK, N page(s), indices lus :
… » ; un échec reste une alerte ⚠ (INDICE absent des révisions, ou contrôle impossible).
Rejeu sans API de la conversion des pages de garde (réponses du 2026-10-02) :
`✓ contrôle INDICE : OK, 2 page(s), indices lus : R, TP3`.

## Nouveaux jeux d'essai 6A23111PE133 et 223111PE012 — étape A (2026-10-05, sans appel API ni changement de l'appli)

### 1. Routage contre la feuille « Pages »

18 pages sur 18 conformes à « Appel Claude attendu ». 223111PE012 : pages 2 et 3 tournées à 90°
(garde scannée → Claude ; modifications vectorielles → grille) ; pages 4 et 6 à mediabox géante
(2481 × 3505 pt, scan intégré 2481 × 3505 px, soit un A4 à 300 DPI) → scan.
Mediabox géante : rendu du convertisseur ×3 = 7443 × 10515 px (78 Mpx, 235 Mo en mémoire,
0,5 s + 2 s d'écriture PNG) ; image envoyée 1823 × 2576 px (≤ CLAUDE_IMAGE_MAX_PX), lisible
(vérifié à l'œil sur la page 6). **À améliorer** : le rendu ×3 agrandit inutilement un scan déjà
à 300 DPI ; un rendu borné à la résolution du scan suffirait.

### 2. Lecture des vérités par le banc

- Colonnes du tableau : en-tête de `Verite_tableaux` (inchangé).
- Lignes « NOM DU CABLE : … » : sections (vérité et Excel livré), comparées texte entier ;
  dans l'Excel, la section est reconnue avant le pied (elle contient « CABLE : »).
- `Verite_pieds` sur deux niveaux : colonnes LOGO à PAGE = pied lu (`pied_lu`) ; colonnes
  « livré » = ce que l'Excel doit porter (`pied_texte`, « (déduit) » retiré). Libellés comparés =
  ceux de la vérité (schéma) ; stricts (espaces compris) : N° PLAN et PAGE livrés, LOGO. Texte
  fixe « Autre texte » (JARRETIERAGE) retiré des valeurs lues. Colonnes de remarque ignorées.
  Ancienne vérité 223111PE011 : mêmes chiffres qu'avant (19 pieds faux sur v1.7).
- `Alertes_attendues` contre les lignes ⚠ du journal de conversion (`--journal`, campagne :
  automatique) : alertes manquantes et fausses alertes comptées.
- `Verite_garde` : indices de révision ; contrôle INDICE jugé contre la ligne « ✓ contrôle
  INDICE : OK … » du journal et les INDICE de `Verite_pieds`.

### 3. Pages vectorielles (grille → Excel livré → mesure)

| Document | Pages | Cellules | Écarts de contenu | Sections | Positions (PDF) | Pieds faux |
|----------|-------|----------|-------------------|----------|-----------------|------------|
| 6A23111PE133 | 7, 8 | 268/272 | 4 : D3T O1A, D3T O1B, D6T O1B, D62T O1A (décision 3) | — | 0 | 2 |
| 223111PE012 | 5, 9, 10 | 358/358 | 0 | 6/6 | 0 | 6 |

Pieds faux restants :
- **N° PLAN « 6A23111PE 133 » / « 223111PE 012 » au lieu de « 6A23111 PE 133 » / « 223111 PE
  012 »** : défaut de la lecture en grille. Le pied est en police proportionnelle ; les mots
  suivants d'un span sont placés au pas moyen de la page, « PE » retombe contre le mot précédent
  et l'espace disparaît (le PDF contient bien « 6A23111 PE 133 »). À corriger dans l'appli.
- PAGE livrée de 223111PE012 (aucun numéro imprimé) : décision B1.
Journal de ces conversions partielles : « BORNIER absent de tout le document » (modèle
REPARTITEUR), « numéro de page illisible » × 3 et « PAGE absent de tout le document » (PE012),
« contrôle INDICE impossible » (pas de garde dans ces pages) : à juger sur le passage complet.

## Grille : espace entre deux mots d'un même span toujours gardé (2026-10-05)

Défaut trouvé à l'étape A : en police proportionnelle (pieds « N° PLAN : 6A23111 PE 133 »),
l'espace du texte source est plus étroit qu'un demi-pas de page ; la garde « au moins un
espace » ne jouait qu'au-delà d'un demi-pas, et « PE » se collait au mot précédent. Deux mots
d'un même span ont toujours été séparés par un espace dans le texte (c'est là qu'ils sont
coupés) : ils en gardent désormais au moins un. Entre spans différents, règle inchangée.
Effets : pages de garde et de modifications enfin lisibles (« Voir détail historique des
modifs » au lieu de « Voirdétailhistoriquedesmodifs ») ; pieds vectoriels de PE133 : 2 → 0
pieds faux ; PE012 : N° PLAN lu « 223111 PE 012 » comme imprimé. Pages de tableau : tests dorés
identiques (PE137 TP2, extrait), 907 tests verts.

## Décision B1 — pied livré (2026-10-05)

`generer_classeur.pied_livre`, après la déduction des champs constants et avant les alertes ;
la lecture (`metadata`, `PIED_BRUT` du journal Claude) reste telle qu'imprimée.
- Libellés du modèle de sortie, valeurs lues : « PET : » → « P.E.T. : », « N° PLAN » → libellé du
  format du modèle (REPARTITEUR et Bornier standard : « NO PLAN » ; REPARTITEUR 2 :
  « N° PLAN »). **À trancher** : ton exemple écrit « N°PLAN » ; aucun modèle ne l'écrit ainsi —
  il suffit de changer le format du modèle dans l'éditeur si tu le veux.
- N° PLAN sans espaces seulement si les pages l'impriment avec des espacements différents :
  PE012 (« 223 111 PE 012 » / « 223111 PE 012 ») → « 223111PE012 » ; PE133 (toujours
  « 6A23111 PE 133 ») inchangé ; **PE137 aussi normalisé** (« 223400 PE 137 » sur les pages TP2,
  « 223400PE137 » ailleurs → « 223400PE137 »). Une ligne d'information au journal.
- PAGE : si aucune page de tableau n'en porte, numérotation 1…n dans l'ordre, ajoutée en fin de
  dernière ligne du pied, cellule colorée « déduit » avec le commentaire « non imprimée :
  numérotée dans l'ordre des pages de tableau », une seule alerte « PAGE non imprimée dans tout
  le document : pages numérotées dans l'ordre » ; plus d'alerte « numéro de page illisible » ni
  « PAGE absent ». Si certaines pages en portent : rien n'est déduit (alertes inchangées).
- Tests mis à jour : pied de PE137 (libellé du modèle, N° PLAN normalisé) ; étape 6, numéro
  jamais tiré du nom d'image (la page seule est numérotée « 1 »). Tests dorés identiques.

## Décision B2 — logo tel qu'imprimé, vérifié sur 223111PE012 (2026-10-05)

Aucun changement de code : la vérification passe telle quelle (7 tests, `tests/test_logo_pe012.py`).
- Pages vectorielles 5, 9, 10 (SIEMENS dans la vérité) : grille → « SIEMENS » → cellule gauche de
  l'Excel « SIEMENS », collé.
- Pages scannées 4, 6, 7, 8 (M A T R A dans la vérité) : réponse Claude fabriquée « LOGO: M A T R A »
  → « M A T R A » dans l'Excel ; logo vertical recopié dans le pied sans ligne LOGO → « M A T R A ».
- Aucune forme n'est convertie en l'autre (« MATRA », « S I E M E N S » gardés tels que lus) : la
  forme finale sur les scans dépend donc de ce que Claude recopie — à lire au passage réel.

## Décision B3 — coquille O/0 dans le numéro de borne (2026-10-05)

`generer_classeur.corriger_coquilles_o`, à la génération de l'Excel (lecture et journal Claude
inchangés, `ocr_processor.py` non modifié) : dans TENANT, ABOUTISSANT ou BORNE, une cellule de
deux mots dont le 2e est `O\d{1,2}[A-Z]?` prend un 0 à la place du O ; cellule orange
(`COULEUR_CORRIGE`), commentaire « corrigé : l'original porte O1A », une ligne ⚠ par cellule
« page 18, ligne 3, TENANT : Corrigé O → 0 : l'original porte « D3T O1A » ». S'applique à tous
les modes (la coquille est dans l'original, pas dans la lecture).
- 6A23111PE133 p. 8 : les 4 cellules (lignes 3, 4, 8, 24) corrigées et signalées ; les 4 alertes
  de la feuille Alertes_attendues émises ; pages vectorielles PE133 : **0 écart** (4 avant).
- Inchangés : « OC21-37 », « QG 09 », « 0VG (EAS) », un O ailleurs qu'en 2e mot, en SIGNAL ou JAR.
- Instantané de non-régression et tests dorés identiques ; 941 tests passent.

## Passage réel du 2026-10-05 (commit 2c40424) et corrections de vérité

Opus 5.5, effort medium, 1 passage par extrait — 0,77 $ en tout.

| | PE011 | PE133 | PE012 |
|---|---|---|---|
| Cellules fausses | 2 / 664 (O/C d'Opus, connu) | 1 / 892 (« TRANS. » lu sur une tache) | 0 / 949 |
| Pieds faux, glissements, lignes déplacées | 0 | 0 | 0 |
| Lignes manquantes | 0 | 0 | 3 (sections « NOM DU CABLE » des scans) |
| Logo des scans | 8 × M A T R A | 3 × M A T R A | 4 × M A T R A |
| Coût | 0,333 $ | 0,217 $ | 0,217 $ |

Positions fausses : PE011 p. 52 = 120 / 240 (référence du commit A : 120, inchangé) ; PE133 p. 15 =
**112 / 220** (1re mesure : TENANT 56, ABOUTISSANT 56, espaces multiples ramenés à un) ; PE012
p. 39 = **0 / 139** (1re mesure ; original à un espace ; la 140e cellule est la section manquante).
Réponses de Claude au mauvais nombre de colonnes : **0 ligne sur 454**.

Vérités corrigées (seules cellules autorisées, toutes les autres valeurs vérifiées identiques) :
- 223111PE012, Alertes_attendues E2 : le texte du journal seul (la case portait aussi la consigne
  « Une seule ligne au journal : « … » », que le banc cherchait mot pour mot).
- 223111PE011 : feuille Alertes_attendues ajoutée (format de PE133) — « champ TYPE absent du pied,
  laissé vide : page(s) 104 » et « contrôle INDICE impossible : aucune liste de révisions lue sur
  une page de garde ».
- 6A23111PE133 p. 15, RC 20 : vérité **inchangée** (« TRANS » sans point). Preuve par Verite_positions :
  « C200 » en colonne 7 sur les lignes 37 à 40 (point tapé), en colonne 6 sur 41 à 48 dont RC 20 ;
  la marque n'occupe pas de colonne, c'est une tache. L'écart reste compté.

Remesure : alertes PE011 0 manquante / 0 fausse ; PE012 0 / 0 ; PE133 0 / 1 (BORNIER, point 2).

## Emplacement BORNIER occupé par un texte sans libellé (2026-10-05)

Décision : le champ n'est pas absent, il est remplacé. Règle générale, pas un cas JARRETIERAGE.
- `config.PIED_EMPLACEMENTS = {"BORNIER": "PET"}` : l'emplacement de BORNIER est la fin de la ligne
  qui porte P.E.T., après sa valeur. Le texte qui y est posé est reconnu s'il suit un grand blanc
  (≥ `PIED_ECART_EMPLACEMENT` = 3, pages vectorielles) ou s'il est fait des mots fixes du modèle
  (réponses Claude, à un seul blanc). Il va dans `EMPLACEMENT_BORNIER`, jamais dans P.E.T. ni
  COMPLEMENT ; `alertes_pied` ne compte plus la page comme « BORNIER absent ».
- Limite : à un seul blanc et sans mot fixe du modèle, rien n'est deviné (P.E.T. garde tout le
  segment, l'alerte reste) — Claude écrase les blancs (cf. positions, commit A).
- Pied livré : inchangé, il recopiait déjà le texte à sa place. Rejeu sans API du passage réel
  de 6A23111PE133 : 5 pieds « P.E.T. : SAINT MAURICE … JARRETIERAGE », alertes 0 manquante /
  **0 fausse** (1 avant), cellules et pieds inchangés.
- 223400PE137 : ses 48 pieds portent aussi JARRETIERAGE ; l'alerte « BORNIER absent de tout le
  document » disparaît (test mis à jour). 223111PE012 : BORNIER lu avec son libellé, inchangé.

## Lignes de section sur les pages lues par Claude (2026-10-05)

Cause des 3 lignes manquantes de 223111PE012 (scans p. 8, 18, 39) : le prompt disait « Ne pas
inclure les lignes de séparation 'NOM DU CABLE' ». Il demande maintenant de les recopier telles
qu'imprimées, à leur place parmi les lignes de données, sur une ligne `SECTION: NOM DU CABLE : …`
(mot de section du modèle) ; `_parse_pipe_response` en fait une ligne `{'type': 'section', 'text'}`
du format pivot, avant le filtre de pied (« CABLE : » est un marqueur de pied). Modes claude et
agent (prompt partagé) ; le mode hybride garde son propre prompt. Rejeu des anciens journaux
inchangé (aucune ligne SECTION:).

À mesurer par un passage réel sur 223111PE012 seul (≈ 0,22 $) : attendu 3 sections sur 3,
0 ligne manquante, rien d'autre ne bouge (949/949, 0 pied faux, alertes 0 / 0, INDICE conforme,
positions p. 39 : 0).

## Positions (espaces ramenés à un par Claude) : décision (2026-10-05)

Aucune consigne d'espacement dans le prompt. Les positions seront remises par la géométrie
(boîtes des mots Tesseract) au commit A. Ordre de l'étape 8 maintenu : correction du
vérificateur, puis commit A. Chiffres de départ (passage réel du 2026-10-05) : 223111PE011 p. 52
= 120 / 240 ; 6A23111PE133 p. 15 = 112 / 220 ; 223111PE012 p. 39 = 0 / 139.

## Colonnes en trop : compteur gardé dans la campagne (2026-10-05)

Mesure prévue avant le commit A : 0 ligne sur 454 (152 PE011, 155 PE133, 147 PE012) n'a pas le
nombre de colonnes du modèle. Les points 2 et 3 du message « plus de colonnes » sont en attente.
`campagne_mesure.lignes_hors_colonnes` compte, à chaque passage, les lignes de tableau des
réponses brutes (hors TYPE_PAGE, META, PIED_BRUT, LOGO, REVISIONS, SECTION) dont le nombre de
segments diffère du modèle ; colonnes `lignes_tableau_brutes` et `lignes_hors_colonnes` du CSV
(ancien en-tête réécrit), 5 premiers exemples affichés (image, segments, ligne brute).

## Passage réel 223111PE012 après le prompt des sections (2026-10-05, commit 5c23711)

Opus 5.5, effort medium, passage 2 — 0,219 $ ; 5 réponses, identifiants neufs (aucun commun au
passage 1).
- Sections : **3 / 3** recopiées par Claude (`SECTION: NOM DU CABLE : WPHR/A107` p. 8,
  `BRPH01/PH01` p. 18, `WPHR/A105` p. 39) ; les 9 sections de l'extrait livrées comme la vérité.
- Lignes manquantes **0** (3 au passage 1). Inchangés : 949 / 949 cellules, 0 pied faux,
  0 glissement, 0 ligne déplacée, alertes 0 manquante / 0 fausse, INDICE conforme, positions p. 39
  **0 / 140** (section comprise), lignes hors colonnes 0 / 147, logos 4 × M A T R A.
- Seule autre différence dans l'Excel livré : pied de la p. 39, Claude recopie cette fois
  « NO PLAN : 223111PE012 INDICE : R4 » sans le trait vertical « | » avant INDICE (variation de
  recopie, non comptée comme pied faux).

## Commit A — positions d'origine des pages scannées (2026-10-05)

`positions_scan.py` (nouveau) : sur chaque page passée par Claude, mots bruts de Tesseract
(`image_to_data`, psm 6, page rendue à l'échelle d'un A4 à 300 DPI), une grille de caractères
par page, mots coupés aux traits du cadre, lignes appariées (difflib, texte replié O/0, I/1,
l/1), chaque mot lu prend la colonne de son jumeau. Le contenu ne change jamais ; Excel en
Courier New 11, sous-champs complétés par des espaces (`generer_classeur.appliquer_positions`).
Lecture Tesseract gardée en mémoire et dans `<document>_tesseract.json` (double lecture et
contrôle de conservation du commit B, sans 2e OCR).

Ajustements trouvés à la mesure (tests d'abord pour chacun) :
- Grille : le pas estimé par largeur / nombre de caractères est biaisé (boîte du dernier
  caractère plus étroite) et la recherche à ±20 % calait PE012 p. 6 sur 22,98 au lieu de 28,6
  (les débuts se répètent sur quelques colonnes). Pas estimé = pente largeur selon le nombre de
  caractères (à quelques % du vrai pas sur les 15 pages de tableau), recherche à ±5 %.
- Pages géantes (PE012 p. 4 et 6, 2481 × 3505 pt) : rendues à 72 DPI (même nombre de pixels
  qu'un A4 à 300 DPI) ; 118 s → 2 s par page.
- Regroupement en lignes propre au module : un trait isolé lu « | » (3 px) coupait la ligne 1
  de PE011 p. 52 en trois (`relecture_scan` inchangé, le vérificateur est calibré dessus).
- Trait lu sur deux caractères (« 0815B/|RM », PE133 p. 15 ligne 31) : les caractères du trait
  sont retirés, la partie droite commence à la colonne qui suit le trait.
- Jumeau cherché d'abord dans la cellule (exact puis par rang) : sur PE011 p. 7, « PH » de fin
  de SIGNAL lu « FH » s'appariait au « PH » d'ABOUTISSANT et changeait de cellule (3 lignes).
- Déplacement vers la gauche refusé si le jumeau touche le trait (`POSITIONS_MARGE_DEBORDEMENT`) :
  PE011 p. 4 ligne 1, « PH » de TENANT imprimé à cheval sur le trait.
- Écriture du cache refusée (chemin de plus de 260 caractères sous Windows) : journalisée,
  la conversion continue.

Banc (mesure_precision / mesurer_precision) :
- Sections mesurées en position (`positions_sections`), depuis la colonne 0 de la 1re colonne.
- Une vérité qui a sa feuille Verite_positions saisit Verite_tableaux à un espace (0 cellule à
  blancs multiples sur 520 / 341 / 662) : ses lignes ne sont plus `exact`, les positions ne sont
  comparées que là où elles ont été saisies. Avant, ces comparaisons donnaient 0 par coïncidence
  (Claude aussi à un espace). Vérité TP2 de PE137 (sans feuille, espaces d'origine) inchangée.
- Chiffres dorés identiques ; instantané Excel identique avec `POSITIONS_ORIGINALES = False`,
  seule la police change avec True.

Mesure sans appel API (rejeu complet des réponses enregistrées, Tesseract local) :

| Extrait | Positions fausses avant → après | Cellules fausses | Glissements | Déplacés | Temps ajouté / page scannée |
|---|---|---|---|---|---|
| 223111PE011 | 120 → **4** (p. 52) | 2 → 2 | 0 → 0 | 0 | 1,4 à 4,4 s |
| 6A23111PE133 | 112 → **0** (p. 15) | 1 → 1 | 0 → 0 | 0 | 2,6 à 2,9 s |
| 223111PE012 | 1 → **0** (p. 39, section) | 0 → 0 | 0 → 0 | 0 | 1,7 à 2,6 s |

Restes : PE011 p. 52 lignes 18 et 32 (TENANT, ABOUTISSANT) — Tesseract n'y lit aucun mot,
aucune position n'est inventée, la cellule garde les espaces de Claude. PE011 p. 10 :
« colonnes du cadre non trouvées », positions non recalculées (journal). Aucun déplacement sur
les 3 extraits : le mécanisme n'est éprouvé que par les tests fabriqués.
`TriosSeconverter.spec` reçoit `positions_scan` et `relecture_scan` (import à la demande) ;
l'exe est à retester avant livraison (règle 08).

## Positions : page 123 de 223111PE011, cadre ouvert à droite (2026-10-06)

Cause : la page n'a pas de bord droit de cadre (tableau ouvert à droite). On trouvait le bord
gauche et les 3 séparateurs, 4 traits, alors que la règle en exige colonnes + 1 = 5. Le cadre
n'est ni pâle ni interrompu.

Repli par les libellés de l'en-tête : il existe déjà (`relecture_scan.bornes_entete`), mais
Tesseract ne lit **aucun** libellé d'en-tête sur ces scans (ni p. 123 ni p. 52 : police de
l'en-tête différente) ; il ne peut rien donner ici et n'a pas été étendu.

Correction (`positions_scan.bornes_page`, `relecture_scan` inchangé) : avec un trait de moins
que colonnes + 1, le bord absent est pris au bord de l'image, du côté où le plus de mots sortent
des traits. Une première version (« un mot à gauche du 1er trait = bord gauche absent ») se
trompait sur la p. 123 à cause des lettres du logo vertical M A T R A dans la marge : 4 mots
déplacés à tort, vus au test réel avant tout commit.

Campagne : colonne `pages_sans_positions` (lignes « positions d'origine p. N non recalculées »
du journal de conversion).

Mesure sans API (rejeu) : page 123 placée (69 jumeaux exacts, 15 par rang, 24 sans jumeau,
0 déplacé) ; chiffres du commit A inchangés (PE011 p. 52 : 4, PE133 p. 15 : 0, PE012 p. 39 : 0) ;
cellules, glissements identiques ; pages sans positions : 0 sur les 3 extraits.

## Cache des lectures Tesseract hors des fichiers de l'utilisateur (2026-10-06)

Avant : `<document>_tesseract.json` écrit dans le dossier de sortie de la conversion (à côté
de l'Excel), avec un échec possible au-delà de 260 caractères de chemin.

`cache_lectures.py` (nouveau, module pur) : une lecture par fichier JSON dans
`Config.POSITIONS_CACHE_DOSSIER` = `%LOCALAPPDATA%\TriosSeconverter\cache`. Clé = SHA-256 du
contenu du PDF (un PDF renommé ou déplacé est retrouvé) + page + DPI + psm (un réglage changé
force une nouvelle lecture) ; nom de fichier de 37 caractères. Purge à chaque écriture : plus de
`POSITIONS_CACHE_AGE_MAX_JOURS` (30) jours, puis les plus anciennes au-delà de
`POSITIONS_CACHE_TAILLE_MAX_MO` (200 Mo). Écriture impossible : une ligne ⚠ au journal, la
conversion continue (lecture gardée en mémoire).

Converter : lecture prise en mémoire, sinon dans le cache, sinon OCR puis écrite au cache ; une
2e conversion du même PDF ne relance pas Tesseract (test). `tests/conftest.py` redirige le cache
vers un dossier temporaire : la suite de tests ne remplit pas `%LOCALAPPDATA%`.
`TriosSeconverter.spec` reçoit `cache_lectures` (import à la demande).

## Tesseract pendant Claude (2026-10-06)

Estimation, sur les passages réels : Claude met 6 à 34 s par page (médiane ≈ 14 s), Tesseract
1,3 à 4,0 s (≈ 2,3 s). Tesseract est toujours plus court : lancé dès la rastérisation, dans un
fil à part, tout son temps est caché derrière Claude. Gain attendu ≈ temps Tesseract entier :
PE011 ≈ 18 s (8 scans, ≈ 12 %), PE133 ≈ 8 s, PE012 ≈ 9 s ; document complet 223111PE011
(104 scans) ≈ 4 min sur ≈ 25.

Code (simple, 30 lignes) : `Converter._lancer_lectures_tesseract` démarre un fil unique
(`ThreadPoolExecutor`, nom « tesseract ») qui lit chaque page scannée (mémoire, cache de
l'appli, sinon OCR) avec son propre document PyMuPDF ; le placement attend sa fin, puis place.
Une erreur de lecture d'une page est rendue par le fil et journalisée au placement ; l'arrêt
demandé par l'utilisateur est vérifié entre deux pages. Le temps affiché par page au journal
ne compte plus que le placement.

Mesure (rejeu PE011, faux client à 4 s par page, Tesseract local, cache vide) : 57,4 s en série
→ 38,7 s en parallèle, **18,7 s gagnées**. Test : la lecture se fait dans le fil « tesseract »,
finit avant la réponse de Claude, et l'Excel est identique.
Limite : les pages de garde scannées sont lues par Tesseract même si Claude les écarte ensuite
(≈ 2 s chacune, dans le temps caché).

## Étape 8 — mesure B0 : Tesseract seconde lecture et contrôle de conservation (2026-10-09)

Outil `outils_reference/mesure_b0.py` (hors de l'appli, aucun appel API, aucun code de l'appli
modifié) ; rapport complet : `mesures/b0_rapport.md`. 15 pages scannées de tableau (PE011 : 8,
PE133 : 3, PE012 : 4), dernières réponses Claude enregistrées, lecture Tesseract du commit A,
vérités validées, graine 20261009. Divergence = mot Claude apparié (alignement du commit A) à un
mot Tesseract de texte différent ; vraie si le mot Claude est faux selon la vérité.

Totaux, divergences brutes :

| Seuil conf | Alertes/page moy (max) | Vraies / fausses | Ratées | Erreurs injectées vues | Mots retrouvés | Lignes retrouvées | Bruit conservation/page moy (max) |
|---|---|---|---|---|---|---|---|
| aucun | 31,7 (183) | 3 / 472 | 1 | 48/50 | 18/20 | 4/5 | 3,0 (17) |
| 60 | 11,1 (55) | 2 / 164 | 2 | 42/50 | 16/20 | 4/5 | 1,4 (7) |
| 70 | 7,0 (36) | 0 / 105 | 4 | 35/50 | 15/20 | 4/5 | 1,2 (6) |
| 80 | 3,1 (15) | 0 / 47 | 4 | 33/50 | 13/20 | 4/5 | 1,1 (5) |
| 90 | 1,0 (7) | 0 / 15 | 4 | 29/50 | 8/20 | 4/5 | 0,3 (2) |
| 95 | 0,3 (2) | 0 / 5 | 4 | 12/50 | 6/20 | 3/5 | 0,0 (0) |

Par document, à 80 : PE011 3,8 alertes/page (max 15), 30 fausses ; PE133 3,7 (7), 11 fausses ;
PE012 1,5 (3), 6 fausses. Sans seuil : PE011 50,6/page (max 183 en p. 119), PE133 19,0,
PE012 3,2. Variante sans les confusions O/0, I/1, l/1 : fausses alertes − 17 % sans seuil,
mais les erreurs injectées O/0 et I/1 ne sont plus vues (35/50 sans seuil).

Erreurs connues de Claude : OC→CC de PE011 p. 119 signalées 2/2 sans seuil et à 60 (conf
Tesseract 64, 66 et 26), 0/2 dès 70. TRANS. de PE133 p. 15 : 0/1 à tout seuil — Tesseract lit
lui aussi la tache comme un point.

Glissements remis par le commit A : 9/10 (PE011 p. 1 : « QTEL2 » mal lu par Tesseract, seul
« 12 » revient) ; déplacements à tort : 0 sur les réponses non modifiées, 0 sur la copie.

Qualité de Tesseract seul (cellules identiques à la vérité) : PE133 et PE012 81 à 100 % par
colonne, part des mots Claude alignés 89 à 100 %, autant de lignes Tesseract que de lignes
Claude ; PE011 0 à 86 % (TENANT 0 à 12 % sur p. 52 et 119 : « Al04 », « FH », « TAl06 »),
part alignée 74 à 96 %, lignes manquées (p. 1 : 3 pour 4 ; p. 2 et 3 : 5 pour 7 ; p. 52 : 58
pour 60).

Pourquoi des omissions ne sont pas retrouvées : sur les pages aux lignes presque identiques
(p. 52 « PH A104 nn … »), une ligne retirée fait glisser l'appariement d'un cran ; erreurs
injectées non vues : ligne non lue par Tesseract (p. 52 ligne 32) ou aucun mot Tesseract en face.

Constat : sur les scans propres (PE133, PE012), Tesseract tient le rôle — ≈ 1 à 4 alertes par
page à 80, 2/3 des erreurs injectées vues, bruit de conservation ≈ 1 mot par page. Sur un scan
dégradé (PE011), il noierait l'utilisateur : tout seuil qui ramène les fausses alertes à un niveau
lisible (≥ 70) fait aussi perdre les vraies (OC→CC). Taux de divergence parmi les mots appariés :
PE011 p. 52 28 %, p. 119 29 % ; PE133 2 à 6 % ; PE012 ≤ 2 % — une jauge de page pourrait
séparer les deux cas (à décider, rien n'est branché).

## Commit B1 — indicateur de page et feuille A VERIFIER (2026-10-09)

`controle_conservation.analyser_page` (nouveau module pur) : taux de divergence = mots Claude
appariés à un mot Tesseract de texte différent / mots appariés (même définition que la mesure
B0 : alignement du commit A, texte brut). Page « scan dégradé » si taux > `PAGE_DEGRADEE`
(0,10). `positions_scan` expose `lignes_page` et `apparier_rangs` (factorisation de
`placer_page`, placement identique ; mots Tesseract avec confiance et y).

Converter : le taux est ajouté à la ligne « positions d'origine p. N » ; page dégradée =
« ℹ p. N : scan dégradé (divergence N %) : à relire en priorité » (information, pas ⚠).
Excel : feuille « A VERIFIER » (Page, Ligne, Colonne, Type, Message, Lecture Tesseract, Lien),
placée après « Borniers », lien cliquable vers le bloc de la page ; conçue pour que l'étape 9
y ajoute ses alertes (cible = page, ligne, colonne). Plus de la moitié des scans dégradés :
une synthèse « scan dégradé sur N pages sur M (taux de x à y %) : contrôle de conservation
impossible » puis les pages par taux décroissant ; sinon une ligne par page dégradée.
Pas de feuille sans entrée (instantané Excel inchangé). Banc : lignes ℹ listées
(`RapportMesure.informations`), jamais comptées comme fausses alertes. Campagne : colonne
`pages_degradees`.

Rejeu sans API des 3 extraits :

| Document | Pages scannées : taux | Classement |
|---|---|---|
| 223111PE011 | 1 : 50 %, 2 : 31 %, 3 : 19 %, 9 : 36 %, 52 : 29 %, 119 : 31 %, 122 : 33 %, 123 : 18 % | 8 dégradées sur 8 → synthèse + liste |
| 6A23111PE133 | 6 : 6 %, 12 : 3 %, 15 : 5 % | propres, pas de feuille A VERIFIER |
| 223111PE012 | 1 : 2 %, 8 : 2 %, 18 : 1 %, 39 : 1 % | propres, pas de feuille A VERIFIER |

Pages vectorielles : non concernées (lues en grille, pas de lecture Tesseract). Banc : cellules,
positions, alertes inchangées (PE011 : 0 manquante / 0 fausse, 8 informations listées).
Test du fil Tesseract pendant Claude rendu indépendant de la charge de la machine (Tesseract
commence avant la réponse de Claude ; exiger qu'il finisse avant échouait sous charge).
