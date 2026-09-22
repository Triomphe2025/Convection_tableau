# Guide complet — Créer un logiciel fonctionnel, protégé, maintenable et améliorable

> Ce guide est basé sur le projet **TriosSeconverter** comme cas concret.
> Chaque principe est illustré par un exemple tiré des fichiers réels du projet.

---

## Table des matières

1. [Architecture du projet](#1-architecture-du-projet)
2. [Organisation du code — Séparation des responsabilités](#2-organisation-du-code--séparation-des-responsabilités)
3. [Configuration centralisée](#3-configuration-centralisée)
4. [Gestion des erreurs et robustesse](#4-gestion-des-erreurs-et-robustesse)
5. [Journalisation (logs)](#5-journalisation-logs)
6. [Interface graphique découplée du moteur](#6-interface-graphique-découplée-du-moteur)
7. [Système de modèles extensible](#7-système-de-modèles-extensible)
8. [Dictionnaire de correction — données évolutives sans recompilation](#8-dictionnaire-de-correction--données-évolutives-sans-recompilation)
9. [Tests et validation](#9-tests-et-validation)
10. [Protection du logiciel — compilation en exécutable .exe](#10-protection-du-logiciel--compilation-en-exécutable-exe)
11. [Comment maintenir le logiciel](#11-comment-maintenir-le-logiciel)
12. [Comment améliorer le logiciel](#12-comment-améliorer-le-logiciel)
13. [Gestion des versions avec Git](#13-gestion-des-versions-avec-git)
14. [Checklist avant livraison](#14-checklist-avant-livraison)

---

## 1. Architecture du projet

### Principe

Un bon logiciel ne met **pas tout le code dans un seul fichier**. Chaque fichier a une responsabilité précise et unique. Si un fichier doit être modifié pour deux raisons différentes, il fait trop de choses.

### Structure de TriosSeconverter

```
convertion Tableau/
│
├── interface.py          → Interface graphique UNIQUEMENT (affichage)
├── converter.py          → Moteur d'orchestration (coordination des étapes)
├── ocr_processor.py      → Traitement OCR (lecture des images)
├── generer_classeur.py   → Génération des fichiers de sortie (Excel + Word)
├── word_table_importer.py→ Import depuis Word (source alternative)
├── template.py           → Définition des modèles de tableau
├── config.py             → Configuration globale (chemins, paramètres)
├── data_dictionary.py    → Dictionnaire de correction OCR
├── recuperer_image.py    → Extraction des images depuis Word
│
├── PROCESSUS_OCR.md      → Documentation technique du pipeline OCR
├── GUIDE_CREATION_LOGICIEL.md → Ce fichier
├── FONCTIONNEMENT_COMPLET.cmd → Documentation interactive
│
└── tests/                → Dossier des tests automatisés
    ├── test_ocr.py
    ├── test_template.py
    └── test_excel.py
```

### Règle fondamentale

```
1 fichier = 1 responsabilité = 1 raison de changer
```

| Fichier | Sa seule responsabilité |
|---------|------------------------|
| `interface.py` | Afficher l'UI, capturer les actions utilisateur |
| `converter.py` | Coordonner les étapes dans le bon ordre |
| `ocr_processor.py` | Lire le texte dans les images |
| `generer_classeur.py` | Écrire les fichiers Excel et Word |
| `config.py` | Centraliser tous les paramètres modifiables |

---

## 2. Organisation du code — Séparation des responsabilités

### Le mauvais exemple (tout dans un seul fichier)

```python
# ❌ MAUVAIS — tout mélangé dans main.py
import tkinter as tk
import cv2
import pytesseract
from openpyxl import Workbook

def main():
    # Interface
    root = tk.Tk()
    # ... 50 lignes d'interface ...
    
    # OCR
    img = cv2.imread("image.jpg")
    text = pytesseract.image_to_string(img)
    # ... 80 lignes d'OCR ...
    
    # Excel
    wb = Workbook()
    # ... 60 lignes d'Excel ...
    
    root.mainloop()
```

Problème : si l'OCR change, il faut modifier `main.py` ; si l'UI change aussi. Si Excel change aussi.
On ne sait plus quelle partie on touche. Les bugs se cachent partout.

### Le bon exemple (séparation claire)

```python
# ✅ BON — converter.py orchestre sans implémenter les détails

from recuperer_image import ImageExtractor, ImageStorage
from ocr_processor import BornierTableExtractor
from generer_classeur import generer_excel, generer_word

class Converter:
    def run(self) -> Dict:
        # Étape 1 : extraction des images
        images = self._extraire_images()
        
        # Étape 2 : OCR
        resultats = self._faire_ocr(images)
        
        # Étape 3 : Excel
        generer_excel(resultats, extractor, chemin_excel)
        
        # Étape 4 : Word
        generer_word(resultats, extractor, chemin_word)
        
        return {'excel': chemin_excel, 'word': chemin_word}
```

`converter.py` coordonne. Il ne sait PAS comment fonctionne l'OCR en détail. Il délègue.

### Principe des couches

```
┌─────────────────────────────────────────┐
│           COUCHE PRÉSENTATION           │  interface.py
│  (affichage, boutons, barre progression)│
├─────────────────────────────────────────┤
│           COUCHE MÉTIER                 │  converter.py
│  (logique applicative, orchestration)   │
├─────────────────────────────────────────┤
│           COUCHE TRAITEMENT             │  ocr_processor.py
│  (algorithmes, OCR, calculs)            │  generer_classeur.py
├─────────────────────────────────────────┤
│           COUCHE DONNÉES                │  config.py
│  (paramètres, fichiers, persistance)    │  data_dictionary.py
└─────────────────────────────────────────┘
```

Chaque couche ne parle qu'à la couche adjacente. L'interface ne fait jamais d'OCR directement.

---

## 3. Configuration centralisée

### Principe

Tous les paramètres qui peuvent changer (chemin Tesseract, taille de page, nom de station)
doivent être dans **un seul endroit**. Jamais dispersés dans le code.

### Implémentation dans TriosSeconverter (`config.py`)

```python
class Config:
    # Chemin vers Tesseract — à changer selon la machine
    TESSERACT_PATH = r"C:\Tesseract\TesseractOCR\tesseract.exe"
    
    # Langue OCR
    OCR_LANGUAGE = "fra"
    
    # Nombre de lignes par page A4
    PAGE_SIZE = 48
    
    # Nom de la station (repli si OCR échoue)
    STATION_NAME = "EPEULE"
    
    # Nombre minimal de lignes pour valider un bornier
    MIN_DATA_ROWS = 1
```

### Pourquoi c'est important

```
❌ Sans config centralisée :
   ocr_processor.py, ligne 726 : tesseract_cmd = r"C:\Tesseract\..."
   generer_classeur.py, ligne 105 : page_size = 48
   interface.py, ligne 302 : station = "EPEULE"
   → Pour changer le chemin Tesseract, il faut chercher dans 3 fichiers.

✅ Avec config centralisée :
   config.py, ligne 84 : TESSERACT_PATH = r"C:\Tesseract\..."
   → Un seul endroit à modifier. Toujours.
```

### Profils de configuration (développement / production)

```python
class Config:
    # ... configuration de base ...
    LOG_LEVEL = "INFO"

class ConfigDev(Config):
    """Pour le développement : logs détaillés, rapports activés."""
    LOG_LEVEL = "DEBUG"
    GENERATE_REPORT = True

class ConfigProd(Config):
    """Pour la production : minimal, rapide."""
    LOG_LEVEL = "WARNING"
    VERBOSE = False
```

Usage : `from config import ConfigDev as Config` pendant le développement,
puis `from config import ConfigProd as Config` pour la livraison.

---

## 4. Gestion des erreurs et robustesse

### Principe

Un logiciel robuste ne plante pas sur une entrée imprévue. Il **anticipe** les problèmes
et les communique clairement à l'utilisateur.

### Les 3 niveaux de gestion d'erreur

#### Niveau 1 — Validation à l'entrée (interface.py)

```python
def _start(self):
    word = self._word_file.get().strip()
    
    # Vérification AVANT de lancer quoi que ce soit
    if not word:
        messagebox.showwarning("Champ manquant",
                               "Veuillez sélectionner le fichier Word source.")
        return
    
    if not Path(word).exists():
        messagebox.showerror("Fichier introuvable",
                             f"Le fichier suivant est introuvable :\n{word}")
        return
```

#### Niveau 2 — Erreurs récupérables (converter.py)

```python
# Erreur critique : stop tout
try:
    images = img_extractor.extract_images()
except Exception as exc:
    raise RuntimeError(f"Extraction des images échouée : {exc}") from exc

# Erreur non-critique : on log et on continue
try:
    storage.save_image(data, idx, ext)
    saved += 1
except Exception as e:
    self._log(f"  ⚠ Image {idx} ignorée : {e}")
    # Le traitement continue avec les autres images
```

#### Niveau 3 — Dégradation gracieuse (ocr_processor.py)

```python
def extract(self, image_path: Path) -> Dict:
    try:
        # ... traitement OCR ...
        return {'success': True, 'rows': rows, ...}
    except Exception as e:
        logger.error(f"Erreur extraction {image_path.name}: {e}")
        # Ne pas propager l'exception — retourner un résultat d'échec
        return {'success': False, 'error': str(e)}
```

Le résultat `{'success': False}` permet à l'appelant de continuer
avec les autres images même si une seule échoue.

### Règles de gestion d'erreur

| Situation | Action |
|-----------|--------|
| Fichier source introuvable | Erreur bloquante + message clair à l'utilisateur |
| Image illisible par OCR | Log d'avertissement + continuer avec les autres images |
| Résultat OCR insuffisant | Ignorer le bornier + comptabiliser |
| Écriture Excel impossible | Log d'erreur + continuer (Word peut encore être généré) |
| Bug inattendu | Capturer, logger la trace complète, afficher message générique |

---

## 5. Journalisation (logs)

### Principe

Les logs permettent de comprendre ce qui s'est passé **après** une erreur,
sans avoir à être devant la machine au moment où ça s'est produit.

### Configuration des logs (`ocr_processor.py`)

```python
import logging

# En haut de chaque fichier — NE PAS configurer ici, juste déclarer
logger = logging.getLogger(__name__)

# Dans les fonctions
logger.debug("Détail technique invisible en prod")
logger.info("✓ Tesseract trouvé: version 5.3.0")
logger.warning("⚠ Image floue détectée (82%) — résultat peut être imprécis")
logger.error("✗ Impossible de lire l'image : chemin inexistant")
```

### Configuration globale (`interface.py`)

```python
# Une seule fois dans le point d'entrée principal
logging.basicConfig(level=logging.DEBUG)
```

### Logs dans l'interface graphique

TriosSeconverter utilise une **file d'attente (Queue)** pour passer les logs
du thread de travail au thread de l'interface, sans blocage :

```python
# Thread de travail → envoie dans la queue
self._queue.put(('log', "OCR image 3/12 : bornier_3.jpg", 'info'))

# Thread UI → lit la queue toutes les 80ms
def _poll_queue(self):
    while True:
        item = self._queue.get_nowait()
        if item[0] == 'log':
            self._log(item[1], item[2])  # Affiche dans la zone de log
    self.after(80, self._poll_queue)     # Rappel automatique
```

Cette technique est **obligatoire** avec Tkinter : on ne peut modifier
l'interface que depuis le thread principal.

---

## 6. Interface graphique découplée du moteur

### Principe

L'interface ne doit **jamais** contenir de logique métier. Elle ne sait pas
comment fonctionne l'OCR. Elle sait seulement :
- Récupérer les paramètres saisis par l'utilisateur
- Lancer le moteur en arrière-plan
- Afficher les résultats et la progression

### Découplage via callbacks (`converter.py`)

```python
class Converter:
    def __init__(
        self,
        word_file: Path,
        output_dir: Path,
        on_progress: Callable[[float, str], None] = None,  # ← callback
        on_log: Callable[[str], None] = None,              # ← callback
    ):
        self._on_progress = on_progress or (lambda p, m: None)
        self._on_log = on_log or (lambda m: None)
    
    def run(self):
        # Le moteur signale sa progression sans CONNAÎTRE l'interface
        self._on_progress(0.25, "Images extraites…")
        self._on_log("  → 12 images trouvées dans le document.")
```

### Utilisation depuis l'interface (`interface.py`)

```python
conv = Converter(
    word_file=Path(word),
    output_dir=Path(outdir),
    # L'interface injecte ses propres fonctions de callback
    on_progress=lambda p, m: self._queue.put(('progress', p, m)),
    on_log=lambda m: self._queue.put(('log', m, 'info')),
)
```

**Avantage :** Le même `Converter` peut être utilisé depuis un script en ligne
de commande (sans interface graphique), en changeant simplement les callbacks :

```python
# Script sans interface graphique
conv = Converter(
    word_file=Path("mon_fichier.docx"),
    output_dir=Path("sortie/"),
    on_progress=lambda p, m: print(f"[{p*100:.0f}%] {m}"),
    on_log=lambda m: print(m),
)
conv.run()
```

---

## 7. Système de modèles extensible

### Principe

Quand une structure de données peut varier selon l'utilisateur ou le projet,
il faut la rendre **paramétrable** plutôt que de la coder en dur.

### Implémentation dans TriosSeconverter (`template.py`)

```python
@dataclass
class TableTemplate:
    name: str                     # Nom affiché dans l'interface
    columns: List[str]            # Liste des colonnes
    col_widths: Dict[str, float]  # Largeur de chaque colonne
    section_keyword: str          # Mot-clé de séparation de section
    has_footer: bool              # Activer le pied de page
    footer_left_label: str        # Étiquette gauche (ex: "M T I")
    footer_row1_format: str       # "{PET} BORNIER : {BORNIER}"
    footer_row2_format: str       # "NO PLAN : {NO_PLAN} PAGE : {PAGE}"
    
    def render_footer_row1(self, meta: Dict) -> str:
        """Remplace les placeholders {PET}, {BORNIER}, etc. par les vraies valeurs."""
        return self.footer_row1_format.format_map(
            {k: meta.get(k, '') for k in meta}
        )
```

### Pourquoi c'est puissant

```
Sans modèles :
  Le code connaît "BORNE, COULEUR, SIGNAL, JARRETIERES" en dur.
  Un client avec "REF, SECTION, DESTINATION" doit modifier le code source.

Avec modèles :
  L'utilisateur crée un nouveau modèle depuis l'interface.
  Le code ne change pas. Les colonnes, le pied de page, tout est paramétré.
```

### Persistance des modèles (`TemplateManager`)

```python
class TemplateManager:
    _FILE = Path.home() / '.triosseconverter' / 'templates.json'
    
    def add_or_update(self, tpl: TableTemplate):
        self._templates[tpl.name] = tpl
        self._save()      # Sauvegarde automatique en JSON
    
    def _save(self):
        data = {name: asdict(tpl) for name, tpl in self._templates.items()}
        self._FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding='utf-8')
```

Les modèles sont sauvegardés dans le dossier personnel de l'utilisateur
(`~/.triosseconverter/templates.json`). Ils survivent aux mises à jour du logiciel.

---

## 8. Dictionnaire de correction — données évolutives sans recompilation

### Principe

L'OCR fait des erreurs prévisibles (confusions de lettres, artefacts).
Ces erreurs peuvent être corrigées via un **dictionnaire externe** que
l'utilisateur peut enrichir sans toucher au code.

### Implémentation (`data_dictionary.py`)

```python
# data_dictionary.json (exemple)
{
  "COULEUR": {
    "ROUSE": "ROUGE",
    "BLENC": "BLANC",
    "VER": "VERT"
  },
  "BORNIER": {
    "B7O2A": "B702A",    # confusion O/0
    "B702/A": "B702A"    # slash parasite
  }
}
```

```python
class DataDictionary:
    def correct(self, column: str, value: str) -> Tuple[str, bool]:
        corrections = self._data.get(column.upper(), {})
        corrected = corrections.get(value.upper(), value)
        changed = (corrected != value)
        return corrected, changed
```

### Avantage opérationnel

Quand un technicien constate qu'un bornier est toujours mal lu (ex: "B7O2A"
au lieu de "B702A"), il ajoute la correction dans le fichier JSON.
**Aucune mise à jour du logiciel n'est nécessaire.**

---

## 9. Tests et validation

### Pourquoi tester

Un test automatisé vérifie en 2 secondes ce qu'un humain mettrait 10 minutes
à vérifier manuellement. Il détecte immédiatement si une modification casse
une fonctionnalité existante.

### Structure des tests recommandée

```
tests/
├── test_ocr_processor.py     → Tests du pipeline OCR
├── test_template.py          → Tests du système de modèles
├── test_generer_classeur.py  → Tests de génération Excel
├── test_word_importer.py     → Tests de l'import Word
├── images_test/              → Images de test fixes
│   ├── bornier_simple.jpg
│   └── bornier_flou.jpg
└── conftest.py               → Fixtures partagées (pytest)
```

### Exemples de tests pour TriosSeconverter

```python
# tests/test_ocr_processor.py
import pytest
from pathlib import Path
from ocr_processor import BornierTableExtractor

@pytest.fixture
def extractor():
    return BornierTableExtractor(language='fra')

def test_extract_retourne_succes_sur_image_valide(extractor):
    """Une image lisible doit retourner success=True."""
    result = extractor.extract(Path("tests/images_test/bornier_simple.jpg"))
    assert result['success'] is True
    assert len(result['rows']) > 0
    assert 'BORNIER' in result['metadata'] or 'PAGE' in result['metadata']

def test_extract_retourne_echec_sur_image_inexistante(extractor):
    """Une image manquante ne doit pas lever d'exception, mais retourner success=False."""
    result = extractor.extract(Path("tests/images_test/inexistant.jpg"))
    assert result['success'] is False
    assert 'error' in result

def test_clean_cell_supprime_pipes():
    """Les pipes en bord de cellule doivent être supprimés."""
    from ocr_processor import BornierTableExtractor
    assert BornierTableExtractor._clean_cell("| ROUGE |") == "ROUGE"

def test_clean_cell_retourne_vide_si_bruit():
    """Une séquence de caractères identiques = bruit scanner."""
    assert BornierTableExtractor._clean_cell("||||||") == ""

def test_extract_meta_trouve_page(extractor):
    """L'extraction de métadonnées doit trouver le numéro de page."""
    footer_lines = [[
        {'text': 'PAGE', 'cx': 100, 'cy': 0},
        {'text': ':', 'cx': 120, 'cy': 0},
        {'text': '92', 'cx': 135, 'cy': 0},
    ]]
    meta = extractor._extract_meta(footer_lines)
    assert meta.get('PAGE') == '92'
```

```python
# tests/test_template.py
from template import TableTemplate, TemplateManager

def test_render_footer_row1_remplace_placeholders():
    tpl = TableTemplate(
        name="Test",
        columns=["A"],
        footer_row1_format="P.E.T : {PET}  BORNIER : {BORNIER}",
        # ... autres champs ...
    )
    meta = {'PET': 'EPEULE', 'BORNIER': 'B702A'}
    result = tpl.render_footer_row1(meta)
    assert result == "P.E.T : EPEULE  BORNIER : B702A"

def test_manager_sauvegarde_et_recharge(tmp_path):
    """Un modèle sauvegardé doit être rechargeable."""
    mgr = TemplateManager(storage_path=tmp_path / "templates.json")
    tpl = TableTemplate(name="MonModele", columns=["COL1", "COL2"])
    mgr.add_or_update(tpl)
    
    # Recharger depuis le disque
    mgr2 = TemplateManager(storage_path=tmp_path / "templates.json")
    assert "MonModele" in mgr2.names()
```

### Lancer les tests

```bash
# Installation de pytest
pip install pytest

# Lancer tous les tests
pytest tests/ -v

# Lancer un seul fichier
pytest tests/test_ocr_processor.py -v

# Avec affichage des logs
pytest tests/ -v --log-cli-level=DEBUG
```

---

## 10. Protection du logiciel — compilation en exécutable .exe

### Principe

Pour distribuer le logiciel sans donner accès au code source Python,
on compile en un exécutable Windows autonome avec **PyInstaller**.

### Installation de PyInstaller

```bash
pip install pyinstaller
```

### Compilation simple

```bash
# Depuis le dossier du projet
pyinstaller --onefile --windowed interface.py
```

- `--onefile` : tout dans un seul fichier `.exe`
- `--windowed` : pas de fenêtre console (application graphique)

### Compilation avec icône et ressources (`TriosSeconverter`)

```bash
pyinstaller ^
  --onefile ^
  --windowed ^
  --icon=icon.ico ^
  --add-data "icon.ico;." ^
  --add-data "templates.json;." ^
  --name "TriosSeconverter" ^
  interface.py
```

- `--icon` : icône de l'exécutable
- `--add-data "source;dest"` : inclure des fichiers dans l'exe
- `--name` : nom du fichier .exe généré

### Fichier .spec pour builds reproductibles

PyInstaller génère un fichier `TriosSeconverter.spec`. Ce fichier
doit être versionné (Git) pour reproduire le build identiquement :

```python
# TriosSeconverter.spec (extrait)
a = Analysis(
    ['interface.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
        ('templates.json', '.'),
    ],
    hiddenimports=['cv2', 'pytesseract', 'openpyxl', 'docx'],
    ...
)
```

### Résolution des ressources dans l'exe (`interface.py`)

Quand PyInstaller empaquette tout, les chemins relatifs ne fonctionnent plus.
Il faut utiliser `sys._MEIPASS` (dossier temporaire de l'exe) :

```python
def _resource(name: str) -> Path:
    """Résout le chemin d'une ressource dans l'exe ou le dossier source."""
    if hasattr(sys, '_MEIPASS'):       # Mode exe PyInstaller
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name  # Mode développement

# Usage
ico = _resource("icon.ico")
if ico.exists():
    self.iconbitmap(str(ico))
```

### Résultat

```
dist/
└── TriosSeconverter.exe   ← exécutable autonome, ~50-100 Mo
                              Inclut Python, toutes les bibliothèques,
                              et les ressources. Pas besoin d'installation.
```

### Protection supplémentaire (obfuscation)

Si le code doit être protégé contre la rétro-ingénierie :

```bash
# Installer PyArmor
pip install pyarmor

# Obfusquer le code source
pyarmor gen interface.py converter.py ocr_processor.py

# Puis compiler l'obfusqué avec PyInstaller
pyinstaller --onefile --windowed dist/pyarmor/interface.py
```

**Note :** L'obfuscation ralentit légèrement le démarrage. Ne l'appliquer
que si la protection du code source est réellement nécessaire.

---

## 11. Comment maintenir le logiciel

### Qu'est-ce que la maintenance ?

La maintenance c'est garder le logiciel fonctionnel dans le temps :
- Corriger les bugs remontés par les utilisateurs
- Adapter aux changements d'environnement (nouvelle version de Windows,
  nouvelle version de Tesseract, nouveau format de document source)
- Améliorer les performances sans casser ce qui fonctionne

### Règle 1 — Ne jamais modifier sans comprendre

Avant de modifier une ligne de code :
1. Lire la fonction entière, pas seulement la ligne à changer
2. Chercher tous les endroits où la fonction est appelée (Ctrl+Shift+F dans VS Code)
3. Vérifier que le changement est compatible avec tous les appelants

```python
# Exemple : modifier la signature de generer_excel
# AVANT  → generer_excel(results, extractor, output_path)
# APRÈS  → generer_excel(results, extractor, output_path, word_results=None)

# Vérifier TOUS les appels dans le projet :
# converter.py   : generer_excel(ocr_results, extractor, excel_path, word_results=...)  ✓
# generer_classeur.py main() : generer_excel(results, extractor, ...) ← word_results=None par défaut ✓
```

### Règle 2 — Ajouter des paramètres optionnels, ne pas casser les existants

```python
# ❌ MAUVAIS — casse les appels existants
def generer_excel(results, extractor, output_path, word_results):
    # word_results est maintenant OBLIGATOIRE

# ✅ BON — rétrocompatible
def generer_excel(results, extractor, output_path, word_results=None):
    # word_results est optionnel, None par défaut
    if word_results:
        # ... créer la feuille "tableaux word" ...
```

### Règle 3 — Un bug = un test

Quand un bug est trouvé et corrigé, écrire immédiatement un test qui
aurait détecté ce bug. Ce test empêchera la régression future.

```python
# Bug trouvé : les pieds de page des images étaient écrasés par les tableaux Word
# Correction : séparer word_results dans une feuille distincte
# Test correspondant :

def test_word_results_ne_contamine_pas_borniers(tmp_path):
    """Les tableaux Word ne doivent pas modifier la feuille Borniers."""
    wb = generer_excel_en_memoire(ocr_results, word_results)
    
    assert "Borniers" in wb.sheetnames
    assert "tableaux word" in wb.sheetnames
    
    # La feuille Borniers ne doit contenir que des données OCR
    ws_borniers = wb["Borniers"]
    # ... vérifications des pieds de page ...
```

### Règle 4 — Journaliser les décisions importantes

Quand un choix technique non-évident est fait, le documenter dans le code :

```python
# Utiliser x (bord gauche) au lieu de cx (centre) évite qu'un mot
# large commençant dans SIGNAL soit attribué à JARRETIERES parce
# que son centre dépasse la frontière.
x_start = elem['x']   # bord gauche, intentionnel
```

Ce commentaire explique le POURQUOI, pas le QUOI. Le QUOI se lit dans le code.

### Gestion des mises à jour de Tesseract

Si la version de Tesseract change, vérifier :
1. `config.py` → `TESSERACT_PATH` pointe toujours vers le bon exe
2. Les options `--oem 3 --psm 6` sont toujours valides (consulter `tesseract --help-oem`)
3. Le fichier de langue `fra.traineddata` est présent dans le dossier `tessdata/`

---

## 12. Comment améliorer le logiciel

### Amélioration 1 — Support de nouveaux formats d'image

Le code actuel accepte `.jpg`, `.jpeg`, `.png`, `.bmp`.
Pour ajouter `.tiff` (fréquent dans les scans industriels) :

```python
# config.py — une seule ligne à modifier
OCR_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]

# converter.py et generer_classeur.py utilisent Config.OCR_IMAGE_EXTENSIONS
# → Le changement se propage automatiquement partout
```

### Amélioration 2 — Nouveau modèle de tableau

L'utilisateur peut créer un modèle "Bornier 6 colonnes" directement
depuis l'interface (bouton "+ Nouveau modèle") sans modifier le code.

### Amélioration 3 — Ajouter une colonne de corrections OCR

Pour tracer les corrections appliquées par le dictionnaire,
ajouter un commentaire Excel sur les cellules corrigées :

```python
# Dans ocr_processor.py → _fill_worksheet()
if dictionary and val:
    val_corrige, a_change = dictionary.correct(col_name, val)
    c = ws.cell(row=cur, column=ci, value=val_corrige)
    if a_change:
        # Nouveau : commentaire pour tracer la correction
        from openpyxl.comments import Comment
        c.comment = Comment(
            f'Corrigé par dictionnaire : "{val}" → "{val_corrige}"',
            'TriosSeconverter'
        )
```

### Amélioration 4 — Export vers d'autres formats

Pour ajouter un export CSV, créer une nouvelle fonction dans `generer_classeur.py` :

```python
def generer_csv(results: List[Dict], output_path: Path) -> None:
    """Exporte les données en CSV (format universel)."""
    import csv
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        # utf-8-sig = UTF-8 avec BOM pour Excel qui l'ouvre correctement
        writer = csv.writer(f, delimiter=';')
        for result in results:
            if not result.get('success'):
                continue
            writer.writerow(result.get('headers', []))
            for row in result.get('rows', []):
                if row['type'] == 'data':
                    writer.writerow(row.get('cells', []))
```

Puis dans `converter.py` :
```python
# Étape 5 (nouvelle) : export CSV
if Config.EXPORT_CSV:
    csv_path = self.output_dir / 'tous_les_borniers.csv'
    generer_csv(ocr_results, csv_path)
```

### Amélioration 5 — Rapport de qualité OCR

Générer un rapport HTML indiquant pour chaque bornier :
- Le niveau de flou de l'image source
- Le nombre de cellules corrigées par le dictionnaire
- Les métadonnées extraites (pour vérification)

```python
def generer_rapport_html(results: List[Dict], output_path: Path) -> None:
    lignes = ["<html><body><table border='1'>"]
    lignes.append("<tr><th>Bornier</th><th>Page</th><th>Flou%</th><th>Lignes</th></tr>")
    
    for r in results:
        if not r.get('success'):
            continue
        meta = r.get('metadata', {})
        flou = r.get('blur_pct', 0)
        couleur = '#ffaaaa' if flou > 80 else '#ffffff'
        lignes.append(
            f"<tr style='background:{couleur}'>"
            f"<td>{meta.get('BORNIER','?')}</td>"
            f"<td>{meta.get('PAGE','?')}</td>"
            f"<td>{flou:.0f}%</td>"
            f"<td>{sum(1 for row in r.get('rows',[]) if row.get('type')=='data')}</td>"
            f"</tr>"
        )
    
    lignes.append("</table></body></html>")
    output_path.write_text('\n'.join(lignes), encoding='utf-8')
```

---

## 13. Gestion des versions avec Git

### Pourquoi Git est indispensable

Git permet de :
- Revenir à une version qui fonctionnait si une modification casse tout
- Travailler sur une amélioration sans risquer le code stable
- Voir exactement ce qui a changé entre deux versions
- Collaborer à plusieurs sans écraser le travail des autres

### Initialiser Git pour ce projet

```bash
# Dans le dossier du projet
git init
git add .
git commit -m "Version initiale de TriosSeconverter v1.0"
```

### Fichier `.gitignore` recommandé

```gitignore
# Dossiers générés automatiquement
__pycache__/
*.pyc
*.pyo
dist/
build/
*.spec

# Fichiers de données volumineux
images_borniers/
*.xlsx
*.docx

# Fichiers de configuration locaux (chemins machines)
config_local.py
*.log
*.json.bak

# Environnement Python
venv/
.env
```

### Flux de travail recommandé

```bash
# 1. Avant toute modification, créer une branche
git checkout -b amelioration/export-csv

# 2. Travailler et committer régulièrement
git add generer_classeur.py config.py
git commit -m "Ajouter export CSV dans generer_classeur"

# 3. Tester que tout fonctionne
pytest tests/ -v

# 4. Fusionner dans la branche principale
git checkout main
git merge amelioration/export-csv

# 5. Créer un tag de version
git tag -a v1.1 -m "v1.1 — ajout export CSV"
```

### Numérotation des versions

Adopter le format **MAJEUR.MINEUR.CORRECTIF** (SemVer) :

| Version | Signification |
|---------|--------------|
| `v1.0.0` | Version initiale stable |
| `v1.0.1` | Correction d'un bug (pied de page) |
| `v1.1.0` | Nouvelle fonctionnalité (feuille "tableaux word") |
| `v2.0.0` | Refonte majeure incompatible avec la v1 |

---

## 14. Checklist avant livraison

Avant de livrer une nouvelle version à l'utilisateur final :

### Code
- [ ] Tous les chemins codés en dur ont été déplacés vers `config.py`
- [ ] Aucun `print("debug")` ou `print(variable)` oublié dans le code
- [ ] La variable `LOG_LEVEL` est à `"INFO"` (pas `"DEBUG"`) dans la config de prod
- [ ] Tous les fichiers de test passent : `pytest tests/ -v`

### Fonctionnalités
- [ ] Tester avec un fichier Word contenant des images (chemin nominal)
- [ ] Tester avec un fichier Word SANS images (cas limite)
- [ ] Tester avec un fichier Word très grand (50+ images)
- [ ] Tester avec Doc.2 (tableaux Word structurés) présent et absent
- [ ] Vérifier que la feuille "Borniers" n'est pas altérée quand Doc.2 est fourni
- [ ] Vérifier que la feuille "tableaux word" est créée si Doc.2 est fourni

### Interface
- [ ] Les boutons Excel / Word / Dossier s'ouvrent correctement
- [ ] La barre de progression atteint bien 100% à la fin
- [ ] Les erreurs sont affichées clairement (pas de plantage silencieux)
- [ ] Le log affiche bien les étapes et les résultats

### Exécutable
- [ ] Compiler avec PyInstaller depuis le fichier `.spec`
- [ ] Tester l'exe sur une machine **sans Python installé**
- [ ] Vérifier que l'icône s'affiche dans la barre des tâches
- [ ] Vérifier que les ressources (icon.ico, templates.json) sont incluses

### Documentation
- [ ] La version dans l'interface (`v1.x`) correspond au tag Git
- [ ] Le fichier `PROCESSUS_OCR.md` est à jour
- [ ] Le fichier `FONCTIONNEMENT_COMPLET.cmd` reflète les nouvelles fonctionnalités

---

## Résumé des principes essentiels

| Principe | Application dans TriosSeconverter |
|----------|----------------------------------|
| **1 fichier = 1 responsabilité** | `interface.py` n'appelle jamais Tesseract |
| **Configuration centralisée** | Tous les paramètres dans `config.py` |
| **Erreurs récupérables** | Une image ratée n'arrête pas tout le traitement |
| **Callbacks pour le découplage** | L'interface injecte ses fonctions dans le `Converter` |
| **Paramètres optionnels** | `word_results=None` ne casse pas les appels existants |
| **Données évolutives** | `data_dictionary.json` modifiable sans recompiler |
| **Modèles paramétrables** | Nouveaux types de tableau sans modifier le code |
| **Tests automatisés** | Un bug corrigé = un test ajouté |
| **Git pour tout** | Chaque version livrée = un tag Git |
| **Exe autonome** | PyInstaller pour la distribution sans Python |

---

*Basé sur le projet TriosSeconverter — Triomphe Tchounda — 2026*
