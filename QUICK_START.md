# 🚀 Guide de Démarrage Rapide

## ⚡ En 3 étapes

### ⚠️ **IMPORTANT: D'abord, installez Python!**

Si vous avez l'erreur: `python : Le terme «python» n'est pas reconnu...`

👉 **Solution rapide** (Windows):
1. Allez sur https://www.python.org/downloads/
2. Téléchargez **Python 3.11 ou plus récent**
3. **TRÈS IMPORTANT**: Cochez ✅ "Add Python to PATH" 
4. Installez et redémarrez votre ordinateur

👉 **Alternative** (avec winget):
```powershell
winget install Python.Python.3.11
```

---

### 1️⃣ Installer les dépendances

**Option A: Si Python fonctionne**
```bash
pip install -r requirements.txt
```

**Option B: Utiliser run.bat (Windows)**
Double-cliquez sur `run.bat` - Il fait tout automatiquement!

**Option C: Utiliser run.ps1 (PowerShell)**
```powershell
.\run.ps1
```

### 2️⃣ Configurer le fichier
Ouvrez `config.py` et modifiez:
```python
WORD_FILE = "votre_document.docx"  # Votre fichier Word
IMAGES_FOLDER_NAME = "VD23111 PE 162"  # Nom du dossier
```

### 3️⃣ Lancer l'extraction

**Option A: Ligne de commande**
```bash
python run.py
```

**Option B: Double-clic sur run.bat (Windows)**
Cherchez `run.bat` dans votre dossier et double-cliquez dessus!

**Option C: Avec OCR activé (pour les tableaux)**
1. Ouvrez `config.py`
2. Changez `ENABLE_OCR = True`
3. Lancez `python run.py`

**Résultat**: Les images sont dans le dossier `VD23111 PE 162/` avec les noms `bornier_1.jpg`, `bornier_2.png`, etc.
**Résultat OCR**: Les tableaux sont dans `VD23111 PE 162/ocr_tables/` avec les noms `bornier_1_table.docx`, etc.

---

## 📁 Structure des fichiers

```
📦 Projet
├── 📄 recuperer_image.py       ← Code principal (3 classes)
├── 📄 config.py                 ← Configuration (modifier ici!)
├── 📄 run.py                    ← Point d'entrée (lancer ce fichier)
├── 📄 run.bat                   ← Lancer l'extraction (double-cliquez, Windows)
├── 📄 run.ps1                   ← Lancer l'extraction (PowerShell)
├── 📄 exemple_utilisation.py    ← Exemples d'utilisation
├── 📄 requirements.txt          ← Dépendances Python
├── 📄 README.md                 ← Documentation complète
├── 📄 QUICK_START.md            ← Ce fichier
└── 📄 PYTHON_PATH_ISSUE.md      ← Guide si Python ne fonctionne pas
```

---

## 🎯 Cas d'usage courants

### Cas 1: Extraction simple (par défaut)
```bash
# Modifiez config.py
WORD_FILE = "mon_rapport.docx"

# Exécutez
python run.py
```

### Cas 2: Personnaliser le dossier
```python
# Dans config.py
IMAGES_FOLDER_NAME = "Mes Images Extraites"
```

### Cas 3: Chemin complet (si fichier ailleurs)
```python
# Dans config.py
WORD_FILE = r"C:\Users\Utilisateur\Documents\rapport.docx"
```

### Cas 4: Noms personnalisés
```python
# Dans config.py
IMAGE_NAME_FORMAT = "scan_{index:03d}"  # scan_001, scan_002, etc.
```

### Cas 5: Activer l'OCR pour les tableaux
```python
# Dans config.py
ENABLE_OCR = True
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # Windows
```

---

## 🔍 Exemple de résultat

Avant:
```
Dossier courant/
├── recuperer_image.py
├── config.py
├── mon_rapport.docx
└── ...
```

Après exécution (sans OCR):
```
Dossier courant/
├── VD23111 PE 162/           ← NOUVEAU!
│   ├── bornier_1.jpg
│   ├── bornier_2.png
│   ├── bornier_3.jpeg
│   └── ...
├── recuperer_image.py
├── config.py
├── mon_rapport.docx
└── ...
```

Après exécution (avec OCR activé):
```
Dossier courant/
├── VD23111 PE 162/           ← NOUVEAU!
│   ├── bornier_1.jpg
│   ├── bornier_2.png
│   ├── bornier_3.jpeg
│   └── ocr_tables/           ← NOUVEAU!
│       ├── bornier_1_table.docx
│       ├── bornier_2_table.docx
│       └── ...
├── recuperer_image.py
├── config.py
├── mon_rapport.docx
└── ...
```

---

## ⚠️ Problèmes courants

| Problème | Solution |
|----------|----------|
| **"python : Le terme «python» n'est pas reconnu"** | 👉 Installez Python depuis https://www.python.org/downloads/ en cochant "Add Python to PATH" |
| "Fichier non trouvé" | Vérifiez le chemin dans `config.py` |
| "Aucune image trouvée" | Le document Word ne contient pas d'images |
| "ImportError: No module named 'docx'" | Exécutez `pip install -r requirements.txt` ou double-cliquez `run.bat` |
| Fichier Word ouvert | Fermez le fichier avant d'extraire |
| "Tesseract non trouvé" | Installez Tesseract: https://github.com/UB-Mannheim/tesseract/wiki |
| "OCR: No text found" | L'image ne contient pas de texte lisible ou la qualité est insuffisante |
| "Erreur lors du traitement OCR" | Vérifiez le chemin Tesseract dans `config.py` |

### Astuce: Utiliser run.bat ou run.ps1
Si vous avez des problèmes avec Python:
- **Windows**: Double-cliquez sur `run.bat` (fait tout automatiquement!)
- **PowerShell**: Exécutez `.\run.ps1`

---

## 📚 Fichiers utiles

- **README.md** → Documentation complète et détaillée
- **exemple_utilisation.py** → Code Python à copier
- **recuperer_image.py** → Code source avec docstrings
- **ocr_processor.py** → Module OCR pour traiter les images
- **exemple_ocr.py** → Exemples d'utilisation de l'OCR
- **test_ocr_processor.py** → Tests pour le module OCR

---

## 🆘 Besoin d'aide?

1. Consultez **README.md** pour la documentation complète
2. Vérifiez **exemple_utilisation.py** pour des exemples
3. Modifiez **config.py** pour personnaliser le comportement

---

**C'est tout! 🎉 Vos images sont prêtes à être extraites!**
