"""
Tests pour le module OCR processor.

Ces tests vérifient le fonctionnement du traitement OCR et de la création de tableaux.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import numpy as np
import cv2
from unittest.mock import patch, MagicMock

from ocr_processor import OCRTableProcessor, BatchOCRProcessor


class TestOCRTableProcessor:
    """Tests pour la classe OCRTableProcessor."""

    @pytest.fixture
    def temp_dir(self):
        """Crée un répertoire temporaire pour les tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def sample_image(self, temp_dir):
        """Crée une image de test simple."""
        image_path = temp_dir / "test_image.png"

        # Créer une image blanche simple
        img = np.ones((100, 200, 3), dtype=np.uint8) * 255

        # Ajouter du texte simulé (rectangle noir)
        cv2.rectangle(img, (10, 10), (190, 90), (0, 0, 0), -1)

        cv2.imwrite(str(image_path), img)
        return image_path

    def test_initialization_without_tesseract_path(self):
        """Test l'initialisation sans chemin Tesseract."""
        with patch('pytesseract.get_tesseract_version') as mock_version:
            mock_version.return_value = "4.1.0"
            processor = OCRTableProcessor()
            assert processor.language == "fra"

    def test_initialization_with_tesseract_path(self):
        """Test l'initialisation avec chemin Tesseract."""
        tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        with patch('pytesseract.get_tesseract_version') as mock_version:
            mock_version.return_value = "4.1.0"
            processor = OCRTableProcessor(tesseract_path=tesseract_path)
            assert processor.language == "fra"

    def test_preprocess_image(self, sample_image):
        """Test le prétraitement d'image."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        result = processor.preprocess_image(sample_image)
        assert isinstance(result, np.ndarray)
        assert len(result.shape) == 2  # Image en niveaux de gris

    @patch('pytesseract.image_to_data')
    def test_extract_text_data(self, mock_ocr, sample_image):
        """Test l'extraction de données texte."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        # Mock des données OCR
        mock_ocr.return_value = {
            'text': ['Hello', 'World', '', 'Test'],
            'left': [10, 50, 0, 20],
            'top': [10, 10, 0, 30],
            'width': [30, 40, 0, 25],
            'height': [15, 15, 0, 15],
            'conf': ['90', '85', '', '80']
        }

        processed_img = processor.preprocess_image(sample_image)
        text_data = processor.extract_text_data(processed_img)

        assert len(text_data) == 3  # 3 éléments valides
        assert text_data[0]['text'] == 'Hello'
        assert text_data[0]['confidence'] == 90

    def test_group_by_lines(self):
        """Test le regroupement par lignes."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        # Données de test
        text_data = [
            {'text': 'A', 'x': 10, 'y': 10},
            {'text': 'B', 'x': 50, 'y': 12},  # Même ligne
            {'text': 'C', 'x': 10, 'y': 40},  # Nouvelle ligne
        ]

        lines = processor.group_by_lines(text_data, y_threshold=10)

        assert len(lines) == 2
        assert len(lines[0]) == 2  # Première ligne: A, B
        assert len(lines[1]) == 1  # Deuxième ligne: C

    def test_merge_words_in_row(self):
        """Test la fusion des mots d'une même ligne en cellules."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        row = [
            {'text': '01A', 'x': 10, 'y': 10, 'width': 20, 'height': 10},
            {'text': '11', 'x': 50, 'y': 12, 'width': 15, 'height': 10},
            {'text': 'FSI-31', 'x': 180, 'y': 11, 'width': 40, 'height': 10},
        ]

        cells = processor.merge_words_in_row(row)
        assert len(cells) == 2
        assert cells[0]['text'] == '01A 11'
        assert cells[1]['text'] == 'FSI-31'

    def test_build_table_data_from_lines(self):
        """Test la construction du tableau à partir des lignes détectées."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        lines = [
            [
                {'text': 'BORNE', 'x': 10, 'y': 10, 'width': 40, 'height': 10},
                {'text': 'COULEUR', 'x': 120, 'y': 10, 'width': 50, 'height': 10},
                {'text': 'SIGNAL', 'x': 230, 'y': 10, 'width': 50, 'height': 10},
                {'text': 'JARRETIERES', 'x': 340, 'y': 10, 'width': 80, 'height': 10},
            ],
            [
                {'text': '01A', 'x': 10, 'y': 25, 'width': 20, 'height': 10},
                {'text': '11', 'x': 120, 'y': 25, 'width': 20, 'height': 10},
                {'text': 'FSI-31', 'x': 230, 'y': 25, 'width': 40, 'height': 10},
                {'text': '0109R', 'x': 340, 'y': 25, 'width': 40, 'height': 10},
            ],
        ]

        table_data = processor.build_table_data_from_lines(lines)
        assert table_data[0] == ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
        assert table_data[1] == ['01A', '11', 'FSI-31', '0109R']

    def test_detect_table_structure(self):
        """Test la détection de structure de tableau."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        # Lignes de test avec colonne vide (COULEUR manquante)
        lines = [
            [{'text': '01A', 'x': 10}, {'text': 'FSI-31', 'x': 210}, {'text': '0109R', 'x': 340}],
            [{'text': '01B', 'x': 10}, {'text': 'FSI-31', 'x': 210}, {'text': '0110W', 'x': 340}],
        ]

        structure = processor.detect_table_structure(lines)

        assert structure['columns'] == 4
        assert structure['headers'][:4] == ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
        assert len(structure['column_positions']) == 4

    def test_build_table_data(self):
        """Test la construction des données de tableau."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        lines = [
            [{'text': 'A', 'x': 10}, {'text': 'B', 'x': 60}],
            [{'text': '1', 'x': 10}, {'text': '2', 'x': 60}],
        ]

        table_structure = {
            'columns': 2,
            'column_positions': [10, 60],
            'headers': ['Col1', 'Col2']
        }

        table_data = processor.build_table_data(lines, table_structure)

        assert len(table_data) == 2
        assert table_data[0] == ['A', 'B']
        assert table_data[1] == ['1', '2']

    def test_build_table_data_with_empty_columns(self):
        """Test la construction du tableau quand certaines colonnes sont vides."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        lines = [
            [{'text': '01A', 'x': 10}, {'text': 'FSI-31', 'x': 210}, {'text': '0109R', 'x': 340}],
            [{'text': '01B', 'x': 10}, {'text': 'FSI-31', 'x': 210}, {'text': '0110W', 'x': 340}],
        ]

        table_structure = {
            'columns': 4,
            'column_positions': [10, 100, 210, 340],
            'headers': ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
        }

        table_data = processor.build_table_data(lines, table_structure)

        assert len(table_data) == 2
        assert table_data[0] == ['01A', '', 'FSI-31', '0109R']
        assert table_data[1] == ['01B', '', 'FSI-31', '0110W']

    def test_build_table_data_from_grid(self):
        """Test la reconstruction du tableau avec une grille détectée."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        text_data = [
            {'text': '01A', 'x': 10, 'y': 10, 'width': 20, 'height': 10},
            {'text': '11', 'x': 110, 'y': 10, 'width': 20, 'height': 10},
            {'text': 'FSI-31', 'x': 230, 'y': 10, 'width': 40, 'height': 10},
            {'text': '0109R', 'x': 340, 'y': 10, 'width': 40, 'height': 10},
            {'text': '01B', 'x': 10, 'y': 40, 'width': 20, 'height': 10},
            {'text': '11', 'x': 110, 'y': 40, 'width': 20, 'height': 10},
            {'text': 'FSI-31', 'x': 230, 'y': 40, 'width': 40, 'height': 10},
            {'text': '0110W', 'x': 340, 'y': 40, 'width': 40, 'height': 10},
        ]

        grid = {
            'valid': True,
            'row_edges': [0, 25, 55],
            'col_edges': [0, 100, 200, 300, 400],
            'cell_boxes': [
                {'row': 0, 'col': 0, 'left': 0, 'right': 100, 'top': 0, 'bottom': 25, 'coordinate': 'A1'},
                {'row': 0, 'col': 1, 'left': 100, 'right': 200, 'top': 0, 'bottom': 25, 'coordinate': 'B1'},
                {'row': 0, 'col': 2, 'left': 200, 'right': 300, 'top': 0, 'bottom': 25, 'coordinate': 'C1'},
                {'row': 0, 'col': 3, 'left': 300, 'right': 400, 'top': 0, 'bottom': 25, 'coordinate': 'D1'},
                {'row': 1, 'col': 0, 'left': 0, 'right': 100, 'top': 25, 'bottom': 55, 'coordinate': 'A2'},
                {'row': 1, 'col': 1, 'left': 100, 'right': 200, 'top': 25, 'bottom': 55, 'coordinate': 'B2'},
                {'row': 1, 'col': 2, 'left': 200, 'right': 300, 'top': 25, 'bottom': 55, 'coordinate': 'C2'},
                {'row': 1, 'col': 3, 'left': 300, 'right': 400, 'top': 25, 'bottom': 55, 'coordinate': 'D2'},
            ],
            'columns': 4,
            'rows': 2
        }

        table_data = processor.build_table_data_from_grid(text_data, grid)

        assert table_data[0] == ['01A', '11', 'FSI-31', '0109R']
        assert table_data[1] == ['01B', '11', 'FSI-31', '0110W']

    def test_detect_table_grid(self, temp_dir):
        """Test la détection de la grille de tableau."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        image_path = temp_dir / "grid.png"
        img = np.ones((200, 300), dtype=np.uint8) * 255
        cv2.line(img, (50, 10), (50, 190), 0, 2)
        cv2.line(img, (150, 10), (150, 190), 0, 2)
        cv2.line(img, (250, 10), (250, 190), 0, 2)
        cv2.line(img, (10, 50), (290, 50), 0, 2)
        cv2.line(img, (10, 100), (290, 100), 0, 2)
        cv2.line(img, (10, 150), (290, 150), 0, 2)
        cv2.imwrite(str(image_path), img)

        grid = processor.detect_table_grid(img)
        assert grid['valid'] is True
        assert len(grid['row_edges']) >= 4
        assert len(grid['col_edges']) >= 4
        assert 'cell_boxes' in grid
        assert any(box['coordinate'] == 'A1' for box in grid['cell_boxes'])

    def test_build_cell_boxes_coordinates(self):
        """Teste la génération des boîtes de cellules et de leur coordonnées."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        table_boxes = processor._build_cell_boxes([0, 100, 200], [0, 50, 100])
        assert len(table_boxes) == 4
        assert table_boxes[0]['coordinate'] == 'A1'
        assert table_boxes[1]['coordinate'] == 'B1'
        assert table_boxes[2]['coordinate'] == 'A2'
        assert table_boxes[3]['coordinate'] == 'B2'

    @patch('docx.Document.save')
    def test_create_word_document(self, mock_save, temp_dir):
        """Test la création de document Word."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        table_data = [['A', 'B'], ['1', '2']]
        table_structure = {
            'columns': 2,
            'headers': ['Col1', 'Col2']
        }
        output_path = temp_dir / "test.docx"

        processor.create_word_document(table_data, table_structure, output_path)

        # Vérifier que save a été appelé
        mock_save.assert_called_once()

    @patch('pytesseract.image_to_data')
    @patch('docx.Document.save')
    def test_process_image_to_table_success(self, mock_save, mock_ocr, sample_image, temp_dir):
        """Test le pipeline complet avec succès."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        # Mock OCR
        mock_ocr.return_value = {
            'text': ['Test', 'Data'],
            'left': [10, 50],
            'top': [10, 10],
            'width': [30, 30],
            'height': [15, 15],
            'conf': ['90', '85']
        }

        output_path = temp_dir / "output.docx"
        result = processor.process_image_to_table(sample_image, output_path)

        assert result['success'] is True
        assert 'text_elements' in result
        assert 'table_rows' in result

    @patch('pytesseract.image_to_data')
    def test_process_image_to_table_no_text(self, mock_ocr, sample_image, temp_dir):
        """Test le pipeline quand aucune donnée texte n'est trouvée."""
        with patch('pytesseract.get_tesseract_version'):
            processor = OCRTableProcessor()

        # Mock OCR sans texte
        mock_ocr.return_value = {
            'text': ['', '', ''],
            'left': [0, 0, 0],
            'top': [0, 0, 0],
            'width': [0, 0, 0],
            'height': [0, 0, 0],
            'conf': ['0', '0', '0']
        }

        output_path = temp_dir / "output.docx"
        result = processor.process_image_to_table(sample_image, output_path)

        assert result['success'] is False
        assert result['error'] == 'No text found'


