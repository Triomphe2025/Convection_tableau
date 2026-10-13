@echo off
setlocal

echo.
echo ====================================================
echo   TriosSeconverter  -  Build executable
echo ====================================================
echo.

:: Environnement du projet (env\, cree par install.bat)
if exist env\Scripts\activate.bat (
    call env\Scripts\activate.bat
    echo [OK] Environnement env\ active.
) else (
    echo [ERREUR] Environnement env\ absent : lancez d'abord install.bat.
    pause
    exit /b 1
)
echo.

:: PyInstaller doit etre installe dans env\ (requirements.txt) : rien n'est installe ici.
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] PyInstaller absent de env\ : relancez install.bat.
    pause
    exit /b 1
)

:: Lexique compile (formes des Excel corriges), embarque dans l'exe
echo [1/3] Compilation du lexique de reference...
python lexique_reference.py --compiler
if errorlevel 1 (
    echo [ERREUR] Lexique non compile : references\excels_valides\ vide ou absent.
    pause
    exit /b 1
)
echo.

:: Nettoyer les anciens builds
echo [2/3] Nettoyage des anciens builds...
if exist dist\TriosSeconverter rmdir /s /q dist\TriosSeconverter
if exist build               rmdir /s /q build
echo [OK] Nettoyage effectue.
echo.

:: Construire l'executable
echo [3/3] Construction de l'executable (peut prendre plusieurs minutes)...
python -m PyInstaller TriosSeconverter.spec --noconfirm --clean
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
echo   Pour distribuer le logiciel, copiez l'integralite
echo   du dossier dist\TriosSeconverter\ sur la machine cible.
echo   Tesseract doit etre installe separement.
echo ====================================================
echo.
pause
