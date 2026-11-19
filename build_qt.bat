@echo off
setlocal

echo.
echo ====================================================
echo   TriosSeconverter Qt (apercu)  -  Build executable
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

:: PyInstaller + PySide6 doivent etre installes (requirements.txt + requirements-qt.txt)
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] PyInstaller absent de env\ : relancez install.bat.
    pause
    exit /b 1
)
python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] PySide6 absent : env\Scripts\python.exe -m pip install -r requirements-qt.txt
    pause
    exit /b 1
)
echo.

:: Construire l'apercu Qt (mode dossier). outils_build.py preserve licence.triosse (deja a
:: cote de l'exe, jamais lue ni copiee ailleurs), rebuild, la remet, puis supprime
:: build\TriosSeconverter_Qt. L'exe actuel (TriosSeconverter.spec) n'est pas touche.
echo [1/1] Construction de l'apercu Qt (peut prendre plusieurs minutes)...
python outils_build.py TriosSeconverter_Qt.spec TriosSeconverter_Qt
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
echo   Executable : dist\TriosSeconverter_Qt\TriosSeconverter_Qt.exe
echo.
echo   Pour distribuer, copiez l'integralite du dossier
echo   dist\TriosSeconverter_Qt\ sur la machine cible.
echo   Placez licence.triosse a cote de l'exe (meme poste).
echo ====================================================
echo.
pause
