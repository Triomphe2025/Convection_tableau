# -*- mode: python ; coding: utf-8 -*-
"""
Fichier de specification PyInstaller pour TriosSeconverter.
Genere un dossier autonome dans dist/TriosSeconverter/
"""

block_cipher = None

a = Analysis(
    ['interface.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Fichiers Python du projet (inclus comme modules)
        ('config.py',           '.'),
        ('converter.py',        '.'),
        ('ocr_processor.py',    '.'),
        ('recuperer_image.py',  '.'),
        ('generer_classeur.py', '.'),
        ('template.py',         '.'),
        # Ressources graphiques
        ('icon.ico',            '.'),
    ],
    hiddenimports=[
        # tkinter et ses sous-modules
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        # Bibliothèques tierces
        'PIL._tkinter_finder',
        'PIL.Image',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.styles.borders',
        'pytesseract',
        'cv2',
        'docx',
        'docx.shared',
        'docx.enum.text',
        'numpy',
        'lxml',
        'lxml.etree',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TriosSeconverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # Pas de fenetre console noire
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
    upx=True,
    upx_exclude=[],
    name='TriosSeconverter',
)
