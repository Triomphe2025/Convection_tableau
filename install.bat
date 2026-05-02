@echo off
setlocal EnableDelayedExpansion

echo.
echo ====================================================
echo   TriosSeconverter  -  Installation
echo ====================================================
echo.

:: ── Verifier Python ──────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou n'est pas dans le PATH.
    echo.
    echo  Telechargez Python sur https://www.python.org/downloads/
    echo  Lors de l'installation, cochez "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] %PY_VER% detecte.
echo.

:: ── Creer l'environnement virtuel ────────────────────────────────────
echo [1/5] Creation de l'environnement virtuel...
if exist venv (
    echo        Environnement existant detecte - reutilisation.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [ERREUR] Impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
)
echo [OK] Environnement virtuel pret.
echo.

:: ── Activer et mettre a jour pip ─────────────────────────────────────
call venv\Scripts\activate.bat

echo [2/5] Mise a jour de pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip mis a jour.
echo.

:: ── Installer les dependances ─────────────────────────────────────────
echo [3/5] Installation des dependances (peut prendre quelques minutes)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERREUR] Installation des dependances echouee.
    echo          Verifiez votre connexion Internet et relancez install.bat.
    pause
    exit /b 1
)
echo [OK] Dependances installees.
echo.

:: ── Creer le script de lancement ─────────────────────────────────────
echo [4/5] Creation du lanceur TriosSeconverter.bat...
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo call venv\Scripts\activate.bat
    echo python interface.py
) > TriosSeconverter.bat
echo [OK] Lanceur cree : TriosSeconverter.bat
echo.

:: ── Raccourci bureau ──────────────────────────────────────────────────
echo [5/5] Creation du raccourci bureau...
set "SCRIPT_DIR=%~dp0"
set "SHORTCUT=%USERPROFILE%\Desktop\TriosSeconverter.lnk"

powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s  = $ws.CreateShortcut('%SHORTCUT%');" ^
    "$s.TargetPath      = '%SCRIPT_DIR%TriosSeconverter.bat';" ^
    "$s.WorkingDirectory = '%SCRIPT_DIR%';" ^
    "$s.IconLocation    = '%SCRIPT_DIR%icon.ico';" ^
    "$s.Description     = 'TriosSeconverter - Conversion de borniers electriques';" ^
    "$s.Save()" >nul 2>&1

if exist "%SHORTCUT%" (
    echo [OK] Raccourci bureau cree.
) else (
    echo [INFO] Raccourci non cree - utilisez directement TriosSeconverter.bat.
)
echo.

:: ── Verifier Tesseract ────────────────────────────────────────────────
echo ── Verification de Tesseract OCR ──────────────────────────────────
if exist "C:\Tesseract\TesseractOCR\tesseract.exe" (
    echo [OK] Tesseract detecte dans C:\Tesseract\TesseractOCR\
) else (
    echo [AVERTISSEMENT] Tesseract OCR non trouve dans C:\Tesseract\TesseractOCR\
    echo.
    echo  Pour que l'OCR fonctionne, installez Tesseract :
    echo    1. Telechargez l'installateur depuis :
    echo       https://github.com/UB-Mannheim/tesseract/wiki
    echo    2. Lors de l'installation, ajoutez le support du francais (fra).
    echo    3. Mettez a jour le chemin dans config.py si necessaire.
    echo       TESSERACT_PATH = r"C:\chemin\vers\tesseract.exe"
)
echo.

echo ====================================================
echo   Installation terminee !
echo.
echo   Pour lancer TriosSeconverter :
echo     - Double-cliquez sur le raccourci du bureau, ou
echo     - Double-cliquez sur TriosSeconverter.bat
echo ====================================================
echo.
pause
