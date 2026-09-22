# Règle 01 — Architecture et responsabilité des fichiers

## Principe fondamental : 1 fichier = 1 responsabilité

Chaque fichier Python du projet a un rôle unique. Ne jamais mélanger les rôles.

| Fichier | Rôle unique — ne toucher que si ce rôle change |
|---------|-----------------------------------------------|
| `interface.py` | Interface graphique Tkinter — affichage UNIQUEMENT, zéro logique métier |
| `converter.py` | Orchestration des étapes avec callbacks `on_progress` / `on_log` |
| `ocr_processor.py` | `BornierTableExtractor` : prétraitement → OCR → colonnes → cellules |
| `pdf_extractor.py` | `PdfTableExtractor` : extraction des tableaux d'un PDF par couche texte (PyMuPDF), repli OCR Tesseract sur les pages raster |
| `claude_ocr.py` | `ClaudeVisionExtractor` : OCR via Claude Vision (API Anthropic) + `LogReplayer` (replay du journal sans appel API) + parseur pipe partagé par les moteurs vision |
| `ollama_ocr.py` | `OllamaVisionExtractor` : OCR via un modèle vision local Ollama (sans API externe) |
| `hybrid_ocr.py` | `HybridVisionExtractor` : Ollama classe les colonnes, Claude corrige les caractères (2 passes) |
| `agent_ocr.py` | `AgentVisionExtractor` : OCR via une session Managed Agent Anthropic |
| `docling_ocr.py` | `DoclingExtractor` : OCR par IA locale Docling (IBM Research) |
| `verificateur.py` | Vérification de conversion : compare deux lectures au format pivot et classe les divergences (IDENTIQUE / BENIN / A_VERIFIER) — module pur, aucun OCR, PDF ni Excel |
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
6. **`verificateur.py` est un module pur** — il n'importe ni `ocr_processor` ni `pdf_extractor` (seulement `config` et la bibliothèque standard). Seul `converter.py` l'appelle (`Converter.verifier_conversion`) ; `interface.py` passe par `Converter`

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
