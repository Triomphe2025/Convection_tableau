# 🔧 Guide: Résoudre l'Erreur "python n'est pas reconnu"

## ❌ Le Problème

```
python : Le terme «python» n'est pas reconnu comme nom d'applet de commande, 
fonction, fichier de script ou programme exécutable.
```

Cela signifie que **Python n'est pas installé** ou **n'est pas dans le PATH** de votre système.

---

## ✅ Solutions (Du Plus Simple au Plus Complexe)

### **Solution 1: Utiliser run.bat (La Plus Simple!)** ⭐

**Pour Windows uniquement**

1. Ouvrez l'explorateur de fichiers
2. Allez dans votre dossier du projet
3. Trouvez le fichier `run.bat`
4. **Double-cliquez dessus**
5. Il va installer Python et faire l'extraction automatiquement!

**C'est tout!** Vous n'avez rien à configurer dans PowerShell.

---

### **Solution 2: Installer Python Correctement** (Recommandé)

#### **Étape 1: Télécharger Python**
1. Allez sur https://www.python.org/downloads/
2. Cliquez sur "Download Python 3.11" (ou version plus récente)
3. Attendez que le fichier se télécharge

#### **Étape 2: Installer avec le PATH**
1. Ouvrez le fichier d'installation (exécutez-le)
2. **🔴 TRÈS IMPORTANT**: Cochez la case:
   ```
   ☑ Add Python to PATH
   ```
3. Cliquez "Install Now"
4. Attendez que l'installation se termine
5. Fermez le programme

#### **Étape 3: Redémarrer votre ordinateur**
Cette étape est **importante** pour que le PATH soit reconnu!

#### **Étape 4: Tester**
Ouvrez PowerShell et testez:
```powershell
python --version
```

Si ça affiche `Python 3.11.x` (ou similaire) → **Succès!** ✅

---

### **Solution 3: Utiliser winget (Si Disponible)**

Si vous avez Windows 10/11:

```powershell
# Installer Python avec winget
winget install Python.Python.3.11

# Tester
python --version
```

**Avantage**: Installation simple et automatique

---

### **Solution 4: Utiliser py.exe** (Fonctionne Souvent)

Windows fournit `py.exe` automatiquement. Essayez:

```powershell
# Tester
py --version

# Si ça marche, utilisez py au lieu de python:
py run.py
py -m pip install -r requirements.txt
```

---

### **Solution 5: Ajouter Python au PATH Manuellement**

Si Python est installé mais non détecté:

#### **Windows Subsystem for Linux (WSL) - Trouver Python:**

1. **Trouvez où est installé Python**:
```powershell
Get-ChildItem -Path "C:\Users\$env:USERNAME\AppData\Local\Programs\Python" -Directory
```

Vous devriez voir quelque chose comme:
```
Python311
Python310
```

2. **Notez le chemin complet**, par exemple:
```
C:\Users\Triomphe Tchounda\AppData\Local\Programs\Python\Python311
```

3. **Ajoutez ce chemin au PATH** (temporaire, dans PowerShell):
```powershell
$env:Path += ";C:\Users\Triomphe Tchounda\AppData\Local\Programs\Python\Python311"
python --version
```

4. **Pour que ce soit permanent**, ouvrez les Variables d'Environnement:
   - Cliquez sur le logo Windows
   - Tapez: "Variables d'environnement"
   - Cliquez sur "Modifier les variables d'environnement du système"
   - Cliquez sur "Variables d'environnement..."
   - Sélectionnez "Path" dans la liste
   - Cliquez "Modifier"
   - Cliquez "Nouveau"
   - Collez votre chemin Python (ex: `C:\Users\Triomphe Tchounda\AppData\Local\Programs\Python\Python311`)
   - Cliquez "OK" trois fois
   - Redémarrez PowerShell

---

## 🎯 Approche Recommandée

### **Pour vous (sur Windows)**:

1. **Essayez d'abord** `run.bat` (le plus simple)
   ```
   Double-cliquez sur run.bat dans votre dossier
   ```

2. **Si ça ne fonctionne pas**, installez Python:
   - Allez sur https://www.python.org/downloads/
   - Téléchargez la version la plus récente
   - **Cochez "Add Python to PATH"** (très important!)
   - Installez
   - Redémarrez votre ordinateur

3. **Testez dans PowerShell**:
   ```powershell
   python --version
   ```

4. **Lancez votre extraction**:
   ```powershell
   python run.py
   ```

---

## 🧪 Vérifier que Python Fonctionne

```powershell
# Tester que Python est accessible
python --version

# Ou utiliser py
py --version

# Tester que pip fonctionne
python -m pip --version
```

Si toutes ces commandes affichent une version → **C'est bon!** ✅

---

## 📋 Vérifier Votre Installation

Exécutez ce script pour tout vérifier:

```powershell
# Depuis le dossier du projet
python startup_checklist.py
```

Ou sans Python (utiliser py):
```powershell
py startup_checklist.py
```

Cela affichera:
- ✅ Si les fichiers existent
- ✅ Si les dépendances sont installées
- ✅ Si votre configuration est correcte

---

## 🆘 Aide Supplémentaire

Si vous avez toujours des problèmes:

1. **Vérifiez votre version de Windows**: 
   ```powershell
   [System.Environment]::OSVersion.VersionString
   ```

2. **Vérifiez que vous avez un compte administrateur**
   - Les installations Python peuvent nécessiter des droits admin

3. **Essayez avec un autre terminal**:
   - Au lieu de PowerShell, essayez CMD:
   ```cmd
   python --version
   ```

4. **Consultez le README.md** pour plus de détails

---

## 📝 Résumé des Commandes

```powershell
# Vérifier si Python est installé
python --version
py --version

# Installer les dépendances
pip install -r requirements.txt
py -m pip install -r requirements.txt

# Lancer l'extraction
python run.py
py run.py

# Vérifier la configuration
python startup_checklist.py
```

---

## ✨ Point Clé

**La plupart des problèmes viennent de l'installation de Python sans cocher "Add Python to PATH".**

Réinstallez Python en vous assurant que cette case est cochée! ☑️

---

**Besoin d'aide?** Consultez **README.md** ou **INDEX.md** dans votre dossier du projet.

Bonne chance! 🚀
