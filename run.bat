@echo off
REM Script pour lancer l'extraction d'images sans dépendre du PATH Python
REM Utilise py.exe qui est généralement disponible sur Windows

echo.
echo ========================================
echo  EXTRACTEUR D'IMAGES DEPUIS WORD
echo ========================================
echo.

REM Vérifier que py.exe existe
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Python n'est pas installé ou pas dans le PATH
    echo.
    echo Solutions:
    echo 1. Installer Python depuis https://www.python.org/downloads/
    echo    IMPORTANT: Cochez "Add Python to PATH"
    echo.
    echo 2. Ou installer avec: winget install Python.Python.3.11
    echo.
    pause
    exit /b 1
)

echo Python trouvé!
py --version
echo.

REM Installer les dépendances
echo Installation des dépendances...
py -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERREUR lors de l'installation des dépendances
    pause
    exit /b 1
)

echo.
echo Dépendances installées avec succès!
echo.

REM Lancer le script principal
echo Lancement de l'extraction...
echo.
py run.py

pause