class TestBatchOCRProcessor:
    """Tests pour la classe BatchOCRProcessor."""

    @pytest.fixture
    def temp_dirs(self):
        """Crée des répertoires temporaires pour les tests batch."""
        input_dir = Path(tempfile.mkdtemp()) / "input"
        output_dir = Path(tempfile.mkdtemp()) / "output"

        input_dir.mkdir()
        output_dir.mkdir()

        yield input_dir, output_dir

        shutil.rmtree(input_dir.parent)
        shutil.rmtree(output_dir.parent)

    def test_initialization(self):
        """Test l'initialisation du processeur batch."""
        with patch('pytesseract.get_tesseract_version'):
            processor = BatchOCRProcessor()
            assert hasattr(processor, 'processor')

    @patch('pytesseract.image_to_data')
    def test_process_folder(self, mock_ocr, temp_dirs):
        """Test le traitement d'un dossier."""
        input_dir, output_dir = temp_dirs

        with patch('pytesseract.get_tesseract_version'):
            processor = BatchOCRProcessor()

        # Créer une image de test
        img = np.ones((50, 100, 3), dtype=np.uint8) * 255
        image_path = input_dir / "test.jpg"
        cv2.imwrite(str(image_path), img)

        # Mock OCR
        mock_ocr.return_value = {
            'text': ['Test'],
            'left': [10],
            'top': [10],
            'width': [30],
            'height': [15],
            'conf': ['90']
        }

        results = processor.process_folder(input_dir, output_dir, save_excel=True)

        assert len(results) == 1
        assert results[0]['success'] is True

        # Vérifier que les fichiers de sortie ont été créés
        output_files = list(output_dir.glob("*.docx"))
        output_excel = list(output_dir.glob("*.xlsx"))
        assert len(output_files) == 1
        assert len(output_excel) == 1


# Tests d'intégration
class TestIntegration:
    """Tests d'intégration pour vérifier le fonctionnement global."""

    def test_import_ocr_processor(self):
        """Test que le module peut être importé."""
        try:
            from ocr_processor import OCRTableProcessor, BatchOCRProcessor
            assert True
        except ImportError:
            pytest.fail("Impossible d'importer le module OCR")

    def test_dependencies_available(self):
        """Test que les dépendances sont disponibles."""
        try:
            import cv2
            import pytesseract
            import numpy as np
            from docx import Document
            assert True
        except ImportError as e:
            pytest.fail(f"Dépendance manquante: {e}")


if __name__ == "__main__":
    pytest.main([__file__])