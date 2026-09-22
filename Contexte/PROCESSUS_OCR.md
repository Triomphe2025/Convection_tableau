# Processus OCR — TriosSeconverter

## Vue d'ensemble

TriosSeconverter transforme des **images de tableaux de borniers électriques** (extraites d'un fichier Word) en données structurées exportées vers Excel et Word. Le cœur du logiciel est un pipeline OCR en 7 étapes, implémenté dans la classe `BornierTableExtractor` (`ocr_processor.py`).

```
Image (.jpg/.png)
       │
       ▼
[1] Prétraitement (agrandissement, binarisation Otsu)
       │
       ▼
[2] OCR Tesseract → liste de mots avec coordonnées (x, y, w, h)
       │
       ▼
[3] Regroupement en lignes horizontales
       │
       ▼
[4] Détection de la ligne d'en-tête + calcul des frontières de colonnes
       │
       ▼
[5] Classification de chaque ligne (data / section / pied de page)
       │
       ▼
[6] Affectation des mots aux colonnes → cellules de données
       │
       ▼
[7] Extraction des métadonnées du pied (BORNIER, PAGE, PET, INDICE, NO_PLAN)
       │
       ▼
  dict structuré → Excel / Word
```

---

## Étape 1 — Prétraitement de l'image

**Fichier :** `ocr_processor.py` → `BornierTableExtractor._preprocess()`

L'image brute est préparée pour maximiser la qualité OCR :

1. **Chargement** : lecture avec OpenCV (`cv2.imread`).
2. **Conversion en niveaux de gris** : `cv2.cvtColor(BGR → GRAY)`.
3. **Agrandissement** : si la largeur est inférieure à 1400 px, l'image est agrandie proportionnellement avec interpolation cubique (INTER_CUBIC). Tesseract produit de meilleurs résultats sur des images larges.
4. **Binarisation Otsu** : `cv2.threshold(THRESH_BINARY + THRESH_OTSU)`. L'algorithme d'Otsu calcule automatiquement le seuil optimal pour séparer le texte noir du fond blanc, même si la luminosité varie entre images.

**Résultat :** image binaire noir/blanc + largeur en pixels.

---

## Étape 2 — Reconnaissance optique de caractères (OCR)

**Fichier :** `ocr_processor.py` → `BornierTableExtractor._ocr_elements()`

Tesseract analyse l'image binarisée et retourne la position précise de chaque mot reconnu :

- **Moteur :** `--oem 3` (mode LSTM, le plus précis)
- **Mode de segmentation :** `--psm 6` (bloc de texte uniforme — adapté aux tableaux)
- **Langue :** `fra` (français, configurable dans `config.py`)
- **Filtrage :** seuls les mots avec une **confiance ≥ 15 %** sont conservés (élimine le bruit visuel)

Chaque mot retenu produit un dictionnaire :
```python
{
    'text': 'B702A',   # texte reconnu
    'x': 412,          # bord gauche (pixels)
    'y': 238,          # bord haut (pixels)
    'w': 54,           # largeur du mot
    'h': 18,           # hauteur du mot
    'cx': 439,         # centre horizontal
    'cy': 247,         # centre vertical
    'conf': 87,        # confiance Tesseract (%)
}
```

---

## Étape 3 — Regroupement des mots en lignes

**Fichier :** `ocr_processor.py` → `BornierTableExtractor._group_lines()`

Les mots extraits par Tesseract ne sont pas ordonnés : ils peuvent appartenir à n'importe quelle ligne du tableau. Cette étape les regroupe par ligne horizontale.

**Algorithme :**
1. Calcul de la **tolérance verticale** = 60 % de la hauteur médiane des mots (adaptative, minimum 8 px).
2. Tri de tous les mots par centre vertical (`cy`).
3. Parcours séquentiel : si `|cy_nouveau - cy_courant| ≤ tolérance`, le mot rejoint la ligne courante ; sinon, une nouvelle ligne est créée.
4. La `cy` courante est recalculée comme **moyenne** des centres de la ligne en cours (stabilisation).
5. Dans chaque ligne, les mots sont triés par position `x` (gauche → droite).

**Résultat :** liste de lignes, chacune étant une liste de mots triés de gauche à droite.

---

## Étape 4 — Détection de l'en-tête et calcul des frontières de colonnes

**Fichier :** `ocr_processor.py` → `BornierTableExtractor._find_header_idx()` et `_col_boundaries()`

### Détection de l'en-tête

Le logiciel cherche la ligne contenant au moins la moitié des mots-clés de colonnes définis dans le **modèle de tableau** (ex. : BORNE, COULEUR, SIGNAL, JARRETIERES). La correspondance est partielle : un mot-clé est trouvé s'il apparaît n'importe où dans le texte de la ligne (gère les fautes OCR mineures).

### Calcul des frontières de colonnes

Une fois l'en-tête trouvée :
1. La position horizontale du centre (`cx`) de chaque mot-clé de l'en-tête est mémorisée.
2. Les mots-clés sont triés par position `cx` croissante.
3. Les **frontières** de colonnes sont placées au milieu de chaque paire de centres successifs.
4. La première frontière est 0 (bord gauche de l'image) ; la dernière est la largeur totale.

```
          BORNE        COULEUR      SIGNAL      JARRETIERES
cx :       120           320          520            720
           |              |            |              |
frontières : 0   |   220   |   420   |   620   |   img_width
```

Si l'en-tête n'est pas détectée, les colonnes sont réparties en parts égales.

---

## Étape 5 — Classification de chaque ligne

**Fichier :** `ocr_processor.py` → `BornierTableExtractor._classify_line()`

Chaque ligne située sous l'en-tête est classifiée en trois catégories :

| Catégorie | Critère de détection |
|-----------|---------------------|
| `section` | Contient le mot-clé de séparation du modèle (ex. : « NOM DU CABLE ») |
| `footer`  | Contient un mot-clé de pied (NO PLAN, INDICE, PAGE, BORNIER, P.E.T., M T I) |
| `data`    | Toute autre ligne → ligne de données du bornier |

Les lignes `footer` sont collectées séparément pour extraire les métadonnées (étape 7). Les lignes `section` sont fusionnées sur toute la largeur du tableau.

---

## Étape 6 — Affectation des mots aux colonnes

**Fichier :** `ocr_processor.py` → `BornierTableExtractor._line_to_cells()`

Pour chaque ligne de données, les mots sont assignés à leur colonne selon la position de leur **bord gauche** (`x`), comparée aux frontières calculées à l'étape 4.

L'utilisation du bord gauche (et non du centre `cx`) évite qu'un mot long commençant dans une colonne soit attribué à la colonne suivante parce que son centre dépasse la frontière.

Si plusieurs mots tombent dans la même colonne, leur texte est **concaténé** avec un espace.

### Nettoyage des cellules (`_clean_cell`)

Après affectation, chaque valeur est nettoyée :
- Suppression des pipes `|` en début/fin (artefacts de séparation de colonnes mal lus)
- Retour de chaîne vide si aucun caractère alphanumérique
- Retour de chaîne vide si ≥ 5 caractères identiques consécutifs (bruit scanner)

### Correction via dictionnaire (`data_dictionary.py`)

Si un dictionnaire de données est chargé, chaque valeur de cellule est soumise à une correction : le dictionnaire remplace les erreurs OCR connues par leur valeur correcte, colonne par colonne.

---

## Étape 7 — Extraction des métadonnées du pied de page

**Fichier :** `ocr_processor.py` → `BornierTableExtractor._extract_meta()`

Les lignes de type `footer` (collectées à l'étape 5) sont concaténées en une seule chaîne de texte. Des expressions régulières extraient alors les champs :

| Champ    | Pattern regex (simplifié)                         | Exemple résultat |
|----------|--------------------------------------------------|-----------------|
| PET      | `P.E.T. : <nom multi-mots jusqu'à BORNIER>`       | `EPEULE`        |
| BORNIER  | `BORNIER : <code alphanumérique>`                 | `B702A`         |
| NO_PLAN  | `NO PLAN : <texte jusqu'à INDICE ou pipe>`        | `VD23111 PE 162`|
| INDICE   | `INDICE : <chiffre>`                              | `0`             |
| PAGE     | `PAGE : <nombre>`                                 | `92`            |

La confusion OCR courante `O` ↔ `0` est normalisée automatiquement sur le champ INDICE.

---

## Génération des fichiers de sortie

### Classeur Excel (`generer_classeur.py` → `generer_excel`)

Le classeur contient deux feuilles distinctes :

**Feuille « Borniers »** (tableaux issus de l'OCR sur les images)
- Chaque bornier occupe exactement `PAGE_SIZE` lignes (défaut : 48) simulant une page A4.
- En-tête gris (`D9D9D9`) ou orange si l'image source est trop floue (flou > 80 %).
- Bordures complètes sur l'en-tête, bordures latérales uniquement sur les données.
- Lignes de section en italique gras sur toute la largeur.
- Pied de page à 2 lignes avec fusion de cellules : colonne gauche (M T I) + bloc droit (P.E.T., BORNIER / NO PLAN, INDICE, PAGE).
- Sauts de page Excel insérés automatiquement entre chaque bornier.

**Feuille « tableaux word »** (tableaux importés depuis un fichier Word `.docx`)
- Même mise en forme que « Borniers » mais avec des données provenant du `WordTableImporter`.
- Complètement séparée pour ne pas perturber la mise en forme de la feuille principale.

### Document Word (`generer_classeur.py` → `generer_word`)

Un seul document `.docx` contenant tous les tableaux OCR, séparés par des sauts de page. Chaque tableau est précédé d'un titre de niveau 2 (nom du bornier).

---

## Import de tableaux depuis Word (`word_table_importer.py`)

La classe `WordTableImporter` lit les tableaux d'un fichier Word **déjà structuré** (tableaux propres, pas d'images) et les convertit dans le même format dict que `BornierTableExtractor.extract()`.

**Processus :**
1. Ouverture du `.docx` avec `python-docx`.
2. Pour chaque tableau : détection du pied de page (lignes contenant NO PLAN, INDICE, PAGE, etc.) en remontant depuis la fin.
3. Extraction de l'en-tête (première ligne), des données (lignes intermédiaires) et des métadonnées (pied).
4. Retour d'un dict identique à celui de l'OCR, compatible avec `_fill_worksheet()`.

---

## Modèle de tableau (`template.py`)

La classe `TableTemplate` définit la structure attendue d'un tableau bornier :
- **Colonnes** : liste ordonnée des noms de colonnes (ex. : `[BORNE, COULEUR, SIGNAL, JARRETIERES]`)
- **Largeurs** : largeur en caractères de chaque colonne dans Excel
- **Séparateur de section** : mot-clé identifiant les lignes de section (ex. : `NOM DU CABLE`)
- **Pied de page** : activation, étiquette gauche, format des deux lignes avec placeholders `{PET}`, `{BORNIER}`, `{PAGE}`, etc.

Le modèle est sélectionnable depuis l'interface graphique et peut être créé/modifié par l'utilisateur.

---

## Diagramme de flux complet

```
[Fichier Word source (.docx)]
         │
         ▼
   ImageExtractor
   (récupère les images embarquées)
         │
         ▼
   ImageStorage
   (sauvegarde → dossier images_borniers/)
         │
         ▼
   BornierTableExtractor.extract()
     ├─ _preprocess()       → image binarisée
     ├─ _ocr_elements()     → mots + coordonnées
     ├─ _group_lines()      → lignes horizontales
     ├─ _find_header_idx()  → index ligne en-tête
     ├─ _col_boundaries()   → frontières de colonnes
     ├─ _classify_line()    → data / section / footer
     ├─ _line_to_cells()    → cellules par colonne
     └─ _extract_meta()     → BORNIER, PAGE, PET…
         │
         ▼
    dict résultat OCR
         │
         │  [Fichier Word tableaux (optionnel)]
         │         │
         │   WordTableImporter.extract_tables()
         │         │
         │    dict résultat Word
         │
         ▼
   generer_excel()
     ├─ Feuille « Borniers »      ← résultats OCR
     └─ Feuille « tableaux word » ← résultats Word (séparés)
         │
   generer_word()
     └─ Document .docx combiné ← résultats OCR
```
