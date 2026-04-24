# 📖 Guide Complet - Extraction d'Images depuis Word

## 🎯 Objectif

Ce projet vous permet d'extraire automatiquement **toutes les images** d'un fichier Word (.docx) et de les enregistrer dans un dossier organisé avec un **nommage automatique incrémental**.

---

## 📐 Architecture du Code

### Vue d'ensemble

```
recuperer_image.py
├── ImageExtractor           (Classe d'extraction)
│   ├── Valide le fichier
│   ├── Ouvre le .docx comme archive ZIP
│   └── Récupère les images depuis word/media/
│
├── ImageStorage             (Classe de stockage)
│   ├── Crée le dossier de destination
│   └── Enregistre les images avec nommage auto (bornier_1, bornier_2, etc.)
│
├── ImageExtractionPipeline  (Orchestration)
│   ├── Coordonne les classes
│   ├── Gère les erreurs
│   └── Fournit un résumé complet
│
└── main()                   (Point d'entrée)
    └── Lance le processus complet
```

### Détail de chaque classe

#### 1️⃣ **ImageExtractor**
**Responsabilité**: Extraire les images du document Word

**Fonctionnement**:
- Un fichier .docx est en réalité une **archive ZIP**
- Les images sont stockées dans le dossier `word/media/`
- La classe ouvre le ZIP et récupère toutes les images avec leurs extensions

**Méthodes principales**:
- `__init__(word_path)` : Initialise et valide le fichier
- `extract_images()` : Récupère toutes les images
- `_validate_file()` : Vérifie que c'est un .docx valide

#### 2️⃣ **ImageStorage**
**Responsabilité**: Gérer le stockage des images

**Fonctionnement**:
- Crée le dossier de destination (`VD23111 PE 162` par défaut)
- Enregistre chaque image avec un nom automatique
- Nommage: `bornier_1.jpg`, `bornier_2.png`, etc.

**Méthodes principales**:
- `create_output_folder(base_path)` : Crée le dossier
- `save_image(image_bytes, index, extension)` : Enregistre une image

#### 3️⃣ **ImageExtractionPipeline**
**Responsabilité**: Orchestrer tout le processus

**Fonctionnement**:
- Coordonne `ImageExtractor` et `ImageStorage`
- Gère les erreurs globalement
- Fournit un résumé avec statistiques

**Méthode principale**:
- `run()` : Lance l'extraction et enregistrement complets

---

## 🚀 Installation et Configuration

### Étape 1: Installer les dépendances

```bash
pip install python-docx Pillow
```

**Explications**:
- `python-docx` : Pour manipuler les fichiers Word
- `Pillow` : Pour les manipulations d'images (optionnel si vous voulez redimensionner, etc.)

### Étape 2: Préparer votre fichier Word

1. Placez votre fichier Word dans le même dossier que le script
2. Ou utilisez un chemin complet

### Étape 3: Configurer le chemin

Ouvrez `recuperer_image.py` et modifiez la ligne 228:

```python
# Avant:
word_file = "document.docx"  # À CONFIGURER

# Après:
word_file = "mon_document.docx"
# ou chemin complet:
# word_file = r"C:\Users\Utilisateur\Documents\rapport.docx"
```

---

## 📋 Utilisation

### Méthode 1: Exécution simple (Recommandée)

```bash
python recuperer_image.py
```

**Résultat**: Les images s'enregistrent dans un dossier `VD23111 PE 162` au même endroit que le script.

### Méthode 2: Utilisation avancée

Créez un fichier `main_custom.py`:

```python
from recuperer_image import ImageExtractionPipeline

# Cas 1: Dossier de destination par défaut
pipeline = ImageExtractionPipeline("mon_document.docx")
results = pipeline.run()

# Cas 2: Dossier personnalisé
pipeline = ImageExtractionPipeline(
    word_file="mon_document.docx",
    output_folder="Mes Images Extraites"
)
results = pipeline.run()

# Accéder aux résultats
print(f"Images trouvées: {results['total']}")
print(f"Images enregistrées: {results['saved']}")
print(f"Localisation: {results['output_path']}")
```

### Méthode 3: Avec gestion d'erreurs

```python
from recuperer_image import ImageExtractionPipeline

try:
    pipeline = ImageExtractionPipeline("mon_document.docx")
    results = pipeline.run()
    
    if results['errors'] > 0:
        print(f"⚠ {results['errors']} image(s) n'a pas pu être enregistrée")
    
except FileNotFoundError:
    print("Le fichier Word n'existe pas")
except ValueError as e:
    print(f"Erreur: {e}")
```

---

## 📊 Exemple de résultat

```
==================================================
🚀 Début du traitement
==================================================
✓ Fichier validé: mon_document.docx
✓ Dossier créé/existant: C:\...\VD23111 PE 162
🔍 Extraction des images en cours...
✓ Image enregistrée: bornier_1.jpg
✓ Image enregistrée: bornier_2.png
✓ Image enregistrée: bornier_3.jpeg
✓ 3 image(s) extraite(s) avec succès
==================================================
✅ Traitement terminé
   - Images trouvées: 3
   - Images enregistrées: 3
   - Erreurs: 0
   - Localisation: C:\...\VD23111 PE 162
==================================================
```

---

## 🔧 Bonnes pratiques implémentées

