@echo off
chcp 65001 >nul
title Test 3 pages - TriosSeconverter

echo.
echo  TEST CLAUDE VISION - 3 types de tableaux
echo  ==========================================
echo  PAGE 15 : J207A fin, 2 lignes
echo  PAGE 47 : signaux reels AD/B
echo  PAGE 50 : 28 lignes, FIL a 2 sous-cellules
echo.

set /p CLE="Cle API Anthropic (sk-ant-...) : "

echo.
echo Lancement des tests...
echo.

.\env\Scripts\python.exe tester_3_pages.py "%CLE%"

if errorlevel 1 (
    echo.
    echo ERREUR - verifiez votre cle API
    pause
)
