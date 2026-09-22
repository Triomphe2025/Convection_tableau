# Architecture du projet TriosSeconverter

Ce document décrit l'organisation réelle du code. Les règles à respecter en modifiant le
projet sont dans `.claude/Rules/01_architecture.md` ; ici, on explique en plus **comment le
pipeline fonctionne**. Contenu relevé dans le code le 2026-09-20.

---

## 1. Vue d'ensemble

Deux chaînes de traitement indépendantes, toutes deux lancées depuis `interface.py` :

```
Tableaux de borniers → Excel                    Plans → DXF AutoCAD

interface.py                                    interface.py
   │  (thread de travail)                          │
   ▼                                               ▼
converter.py  (Converter.run)                   cad/service.py  (convert_to_dxf)
   │                                               │
   ├─ extraction des tableaux (§3)                 ├─ PDF vectoriel → géométrie PyMuPDF
   ├─ Doc. 2 optionnel → word_table_importer       └─ image / PDF raster → vectorisation
   ▼                                                  │
generer_classeur.py (generer_excel)                   ▼
   │                                              cad/dxf_writer.py
   ▼                                                  │
<source>.xlsx                                         ▼
                                                  <source>.dxf
```

Le module `cad/` est **isolé** : seul `interface.py` l'importe, et `ezdxf` n'est utilisé
qu'à l'intérieur de `cad/`.

---

## 2. Responsabilité de chaque fichier

Règle de base : **1 fichier = 1 responsabilité**.

### Interface, orchestration et données

| Fichier | Rôle unique |
|---------|-------------|
| `interface.py` | Interface graphique Tkinter — affichage uniquement, zéro logique métier |
| `converter.py` | Orchestration : choisit le chemin d'extraction selon la source et le moteur OCR, appelle `generer_excel`, dialogue avec l'interface par callbacks |
| `config.py` | **Tous** les paramètres modifiables |
| `template.py` | `TableTemplate` + `TemplateManager` — structure d'un tableau (colonnes, pied de page), sauvegardée dans `templates.json` |
| `data_dictionary.py` | Corrections OCR évolutives par colonne (`data_dictionary.json`) |
| `recuperer_image.py` | `ImageExtractor` + `ImageStorage` — extraction des images du ZIP `.docx` |
| `word_table_importer.py` | Import des tableaux d'un Word structuré (Doc. 2) → feuille « tableaux word » |
| `generer_classeur.py` | Génération du classeur Excel : feuille « Borniers » et feuille « tableaux word » |
| `audit_claude.py` | Audit du classeur Excel : règles métier hors ligne + analyse Claude en ligne (optionnelle) |
| `verificateur.py` | Vérification de conversion : compare deux lectures au format pivot et classe les divergences (IDENTIQUE / BENIN / A_VERIFIER) — module pur, appelé uniquement par `converter.py` |

### Moteurs d'extraction

Tous retournent le même format de résultat (§4).

