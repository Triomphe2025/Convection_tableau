"""
Test du nouvel extracteur BornierTableExtractor.
Lance ce script pour vérifier que les tableaux sont bien remplis.
"""
from pathlib import Path
from ocr_processor import BornierTableExtractor
from config import Config
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(levelname)s: %(message)s')


def tester_image(image_name: str):
    img_path = Path(Config.get_output_folder()) / image_name
    if not img_path.exists():
        print(f"Image non trouvée: {img_path}")
        return

    print(f"\n{'='*60}")
    print(f"Test: {image_name}")
    print('='*60)

    extractor = BornierTableExtractor(
        tesseract_path=Config.TESSERACT_PATH,
        language=Config.OCR_LANGUAGE
    )

    result = extractor.extract(img_path)

    if not result['success']:
        print(f"ECHEC: {result.get('error')}")
        return

    print(f"Colonnes: {result['headers']}")
    print(f"Métadonnées: {result['metadata']}")
    print(f"Nombre de lignes: {len(result['rows'])}")
    print()

    # Afficher les 10 premières lignes
    for i, row in enumerate(result['rows'][:15]):
        if row['type'] == 'section':
            print(f"  --- {row['text']} ---")
        else:
            cells = row['cells']
            print(f"  {' | '.join(f'{c:<20}' for c in cells)}")

    # Sauvegarder les fichiers de sortie
    out_dir = Path(Config.get_output_folder()) / "test_nouveau_ocr"
    stem = img_path.stem

    extractor.to_excel(result, out_dir / f"{stem}_NEW.xlsx")
    extractor.to_word(result, out_dir / f"{stem}_NEW.docx")
    print(f"\nFichiers sauvegardés dans: {out_dir}")


if __name__ == "__main__":
    # Tester sur différents types de borniers
    tester_image("bornier_1.jpg")   # Avec NOM DU CABLE + COULEUR remplie
    tester_image("bornier_10.jpg")  # Sans COULEUR, BORNE alphanumérique
