# 📐 Architecture et Flux du Projet

## 🏗️ Hiérarchie des Modules

```
recuperer_image.py (Module Principal)
│
├── 📦 Imports externes
│   ├── zipfile     (pour accéder aux images dans le .docx)
│   ├── logging     (pour les messages)
│   └── pathlib     (pour manipuler les chemins)
│
├── ⚙️ Configuration du logging
│   └── logger
│
├── 🔵 Classe: ImageExtractor
│   │   Responsabilité: Extraire les images du Word
│   │
│   ├── __init__(word_path)
│   │   └── Valide le fichier
│   │
│   ├── _validate_file()
│   │   ├── Vérifie l'existence du fichier
│   │   └── Vérifie l'extension .docx
│   │
│   └── extract_images()
│       ├── Ouvre le .docx comme ZIP
│       ├── Parcourt word/media/
│       ├── Extrait chaque image
│       └── Retourne liste[(bytes, extension)]
│
├── 🟢 Classe: ImageStorage
│   │   Responsabilité: Stocker les images extraites
│   │
│   ├── __init__(folder_name)
│   │   └── Initialise le nom du dossier
│   │
│   ├── create_output_folder(base_path)
│   │   ├── Crée le dossier destination
│   │   └── Retourne Path
│   │
│   └── save_image(image_bytes, index, extension)
│       ├── Crée le nom: bornier_{index}.{extension}
│       ├── Enregistre le fichier
│       └── Retourne Path
│
├── 🟡 Classe: ImageExtractionPipeline
│   │   Responsabilité: Orchestrer le processus
│   │
│   ├── __init__(word_path, output_folder)
│   │   ├── Crée ImageExtractor
│   │   └── Crée ImageStorage
│   │
│   └── run()
│       ├── Crée le dossier
│       ├── Extrait les images
│       ├── Sauvegarde chaque image
│       ├── Compte les succès/erreurs
│       └── Retourne dict avec résultats
│
└── 🚀 Fonction: main()
    ├── Configure le chemin du fichier
    ├── Crée ImageExtractionPipeline
    └── Lance pipeline.run()
```

---

## 🔄 Flux d'Exécution

```
START
  │
  ├─→ Charger config.py
  │   └─→ WORD_FILE = "mon_document.docx"
  │
  ├─→ Exécuter run.py
  │   │
  │   ├─→ Afficher config
  │   │
  │   ├─→ Créer ImageExtractionPipeline
  │   │   │
  │   │   ├─→ Créer ImageExtractor(word_path)
  │   │   │   ├─→ Valider le fichier
  │   │   │   └─→ ✓ Fichier OK
  │   │   │
  │   │   └─→ Créer ImageStorage("VD23111 PE 162")
  │   │
  │   ├─→ Exécuter pipeline.run()
  │   │   │
  │   │   ├─→ Créer dossier VD23111 PE 162/
  │   │   │   └─→ ✓ Dossier créé
  │   │   │
  │   │   ├─→ Extraire les images
  │   │   │   ├─→ Ouvrir mon_document.docx comme ZIP
  │   │   │   ├─→ Chercher word/media/*
  │   │   │   └─→ ✓ 3 images trouvées
  │   │   │
  │   │   ├─→ Enregistrer les images
  │   │   │   ├─→ Image 1 → bornier_1.jpg  ✓
  │   │   │   ├─→ Image 2 → bornier_2.png  ✓
  │   │   │   └─→ Image 3 → bornier_3.jpeg ✓
  │   │   │
  │   │   └─→ Afficher résumé
  │   │       ├─→ Images trouvées: 3
  │   │       ├─→ Images enregistrées: 3
  │   │       ├─→ Erreurs: 0
  │   │       └─→ Chemin: C:\...\VD23111 PE 162
  │   │
  │   └─→ Afficher résultats
  │
  └─→ END (exit code 0 = succès)
```

---

## 🔍 Détail: Extraction d'une Image

```
Document Word (.docx)
  │
  ├─→ [C'est un ZIP!]
  │   ├─ [Content_Types].xml
  │   ├─ word/
  │   │  ├─ document.xml (relations aux images)
  │   │  └─ media/
  │   │     ├─ image1.jpg  ← IMAGE 1
  │   │     ├─ image2.png  ← IMAGE 2
  │   │     └─ image3.jpeg ← IMAGE 3
  │   └─ _rels/
  │       └─ document.xml.rels
  │
  └─→ ImageExtractor.extract_images()
      │
      ├─→ zipfile.ZipFile(docx_path, 'r')
      │   └─→ Ouvre le ZIP
      │
      ├─→ docx_zip.namelist()
      │   └─→ ['word/media/image1.jpg', 'word/media/image2.png', ...]
      │
      ├─→ Pour chaque fichier dans word/media/:
      │   │
      │   ├─→ Lire le fichier → bytes
      │   ├─→ Extraire extension → "jpg"
      │   └─→ Ajouter à liste: (bytes, "jpg")
      │
      └─→ Retourner liste complète
          └─→ [(b'...jpg...', 'jpg'), (b'...png...', 'png'), ...]
```

