# TriosSeconverter — Guide utilisateur v1.7

Convertit des tableaux de borniers électriques (Word, PDF, images) en classeur Excel formaté.

---

## Démarrage rapide

```powershell
# 1. Installation (première fois seulement)
install.bat

# 2. Lancer l'interface graphique
env\Scripts\python.exe interface.py
```

---

## Sources acceptées (Doc. 1)

| Type | Extension | Moteur |
|------|-----------|--------|
| Word avec images scannées | `.docx` | Tesseract / Claude Vision / Docling |
| PDF vectoriel | `.pdf` | Extraction couche texte (PyMuPDF) + fallback OCR |
| Dossier d'images | dossier `.png` / `.jpg` | Tesseract / Claude Vision / Docling |
| Journal Claude à rejouer | `.jsonl` | Replay sans appel API |

Le **Doc. 2** (optionnel) est un fichier Word contenant des tableaux structurés — ils sont placés dans une feuille séparée "tableaux word" du classeur Excel.

---

## Modes OCR (page "Mode OCR")

### Tesseract (gratuit, local)
- Aucun abonnement requis
- Nécessite `C:\Tesseract\TesseractOCR\tesseract.exe` + langue française `fra.traineddata`
- Corrections automatiques via `data_dictionary.json`

### Claude Vision (API Anthropic)
- Meilleure précision sur tableaux complexes ou mal scannés
- Nécessite une clé API Anthropic (champ dans l'interface)
- Chaque image = 1 appel API (coût en tokens)
- Journal des appels sauvegardé : `*_claude.jsonl` (permet de rejouer sans repayer)

### Docling IBM (IA locale)
- Modèle IA téléchargé automatiquement au premier lancement (~500 Mo)
- Fonctionne sans GPU (CPU seul, 10–30 s/image)
- Installation : `pip install docling`

---

## Mode validation manuelle

Activez "Validation page par page" dans l'interface avant de lancer.

Après chaque tableau extrait, une fenêtre affiche :
- **Aperçu de l'image source** (vignette du bornier)
- **Données extraites** avec code couleur :
  - Orange = confiance OCR < 60 %
  - Rouge = confiance OCR < 35 %
- **Métadonnées** (PAGE, BORNIER, PET, NO_PLAN, INDICE)

Trois actions disponibles :
| Bouton | Action |
|--------|--------|
| Valider et continuer | Accepte le tableau, passe au suivant |
| Continuer automatiquement | Accepte ce tableau et désactive la validation pour la suite |
| Relancer l'OCR avec ce feedback | Renvoie l'image à l'API Claude avec votre commentaire correctif |

Les corrections validées sont mémorisées dans `data_dictionary.json` et appliquées aux tableaux suivants.

---

## Dictionnaire de correction OCR

Stocké dans `data_dictionary.json` à la racine.

Accessible depuis l'interface (page "Options" → "Consulter / modifier") :
- Valeurs organisées par colonne (BORNE, COULEUR, SIGNAL, JARRETIERES…)
- Recherche, ajout, modification, suppression en temps réel

Pour alimenter automatiquement depuis un Excel corrigé manuellement :
```powershell
env\Scripts\python.exe -c "
from data_dictionary import get_dictionary
from pathlib import Path
get_dictionary().update_from_excel(Path('tous_les_borniers_corrige.xlsx'))
"
```

---

## Paramètres (`config.py`)

| Paramètre | Défaut | Rôle |
|-----------|--------|------|
| `TESSERACT_PATH` | `C:\Tesseract\...\tesseract.exe` | Chemin Tesseract |
| `OCR_LANGUAGE` | `fra` | Langue Tesseract |
| `PAGE_SIZE` | `59` | Lignes par page A4 dans Excel |
| `STATION_NAME` | `EPEULE` | PET de repli si OCR échoue |
| `MIN_DATA_ROWS` | `3` | Lignes minimum pour valider un bornier |
| `OCR_MODE` | `tesseract` | Mode OCR par défaut |
| `CLAUDE_API_KEY` | *(vide)* | Clé API Anthropic |
| `USE_TATR` | `False` | IA Microsoft TATR (mode Python uniquement) |

---

## Résultat généré

Un fichier `<nom_source>.xlsx` dans le dossier de destination :

| Feuille | Contenu |
|---------|---------|
| `Borniers` | Tous les tableaux OCR, un par bloc A4, avec pied de page |
| `tableaux word` | Tableaux structurés du Doc. 2 (si fourni) |

Les cellules à faible confiance OCR sont colorées en jaune dans l'Excel (`< 60 %`).
Les tableaux issus d'images très floues (`> 80 %`) ont l'en-tête orange.

---

## Modèles de tableau

Configurables dans l'onglet "Modèles" de l'interface ou via `/nouveau-template`.

Modèle par défaut : **Bornier standard** — colonnes `[BORNE, COULEUR, SIGNAL, JARRETIERES]`

Les modèles sont sauvegardés dans `templates.json`.

---

## Vérifier une conversion

Après une conversion, le bouton **🔎 Vérifier** de la barre « OUTILS TABLEAUX » relit le
scan avec Tesseract et le compare, cellule par cellule, à ce qui a été converti. Une fenêtre
liste les divergences à vérifier (page, ligne, colonne, valeur du scan, valeur convertie,
raison). Les écarts sans importance (espaces, confusions O/0, texte qui glisse d'une colonne
à l'autre, mots que Tesseract a oubliés) ne sont pas signalés.

La lecture Tesseract prend du temps (environ 20 s par page) ; le bouton devient
« ⏹ Annuler la vérification » pendant son exécution.

En ligne de commande :

```powershell
env\Scripts\python.exe converter.py verifier scan.pdf converti.pdf --rapport rapport.txt
# converti peut aussi être un journal *_claude.jsonl (rejoué sans appel API)
# code retour : 0 = rien à vérifier, 1 = divergences listées
```

Les seuils se règlent dans `config.py` (section « VÉRIFICATION DE CONVERSION »).

---

## Compiler en exécutable (.exe)

```powershell
env\Scripts\activate
pyinstaller TriosSeconverter.spec --clean
# → dist\TriosSeconverter.exe
```

Toujours tester l'exe sur une machine sans Python installé avant livraison.

---

## Tests automatisés

```powershell
env\Scripts\python.exe -m pytest tests\ -v
# 487 tests passent, 0 échec (+ 1 échec attendu documenté, + 1 test lent facultatif)
```

---

## Architecture des fichiers principaux

| Fichier | Rôle |
|---------|------|
| `interface.py` | Interface graphique Tkinter |
| `converter.py` | Orchestration du pipeline de conversion |
| `ocr_processor.py` | OCR Tesseract — prétraitement, colonnes, cellules |
| `claude_ocr.py` | OCR via API Claude Vision |
| `docling_ocr.py` | OCR via Docling IBM |
| `pdf_extractor.py` | Extraction couche texte PDF (PyMuPDF) |
| `verificateur.py` | Vérification de conversion (compare le scan relu à la conversion) |
| `generer_classeur.py` | Génération du classeur Excel |
| `template.py` | Modèles de tableau paramétrables |
| `config.py` | Tous les paramètres modifiables |
| `data_dictionary.py` | Corrections OCR évolutives |

---

## Versions

| Version | Changements principaux |
|---------|----------------------|
| v1.0 | Pipeline complet image → Excel, interface graphique |
| v1.1 | PAGE_SIZE=48, sauts de page, corrections OCR évolutives |
| v1.2 | Feuille "tableaux word" séparée |
| v1.3 | Mode PDF vectoriel, corrections PDF O/0 |
| v1.4 | OCR de repli PDF, pied de page configurable |
| v1.5 | Corrections S↔5/O↔0 bornes, champs footer dynamiques |
| v1.6 | Fidélité Claude Vision, mode validation manuelle, replay log |
| v1.7 | Refonte UX en parcours de traitement : accueil à 3 cartes, assistant en 3 étapes, dashboard de conversion |
