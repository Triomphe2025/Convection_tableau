@echo off
setlocal

echo.
echo ====================================================
echo   TriosSeconverter  -  Build executable
echo ====================================================
echo.

:: Activer l'environnement virtuel si present
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
    echo [OK] Environnement virtuel active.
) else (
    echo [INFO] Pas d'environnement virtuel - utilisation du Python systeme.
)
echo.

:: Installer PyInstaller
echo [1/3] Installation de PyInstaller...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo [ERREUR] Impossible d'installer PyInstaller.
    pause
    exit /b 1
)
echo [OK] PyInstaller pret.
echo.

:: Nettoyer les anciens builds
echo [2/3] Nettoyage des anciens builds...
if exist dist\TriosSeconverter rmdir /s /q dist\TriosSeconverter
if exist build               rmdir /s /q build
echo [OK] Nettoyage effectue.
echo.

:: Construire l'executable
echo [3/3] Construction de l'executable (peut prendre 2-5 minutes)...
pyinstaller TriosSeconverter.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERREUR] Build echoue. Verifiez les messages d'erreur ci-dessus.
    pause
    exit /b 1
)

echo.
echo ====================================================
echo   Build termine !
echo.
echo   Executable : dist\TriosSeconverter\TriosSeconverter.exe
echo.
echo   Pour distribuer le logiciel, copiez l'intégralité
echo   du dossier dist\TriosSeconverter\ sur la machine cible.
echo   Tesseract doit etre installe separement.
echo ====================================================
echo.
pause
