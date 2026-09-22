#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from ocr_processor import OCRTableProcessor
from config import Config
import logging

logging.basicConfig(level=logging.DEBUG)


def quick_test():
    """Test rapide avec une image."""

    output_folder = Path(Config.get_output_folder())
    image_path = output_folder / "bornier_5.jpg"

    if not image_path.exists():
        print(f"ERREUR: Image non trouvée: {image_path}")
        return

    print(f"\nTest rapide avec: {image_path.name}")
    print("="*70)

    try:
        processor = OCRTableProcessor(
            tesseract_path=Config.TESSERACT_PATH,
            language=Config.OCR_LANGUAGE
        )
        print("✓ Processeur OCR créé")

        output_word = output_folder / "ocr_tables" / "test_bornier_5.docx"
        output_word.parent.mkdir(parents=True, exist_ok=True)

        result = processor.process_image_to_table(image_path, output_word, save_excel=False)

        print("\nRésultat:")
        for key, value in result.items():
            print(f"  {key}: {value}")

        if result.get('success'):
            print("\n✅ Succès!")
            print(f"   Fichier créé: {output_word.exists()}")
        else:
            print(f"\n✗ Échec: {result.get('error')}")

    except Exception as e:
        print(f"✗ Erreur: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_test()
