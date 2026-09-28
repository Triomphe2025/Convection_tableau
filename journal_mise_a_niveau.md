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

### Reste ouvert

- **Qualité du repli image Tesseract** sur les pages Paper Capture : lignes lues en réel,
  page 52 (60 lignes dans la vérité) → 8 lignes, page 119 (60) → 42. Le routage n'y est pour
  rien : c'est la lecture Tesseract de ces scans qu'il faudra mesurer et améliorer.
- **Numéro de page « 122a »** lu « 122 » dans les métadonnées : `_extract_meta` ne retient que
  les chiffres de PAGE (comportement v1.7, non modifié).
