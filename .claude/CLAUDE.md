# CLAUDE.md — TriosSeconverter

## Contexte utilisateur

- **Utilisateur :** Triomphe Tchounda — ingénieur en électrotechnique / automatisme industriel
- **Langue :** toujours répondre en **français**, sans exception
- **Niveau technique :** non-développeur ; peut lancer des scripts Python mais n'écrit pas de code
- **Objectif :** automatiser la conversion de tableaux de borniers électriques scannés (images Word) vers Excel/Word, utilisable par des collègues sans compétences informatiques
- **Priorité :** interface graphique simple, installateur clé-en-main, exécutable autonome `.exe`

---

## Équipe de développement IA — Toujours active

L'équipe de 6 agents travaille en parallèle sur toute tâche de développement.
**Commande unique :** `/equipe-dev [description de la tâche]`

| Agent | Skill | Fichiers autorisés |
|-------|-------|-------------------|
| Analyste | `/agent-analyste` | Tous (lecture) — produit le plan |
| Backend Dev | `/agent-backend` | converter.py, ocr_processor.py, generer_classeur.py, cad/, data_dictionary.py, config.py, template.py |
| Frontend Dev | `/agent-frontend` | interface.py UNIQUEMENT |
| Auditeur | `/agent-auditeur` | Tous (lecture) — vérifie la qualité |
| Testeur | `/agent-testeur` | tests/, tous (lecture) |
| Apprentissage | `/agent-apprentissage` | memory/*.md, .claude/Rules/*.md |

**Ordre :** Analyste → Backend + Frontend (parallèle) → Auditeur + Testeur (parallèle) → Apprentissage

**Mémoire de l'équipe :** `memory/equipe_lecons.md` — leçons cumulées de toutes les sessions.

---

## Skills — Commandes disponibles pour ce projet

Ces commandes slash sont utilisables directement dans Claude Code (`/nom-de-la-commande`).
Les définitions sont dans `.claude\commands\`.

### Point d'entrée principal — Senior Application Manager

| Commande | Rôle |
|----------|------|
| `/manager` | **Coordinateur central** — Analyse chaque demande, sélectionne l'agent le mieux adapté parmi tous les agents disponibles, le lance, coordonne plusieurs agents si nécessaire, ou crée un nouvel agent si aucun n'existe. **Point d'entrée recommandé pour toute demande.** |

### Skills de configuration et maintenance quotidienne

| Commande | Action |
|----------|--------|
| `/corriger-ocr` | Ajouter une correction au dictionnaire OCR (`data_dictionary.json`) |
| `/nouveau-template` | Créer un nouveau modèle de tableau dans `templates.json` |
| `/changer-config` | Modifier un paramètre dans `config.py` avec explication de l'impact |
| `/debug-bornier` | Analyser pourquoi une image spécifique est mal lue par l'OCR |
| `/nettoyer-projet` | Supprimer les fichiers temporaires (images, logs, cache) |

### Skills d'agent ingénieur — analyse et diagnostic OCR

| Commande | Ce que fait l'agent |
|----------|---------------------|
| `/analyser-qualite-ocr` | Évalue image par image la qualité OCR, classe les problèmes par priorité (critique / attention / vigilance / ok) |
| `/valider-classeur` | Vérifie l'intégrité structurelle et métier du classeur Excel généré (pagination, pieds de page, zones d'impression) |
| `/diagnostiquer-env` | Contrôle complet de l'environnement : Python, dépendances, Tesseract, langue française, fichiers critiques |
| `/audit-borniers` | Vérifie la cohérence métier des données (doublons de PAGE, séquence, station P.E.T. uniforme, codes BORNIER) |
| `/optimiser-tesseract` | Analyse les métriques d'image (flou, contraste, résolution) et propose des ajustements Tesseract ciblés |
| `/alimenter-dictionnaire` | Extrait les valeurs corrigées d'un Excel manuel et les mémorise dans `data_dictionary.json` |

### Agents IA — UX/UI interface

| Commande | Ce que fait l'agent |
|----------|---------------------|
| `/ameliorer-interface` | Audit UX complet de l'interface Tkinter : 6 critères (feedback, erreurs, raccourcis, lisibilité, cohérence, récupération). Propose et implémente les corrections |
| `/ajouter-apercu` | Ajoute un panneau d'aperçu des données extraites directement dans l'interface (onglet Notebook), permettant de vérifier le résultat OCR avant d'ouvrir Excel |
| `/implementer-workflow-ux` | Restructure l'interface en logique "parcours de traitement" (3 cartes accueil + barre contextuelle + stepper) sans toucher au moteur de conversion. 5 phases progressives |
| `/apprendre-interface` | Enregistre chaque action UX menée, chaque correction effectuée, met à jour `memory/ux_ui_expertise.md` pour rendre les prochaines interventions plus précises |

### Agents IA — développement logiciel

| Commande | Ce que fait l'agent |
|----------|---------------------|
| `/implementer-feature` | Atelier complet pour ajouter une nouvelle fonctionnalité : recueil des besoins, analyse d'impact, plan, code, test — en respectant toutes les conventions du projet |
| `/revoir-architecture` | Vérifie les 8 règles fondamentales du projet (séparation des rôles, config.py, thread safety, bordures openpyxl, ressources PyInstaller, séparation word/ocr, rétrocompatibilité, gestion erreurs) |
| `/profiler-extraction` | Mesure le temps de chaque étape du pipeline OCR (prétraitement / Tesseract / analyse), identifie le goulot et propose des optimisations basées sur les données mesurées |

### Agents IA — analyse d'image

| Commande | Ce que fait l'agent |
|----------|---------------------|
| `/analyser-image-profonde` | Analyse approfondie d'une image : histogramme, 5 chaînes de prétraitement en parallèle (Otsu / CLAHE / adaptatif / débruitage / gamma), comparaison PSM, image annotée avec boîtes OCR colorées par confiance |
| `/visualiser-colonnes` | Génère une image annotée montrant les frontières de colonnes détectées et l'affectation de chaque mot à sa colonne — outil de débogage visuel pour les erreurs d'affectation |
| `/comparer-versions` | Compare deux classeurs Excel (avant/après une modification) : gains OCR, pertes, modifications cellule par cellule, borniers perdus/gagnés — détection de régressions |

### Skills de fiabilité et prévention d'erreurs (v1.6)

| Commande | Ce que fait l'agent |
|----------|---------------------|
| `/isoler-modes-ocr` | Vérifie que chaque mode OCR (tesseract/claude/docling/log-replay) applique exactement les bonnes transformations — protection contre la fuite de corrections vers Claude Vision |
| `/tracer-valeur` | Trace une valeur précise (ex: "TC IDPO1") depuis la réponse brute Claude jusqu'à la cellule Excel, détecte toute modification non voulue |
| `/auditer-code-mort` | Détecte les fonctions, variables et imports définis mais jamais appelés — prévient l'accumulation de code obsolète |
| `/valider-fidelite-log` | Vérifie qu'un fichier `*_claude.jsonl` est complet (`rows_data` présent) pour garantir un replay Excel 100 % fidèle à l'original |
| `/optimiser-prompt-claude` | Agent interactif pour tester le prompt Claude Vision sur une image réelle, diagnostiquer les erreurs (colonne mal assignée, valeur perdue, OCR raté) et itérer jusqu'à obtenir un résultat satisfaisant |

### Équipe chercheurs — Reconstruction mathématique de courbes TIF

| Commande | Rôle |
|----------|------|
| `/equipe-chercheurs-courbes` | **Orchestrateur** — coordonne les 3 agents chercheurs pour améliorer la reconstruction de courbes TIF→DXF |
| `/agent-mathematicien-courbes` | Expert géométrie — classifie les courbes (droite/arc/spline/polyligne) et propose les équations de fitting (B-spline, moindres carrés arc) |
| `/agent-implementeur-formes` | Ingénieur numérique — implémente les équations dans `cad/curve_fitter.py` et les intègre dans le pipeline raster |
| `/agent-comparateur-courbes` | Comparateur — mesure la fidélité original vs reconstruit (Hausdorff, RMS, continuité, courbure) et recommande des ajustements |

### Skills de livraison et version

| Commande | Action |
|----------|--------|
| `/rapport-livraison` | Génère un rapport de livraison complet (stats extraction, contrôles qualité, fichiers produits) |
| `/build-exe` | Compile le projet en `.exe` autonome avec PyInstaller |
| `/tester` | Lance la suite de tests automatisés (pytest) avec analyse des échecs |
| `/nouvelle-version` | Prépare une nouvelle version : badge UI, historique CLAUDE.md, tag Git, compilation exe |

---

## Documentation de référence (dossier Contexte\)

Lire ces fichiers EN PRIORITÉ avant toute intervention sur le projet :

| Fichier | Contenu |
|---------|---------|
| `Contexte\PROCESSUS_OCR.md` | Pipeline OCR complet — 7 étapes, toutes les méthodes expliquées avec leurs arguments et leur logique |
| `Contexte\GUIDE_CREATION_LOGICIEL.md` | Principes d'architecture du projet — séparation des responsabilités, gestion des erreurs, tests, PyInstaller, Git |
| `Contexte\FONCTIONNEMENT_COMPLET.cmd` | Documentation interactive (double-clic) — explication complète en 9 écrans pour l'utilisateur final |

---

## Description du projet

**TriosSeconverter** convertit des images de tableaux de borniers électriques embarquées dans un fichier Word en un classeur Excel formaté et un document Word propre.

```
Fichier Word source (.docx) — images de borniers scannés
  │
  ├─ Doc.1 obligatoire → extraction images → OCR → feuille "Borniers"
  └─ Doc.2 optionnel  → tableaux Word structurés → feuille "tableaux word"
                                                          ↓
                                              tous_les_borniers.xlsx
                                              tous_les_borniers.docx
```

---

## Architecture — rôle de chaque fichier

### Fichiers principaux

| Fichier | Rôle unique — ne toucher que si ce rôle change |
|---------|-----------------------------------------------|
| `interface.py` | Interface graphique Tkinter — affichage uniquement, zéro logique métier |
| `converter.py` | Orchestration des 4 étapes avec callbacks `on_progress` / `on_log` |
| `ocr_processor.py` | `BornierTableExtractor` : prétraitement → OCR → colonnes → cellules → métadonnées |
| `generer_classeur.py` | Génération Excel (2 feuilles distinctes) + Word combiné |
| `word_table_importer.py` | Import tableaux depuis Word structuré (Doc.2) → feuille "tableaux word" |
| `template.py` | `TableTemplate` + `TemplateManager` — structure de tableau paramétrable |
| `config.py` | **Tous** les paramètres modifiables (jamais coder en dur ailleurs) |
| `data_dictionary.py` | Corrections OCR évolutives par colonne depuis `data_dictionary.json` |
| `recuperer_image.py` | `ImageExtractor` + `ImageStorage` — extraction images du ZIP `.docx` |
| `verificateur.py` | Vérification de conversion : compare deux lectures (format pivot) et classe les divergences en IDENTIQUE / BENIN / A_VERIFIER — module pur, appelé uniquement par `converter.py` (`Converter.verifier_conversion`) |
| `relecture_scan.py` | Relecture indépendante d'un scan pour la vérification (Tesseract psm 6 à 300 DPI, colonnes sur les traits du cadre, lignes à clé de borne) — distincte du moteur de conversion ; appelée par `Converter.verifier_conversion` |
| `positions_scan.py` | Positions d'origine des mots lus sur une page scannée : mots bruts de Tesseract (psm 6, page à l'échelle d'un A4 à 300 DPI), une grille de caractères par page (pas = pente largeur / nombre de caractères, phase par alignement circulaire), mots coupés aux traits du cadre, jumeau de chaque mot lu (exact dans la cellule, puis par rang, sinon un espace) ; le contenu ne change jamais — appelé par `converter.py`, rendu par `generer_classeur.py` |
| `cache_lectures.py` | Cache des lectures Tesseract des pages scannées dans `%LOCALAPPDATA%\TriosSeconverter\cache` (jamais à côté des fichiers de l'utilisateur) : clé = empreinte du PDF + page + réglages de lecture, purge par âge et par taille — module pur, appelé par `converter.py` |
| `controle_conservation.py` | Contrôle d'une page scannée lue par Claude à partir de la lecture Tesseract du commit A : taux de divergence Claude / Tesseract parmi les mots appariés, page « scan dégradé » au-delà de `PAGE_DEGRADEE` ; contrôle de conservation des pages propres (mot Tesseract sans mot Claude en face, ligne Tesseract sans ligne Claude) — module pur (config, positions_scan), appelé par `converter.py` ; la lecture de Claude n'est jamais modifiée |
| `mesure_precision.py` | Mesure de précision : compare une sortie à une référence organisée à l'avance (PDF vectoriel ou Excel de vérité terrain), classe les écarts cellule/pied/position — module pur, outil de QA indépendant du produit livré |
| `pied_page.py` | Pied de page : lignes brutes → toutes les paires LIBELLÉ : valeur, COMPLEMENT (texte libre), indices de révision des pages de garde — module pur, partagé par la grille PDF et la lecture Claude (Claude recopie, le code structure) |
| `mesurer_precision.py` | Script CLI : `python mesurer_precision.py <sortie.xlsx> <reference>` — lit les fichiers, appelle `mesure_precision`, écrit une ligne dans `mesures.csv` |

### Fichiers de packaging et outils

| Fichier | Usage |
|---------|-------|
| `install.bat` | Crée `env\`, installe les dépendances, raccourci bureau |
| `build_exe.bat` + `TriosSeconverter.spec` | Compilation PyInstaller → `dist\TriosSeconverter.exe` |
| `requirements.txt` | Dépendances Python du projet |
| `templates.json` | Modèles de tableau sauvegardés (ne pas supprimer) |
| `generer_rapport_evolution.py` | Génère un rapport PDF d'évolution |

### Fichiers de documentation

| Fichier | Ne pas modifier — sauf mise à jour documentaire |
|---------|------------------------------------------------|
| `Contexte\PROCESSUS_OCR.md` | Référence technique pipeline OCR |
| `Contexte\GUIDE_CREATION_LOGICIEL.md` | Guide d'architecture et bonnes pratiques |
| `Contexte\FONCTIONNEMENT_COMPLET.cmd` | Documentation interactive utilisateur |

---

## Lancer le projet

```powershell
# Activer l'environnement virtuel (dossier env\, pas venv\)
env\Scripts\activate

# Interface graphique
python interface.py

# Génération en ligne de commande (sans interface)
python generer_classeur.py

# Vérification de conversion (scan contre document converti)
python converter.py verifier scan.pdf converti.pdf --rapport rapport.txt

# Tests
pytest tests\ -v
```

---

## Configuration (`config.py`)

**Règle absolue : ne jamais coder un paramètre en dur dans un autre fichier.**

| Paramètre | Valeur actuelle | Rôle |
|-----------|----------------|------|
| `TESSERACT_PATH` | `C:\Tesseract\TesseractOCR\tesseract.exe` | Chemin Tesseract OCR |
| `OCR_LANGUAGE` | `fra` | Langue Tesseract |
| `PAGE_SIZE` | `48` | Lignes par page A4 dans Excel |
| `STATION_NAME` | `EPEULE` | Nom de station des rapports ; ne remplit plus jamais le pied (P.E.T. absent = vide + alerte) |
| `MIN_DATA_ROWS` | `1` | Seuil minimal de lignes pour valider un bornier |
| `IMAGES_FOLDER_NAME` | `VD23111 PE 162` | Nom du dossier de sortie des images |

Pour modifier un paramètre → utiliser `/changer-config`.

Les paramètres `PDF_*` (routage PDF par page, section « ROUTAGE PDF PAR PAGE ») pilotent
la lecture des PDF en mode vision. Les paramètres `VERIF_*` (vérification de conversion : seuils d'appariement, confusions OCR,
concordance) sont regroupés dans la section « VÉRIFICATION DE CONVERSION » de `config.py`.

---

## Points techniques critiques à ne jamais oublier

### 1. Séparation OCR / Word dans Excel
Les tableaux Word (Doc.2) vont dans la feuille **"tableaux word"**.  
Ils ne sont **jamais** mélangés avec les résultats OCR dans la feuille "Borniers".  
**Pourquoi :** le mélange écrasait la mise en forme des pieds de page issus des images (bug v1.1 → corrigé v1.2).

`converter.py` maintient `word_results` dans une liste séparée de `ocr_results` et les passe via :
```python
generer_excel(ocr_results, extractor, excel_path, word_results=word_results)
```

### 2. Frontières de colonnes OCR
`_col_boundaries()` utilise les positions pixel (`cx`) des mots-clés de l'en-tête.
**Pas de clustering sur les données.** Plus robuste sur les scans déformés.

L'affectation utilise le **bord gauche** (`x`), pas le centre (`cx`) :
un mot large commençant dans SIGNAL ne doit pas aller dans JARRETIERES parce que son centre dépasse la frontière.

### 3. Thread UI / Thread de travail
Le thread de conversion envoie dans `queue.Queue`.
Le thread UI lit via `self.after(80ms, _poll_queue)`.
**Ne jamais modifier un widget Tkinter depuis un thread secondaire.**

### 4. Bordures de cellules fusionnées (openpyxl)
Les bordures doivent être posées sur **chaque cellule de bordure individuellement**.
openpyxl ne les propage pas automatiquement sur les cellules fusionnées.

### 5. Ressources dans l'exe PyInstaller
```python
def _resource(name: str) -> Path:
    if hasattr(sys, '_MEIPASS'):         # Mode exe
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name  # Mode dev
```
Toujours passer par cette fonction pour `icon.ico` et les ressources statiques.

### 6. Indice OCR — confusion O / 0
La confusion `O` ↔ `0` est normalisée automatiquement dans `_extract_meta()` :
```python
meta['INDICE'] = meta.get('INDICE', '0').replace('O', '0')
```

---

## Modèles de tableau (`template.py` + `templates.json`)

Structure définie par `TableTemplate` :
- colonnes ordonnées + largeurs Excel
- mot-clé de ligne de séparation (ex : `NOM DU CABLE`)
- pied de page : étiquette gauche, format ligne 1 et ligne 2 avec placeholders `{PET}`, `{BORNIER}`, `{PAGE}`, `{NO_PLAN}`, `{INDICE}`

Modèle par défaut : **"Bornier standard"** — colonnes `[BORNE, COULEUR, SIGNAL, JARRETIERES]`

Sauvegardé dans `templates.json` à la racine. Modifiable depuis l'interface (ou `/nouveau-template`).

---

## Dictionnaire de correction OCR (`data_dictionary.json`)

Corrections évolutives sans recompiler le logiciel :
```json
{
  "COULEUR": { "ROUSE": "ROUGE", "BLENC": "BLANC" },
  "BORNIER": { "B7O2A": "B702A" }
}
```

Alimenter depuis un Excel corrigé manuellement :
```python
from data_dictionary import get_dictionary
get_dictionary().update_from_excel(Path("tous_les_borniers_corrigé.xlsx"))
```

Pour ajouter une correction → `/corriger-ocr`.

---

## Conventions de code

- **1 fichier = 1 responsabilité** — ne pas mélanger UI, OCR, écriture fichiers
- **Paramètres optionnels** avec valeur par défaut — ne jamais casser les appels existants
- **Callbacks pour le découplage** — `Converter` ne connaît pas Tkinter
- **Erreurs récupérables** — une image ratée ne stoppe pas le traitement global
- **Commentaires sur le POURQUOI**, jamais sur le QUOI
- **Langue des logs et messages utilisateur** : français uniquement

---

## Dépendances (`requirements.txt`)

```
python-docx==1.1.2       # fichiers Word
openpyxl==3.1.5          # fichiers Excel
opencv-python>=4.8.0     # prétraitement images
pytesseract>=0.3.10      # interface Python → Tesseract
numpy>=1.24.0            # calculs OCR
Pillow>=11.0.0           # manipulation images
pandas>=2.0.0            # données tabulaires
fpdf2>=2.7.0             # génération PDF
pyinstaller>=6.0.0       # compilation exe
pytest>=9.0              # tests
pymupdf>=1.24.0          # extraction PDF couche texte (mode PDF sans Tesseract)
```

**Tesseract OCR (externe) :** `C:\Tesseract\TesseractOCR\tesseract.exe`  
**Langue française :** `fra.traineddata` dans `tessdata\` de Tesseract

---

## Compiler en exécutable

```powershell
env\Scripts\activate
pyinstaller TriosSeconverter.spec --clean
# → dist\TriosSeconverter.exe
```

Toujours tester l'exe sur une **machine sans Python** avant livraison.  
Raccourci → `/build-exe`.

---

## Historique des versions

| Version | Date | Changement |
|---------|------|-----------|
| v1.0 | initial | Pipeline complet image → Excel + Word, interface graphique |
| v1.1 | 2026-05 | PAGE_SIZE=48, sauts de page Excel, hauteur ligne 15pt |
| v1.1 | 2026-05 | `_extract_meta` : PET multi-mots, BORNIER alphanumérique étendu |
| v1.1 | 2026-05 | `data_dictionary.py` : corrections OCR évolutives par colonne |
| v1.1 | 2026-05 | Filtrage `MIN_DATA_ROWS` : borniers OCR ratés exclus du classeur |
| v1.2 | 2026-05 | Feuille "tableaux word" séparée — pieds de page des images préservés |
| v1.3 | 2026-05 | Mode PDF : `pdf_extractor.py` — extraction couche texte vectorielle sans Tesseract |
| v1.3 | 2026-05 | Suppression sortie Word — seul l'Excel est généré (interface + converter + generer_classeur) |
| v1.3 | 2026-05 | Correction bug re-OCR : `split_flags` protège les cellules issues d'un split contre la ré-analyse |
| v1.3 | 2026-05 | Re-OCR sur cellules vides : détecte les cases entièrement manquées par Tesseract |
| v1.3 | 2026-05 | Corrections PDF `_clean()` : OlA→01A, lOB→10B (codes bornes 2 chiffres), FSbll-31→FSb11-31 |
| v1.4 | 2026-05 | OCR de repli PDF : pages raster (sans couche texte) traitées par Tesseract via `_extract_page_ocr()` |
| v1.4 | 2026-05 | Détection de colonnes PDF par position caractère (rawdict) : division des tokens multi-colonnes |
| v1.4 | 2026-05 | Pied de page configurable : `footer_row1_format`/`footer_row2_format` pilotent le rendu ; REPARTITEUR affiche "JARRETIERAGE" à la place de "BORNIER :" |
| v1.4 | 2026-05 | Espacement inter-tableaux : 2 lignes vides + saut de page + 1 ligne vide avant chaque nouveau tableau |
| v1.5 | 2026-05 | Correction S↔5 / O↔0 dans les codes de borne (PDF Adobe) : `_fix_borne_value()` colonne-spécifique |
| v1.5 | 2026-05 | Filtrage lignes garbage : lignes < 2 caractères alphanumériques ignorées en début de tableau PDF |
| v1.5 | 2026-05 | Sauts de page intra-tableau supprimés : les sauts sont uniquement entre tableaux (generer_classeur.py) |
| v1.5 | 2026-05 | Champs de pied configurables : `footer_extract_fields` dans TableTemplate — CABLE, TYPE, etc. extraits dynamiquement ; render_footer_row1/2 supporte tous les placeholders via defaultdict |
| v1.6 | 2026-05 | Fix fidélité Claude Vision : `_fill_worksheet()` saute `data_dictionary.correct()` si `detection_method` est `claude-vision` ou `log-replay` — "TC IDPO1" ne devient plus "TC IDPO8" |
| v1.6 | 2026-05 | Nettoyage `claude_ocr.py` : suppression `_parse_response()`, `_apply_post_corrections()`, `_fix_borne_in_signal()`, `_POST_CORRECTIONS`, `_COL_DESCRIPTIONS` (code mort depuis migration pipe) |
| v1.6 | 2026-05 | 4 skills de fiabilité : `/isoler-modes-ocr`, `/tracer-valeur`, `/auditer-code-mort`, `/valider-fidelite-log` |
| v1.7 | 2026-06 | UX Phase 1 : accueil avec 3 cartes de workflow (Tableaux / Dessins / Mixte) |
| v1.7 | 2026-06 | UX Phase 2 : barre contextuelle tableaux (Reformater, Dictionnaire, Log, Dossier sortie) — contextuelle et persistante |
| v1.7 | 2026-06 | UX Phase 3 : assistant 3 étapes Suivant/Précédent (Source → Modèle & OCR → Lancer) avec validation bloquante par étape |
| v1.7 | 2026-06 | UX Phase 4 : dashboard de conversion — 3 colonnes (source + spinner \| progression \| modèle attendu) + journal miroir + timer |
| v1.7 | 2026-06 | UX Phase 5 : pages squelettes Dessins et Mixte avec étapes prévues et technologies envisagées |
| v1.7 | 2026-06 | Navigation simplifiée : onglets Paramètres/Mode OCR/Options cachés par défaut, révélés via toggle "⚙ Dev" |
| v1.7 | 2026-06 | Bouton "Lancer la conversion" retiré de la toolbar — point d'entrée unique via stepper étape 3 |
| v1.7 | 2026-06 | 2 nouveaux skills UX : `/implementer-workflow-ux` (5 phases) + `/apprendre-interface` (capitalisation leçons) |
| v1.7 | 2026-09 | Vérification de conversion : bouton « 🔎 Vérifier » + `python converter.py verifier` — relecture Tesseract du scan comparée à la conversion, divergences cellule par cellule (`verificateur.py`, seuils `VERIF_*` dans `config.py`, méthode `Converter.verifier_conversion`) |
| v1.7 | 2026-09 | Mesure de précision (outil de QA) : `python mesurer_precision.py <sortie.xlsx> <reference>` — compare à un PDF vectoriel ou un Excel de vérité terrain, alignement `difflib` + Needleman-Wunsch, pieds de page en paires LIBELLÉ:valeur libres, historique `mesures.csv` (`mesure_precision.py`, seuils `MESURE_*` dans `config.py`) |
| v1.7 | 2026-09 | Routage PDF par page (modes vision) : texte vectoriel → lecture exacte de la couche texte en grille, sans appel API (`pdf_extractor.classer_page`/`extract_page_grille`) ; couche OCR invisible et scan → pipeline OCR ; `PDF_ROUTAGE_VECTORIEL` dans `config.py` (False = v1.7). 223400PE137.pdf : 0 appel API au lieu de 53 |
| v1.7 | 2026-09 | Routage PDF étendu à tous les modes (tesseract/docling compris) : couche OCR invisible (Paper Capture) ignorée → repli image ; images cumulées ≥ `PDF_SEUIL_IMAGE` (10 %) → pipeline scan, sinon page ignorée avec motif journalisé ; lignes de section « NOM DU CABLE » reconnues dans la grille. 223111PE011 complet : 25 pages vectorielles / 104 couche invisible |
| v1.7 | 2026-09 | Modes claude et hybrid sur `claude-opus-5` : réflexion (`CLAUDE_THINKING`) et effort (`CLAUDE_EFFORT`) configurables, `max_tokens` 16000, lecture des seuls blocs texte (le 1er bloc peut être de la réflexion), images en PNG ≤ 2576 px, modèle et tokens journalisés par page ; SDK `anthropic` 1.8 |
| v1.7 | 2026-09 | Modèle par défaut `claude-opus-5-5`, effort `medium` ; table `CLAUDE_CAPACITES_MODELES` (champ thinking envoyé ou omis, effort envoyé ou non, par modèle ; modèle absent → refus avant l'appel) ; refus du modèle journalisé avec sa catégorie |
| v1.7 | 2026-09 | Grille PDF : mots placés d'après leur propre x au pas de la page (espace isolé dans un span à part retrouvé, police réduite alignée) — défaut hérité de outils_reference/grille.py ; pages à cadre inchangées |
| v1.7 | 2026-09 | `campagne_mesure.py` : campagne de mesure des modèles Claude (surcharge en mémoire, sortie dans `mesures/`, historique `mesures/campagne.csv`, coût estimé par `CLAUDE_PRIX_MODELES`, plafond `CAMPAGNE_BUDGET_MAX_USD`) ; garde-fou de troncature (max_tokens 64000 à effort xhigh/max, réponse tronquée = page en erreur) |
| v1.7 | 2026-09 | Étape 6 : `MIN_DATA_ROWS` = 1 ; chaque page écartée écrite au journal (« page ignorée : <numéro> <raison> ») ; tableau vide (CABLE : RESERVE) conservé |
| v1.7 | 2026-09 | Étape 6 : numéros de page à suffixe (122a, 44B), ni renumérotés ni retriés — ordre du document conservé, alerte si la séquence n'est pas croissante |
| v1.7 | 2026-10 | Décision B1, pied livré (`generer_classeur.pied_livre`) : lecture telle qu'imprimée ; dans l'Excel, libellés du modèle de sortie, N° PLAN sans espaces si les pages l'impriment avec des espacements différents, pages numérotées dans l'ordre si aucune n'en porte (cellule « déduit », une ligne au journal) |
| v1.7 | 2026-10 | Commit B3 : ancrage des lignes (`positions_scan.apparier_rangs`) — clé de 1re colonne lue à l'identique et unique des deux côtés = lignes appariées d'office, la ressemblance n'apparie qu'entre deux ancres (ancres croisées écartées) ; positions et mesure B0 inchangées sur les 3 extraits |
| v1.7 | 2026-10 | Commit B2 : contrôle de conservation (`CONTROLE_CONSERVATION`, pages propres, confiance ≥ `CONSERVATION_CONFIANCE_MIN` = 60) — « élément peut-être omis » (cellule colorée `COULEUR_CONSERVATION` et commentée, valeur de Claude gardée), « ligne peut-être manquante entre … et … » (commentaire sur la ligne suivante, aucune ligne insérée), mots recollés (« 1B » / « 1 B ») sans alerte ; page dégradée : une ligne « contrôle de conservation impossible » ; alertes au journal (⚠) et dans A VERIFIER |
| v1.7 | 2026-10 | Commit B1 : indicateur de page (`controle_conservation.analyser_page`) — taux de divergence Claude / Tesseract, « scan dégradé » au-delà de `PAGE_DEGRADEE` (10 %) : ligne ℹ au journal (information, pas alerte : le banc la liste sans la compter) ; nouvelle feuille « A VERIFIER » (page, ligne, colonne, type, message, lecture Tesseract, lien cliquable), une ligne par page dégradée ou, si plus de la moitié des scans le sont, une synthèse puis les pages par taux décroissant ; campagne : colonne `pages_degradees` |
| v1.7 | 2026-10 | Tesseract (positions d'origine) lit les pages scannées dans un fil à part pendant que Claude les lit : son temps est caché (PE011 : 18,7 s gagnées sur 57 s, Claude simulé à 4 s par page) |
| v1.7 | 2026-10 | Cache des lectures Tesseract (`cache_lectures.py`) dans `%LOCALAPPDATA%\TriosSeconverter\cache` au lieu du dossier de sortie : clé = empreinte du PDF + page + réglages, purge (`POSITIONS_CACHE_AGE_MAX_JOURS`, `POSITIONS_CACHE_TAILLE_MAX_MO`) ; 2e conversion du même PDF sans 2e OCR |
| v1.7 | 2026-10 | Positions : cadre à un bord absent (tableau ouvert à droite, 223111PE011 page 123) — bord de l'image du côté où sortent le plus de mots ; campagne : colonne `pages_sans_positions` |
| v1.7 | 2026-10 | Commit A, positions d'origine des pages scannées (`positions_scan.py`, `POSITIONS_*`) : chaque mot lu par Claude reprend la colonne de son jumeau Tesseract ; Excel en Courier New 11, sous-champs complétés par des espaces (`POSITIONS_ORIGINALES = False` = avant) ; lecture Tesseract gardée en cache (`<document>_tesseract.json`) ; banc : sections mesurées en position, Verite_tableaux à un espace quand la vérité a sa feuille Verite_positions. Positions fausses : PE011 p. 52 120 → 4, PE133 p. 15 112 → 0, PE012 p. 39 1 → 0 |
| v1.7 | 2026-10 | Campagne : compteur des lignes de tableau des réponses brutes de Claude au mauvais nombre de colonnes (`lignes_tableau_brutes`, `lignes_hors_colonnes` dans `mesures/campagne.csv`, 5 exemples affichés) ; passage réel du 2026-10-05 : 0 sur 454 |
| v1.7 | 2026-10 | Lignes de section des pages lues par Claude : le prompt demande de recopier « NOM DU CABLE : … » telle qu'imprimée, à sa place, précédée de `SECTION:` ; le parseur en fait une ligne 'section' du format pivot (avant : consigne de les omettre, 3 sections perdues sur les scans de 223111PE012) |
| v1.7 | 2026-10 | Emplacement de pied occupé par un texte sans libellé (« JARRETIERAGE » à la place de « BORNIER : … ») : champ remplacé, pas absent — plus d'alerte « BORNIER absent », texte gardé à sa place dans le pied livré ; règle générale `PIED_EMPLACEMENTS` (`pied_page.analyser_pied` → `EMPLACEMENT_<champ>`) |
| v1.7 | 2026-10 | Décision B3, coquille O/0 (`generer_classeur.corriger_coquilles_o`) : dans l'Excel, le numéro de borne (2e mot de TENANT, ABOUTISSANT, BORNE) de forme `O\d{1,2}[A-Z]?` prend un 0, cellule orange commentée, une alerte par cellule ; lecture inchangée, jamais ailleurs (`CORRECTION_O_*`, `COULEUR_CORRIGE`) |
| v1.7 | 2026-10 | Banc : jeux d'essai 6A23111PE133 et 223111PE012 ; sections « NOM DU CABLE », pied de vérité à deux niveaux (imprimé / livré, libellés stricts, texte fixe), alertes attendues contre le journal (`--journal`), contrôle INDICE contre Verite_garde |
| v1.7 | 2026-10 | Contrôle INDICE réussi écrit au journal (« ✓ contrôle INDICE : OK, N page(s), indices lus : … ») ; positions en début absolu (colonne 0 = bord gauche de la colonne du tableau sur la page, retrait compris) ; « Mot » de Verite_positions contrôlé à la lecture |
| v1.7 | 2026-10 | Vérité terrain : feuille facultative « Verite_positions » (page, ligne, colonne, sous-champ, début) — positions des sous-champs des pages scannées, saisies à la main, jamais tirées d'un OCR |
| v1.7 | 2026-10 | Mesure de précision : positions des pages vectorielles mesurées contre la grille du PDF source (`--pdf`, automatique en campagne), plus contre l'Excel de vérité qui ne garde pas la géométrie |
| v1.7 | 2026-10 | Mesure de précision : catégorie GLISSEMENT_COLONNE (ce qui manque dans une cellule est en trop dans sa voisine de la même ligne) et lignes déplacées (inversions) ; colonnes `glissement`, `lignes_deplacees` dans les historiques CSV (ancien en-tête réécrit) ; thermomètre doré à fautes connues |
| v1.7 | 2026-10 | Vérification de conversion au cahier des charges (≤ 20 alertes, ≥ 98 %) sur 6A 23111PE102 : relecture du scan par `relecture_scan.py` (psm 6, 300 DPI) au lieu du moteur de conversion, ponctuation parasite ignorée, case non lue ou lue à confiance basse bénigne aussi par zones. Scan / journal Claude : 57 → 7 alertes, 93,5 → 98,9 % ; scan / PDF final : 4 alertes, 99,6 % |
| v1.7 | 2026-10 | Étape 7 : champs constants d'un document (`CHAMPS_CONSTANTS_DEFAUT` = P.E.T., `CHAMPS_CONSTANTS_PAR_MODELE` dans config.py) — case vide reprise si les autres pages du même document sont unanimes (cellule colorée `COULEUR_DEDUIT`, commentée), sinon vide + alerte, sans vote ; valeur lue jamais remplacée (différente : conservée + alerte) ; INDICE, PAGE, TYPE, CABLE jamais repris |
| v1.7 | 2026-09 | Étape 7 : cellule gauche du pied = logo recopié tel qu'imprimé sur sa page (« SIEMENS » compact, « M A T R A » espacé ; vertical, une lettre par ligne → « M A T R A »), vide s'il n'y en a pas — plus le libellé du modèle ; Claude : ligne `LOGO:` ; mode Tesseract : plus d'INDICE « 0 » par défaut ; champ absent de tout le document = une seule alerte |
| v1.7 | 2026-09 | Étape 7 : pied de page lu sans liste figée (`pied_page.py`) — toutes les paires LIBELLÉ : valeur, texte libre en COMPLEMENT, « 6/10 » diamètre sauf après PAGE/FOLIO ; Claude recopie le pied (bloc `PIED_BRUT`), le code le structure ; l'Excel affiche le pied brut ; aucune valeur inventée (ni nom de bornier tiré du fichier, ni P.E.T. EPEULE, ni INDICE 0) ; alertes : champ absent, INDICE hors révisions de la page de garde, N° PLAN minoritaire |
| v1.7 | 2026-09 | Étape 6 : caractère illisible → Claude écrit « ?? » (jamais deviné ni corrigé), gardé dans l'Excel et coloré (`MARQUEUR_ILLISIBLE`, `COULEUR_ILLISIBLE`) |

---

## Ce qu'il ne faut jamais faire

- Modifier directement `env\` — recréer avec `install.bat` si besoin
- Fusionner `word_results` dans `ocr_results` — écrase les pieds de page
- Coder des chemins absolus en dehors de `config.py`
- Modifier des widgets Tkinter depuis un thread secondaire
- Supprimer `templates.json` — contient les modèles créés par l'utilisateur
- Écrire des commentaires qui expliquent le QUOI (le code le dit) — seulement le POURQUOI
