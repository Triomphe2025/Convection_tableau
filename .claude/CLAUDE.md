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
| `STATION_NAME` | `EPEULE` | Nom P.E.T. de repli si OCR échoue |
| `MIN_DATA_ROWS` | `1` | Seuil minimal de lignes pour valider un bornier |
| `IMAGES_FOLDER_NAME` | `VD23111 PE 162` | Nom du dossier de sortie des images |

Pour modifier un paramètre → utiliser `/changer-config`.

Les paramètres `VERIF_*` (vérification de conversion : seuils d'appariement, confusions OCR,
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

---

## Ce qu'il ne faut jamais faire

- Modifier directement `env\` — recréer avec `install.bat` si besoin
- Fusionner `word_results` dans `ocr_results` — écrase les pieds de page
- Coder des chemins absolus en dehors de `config.py`
- Modifier des widgets Tkinter depuis un thread secondaire
- Supprimer `templates.json` — contient les modèles créés par l'utilisateur
- Écrire des commentaires qui expliquent le QUOI (le code le dit) — seulement le POURQUOI
