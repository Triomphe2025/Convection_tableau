"""
Exemple d'utilisation du traitement OCR pour les images extraites.

Ce script montre comment utiliser les fonctionnalités OCR pour traiter
les images extraites et créer des tableaux Word automatiquement.
"""

from pathlib import Path
from ocr_processor import OCRTableProcessor, BatchOCRProcessor


def exemple_ocr_simple():
    """
    Exemple simple : traiter une seule image.
    """
    print("🔍 Exemple OCR simple")
    print("=" * 40)

    # Chemin vers une image extraite
    image_path = Path("VD23111 PE 162/bornier_1.jpg")  # Adapter le chemin

    # Chemin de sortie pour le document Word
    output_path = Path("tableau_bornier_1.docx")

    # ⚠️ Adapter le chemin Tesseract si nécessaire (Windows)
    # tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    tesseract_path = None  # None = auto-détection

    try:
        # Créer le processeur OCR
        processor = OCRTableProcessor(tesseract_path=tesseract_path, language="fra")

        # Traiter l'image
        result = processor.process_image_to_table(image_path, output_path)

        if result['success']:
            print("✅ Succès !")
            print(f"   📊 Éléments texte trouvés: {result['text_elements']}")
            print(f"   📋 Lignes détectées: {result['lines']}")
            print(f"   📄 Lignes de tableau: {result['table_rows']}")
            print(f"   📊 Colonnes: {result['columns']}")
            print(f"   💾 Document créé: {result['output_path']}")
        else:
            print(f"❌ Échec: {result['error']}")

    except FileNotFoundError:
        print(f"❌ Image non trouvée: {image_path}")
        print("   Assurez-vous d'avoir extrait les images d'abord avec run.py")
    except Exception as e:
        print(f"❌ Erreur: {e}")


def exemple_ocr_batch():
    """
    Exemple batch : traiter toutes les images d'un dossier.
    """
    print("\n📁 Exemple OCR batch")
    print("=" * 40)

    # Dossier contenant les images extraites
    input_folder = Path("VD23111 PE 162")

    # Dossier pour les documents Word générés
    output_folder = Path("tableaux_ocr")

    # ⚠️ Adapter le chemin Tesseract si nécessaire
    tesseract_path = None

    try:
        # Créer le processeur batch
        batch_processor = BatchOCRProcessor(tesseract_path=tesseract_path, language="fra")

        # Traiter toutes les images du dossier
        results = batch_processor.process_folder(
            input_folder=input_folder,
            output_folder=output_folder,
            image_extensions=['.jpg', '.jpeg', '.png']
        )

        print(f"📊 Traitement terminé: {len(results)} images traitées")

        # Afficher les résultats détaillés
        success_count = 0
        for i, result in enumerate(results, 1):
            if result['success']:
                success_count += 1
                print(f"✅ Image {i}: {result['image_path']} → {result['output_path']}")
                print(f"   📋 Tableau: {result['table_rows']} lignes × {result['columns']} colonnes")
            else:
                print(f"❌ Image {i}: {result['image_path']} - Échec: {result['error']}")

        print(f"\n📈 Résumé: {success_count}/{len(results)} documents créés avec succès")

    except Exception as e:
        print(f"❌ Erreur: {e}")


def exemple_configuration_avancee():
    """
    Exemple avec configuration avancée.
    """
    print("\n⚙️ Exemple configuration avancée")
    print("=" * 40)

    # Configuration personnalisée
    config = {
        'tesseract_path': r"C:\Program Files\Tesseract-OCR\tesseract.exe",  # Windows
        'language': 'fra+eng',  # Français + Anglais
        'image_extensions': ['.jpg', '.png'],
        'preprocessing': {
            'clahe_clip': 3.0,
            'blur_size': 3,
            'threshold_block_size': 15,
            'threshold_c': 5
        }
    }

    print("Configuration utilisée:")
    for key, value in config.items():
        print(f"   {key}: {value}")

    # Ici vous pourriez créer un OCRTableProcessor personnalisé
    # avec ces paramètres (extension future)
    print("\n💡 Note: Cette configuration sera utilisée dans une future version")


def main():
    """
    Point d'entrée principal pour les exemples.
    """
    print("🖼️ EXEMPLES D'UTILISATION OCR")
    print("=" * 50)
    print("Ce script montre comment utiliser l'OCR pour traiter")
    print("les images extraites et créer des tableaux Word.")
    print()

    # Vérifier que les dépendances sont installées
    try:
        import cv2
        import pytesseract
        print("✅ Dépendances OCR disponibles")
    except ImportError as e:
        print(f"❌ Dépendance manquante: {e}")
        print("   Installez avec: pip install -r requirements.txt")
        return

    # Exécuter les exemples
    exemple_ocr_simple()
    exemple_ocr_batch()
    exemple_configuration_avancee()

    print("\n" + "=" * 50)
    print("🎯 Prochaines étapes:")
    print("   1. Extrayez d'abord les images avec: python run.py")
    print("   2. Activez l'OCR dans config.py: ENABLE_OCR = True")
    print("   3. Lancez l'extraction complète: python run.py")
    print("   4. Consultez les tableaux dans le dossier 'ocr_tables'")
    print("=" * 50)


if __name__ == "__main__":
    main()
