# Règle 01 — Architecture et responsabilité des fichiers

## Principe fondamental : 1 fichier = 1 responsabilité

Chaque fichier Python du projet a un rôle unique. Ne jamais mélanger les rôles.

| Fichier | Rôle unique — ne toucher que si ce rôle change |
|---------|-----------------------------------------------|
| `interface.py` | Interface graphique Tkinter — affichage UNIQUEMENT, zéro logique métier |
| `converter.py` | Orchestration des étapes avec callbacks `on_progress` / `on_log` |
| `ocr_processor.py` | `BornierTableExtractor` : prétraitement → OCR → colonnes → cellules |
| `pdf_extractor.py` | `PdfTableExtractor` : extraction des tableaux d'un PDF par couche texte (PyMuPDF), repli OCR Tesseract sur les pages raster ; classement d'une page (`diagnostiquer_page`/`classer_page` : vectoriel / OCR invisible / scan / vide) et routage en mode tesseract/docling (`_extract_page_routee`) et lecture exacte en grille de caractères (`grille_page`, `extract_page_grille`) |
| `claude_ocr.py` | `ClaudeVisionExtractor` : OCR via Claude Vision (API Anthropic) + `LogReplayer` (replay du journal sans appel API) + parseur pipe partagé par les moteurs vision |
| `ollama_ocr.py` | `OllamaVisionExtractor` : OCR via un modèle vision local Ollama (sans API externe) |
| `hybrid_ocr.py` | `HybridVisionExtractor` : Ollama classe les colonnes, Claude corrige les caractères (2 passes) |
| `agent_ocr.py` | `AgentVisionExtractor` : OCR via une session Managed Agent Anthropic |
| `docling_ocr.py` | `DoclingExtractor` : OCR par IA locale Docling (IBM Research) |
| `verificateur.py` | Vérification de conversion : compare deux lectures au format pivot et classe les divergences (IDENTIQUE / BENIN / A_VERIFIER) — module pur, aucun OCR, PDF ni Excel |
| `relecture_scan.py` | Relecture indépendante d'un scan pour la vérification (Tesseract psm 6 à 300 DPI, colonnes sur les traits du cadre, lignes à clé de borne) — distincte du moteur de conversion ; appelée par `Converter.verifier_conversion` |
| `positions_scan.py` | Positions d'origine des mots lus sur une page scannée : mots bruts de Tesseract (psm 6, page à l'échelle d'un A4 à 300 DPI), une grille de caractères par page (pas = pente largeur / nombre de caractères, phase par alignement circulaire), mots coupés aux traits du cadre, jumeau de chaque mot lu (exact dans la cellule, puis par rang, sinon un espace) ; le contenu ne change jamais — appelé par `converter.py`, rendu par `generer_classeur.py` |
| `cache_lectures.py` | Cache des lectures Tesseract des pages scannées dans `%LOCALAPPDATA%\TriosSeconverter\cache` (jamais à côté des fichiers de l'utilisateur) : clé = empreinte du PDF + page + réglages de lecture, purge par âge et par taille — module pur, appelé par `converter.py` |
| `mesure_precision.py` | Mesure de précision : compare une sortie à une référence organisée à l'avance (PDF vectoriel ou Excel de vérité terrain) et classe les écarts (cellule, pied de page, position) — module pur, aucun OCR, PDF ni Excel |
| `pied_page.py` | Pied de page : lignes brutes → toutes les paires LIBELLÉ : valeur, COMPLEMENT (texte libre), indices de révision des pages de garde — module pur, partagé par la grille PDF et la lecture Claude (Claude recopie, le code structure) |
| `mesurer_precision.py` | Script CLI : lit `.xlsx`/vérité terrain/PDF vectoriel, appelle `mesure_precision`, écrit `mesures.csv` |
| `generer_classeur.py` | Génération Excel (2 feuilles distinctes) |
| `word_table_importer.py` | Import tableaux depuis Word structuré |
| `template.py` | `TableTemplate` + `TemplateManager` |
| `config.py` | **TOUS** les paramètres modifiables |
| `data_dictionary.py` | Corrections OCR évolutives |
| `recuperer_image.py` | Extraction images du ZIP `.docx` |
| `cad/service.py` | Façade pipeline CAD — seul point d'entrée depuis interface.py |
| `cad/vector_pdf_extractor.py` | Extraction géométrie via PyMuPDF uniquement |
| `cad/dxf_writer.py` | Génération DXF via ezdxf uniquement |

## Règles absolues

1. **Pas de logique métier dans interface.py** — toute logique va dans les modules métier
2. **Pas de paramètres hardcodés** — tout passe par `config.py`
3. **Pas d'import circulaire** — la dépendance est toujours unidirectionnelle
4. **Pas de modification des fichiers moteur pour des raisons UX** — seule `interface.py` évolue pour l'UX
5. **Le module `cad/` est entièrement isolé** — aucune référence à `cad/` depuis `converter.py` ou `ocr_processor.py`
6. **`verificateur.py` est un module pur** — il n'importe ni `ocr_processor` ni `pdf_extractor` (seulement `config` et la bibliothèque standard). Seul `converter.py` l'appelle (`Converter.verifier_conversion`) ; `interface.py` passe par `Converter` La lecture de référence d'un scan vient de `relecture_scan.py`, qui n'importe pas non plus `ocr_processor` : une relecture qui partagerait les défauts du moteur de conversion ne pourrait pas les contredire
7. **`mesure_precision.py` est un module pur** — il n'importe ni `ocr_processor` ni `pdf_extractor` (seulement `config`, `verificateur` et la bibliothèque standard). Toute lecture de fichier (`.xlsx`, vérité terrain, PDF vectoriel) est faite par `mesurer_precision.py`, jamais par `interface.py` ni `converter.py` — c'est un outil de QA autonome, pas une fonctionnalité du produit livré

## Séparation OCR / Word dans Excel

Les tableaux Word (Doc.2) vont dans la feuille **"tableaux word"**.
Ils ne sont **jamais** mélangés avec les résultats OCR dans la feuille "Borniers".

## Thread safety

Le thread de conversion envoie dans `queue.Queue`.
Le thread UI lit via `self.after(80ms, _poll_queue)`.
**Ne jamais modifier un widget Tkinter depuis un thread secondaire.**

## Vérification avant toute modification

Avant de modifier un fichier, se demander :
- Ce changement respecte-t-il la règle "1 fichier = 1 responsabilité" ?
- Est-ce que j'ajoute de la logique dans `interface.py` ?
- Est-ce que je casse un appel existant (rétrocompatibilité) ?
