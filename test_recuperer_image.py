"""
Tests unitaires pour le module d'extraction d'images.

Exécution:
    pytest test_recuperer_image.py -v
    
Ou sans pytest:
    python test_recuperer_image.py
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from io import BytesIO
import zipfile

from recuperer_image import ImageExtractor, ImageStorage


class TestImageStorage(unittest.TestCase):
    """Tests pour la classe ImageStorage."""

    def setUp(self):
        """Préparation avant chaque test."""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = ImageStorage("Test Folder")

    def tearDown(self):
        """Nettoyage après chaque test."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_create_output_folder(self):
        """Test la création du dossier de destination."""
        folder_path = self.storage.create_output_folder(self.temp_dir)

        # Vérifier que le dossier a été créé
        self.assertTrue(folder_path.exists())
        self.assertTrue(folder_path.is_dir())

    def test_create_output_folder_already_exists(self):
        """Test que la création d'un dossier existant ne pose pas problème."""
        self.storage.create_output_folder(self.temp_dir)

        # Créer à nouveau
        folder_path = self.storage.create_output_folder(self.temp_dir)
        self.assertTrue(folder_path.exists())

    def test_save_image(self):
        """Test l'enregistrement d'une image."""
        # Préparation
        self.storage.create_output_folder(self.temp_dir)
        image_data = b"fake image data"

        # Exécution
        saved_path = self.storage.save_image(image_data, 1, "jpg")

        # Vérification
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.name, "bornier_1.jpg")

        # Vérifier le contenu
        with open(saved_path, 'rb') as f:
            content = f.read()
        self.assertEqual(content, image_data)

    def test_save_multiple_images(self):
        """Test l'enregistrement de plusieurs images."""
        self.storage.create_output_folder(self.temp_dir)

        # Enregistrer 3 images
        for i in range(1, 4):
            image_data = f"image data {i}".encode()
            self.storage.save_image(image_data, i, "png")

        # Vérifier qu'elles ont bien été créées
        folder = self.storage.output_folder
        files = list(folder.glob("bornier_*.png"))

        self.assertEqual(len(files), 3)

    def test_different_extensions(self):
        """Test les différentes extensions de fichier."""
        self.storage.create_output_folder(self.temp_dir)

        extensions = ["jpg", "png", "jpeg", "gif", "bmp"]

        for i, ext in enumerate(extensions, 1):
            saved_path = self.storage.save_image(b"data", i, ext)
            self.assertEqual(saved_path.suffix.lower(), f".{ext.lower()}")


class TestImageExtractor(unittest.TestCase):
    """Tests pour la classe ImageExtractor."""

    def setUp(self):
        """Préparation avant chaque test."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Nettoyage après chaque test."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def create_fake_docx(self, with_images=False):
        """
        Crée un fichier .docx factice.
        
        Args:
            with_images: Si True, ajoute des images simulées
            
        Returns:
            Path: Chemin vers le fichier créé
        """
        docx_path = Path(self.temp_dir) / "test_document.docx"

        # Un .docx est un ZIP avec une structure spécifique
        with zipfile.ZipFile(docx_path, 'w') as docx:
            # Créer la structure minimale
            docx.writestr('[Content_Types].xml', '<?xml version="1.0"?>')
            docx.writestr('word/document.xml', '<?xml version="1.0"?>')

            if with_images:
                # Ajouter des images simulées
                docx.writestr('word/media/image1.jpg', b"fake jpeg data")
                docx.writestr('word/media/image2.png', b"fake png data")

        return docx_path

    def test_validate_file_not_found(self):
        """Test que l'extraction échoue si le fichier n'existe pas."""
        with self.assertRaises(FileNotFoundError):
            ImageExtractor("fichier_inexistant.docx")

    def test_validate_file_wrong_extension(self):
        """Test que l'extraction échoue si ce n'est pas un .docx."""
        # Créer un fichier txt
        txt_file = Path(self.temp_dir) / "test.txt"
        txt_file.write_text("test")

        with self.assertRaises(ValueError):
            ImageExtractor(str(txt_file))

    def test_extract_images_no_images(self):
        """Test l'extraction d'un document sans images."""
        docx_file = self.create_fake_docx(with_images=False)
        extractor = ImageExtractor(str(docx_file))

        images = extractor.extract_images()

        self.assertEqual(len(images), 0)

    def test_extract_images_with_images(self):
        """Test l'extraction d'un document avec images."""
        docx_file = self.create_fake_docx(with_images=True)
        extractor = ImageExtractor(str(docx_file))

        images = extractor.extract_images()

        self.assertEqual(len(images), 2)

        # Vérifier les extensions
        extensions = [ext for _, ext in images]
        self.assertIn("jpg", extensions)
        self.assertIn("png", extensions)

    def test_extract_images_content(self):
        """Test que le contenu des images est correct."""
        docx_file = self.create_fake_docx(with_images=True)
        extractor = ImageExtractor(str(docx_file))

        images = extractor.extract_images()

        # Vérifier le contenu
        for image_bytes, ext in images:
            self.assertIsInstance(image_bytes, bytes)
            self.assertGreater(len(image_bytes), 0)
            self.assertIsInstance(ext, str)


def run_simple_tests():
    """Exécution simple des tests (sans pytest)."""
    print("\n" + "=" * 60)
    print("🧪 TESTS DU MODULE D'EXTRACTION D'IMAGES")
    print("=" * 60 + "\n")

    # Créer une suite de tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestImageStorage))
    suite.addTests(loader.loadTestsFromTestCase(TestImageExtractor))

    # Exécuter les tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Afficher le résumé
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ TOUS LES TESTS SONT PASSÉS!")
    else:
        print("❌ CERTAINS TESTS ONT ÉCHOUÉ")
        print(f"Erreurs: {len(result.errors)}")
        print(f"Échecs: {len(result.failures)}")
    print("=" * 60 + "\n")

    return result.wasSuccessful()


if __name__ == "__main__":
    # Exécution simple
    success = run_simple_tests()
    exit(0 if success else 1)
