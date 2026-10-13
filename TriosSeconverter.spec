# -*- mode: python ; coding: utf-8 -*-
"""
Fichier de specification PyInstaller pour TriosSeconverter (v1.8).
Genere un dossier autonome dans dist/TriosSeconverter/.

Le lexique compile (lexique_compile.json) est produit par build_exe.bat avant ce build.
Exclus : Docling (torch, transformers : plusieurs Go ; message clair si ce mode est choisi),
scipy (cad/curve_fitter a une solution de repli), outils de developpement.
"""
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Modules du projet charges depuis l'interface, y compris ceux importes dans une fonction
# (liste calculee en suivant les imports depuis interface.py).
MODULES_PROJET = [
    'agent_ocr', 'audit_claude', 'cache_lectures', 'claude_ocr', 'compte_lignes', 'config',
    'controle_conservation', 'controle_qualite', 'converter', 'data_dictionary',
    'docling_ocr', 'generer_classeur', 'hybrid_ocr', 'lexique_reference', 'ocr_processor',
    'ollama_ocr', 'pdf_extractor', 'pied_page', 'positions_scan', 'recuperer_image',
    'relecture_scan', 'template', 'verificateur', 'word_table_importer',
    'cad', 'cad.block_builder', 'cad.curve_fitter', 'cad.dxf_writer', 'cad.models',
    'cad.raster_tif_extractor', 'cad.segment_merger', 'cad.service', 'cad.source_detector',
    'cad.vector_pdf_extractor', 'cad.vectorizer',
]

a = Analysis(
    ['interface.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Fichiers livres, lus en lecture seule (config.chemin_ressource)
        ('icon.ico',              '.'),
        ('templates.json',        '.'),
        ('data_dictionary.json',  '.'),
        ('lexique_compile.json',  '.'),
    ],
    hiddenimports=[
        # tkinter et ses sous-modules
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        # Bibliotheques tierces
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
        'fitz',
        'ezdxf',
        'shapely',
        'skimage',
        'sknw',
        'networkx',
    ] + MODULES_PROJET + collect_submodules('anthropic'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        'docling',
        'torch',
        'torchvision',
        'transformers',
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