### 1. **Validation des entrées**
```python
# Vérifier que le fichier existe et est un .docx
if not self.word_path.exists():
    raise FileNotFoundError(...)
```

### 2. **Logging structuré**
```python
logger.info("✓ Fichier validé")
logger.error("✗ Erreur lors de l'extraction")
```

### 3. **Type hints (annotations de types)**
```python
def extract_images(self) -> List[Tuple[bytes, str]]:
    # Le code retourne clairement une liste de tuples
```

### 4. **Documentation (Docstrings)**
```python
def save_image(self, image_bytes: bytes, index: int, extension: str) -> Path:
    """
    Enregistre une image dans le dossier de destination.
    
    Args:
        image_bytes: Données binaires de l'image
        index: Numéro séquentiel de l'image (commence à 1)
        extension: Extension du fichier (jpg, png, etc.)
    
    Returns:
        Path: Chemin du fichier enregistré
    """
```

### 5. **Gestion d'erreurs**
```python
try:
    with zipfile.ZipFile(self.word_path, 'r') as docx_zip:
        # Traitement
except zipfile.BadZipFile:
    raise ValueError(f"Le fichier n'est pas un .docx valide")
except Exception as e:
    logger.error(f"Erreur: {e}")
```

### 6. **Architecture modulaire**
- Chaque classe a une responsabilité unique (Single Responsibility Principle)
- Facile à tester, déboguer et étendre

### 7. **Nommage incrémental automatique**
```python
# Format: bornier_1.jpg, bornier_2.png, etc.
for index, (image_bytes, extension) in enumerate(images, start=1):
    self.storage.save_image(image_bytes, index, extension)
```

---

## 🐛 Dépannage

### ❌ "FileNotFoundError: Le fichier n'existe pas"

**Solution**: Vérifiez le chemin du fichier Word
```python
# ❌ Incorrect (fichier dans un autre dossier)
word_file = "rapport.docx"

# ✅ Correct (chemin complet)
word_file = r"C:\Users\Utilisateur\Documents\rapport.docx"
```

### ❌ "ValueError: Le fichier n'est pas un .docx valide"

**Solution**: Assurez-vous que c'est bien un fichier .docx et non .doc
- Microsoft Word 2007+ (.docx) ✅
- Ancien format Word (.doc) ❌

### ❌ "Aucune image trouvée"

**Possible**: Le document Word ne contient pas d'images

**À vérifier**:
1. Ouvrez le document dans Word
2. Vérifiez qu'il y a bien des images
3. Les images sont directement insérées (pas des liens)

---

## 📈 Extensions possibles

Voici comment vous pourriez améliorer le code:

### 1. **Redimensionner les images**
```python
from PIL import Image

# Dans ImageStorage.save_image()
img = Image.open(BytesIO(image_bytes))
img.thumbnail((1024, 1024))  # Redimensionner
img.save(file_path)
```

### 2. **Créer un rapport avec aperçus**
```python
# Générer un HTML avec les images
html = "<html><body>"
for index, path in enumerate(saved_paths, 1):
    html += f"<h3>Image {index}</h3><img src='{path}' width='200'>"
html += "</body></html>"
```

### 3. **Supporter plusieurs formats**
```python
# Modifier pour .doc, .odt, etc.
if self.word_path.suffix.lower() == '.doc':
    # Utiliser la librairie python-pptx pour PowerPoint, etc.
```

### 4. **Extraction sélective**
```python
# Extraire uniquement les images avec certaines dimensions
if width > 100 and height > 100:
    images.append((image_bytes, extension))
```

---

## 📝 Notes importantes

1. **Sauvegarde**: Les images extraites ne sont pas supprimées du Word
2. **Format**: Les images gardent leur format original (jpg, png, etc.)
3. **Chemin absolu**: Préférez les chemins complets pour éviter les erreurs
4. **Dossiers**: Le dossier de destination est créé automatiquement s'il n'existe pas

---

## 🎓 Concepts clés expliqués

### Tuple (Tuple)
```python
(image_bytes, extension)  # Paire de valeurs
# Avantage: immutable et rapide
```

### Type hints
```python
def extract_images(self) -> List[Tuple[bytes, str]]:
    # Clair: retourne une liste de tuples
    # Format: (bytes, string)
```

### Enumerate avec start=1
```python
for index, item in enumerate(images, start=1):
    # index: 1, 2, 3, ... (pas 0, 1, 2, ...)
    print(f"bornier_{index}")  # bornier_1, bornier_2, ...
```

### Archive ZIP (.docx)
```python
# .docx = Dossier zippé avec cette structure:
# ├── word/
# │   ├── media/          ← Images ici
# │   └── document.xml
# ├── _rels/
# └── [Content_Types].xml
```

---

## 📞 Support

Pour toute question ou amélioration:
1. Consultez les docstrings du code (`Ctrl + K, Ctrl + I` dans VS Code)
2. Vérifiez les logs (messages ✓ et ✗)
3. Utilisez les exemples dans `exemple_utilisation.py`

---

**Bon extraction! 🎉**
#   C o n v e c t i o n _ t a b l e a u  
 #   C o n v e c t i o n _ t a b l e a u  
 # Convection_tableau
#   C o n v e c t i o n _ t a b l e a u  
 # Convection_tableau
