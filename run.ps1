#!/usr/bin/env pwsh
# Script PowerShell pour lancer l'extraction d'images
# Compatible avec Windows, macOS et Linux

Write-Host ""
Write-Host "========================================"
Write-Host "  EXTRACTEUR D'IMAGES DEPUIS WORD"
Write-Host "========================================"
Write-Host ""

# Vérifier que py ou python existe
$pythonCmd = $null

# Essayer py d'abord (Windows)
try {
    py --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $pythonCmd = "py"
    }
}
catch {}

# Essayer python
if (-not $pythonCmd) {
    try {
        python --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $pythonCmd = "python"
        }
    }
    catch {}
}

# Si rien ne fonctionne, afficher une erreur
if (-not $pythonCmd) {
    Write-Host "❌ ERREUR: Python n'est pas installé ou pas dans le PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Solutions:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Installer Python depuis https://www.python.org/downloads/"
    Write-Host "   ⚠️  IMPORTANT: Cochez 'Add Python to PATH'"
    Write-Host ""
    Write-Host "2. Ou utiliser winget:"
    Write-Host "   winget install Python.Python.3.11"
    Write-Host ""
    Read-Host "Appuyez sur Entrée pour quitter"
    exit 1
}

Write-Host "✅ Python trouvé!" -ForegroundColor Green
& $pythonCmd --version
Write-Host ""

# Installer les dépendances
Write-Host "📦 Installation des dépendances..." -ForegroundColor Cyan
& $pythonCmd -m pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ ERREUR lors de l'installation des dépendances" -ForegroundColor Red
    Read-Host "Appuyez sur Entrée pour quitter"
    exit 1
}

Write-Host ""
Write-Host "✅ Dépendances installées avec succès!" -ForegroundColor Green
Write-Host ""

# Lancer le script principal
Write-Host "🚀 Lancement de l'extraction..." -ForegroundColor Cyan
Write-Host ""
& $pythonCmd run.py

Write-Host ""
Read-Host "Appuyez sur Entrée pour quitter"