| Fichier | Rôle unique | `Config.OCR_MODE` |
|---------|-------------|-------------------|
| `ocr_processor.py` | `BornierTableExtractor` : prétraitement → OCR → colonnes → cellules → métadonnées | `tesseract` |
| `pdf_extractor.py` | `PdfTableExtractor` : extraction d'un PDF par couche texte (PyMuPDF), repli OCR Tesseract sur les pages raster | *(chemin PDF, voir §3)* |
| `claude_ocr.py` | `ClaudeVisionExtractor` (API Anthropic) + `LogReplayer` (replay d'un journal `*_claude.jsonl` sans appel API) + parseur pipe partagé par les moteurs vision | `claude` |
| `ollama_ocr.py` | `OllamaVisionExtractor` : modèle vision local Ollama, sans API externe | `ollama` |
| `hybrid_ocr.py` | `HybridVisionExtractor` : Ollama classe les colonnes, Claude corrige les caractères (2 passes) | `hybrid` |
| `agent_ocr.py` | `AgentVisionExtractor` : session Managed Agent Anthropic | `agent` |
| `docling_ocr.py` | `DoclingExtractor` : IA locale Docling (IBM Research) | `docling` |

### Pipeline CAD (`cad/`)

| Fichier | Rôle unique |
|---------|-------------|
| `cad/service.py` | Façade — `convert_to_dxf()`, seul point d'entrée depuis `interface.py` |
| `cad/source_detector.py` | Détecte PDF vectoriel / scan raster / image (`detect_source_mode`, `count_pages`) |
| `cad/models.py` | Modèles de données communs : `CadDocument`, `CadPage`, `CadEntity`, `EntityKind` |
| `cad/vector_pdf_extractor.py` | Extraction de la géométrie d'un PDF vectoriel via PyMuPDF |
| `cad/block_builder.py` | Détection des tableaux de légende et création de blocs AutoCAD (`BLOCK`) |
| `cad/vectorizer.py` | Vectorisation raster avancée en 7 étapes nommées (callbacks `on_step_start` / `on_step_done`) ; rend aussi les PDF non vectorisés en image avant traitement |
| `cad/raster_tif_extractor.py` | Extraction géométrie et textes d'une image raster via OpenCV ; réutilisé par `vectorizer.py` et utilisé comme pipeline de secours |
| `cad/curve_fitter.py` | Classification et reconstruction des entités (lignes tiretées, courbes) |
| `cad/segment_merger.py` | Fusion de segments colinéaires fragmentés |
| `cad/dxf_writer.py` | Génération du fichier DXF via `ezdxf` |

### Hors pipeline

À la racine se trouvent aussi des scripts d'appoint et d'essai (`analyse_*`, `diagnostic_*`,
`exemple_*`, `quick_test.py`, `test_*.py` à la racine, `run.py`, etc.). Aucun module du
pipeline ne les importe. `run.py` est un point d'entrée en ligne de commande historique
(d'après sa docstring : images → OCR → `.xlsx` + `.docx`).

---

## 3. Choix du chemin d'extraction (`Converter.run`)

Selon la source :

| Source | Chemin |
|--------|--------|
| `.docx` | `recuperer_image` extrait les images du ZIP, puis OCR image par image |
| Dossier d'images | OCR image par image |
| `.pdf` avec `OCR_MODE` = `claude`, `ollama`, `hybrid` ou `agent` | Le PDF est rastérisé page par page (PyMuPDF), puis OCR image par image |
| `.pdf` avec `OCR_MODE` = `tesseract` ou `docling` | `PdfTableExtractor` : couche texte du PDF, repli OCR sur les pages raster |
| `.jsonl` | `LogReplayer` relit le journal Claude — aucun appel API |

L'OCR image par image (`_extraire_avec_progres`) choisit le moteur selon `Config.OCR_MODE`
(tableau du §2). Un `BornierTableExtractor` est **toujours** créé, même avec un moteur
vision, car `generer_excel` en a besoin pour les informations de modèle (colonnes, pied de
page). Par ailleurs, `BornierTableExtractor.extract()` délègue lui-même à `claude_ocr` ou
`docling_ocr` quand `OCR_MODE` vaut `claude` ou `docling`.

Si un **Doc. 2** est fourni, `word_table_importer` extrait ses tableaux ; ils sont gardés
dans une liste **séparée** (`word_results`) et vont dans la feuille « tableaux word ».
Ils ne sont jamais fusionnés avec les résultats OCR, sinon la mise en forme des pieds de
page de la feuille « Borniers » est écrasée.

Enfin `generer_excel(ocr_results, extractor, excel_path, word_results=...)` produit
`<nom_source>.xlsx`.

---

## 4. Format de résultat commun

`extract()` de chaque moteur retourne un dict :

| Clé | Contenu |
|-----|---------|
| `success` | `True` / `False` (avec `error` si `False`) |
| `headers` | Noms des colonnes du modèle |
| `rows` | Liste de lignes : `{'type': 'data', 'cells': [...], 'confidence': [...]}`, plus `'section'` et `'blank'` produits par Tesseract |
| `metadata` | `PAGE`, `BORNIER`, `PET`, `NO_PLAN`, `INDICE` + champs de pied de page du modèle |
| `image_path` | Image source |
| `detection_method` | `header`, `tatr`, `morpho`, `hough`, `whitespace`, `weighted` (Tesseract) ; `claude-vision`, `ollama-vision`, `hybrid`, `agent-vision`, `docling` ; `log-replay` |

Pour `claude-vision` et `log-replay`, `data_dictionary.correct()` n'est **pas** appliqué :
la valeur lue par Claude est conservée telle quelle.

---

## 5. Moteur Tesseract (`BornierTableExtractor.extract`)

1. **Prétraitement** — mise à l'échelle, CLAHE, débruitage, accentuation, binarisation Otsu, correction d'inclinaison.
2. **OCR** — Tesseract PSM 6, repli PSM 4 si moins de 10 éléments détectés.
3. **Lignes et en-tête** — regroupement des mots en lignes ; recherche de la ligne d'en-tête ; si elle est introuvable, essai des autres modèles connus.
4. **Mapping manuel** — si le modèle dépasse `Config.MAX_AUTO_COLUMNS` colonnes, l'utilisateur classe lui-même les blocs (voir §6).
5. **Frontières de colonnes** — positions des mots-clés de l'en-tête (`_col_boundaries`) ; à défaut : TATR, lignes verticales, Hough, espaces blancs, puis répartition pondérée selon les largeurs du modèle.
6. **Cellules** — mode grille (OCR cellule par cellule) si `OCR_CELL_BY_CELL` et grille détectée ; sinon affectation des mots par **bord gauche** (`x`, jamais le centre), rééquilibrage, re-OCR par colonne si `OCR_PER_COLUMN`.
7. **Métadonnées** — extraction du pied de page (`_extract_meta`).

Détail complet : `Contexte/PROCESSUS_OCR.md` et `.claude/Rules/03_ocr_pipeline.md`.

---

## 6. Interaction avec l'interface : callbacks et threads

`Converter` ne connaît pas Tkinter. Il dialogue avec l'interface par des paramètres
optionnels (tous à `None` par défaut) :

| Paramètre | Rôle |
|-----------|------|
| `on_progress(pct, message)` | Barre de progression |
| `on_log(message)` | Journal |
| `on_validation(page, total, result, image_path)` | Validation page par page ; retourne un commentaire, ou `('retry', feedback)` pour relancer l'OCR |
| `on_column_mapping(candidate_blocks, template_columns, image_path)` | Classement manuel bloc → colonne. Déclenché avec Tesseract si le modèle dépasse `MAX_AUTO_COLUMNS`, et avec les moteurs Claude / Ollama / Agent / Hybride si la réponse contient plus de segments que de colonnes. Docling n'est pas concerné |
| `on_wide_template_confirm(template_columns, ocr_mode)` | Confirmation oui/non pour un modèle large avec un moteur autre que Tesseract |
| `cancel_event` (`threading.Event`) | Arrêt coopératif, vérifié entre deux images ou pages ; les résultats déjà extraits sont conservés |

**Threads.** La conversion tourne dans un thread de travail qui envoie ses messages dans une
`queue.Queue` ; le thread de l'interface la lit toutes les 80 ms (`_poll_queue`). Un widget
Tkinter n'est jamais modifié depuis le thread de travail.

Quand le thread de travail a besoin d'une réponse de l'utilisateur, l'interface applique le
même schéma : un `threading.Event` **local** à chaque appel, la boîte de dialogue ouverte
via `self.after(0, ...)`, et `event.wait(timeout=300)` pour ne jamais bloquer indéfiniment.
Le bouton « Arrêter » ne fait que `cancel_event.set()`.

---

## 7. Pipeline CAD

`cad.convert_to_dxf()` appelle `detect_source_mode()` :

- **PDF vectoriel** (au moins 5 tracés vectoriels, ou au moins 3 blocs de texte) →
  `extract_vector_pdf` → détection des tableaux de légende et création de blocs AutoCAD
  (`block_builder`) → `write_dxf`.
- **Image raster ou PDF non vectorisé** → `vectorizer.vectorize` ; en cas d'échec, pipeline
  de secours `raster_tif_extractor.extract_raster_tif` → `write_dxf`. `raster_tif_extractor`
  s'appuie sur `curve_fitter` et `segment_merger`.

Le fichier `<nom_source>.dxf` est écrit dans le dossier de destination. Règles de
coordonnées, déduplication et décalage des folios : `.claude/Rules/05_cad_pipeline.md`.

---

## 8. Vérification de conversion

`Converter.verifier_conversion(reference=None, converti=None)` compare une **lecture
indépendante du scan** à la conversion et liste les divergences cellule par cellule. Elle est
indépendante à dessein : sur le cas réel 6A 23111PE102, c'est Claude Vision qui a lu
« DISCONTINUOSITE » là où le scan porte « DISCORDANCE » ; comparer la conversion à elle-même
ne trouverait rien.

| Élément | Détail |
|---------|--------|
| Sources | `Converter._charger_pivots` accepte un chemin (`.pdf`, `.jsonl`, `.docx`, dossier d'images) ou une liste de résultats pivot |
| Référence | Par défaut le Doc. 1, relu par Tesseract. Les fichiers sont lus sous `_mode_ocr_tesseract()`, qui force `OCR_MODE='tesseract'` puis le restaure : sinon `extract()` déléguerait à Claude |
| Converti | Par défaut les résultats de la dernière conversion (`_derniers_resultats`), ou un chemin |
| Comparaison | `verificateur.verifier` : (1) appariement des pages par contenu, ordre conservé ; (2) alignement des lignes par `difflib` avec `autojunk=False`, jamais par clé de borne ; (3) comparaison de la ligne concaténée, puis rattachement des zones différentes à leurs colonnes (débordement de colonne, confusions OCR O/0, I/1, S/5…) ; (4) classement IDENTIQUE / BENIN / A_VERIFIER — seul A_VERIFIER remonte |
| Arbitrage | Confiance OCR de la lecture de référence, liste blanche de `data_dictionary.json`, distance `_levenshtein` injectée par `converter.py` |
| Seuils | `config.py`, section « VÉRIFICATION DE CONVERSION » (`VERIF_*`) |
| Interface | Bouton « 🔎 Vérifier » de la barre contextuelle tableaux → `VerificationDialog` (affichage seul), calcul dans un thread de travail |
| Ligne de commande | `python converter.py verifier <scan> <converti> [--modele NOM] [--rapport FICHIER]` — code retour 1 s'il reste des divergences |

Limites connues (mesure du 2026-09-20 sur le cas réel) :
- La confiance OCR n'est fiable que pour Tesseract (`pdf_extractor` met 90 partout, les moteurs
  vision 100) : seule celle de la référence sert d'arbitre.
- La divergence attendue est trouvée (page 10, ligne 8), mais avec 57 alertes et 93,5 % de
  concordance contre les cibles de 20 alertes et 98 % : le bruit vient surtout de la relecture
  Tesseract du scan et de vrais défauts de la conversion. Le test doré porte cet écart en
  « échec attendu » (`test_criteres_du_cahier_des_charges`).

---

## 9. Dépendances entre modules

Sens unique, sans import circulaire. Relevé par analyse des imports (imports différés
dans les fonctions inclus) :

| Module | Importe (modules du projet) |
|--------|-----------------------------|
| `interface` | `converter`, `generer_classeur`, `data_dictionary`, `template`, `config`, `audit_claude`, `ollama_ocr`, `cad` |
| `converter` | `recuperer_image`, `ocr_processor`, `pdf_extractor`, `claude_ocr`, `ollama_ocr`, `hybrid_ocr`, `agent_ocr`, `docling_ocr`, `word_table_importer`, `generer_classeur`, `verificateur`, `data_dictionary`, `template`, `config` |
| `generer_classeur` | `ocr_processor`, `pdf_extractor`, `data_dictionary`, `template`, `config` |
| `pdf_extractor` | `ocr_processor`, `template`, `config` |
| `ocr_processor` | `claude_ocr`, `docling_ocr`, `data_dictionary`, `template`, `config` |
| `recuperer_image` | `ocr_processor` (chargé à la demande) |
| `hybrid_ocr` | `claude_ocr`, `ollama_ocr` |
| `ollama_ocr` | `claude_ocr`, `config` |
| `agent_ocr` | `claude_ocr`, `config` |
| `claude_ocr` | `config` |
| `verificateur` | `config` |
| `docling_ocr`, `word_table_importer`, `template`, `data_dictionary`, `config`, `audit_claude` | *(aucun)* |

---

## 10. Ajouter un moteur OCR

D'après la structure actuelle de `converter.py` :

1. Créer `<nom>_ocr.py` avec une classe `XxxExtractor(template)` dont `extract(image_path, feedback=None)` retourne le format du §4.
2. Ajouter la branche correspondante dans `Converter._extraire_avec_progres` (et dans le choix de `_retry_extractor` de `_extraire_depuis_pdf`).
3. Documenter la valeur de `Config.OCR_MODE` dans `config.py` et ajouter son libellé dans `interface.py` (`ocr_labels`).
4. Ajouter le module aux `hiddenimports` de `TriosSeconverter.spec` (voir `.claude/Rules/08_delivery.md`).
5. Écrire les tests et ajouter une ligne au tableau de `.claude/Rules/01_architecture.md`.

---

## Pour aller plus loin

| Document | Contenu |
|----------|---------|
| `.claude/Rules/01_architecture.md` | Règles absolues de responsabilité des fichiers |
| `.claude/Rules/03_ocr_pipeline.md` | Règles critiques du pipeline OCR |
| `.claude/Rules/05_cad_pipeline.md` | Formules de coordonnées, déduplication, blocs AutoCAD |
| `Contexte/PROCESSUS_OCR.md` | Pipeline OCR complet, méthode par méthode |
| `Contexte/GUIDE_CREATION_LOGICIEL.md` | Principes d'architecture et de développement |
