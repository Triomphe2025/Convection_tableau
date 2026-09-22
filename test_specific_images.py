"""
Script de test pour debuguer les images 5, 6, 7, 8, 10.
"""

import logging
from pathlib import Path
from ocr_processor import OCRTableProcessor
from config import Config

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_specific_images():
    """Teste les images 5, 6, 7, 8, 10."""

    # Chemins
    output_folder = Path(Config.get_output_folder())
    images_to_test = [5, 6, 7, 8, 10]

    # Créer le processeur OCR
    try:
        processor = OCRTableProcessor(
            tesseract_path=Config.TESSERACT_PATH,
            language=Config.OCR_LANGUAGE
        )
        print("✓ OCR processor créé avec succès")
    except Exception as e:
        print(f"✗ Erreur lors de la création du processeur OCR: {e}")
        return

    # Tester chaque image
    for img_num in images_to_test:
        image_path = output_folder / f"bornier_{img_num}.jpg"

        if not image_path.exists():
            print(f"\n✗ Image non trouvée: {image_path}")
            continue

        print(f"\n{'='*60}")
        print(f"🧪 Test image {img_num}: {image_path.name}")
        print(f"{'='*60}")

        try:
            # Prétraitement
            print("  1️⃣  Prétraitement...")
            processed = processor.preprocess_image(image_path)
            print(f"     ✓ Image prétraitée: shape={processed.shape}")

            # Extraction du texte
            print("  2️⃣  Extraction OCR...")
            text_data = processor.extract_text_data(processed)
            print(f"     ✓ {len(text_data)} éléments texte trouvés")
            if text_data:
                for i, item in enumerate(text_data[:5]):
                    print(f"        [{i}] '{item['text']}' @ ({item['x']}, {item['y']})")
                if len(text_data) > 5:
                    print(f"        ... et {len(text_data) - 5} autres")

            # Détection de grille
            print("  3️⃣  Détection de grille...")
            grid = processor.detect_table_grid(processed)
            if grid.get('valid'):
                print(f"     ✓ Grille valide: {grid['rows']} lignes x {grid['columns']} colonnes")
                print(f"        Lignes: {grid['row_edges'][:3]}...")
                print(f"        Colonnes: {grid['col_edges'][:3]}...")
                print(f"        Cell boxes: {len(grid.get('cell_boxes', []))} cellules")
            else:
                print("     ✗ Grille non valide")

            # Regroupement par lignes
            print("  4️⃣  Regroupement par lignes...")
            lines = processor.group_by_lines(text_data)
            print(f"     ✓ {len(lines)} lignes regroupées")
            for i, line in enumerate(lines[:3]):
                texts = [item['text'] for item in line]
                print(f"        Ligne {i+1}: {texts}")

            # Détection de structure
            print("  5️⃣  Détection de structure...")
            structure = processor.detect_table_structure(lines)
            print(f"     ✓ Structure: {structure['columns']} colonnes")
            print(f"        En-têtes: {structure['headers'][:4]}")
            print(f"        Positions: {structure['column_positions']}")

            # Construction du tableau
            print("  6️⃣  Construction du tableau...")
            if grid.get('valid'):
                table_data = processor.build_table_data_from_grid(text_data, grid)
            else:
                table_data = processor.build_table_data(lines, structure)
            print(f"     ✓ Tableau construit: {len(table_data)} lignes")
            for i, row in enumerate(table_data[:3]):
                print(f"        Ligne {i+1}: {row}")

            print(f"\n✅ Image {img_num} traitée avec succès!")

        except Exception as e:
            print(f"\n❌ Erreur lors du traitement de l'image {img_num}:")
            print(f"   Type: {type(e).__name__}")
            print(f"   Message: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("\n🚀 Début du test des images spécifiques\n")
    test_specific_images()
    print("\n✅ Test terminé\n")
