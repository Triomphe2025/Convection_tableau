@echo off
chcp 65001 >nul
title Test Claude Vision — TriosSeconverter

echo ============================================================
echo   TEST CLAUDE VISION — verification du prompt corrige
echo ============================================================
echo.
echo Image testee : exemple traitement\repartiteur 2\page_J207A_ORIGINAL_p019_300dpi.png
echo Template     : REPARTITEUR 2  (FIL / TENANT / SIGNAL / ABOUTISSANT)
echo.

set /p CLE_API="Entrez votre cle API Anthropic (sk-ant-...) : "

if "%CLE_API%"=="" (
    echo ERREUR : aucune cle saisie.
    pause
    exit /b 1
)

echo.
echo Envoi a l'API Claude Vision...
echo ------------------------------------------------------------

.\env\Scripts\python.exe test_vision.py "exemple traitement\repartiteur 2\page_J207A_ORIGINAL_p019_300dpi.png" "REPARTITEUR 2" %CLE_API%

echo.
echo ============================================================
echo   Pour tester la page suivante, remplacez p019 par p020 :
echo   page_J207A_p020_300dpi.png
echo ============================================================
echo.
pause
