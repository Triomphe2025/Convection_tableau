#!/usr/bin/env python3
"""
Point d'entrée principal.

Étapes exécutées :
  1. Extraction des images depuis le fichier Word source
  2. OCR sur chaque image avec BornierTableExtractor
  3. Génération de tous_les_borniers.xlsx  (tous les tableaux, feuille unique)
  4. Génération de tous_les_borniers.docx  (tous les tableaux, document unique)

Exécution :
    py run.py
"""

import sys
import logging
from pathlib import Path

from config import Config
from recuperer_image import ImageExtractionPipeline
from generer_classeur import extraire_tous, generer_excel, generer_word


def setup_logging(log_level: str) -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(levelname)s: %(message)s'
    )


def get_word_file_path() -> Path:
    """Résout le chemin du fichier Word source."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        user_input = sys.argv[1].strip().strip('"').strip("'")
    else:
        user_input = str(Config.get_word_file_path())

    word_file = Path(user_input)
    if not word_file.is_absolute():
        word_file = Path.cwd() / word_file

    if word_file.exists():
        return word_file

    if word_file.suffix.lower() != '.docx':
        alt = word_file.with_suffix('.docx')
        if alt.exists():
            return alt

    # Demander à l'utilisateur si le fichier n'est pas trouvé
    while True:
        user_input = input(
            "Chemin du document Word (.docx) : "
        ).strip().strip('"').strip("'")
        if not user_input:
            print("  Veuillez indiquer un chemin valide.")
            continue
        word_file = Path(user_input)
        if not word_file.is_absolute():
            word_file = Path.cwd() / word_file
        if word_file.exists():
            return word_file
        print(f"  Fichier introuvable : {word_file}")


def main() -> int:
    sep = '=' * 62

    # ── Étape 1 : extraction des images depuis le Word ────────────────
    print(f'\n{sep}')
    print('  ÉTAPE 1 — EXTRACTION DES IMAGES DEPUIS LE WORD')
    print(sep)

    try:
        word_file = get_word_file_path()
        Config.validate()
    except Exception as e:
        print(f'  Erreur de configuration : {e}')
        return 1

    if not word_file.exists():
        print(f'  Fichier Word introuvable : {word_file}')
        return 1

    print(f'  Fichier : {word_file.name}')
    print(f'  Dossier de sortie : {Config.IMAGES_FOLDER_NAME}\n')

    try:
        # Le pipeline extrait uniquement les images (pas d'OCR ici,
        # l'OCR est géré par generer_classeur avec BornierTableExtractor)
        pipeline = ImageExtractionPipeline(
            word_path=str(word_file),
            output_folder=Config.IMAGES_FOLDER_NAME,
            enable_ocr=False,
            tesseract_path=Config.TESSERACT_PATH,
            export_excel=False
        )
        results = pipeline.run()
    except Exception as e:
        print(f'  Erreur lors de l\'extraction : {e}')
        return 1

    print(f'\n  Images extraites : {results["saved"]} / {results["total"]}')
    if results['errors']:
        print(f'  Erreurs          : {results["errors"]}')

    if results['saved'] == 0:
        print('  Aucune image extraite — arrêt.')
        return 1

    # ── Étapes 2-4 : OCR + génération des classeurs ──────────────────
    images_dir = Config.get_output_folder()
    out_dir = Path.cwd()

    print(f'\n{sep}')
    print('  ÉTAPE 2 — OCR SUR CHAQUE IMAGE')
    print(sep)

    try:
        ocr_results, extractor = extraire_tous(images_dir)
    except Exception as e:
        print(f'  Erreur OCR : {e}')
        return 1

    if not ocr_results:
        print('  Aucun résultat OCR — arrêt.')
        return 1

    print(f'\n{sep}')
    print('  ÉTAPE 3 — GÉNÉRATION DU CLASSEUR EXCEL')
    print(sep)

    try:
        generer_excel(
            ocr_results, extractor,
            out_dir / 'tous_les_borniers.xlsx'
        )
    except Exception as e:
        print(f'  Erreur Excel : {e}')

    print(f'\n{sep}')
    print('  ÉTAPE 4 — GÉNÉRATION DU DOCUMENT WORD')
    print(sep)

    try:
        generer_word(
            ocr_results, extractor,
            out_dir / 'tous_les_borniers.docx'
        )
    except Exception as e:
        print(f'  Erreur Word : {e}')

    # ── Résumé final ──────────────────────────────────────────────────
    ok = sum(1 for r in ocr_results if r.get('success'))
    print(f'\n{sep}')
    print('  TERMINÉ')
    print(sep)
    print(f'  Images extraites   : {results["saved"]}')
    print(f'  Tableaux lus       : {ok} / {len(ocr_results)}')
    print()
    print('  Fichiers créés :')
    print('    → tous_les_borniers.xlsx')
    print('    → tous_les_borniers.docx')
    print(sep)
    return 0


if __name__ == '__main__':
    setup_logging(Config.LOG_LEVEL)
    sys.exit(main())
