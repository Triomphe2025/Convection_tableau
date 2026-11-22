# -*- mode: python ; coding: utf-8 -*-
"""Spécification PyInstaller de la NOUVELLE interface Qt (aperçu, phase 2).

SÉPARÉE de TriosSeconverter.spec : l'exe actuel (Tkinter) de l'équipe ne change pas.
Mode DOSSIER (onedir), jamais fichier unique : PySide6 est sous LGPL — l'utilisateur doit
pouvoir remplacer les bibliothèques Qt, ce qu'un onefile empêche. Le texte de la LGPL et les
licences des polices (OFL) et des icônes (ISC) sont joints dans licences\\.

Build : env\\Scripts\\python.exe -m PyInstaller TriosSeconverter_Qt.spec --noconfirm --clean
Aucune obfuscation dans la chaîne actuelle (PyInstaller simple + textes_proteges + licence) :
rien à contourner pour ce build.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

_RACINE = Path(SPECPATH)


def _datas_du_dossier(dossier: str, motif: str = "*"):
    # Chaque fichier conserve son chemin relatif : theme.py / icones.py les cherchent sous
    # _MEIPASS/<dossier> (polices, icônes), et theme.chemin_jetons sous docs/maquettes.
    return [(str(p), dossier) for p in (_RACINE / dossier).glob(motif) if p.is_file()]


DATAS = (
    _datas_du_dossier("trios_qt/polices", "*.ttf")
    + _datas_du_dossier("trios_qt/icones", "*.svg")
    + _datas_du_dossier("licences", "*.txt")
    + [
        ("docs/maquettes/jetons.json", "docs/maquettes"),
        ("icon.ico", "."),
        # Modèles livrés : le registre les lit via chemin_ressource (_MEIPASS). Sans ce fichier,
        # l'exe n'affiche que les modèles codés (REPARTITEUR / REPARTITEUR 2 manquaient).
        ("templates.json", "."),
    ]
)

a = Analysis(
    ['run_qt.py'],
    pathex=['.'],
    binaries=[],
    datas=DATAS,
    hiddenimports=[
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg',
        'fiabiliser_tesseract',   # importé paresseusement par config.appliquer_env_ocr
    ] + collect_submodules('trios_qt'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # L'aperçu Qt n'embarque pas l'ancienne interface ni les moteurs lourds.
        'tkinter', 'matplotlib', 'IPython', 'jupyter', 'notebook',
        'docling', 'torch', 'torchvision', 'transformers',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir : les binaires vont dans COLLECT, pas dans l'exe
    name='TriosSeconverter_Qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX peut casser les DLL Qt ; on ne compresse pas
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TriosSeconverter_Qt',
)