---

## 💾 Détail: Enregistrement d'une Image

```
ImageStorage.save_image(image_bytes, index=1, extension='jpg')
  │
  ├─→ Créer nom de fichier
  │   ├─→ format: f"bornier_{index}.{extension}"
  │   └─→ nom final: "bornier_1.jpg"
  │
  ├─→ Construire chemin complet
  │   ├─→ output_folder: C:\...\VD23111 PE 162
  │   ├─→ filename: bornier_1.jpg
  │   └─→ file_path: C:\...\VD23111 PE 162\bornier_1.jpg
  │
  ├─→ Ouvrir fichier en mode binaire ('wb')
  │
  ├─→ Écrire les bytes
  │   └─→ f.write(image_bytes)
  │
  ├─→ Fermer le fichier
  │
  └─→ Retourner Path
      └─→ ✓ C:\...\VD23111 PE 162\bornier_1.jpg
```

---

## 📊 Relation entre les Classes

```
┌─────────────────────────────────────────────────┐
│       ImageExtractionPipeline                   │
│                                                 │
│  Orchester le processus complet                │
└────────┬──────────────────────────┬─────────────┘
         │                          │
         │ crée                     │ crée
         ▼                          ▼
    ┌─────────────┐          ┌──────────────┐
    │ ImageEx-    │          │ ImageStorage │
    │ tractor     │          │              │
    │             │          │              │
    │ Extrait les │          │ Enregistre   │
    │ images du   │          │ les images   │
    │ Word        │          │              │
    └─────────────┘          └──────────────┘
         │                          │
         │ retourne                 │ écrit
         │ (bytes, ext)             │ fichiers
         ▼                          ▼
    Images en mémoire         Dossier VD23111 PE 162/
    ├─ (b'...', 'jpg')       ├─ bornier_1.jpg
    ├─ (b'...', 'png')       ├─ bornier_2.png
    └─ (b'...', 'jpeg')      └─ bornier_3.jpeg
```

---

## 🔐 Gestion des Erreurs

```
Processus d'extraction
  │
  ├─→ Fichier n'existe pas
  │   └─→ FileNotFoundError
  │       └─→ catch & afficher message
  │
  ├─→ Fichier n'est pas .docx
  │   └─→ ValueError
  │       └─→ catch & afficher message
  │
  ├─→ Fichier .docx invalide (pas un ZIP)
  │   └─→ BadZipFile
  │       └─→ catch & afficher message
  │
  ├─→ Erreur lors de la création du dossier
  │   └─→ OSError / PermissionError
  │       └─→ catch & afficher message
  │
  └─→ Erreur lors de l'enregistrement d'une image
      └─→ IOError
          ├─→ Enregistrer l'erreur
          ├─→ Continuer avec les autres images
          └─→ Afficher le nombre d'erreurs
```

---

## 🎯 Points Clés de l'Architecture

1. **Séparation des responsabilités**
   - ImageExtractor = extraction
   - ImageStorage = stockage
   - Pipeline = orchestration

2. **Robustesse**
   - Validation des fichiers
   - Gestion des erreurs
   - Logs détaillés

3. **Extensibilité**
   - Facile d'ajouter des fonctionnalités
   - Facile de modifier le nommage
   - Facile de changer le dossier destination

4. **Testabilité**
   - Classes indépendantes
   - Méthodes pures (pas d'état global)
   - Faciles à tester unitairement

---

## 🧩 Exemple: Modifier le Format de Nommage

**Objectif**: Changer `bornier_1.jpg` en `scan_001.jpg`

```python
# Dans config.py
IMAGE_NAME_FORMAT = "scan_{index:03d}"

# Dans recuperer_image.py, ImageStorage.save_image()
# De: filename = f"bornier_{index}.{extension}"
# À:  filename = f"{Config.IMAGE_NAME_FORMAT.format(index=index)}.{extension}"
```

---

## 🧩 Exemple: Ajouter du Redimensionnement

```python
# Dans recuperer_image.py, ImageStorage.save_image()
from PIL import Image

img = Image.open(BytesIO(image_bytes))
img.thumbnail((1024, 1024))  # Redimensionner
img.save(file_path, quality=85)
```

---

**L'architecture est conçue pour être claire, maintenable et extensible!** ✨
