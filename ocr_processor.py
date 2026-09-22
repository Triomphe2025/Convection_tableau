"""
Module OCR pour traiter les images extraites et créer des tableaux Word.

Ce module utilise OpenCV et Tesseract pour extraire le texte des images
et créer des tableaux structurés dans des documents Word.
"""

import re
import cv2
import pytesseract
import numpy as np
from pathlib import Path
from typing import Callable, List, Dict, Optional, Tuple
from docx import Document
from docx.shared import Inches
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
import logging
from config import Config
from data_dictionary import get_dictionary

logger = logging.getLogger(__name__)


class OCRTableProcessor:
    """
    Classe pour traiter les images avec OCR et créer des tableaux Word.

    Attributes:
        tesseract_path (str): Chemin vers l'exécutable Tesseract
        language (str): Langue pour l'OCR (par défaut 'fra')
    """

    def __init__(self, tesseract_path: Optional[str] = None, language: str = "fra"):
        """
        Initialise le processeur OCR.

        Args:
            tesseract_path: Chemin vers Tesseract (optionnel)
            language: Langue pour l'OCR
        """
        self.tesseract_path = tesseract_path
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        self.language = language
        self._validate_tesseract()

    def _validate_tesseract(self) -> None:
        """Valide que Tesseract est installé et accessible."""
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"✓ Tesseract trouvé: {version}")
        except Exception as e:
            logger.error(f"✗ Tesseract non trouvé: {e}")
            raise RuntimeError("Tesseract n'est pas installé ou accessible")

    def preprocess_image(self, image_path: Path) -> np.ndarray:
        """
        Prétraite l'image pour améliorer la qualité OCR.

        Args:
            image_path: Chemin vers l'image

        Returns:
            Image prétraitée
        """
        logger.info(f"🔄 Prétraitement de l'image: {image_path.name}")

        # Charger l'image
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Impossible de charger l'image: {image_path}")

        # Convertir en niveaux de gris
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Améliorer le contraste avec CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Réduction du bruit
        denoised = cv2.medianBlur(enhanced, 3)

        # Binarisation adaptative
        thresh = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Correction d'inclinaison (deskew)
        coords = np.column_stack(np.where(thresh > 0))
        angle = cv2.minAreaRect(coords)[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        (h, w) = thresh.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(thresh, M, (w, h),
                                 flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)

        logger.info("✓ Prétraitement terminé")
        return rotated

    def extract_text_data(self, image: np.ndarray) -> List[Dict]:
        """
        Extrait le texte et les coordonnées avec OCR.

        Args:
            image: Image prétraitée

        Returns:
            Liste des éléments texte avec coordonnées
        """
        logger.info("🔍 Extraction du texte avec OCR...")

        # Configuration Tesseract
        custom_config = f'--oem 3 --psm 6 -l {self.language}'

        # OCR avec données détaillées
        data = pytesseract.image_to_data(
            image, config=custom_config,
            output_type=pytesseract.Output.DICT
        )

        # Filtrer et structurer les données
        text_data = []
        n_boxes = len(data['text'])

        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf_str = data['conf'][i]
            try:
                confidence = int(conf_str)
            except (TypeError, ValueError):
                confidence = 0

            # Garder seulement le texte valide avec bonne confiance
            if text and confidence > 30:
                x = data['left'][i]
                y = data['top'][i]
                width = data['width'][i]
                height = data['height'][i]
                text_data.append({
                    'text': text,
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height,
                    'confidence': confidence,
                    'x_center': x + width // 2,
                    'y_center': y + height // 2,
                    'x_end': x + width,
                    'y_end': y + height
                })

        logger.info(f"✓ {len(text_data)} éléments texte extraits")
        return text_data

    def group_by_lines(self, text_data: List[Dict],
                       y_threshold: Optional[int] = None) -> List[List[Dict]]:
        """
        Regroupe les éléments texte par lignes en utilisant les centres verticaux.

        Args:
            text_data: Données texte avec coordonnées
            y_threshold: Tolérance verticale pour regrouper

        Returns:
            Liste de lignes, chaque ligne contenant les éléments
        """
        logger.info("📏 Regroupement par lignes...")

        if not text_data:
            return []

        heights = [item.get('height', 0) for item in text_data if item.get('height', 0) > 0]
        median_height = int(np.median(heights)) if heights else 10
        if y_threshold is None:
            y_threshold = max(12, int(median_height * 0.8))

        items = sorted(text_data, key=lambda item: item['y_center'])
        lines = []
        current_row = []
        current_y = None

        for item in items:
            if current_y is None:
                current_row = [item]
                current_y = item['y_center']
                continue

            if abs(item['y_center'] - current_y) <= y_threshold:
                current_row.append(item)
                current_y = sum(elem['y_center'] for elem in current_row) / len(current_row)
            else:
                lines.append(current_row)
                current_row = [item]
                current_y = item['y_center']

        if current_row:
            lines.append(current_row)

        lines.sort(key=lambda line: sum(elem['y_center'] for elem in line) / len(line))
        for line in lines:
            line.sort(key=lambda item: item['x'])

        logger.info(f"✓ {len(lines)} lignes identifiées")
        return lines

    def merge_words_in_row(self, row: List[Dict]) -> List[Dict]:
        """Fusionne les mots d'une même ligne pour former des cellules potentielles."""
        if not row:
            return []

        sorted_row = sorted(row, key=lambda item: item['x'])
        widths = [item.get('width', 0) for item in sorted_row if item.get('width', 0) > 0]
        gap_threshold = max(10, int(np.median(widths) * 0.75)) if widths else 15

        cells = []
        current = {
            'text': sorted_row[0]['text'],
            'left': sorted_row[0]['x'],
            'right': sorted_row[0]['x'] + sorted_row[0].get('width', 0),
            'top': sorted_row[0]['y'],
            'bottom': sorted_row[0]['y'] + sorted_row[0].get('height', 0)
        }

        for item in sorted_row[1:]:
            left = item['x']
            right = item['x'] + item.get('width', 0)
            if left <= current['right'] + gap_threshold:
                current['text'] += ' ' + item['text']
                current['right'] = max(current['right'], right)
                current['top'] = min(current['top'], item['y'])
                current['bottom'] = max(current['bottom'], item['y'] + item.get('height', 0))
            else:
                current['center'] = (current['left'] + current['right']) / 2
                cells.append(current)
                current = {
                    'text': item['text'],
                    'left': left,
                    'right': right,
                    'top': item['y'],
                    'bottom': item['y'] + item.get('height', 0)
                }

        current['center'] = (current['left'] + current['right']) / 2
        cells.append(current)
        return cells

    def _cluster_positions(self, positions: List[int], tolerance: int = 20) -> List[int]:
        """Regroupe les positions proches en moyennes de colonne/ligne."""
        if not positions:
            return []

        positions.sort()
        clusters = []
        current_cluster = [positions[0]]

        for position in positions[1:]:
            if position - current_cluster[-1] <= tolerance:
                current_cluster.append(position)
            else:
                clusters.append(int(np.mean(current_cluster)))
                current_cluster = [position]

        clusters.append(int(np.mean(current_cluster)))
        return clusters

    def _extract_line_centers(self, mask: np.ndarray, vertical: bool = True) -> List[int]:
        """Extrait les centres de lignes verticales ou horizontales depuis un masque."""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        centers = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if vertical:
                if h > mask.shape[0] * 0.25 and w < mask.shape[1] * 0.2:
                    centers.append(x + w // 2)
            else:
                if w > mask.shape[1] * 0.25 and h < mask.shape[0] * 0.2:
                    centers.append(y + h // 2)

        return self._cluster_positions(centers, tolerance=20)

    def _compute_column_boundaries(self, positions: List[int], image_width: int) -> List[int]:
        """Calcule les limites de colonnes à partir des positions centrales détectées."""
        if not positions:
            return [0, image_width]

        positions = sorted(set(positions))
        boundaries = [0]
        for i in range(len(positions) - 1):
            boundaries.append(int((positions[i] + positions[i + 1]) / 2))
        boundaries.append(image_width)
        return boundaries

    def _build_cell_boxes(self, col_edges: List[int], row_edges: List[int]) -> List[Dict]:
        """Construit les boîtes de cellules à partir des bordures de grille."""
        boxes = []
        rows = len(row_edges) - 1
        cols = len(col_edges) - 1

        for row_index in range(rows):
            for col_index in range(cols):
                boxes.append({
                    'row': row_index,
                    'col': col_index,
                    'left': col_edges[col_index],
                    'right': col_edges[col_index + 1],
                    'top': row_edges[row_index],
                    'bottom': row_edges[row_index + 1],
                    'coordinate': f"{chr(ord('A') + col_index)}{row_index + 1}"
                })

        return boxes

    def detect_table_grid(self, image: np.ndarray) -> Dict:
        """Détecte la grille du tableau à partir des lignes de l'image."""
        logger.info("🔍 Détection de la grille du tableau...")

        if image is None or image.size == 0:
            return {'valid': False}

        inverted = cv2.bitwise_not(image)
        height, width = image.shape[:2]

        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, height // 40)))
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, width // 40), 1))

        vertical_mask = cv2.erode(inverted, vertical_kernel, iterations=1)
        vertical_mask = cv2.dilate(vertical_mask, vertical_kernel, iterations=2)

        horizontal_mask = cv2.erode(inverted, horizontal_kernel, iterations=1)
        horizontal_mask = cv2.dilate(horizontal_mask, horizontal_kernel, iterations=2)

        col_centers = self._extract_line_centers(vertical_mask, vertical=True)
        row_centers = self._extract_line_centers(horizontal_mask, vertical=False)

        if len(col_centers) < 2 or len(row_centers) < 2:
            return {'valid': False}

        col_edges = self._compute_column_boundaries(col_centers, width)
        row_edges = self._compute_column_boundaries(row_centers, height)
        cell_boxes = self._build_cell_boxes(col_edges, row_edges)

        logger.info(
            f"✓ Grille détectée: {len(row_edges)-1} lignes x {len(col_edges)-1} colonnes"
        )
        return {
            'valid': True,
            'row_edges': row_edges,
            'col_edges': col_edges,
            'cell_boxes': cell_boxes,
            'columns': len(col_edges) - 1,
            'rows': len(row_edges) - 1
        }

    def build_table_data_from_grid(self, text_data: List[Dict], grid: Dict) -> List[List[str]]:
        """Construit un tableau à partir des données texte et des bordures détectées."""
        logger.info("📊 Construction du tableau à partir de la grille...")

        if not grid.get('valid'):
            return []

        rows = grid['rows']
        columns = grid['columns']
        table_data = [[''] * columns for _ in range(rows)]
        cell_boxes = grid.get('cell_boxes', [])

        for item in sorted(text_data, key=lambda x: (x['y'] + x['height'] // 2, x['x'])):
            center_x = item['x'] + item['width'] // 2
            center_y = item['y'] + item['height'] // 2
            assigned = False

            for box in cell_boxes:
                if (box['left'] <= center_x <= box['right'] and
                        box['top'] <= center_y <= box['bottom']):
                    row_index = box['row']
                    col_index = box['col']
                    cell_value = table_data[row_index][col_index]
                    if cell_value:
                        table_data[row_index][col_index] = f"{cell_value} {item['text']}"
                    else:
                        table_data[row_index][col_index] = item['text']
                    assigned = True
                    break

            if not assigned:
                row_index = next(
                    (i for i in range(rows) if grid['row_edges']
                     [i] <= center_y < grid['row_edges'][i + 1]),
                    rows - 1
                )
                col_index = next(
                    (i for i in range(columns) if grid['col_edges']
                     [i] <= center_x < grid['col_edges'][i + 1]),
                    columns - 1
                )
                cell_value = table_data[row_index][col_index]
                if cell_value:
                    table_data[row_index][col_index] = f"{cell_value} {item['text']}"
                else:
                    table_data[row_index][col_index] = item['text']

        cleaned_data = [[cell.strip() for cell in row] for row in table_data]
        non_empty_rows = [row for row in cleaned_data if any(row)]

        logger.info(f"✓ Tableau construit: {len(non_empty_rows)} lignes")
        return non_empty_rows

    def detect_table_structure(self, lines: List[List[Dict]]) -> Dict:
        """
        Détecte la structure du tableau automatiquement.

        Args:
            lines: Lignes de texte regroupées

        Returns:
            Structure détectée du tableau
        """
        logger.info("🔍 Analyse de la structure du tableau...")

        if not lines:
            return {
                'columns': 4,
                'headers': ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'],
                'column_positions': [0, 100, 250, 400],
            }

        # Analyser les positions X pour détecter les colonnes
        all_x_positions = [
            item['x'] + item.get('width', 0) // 2
            for line in lines
            for item in line
        ]
        all_x_positions.sort()

        if not all_x_positions:
            return {
                'columns': 4,
                'headers': ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'],
                'column_positions': [0, 100, 250, 400],
            }

        # Calibration dynamique du seuil en fonction des écarts
        if len(all_x_positions) > 1:
            diffs = np.diff(all_x_positions)
            median_gap = int(np.median(diffs)) if len(diffs) else 50
            cluster_threshold = max(40, int(median_gap * 1.5))
        else:
            cluster_threshold = 50

        column_positions = [all_x_positions[0]]
        for x in all_x_positions[1:]:
            if x - column_positions[-1] > cluster_threshold:
                column_positions.append(x)

        # Garantir au moins 4 colonnes
        if len(column_positions) < 4:
            if lines:
                min_x = min(item['x'] for line in lines for item in line)
                max_x = max(item['x'] + item.get('width', 0) for line in lines for item in line)
                span = max(max_x - min_x, 320)
                step = span // 4
                column_positions = [min_x + i * step for i in range(4)]
            else:
                column_positions = [0, 100, 200, 300]

        num_columns = max(4, len(column_positions))

        headers = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
        if num_columns > 4:
            headers.extend([f'COLONNE_{i+1}' for i in range(4, num_columns)])

        structure = {
            'columns': num_columns,
            'column_positions': column_positions,
            'headers': headers
        }

        logger.info(f"✓ Structure détectée: {num_columns} colonnes")
        return structure

    def build_table_data_from_lines(self, lines: List[List[Dict]]) -> List[List[str]]:
        """Construit le tableau à partir des lignes regroupées et des positions X/Y."""
        logger.info("📊 Construction du tableau à partir des lignes détectées...")

        if not lines:
            return []

        header_cells = self.merge_words_in_row(lines[0])
        header_centers = [
            (cell['left'] + cell['right']) / 2 for cell in header_cells
        ]
        header_texts = [cell['text'].strip() for cell in header_cells]
        if not header_texts:
            return []

        table_data = [header_texts]

        for line in lines[1:]:
            row_cells = self.merge_words_in_row(line)
            # Trier les cellules par position X (de gauche à droite)
            row_cells.sort(key=lambda c: c['left'])
            # Prendre les 4 premières cellules (ou moins si pas assez)
            row_values = [cell['text'] for cell in row_cells[:4]]
            # Compléter avec 'none' si moins de 4
            while len(row_values) < 4:
                row_values.append('none')
            table_data.append(row_values)

        logger.info(
            f"✓ Tableau construit: {len(table_data)} lignes, {len(header_centers)} colonnes"
        )
        return table_data

    def build_table_data(self, lines: List[List[Dict]],
                         table_structure: Dict) -> List[List[str]]:
        """
        Construit les données du tableau structuré.

        Args:
            lines: Lignes de texte regroupées
            table_structure: Structure du tableau détectée

        Returns:
            Données du tableau (liste de listes)
        """
        logger.info("📊 Construction du tableau...")

        table_data = []
        column_positions = table_structure.get('column_positions', [])

        max_x_end = 0
        for line in lines:
            for item in line:
                max_x_end = max(max_x_end, item['x'] + item.get('width', 0))

        boundaries = self._compute_column_boundaries(column_positions, max_x_end + 50)

        for line in lines:
            row = [''] * table_structure['columns']
            for item in line:
                text = item['text']
                x_center = item['x'] + item.get('width', 0) // 2

                column_index = len(boundaries) - 2
                for i in range(len(boundaries) - 1):
                    if boundaries[i] <= x_center < boundaries[i + 1]:
                        column_index = i
                        break

                if column_index < len(row):
                    if row[column_index]:
                        row[column_index] += ' ' + text
                    else:
                        row[column_index] = text

            cleaned_row = [cell.strip() for cell in row]
            if any(cleaned_row):
                table_data.append(cleaned_row)

        logger.info(f"✓ Tableau construit: {len(table_data)} lignes")
        return table_data

    def create_word_document(self, table_data: List[List[str]],
                             table_structure: Dict,
                             output_path: Path,
                             image_path: Optional[Path] = None) -> None:
        """
        Crée un document Word avec le tableau.

        Args:
            table_data: Données du tableau
            table_structure: Structure du tableau
            output_path: Chemin du fichier de sortie
            image_path: Chemin de l'image source (optionnel)
        """
        logger.info(f"📝 Création du document Word: {output_path.name}")

        doc = Document()

        # Titre
        doc.add_heading("Tableau OCR - Extraction Automatique", 0)

        # Informations sur l'image source
        if image_path:
            doc.add_paragraph(f"Image source: {image_path.name}")

        # Créer le tableau
        if table_data:
            rows = len(table_data)
            cols = table_structure.get('columns', max(len(row) for row in table_data))
            table = doc.add_table(rows=rows, cols=cols)
            table.style = 'Table Grid'

            for row_index, row_data in enumerate(table_data):
                cells = table.rows[row_index].cells
                for col_index in range(cols):
                    cell_text = row_data[col_index] if col_index < len(row_data) else ""
                    cells[col_index].text = cell_text

            # Ajuster les largeurs de colonnes si elles sont détectées
            widths = table_structure.get('column_widths')
            if widths:
                for col_index, width_px in enumerate(widths):
                    if col_index < len(table.columns):
                        table.columns[col_index].width = Inches(width_px / 96)

        doc.save(str(output_path))
        logger.info(f"✓ Document Word créé: {output_path}")

    def create_excel_document(self, table_data: List[List[str]],
                              output_path: Path, image_path: Optional[Path] = None) -> None:
        """
        Crée un fichier Excel à partir du tableau extrait,
        suivant le modèle de exemple_tableaux.xlsx Feuil3.

        Args:
            table_data: Données du tableau (avec en-tête)
            output_path: Chemin du fichier Excel de sortie
            image_path: Chemin de l'image pour extraire le numéro du bornier
        """
        logger.info(f"📝 Création du fichier Excel: {output_path.name}")

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Tableau OCR"

        # En-tête
        headers = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
        for col_index, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=col_index, value=header)
            cell.font = Font(bold=True)

        # Données (à partir de la ligne 2)
        data_rows = table_data[1:] if len(table_data) > 1 else []  # Skip header if present
        for row_index, row_data in enumerate(data_rows, start=2):
            for col_index in range(4):  # Only 4 columns
                cell_value = row_data[col_index] if col_index < len(row_data) else ""
                cell = sheet.cell(row=row_index, column=col_index + 1, value=cell_value)
                cell.alignment = Alignment(wrap_text=True, vertical='top')

        # Ligne d'en-tête M T I
        mti_row = len(data_rows) + 3
        sheet.cell(row=mti_row, column=1, value="M     T      I")
        sheet.cell(row=mti_row, column=2,
                   value="    P.E.T : EPEULE"
                         "                          BORNIER : B702A"
                         "                                   ")

        # Ligne NO PLAN
        plan_row = mti_row + 1
        sheet.cell(
            row=plan_row, column=2,
            value="NO PLAN : VD23111 PE 162"
                  "                      |  INDICE : 0      |    PAGE :        92"
        )

        # Ajuster les largeurs de colonnes
        for col_index in range(1, 5):
            sheet.column_dimensions[get_column_letter(col_index)].width = 20

        workbook.save(str(output_path))
        logger.info(f"✓ Fichier Excel créé: {output_path}")

    def process_image_to_table(self, image_path: Path,
                               output_path: Path,
                               save_excel: bool = False,
                               excel_output_path: Optional[Path] = None) -> Dict:
        """
        Pipeline complet: image → OCR → tableau → Word/Excel.
        Utilise BornierTableExtractor pour une extraction précise.
        """
        logger.info(f"🚀 Traitement OCR: {image_path.name}")
        try:
            extractor = BornierTableExtractor(
                tesseract_path=self.tesseract_path,
                language=self.language
            )
            result = extractor.extract(image_path)

            if not result['success']:
                logger.warning(f"⚠ {result.get('error', 'Échec')}")
                return {'success': False, 'error': result.get('error')}

            extractor.to_word(result, output_path)

            if save_excel:
                if excel_output_path is None:
                    excel_output_path = output_path.with_suffix('.xlsx')
                extractor.to_excel(result, excel_output_path)

            data_rows = [r for r in result['rows'] if r['type'] == 'data']
            logger.info(f"✅ Terminé: {len(data_rows)} lignes de données")
            return {
                'success': True,
                'image_path': str(image_path),
                'output_path': str(output_path),
                'text_elements': sum(
                    len([c for c in r.get('cells', []) if c])
                    for r in data_rows
                ),
                'table_rows': len(result['rows']),
                'columns': len(result['headers']),
                'excel_path': str(excel_output_path) if save_excel else None
            }
        except Exception as e:
            logger.error(f"✗ Erreur: {e}")
            return {'success': False, 'error': str(e)}


class BornierTableExtractor:
    """
    Extracteur générique pour tableaux tabulaires dans des images.

    Paramétrable via TableTemplate : colonnes, séparateur de section,
    pied de page. Compatible avec n'importe quelle structure de tableau.
    """

    # Modèle par défaut (rétrocompatibilité)
    EXPECTED_HEADERS = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']

    # Cache TATR — chargé une seule fois par session Python, jamais en .exe
    _tatr_model = None
    _tatr_processor = None
    _tatr_available: Optional[bool] = None   # None=pas testé, True/False=résultat

    _COULEURS_FR: List[str] = [
        'ROUGE', 'VERT', 'BLEU', 'NOIR', 'BLANC', 'JAUNE', 'ORANGE',
        'VIOLET', 'MARRON', 'GRIS', 'ROSE', 'BRUN', 'BEIGE', 'CYAN',
    ]

    # Préfixes de mots SIGNAL commençant par A (OCR peut lire 4 au lieu de A)
    _SIGNAL_A_STARTS: frozenset = frozenset([
        'ARRET', 'ALERTE', 'ALARME', 'ALIM', 'APPEL', 'AUTO', 'AUX',
        'ACCES', 'ASSER', 'AVERT', 'AMONT', 'AVAL', 'AVANT', 'APPAR',
        'ARRI', 'ALLU', 'ALIM', 'ACTIV',
    ])

    def __init__(self, tesseract_path: Optional[str] = None,
                 language: str = 'fra',
                 template=None,
                 on_column_mapping: Optional[Callable] = None):
        """
        Args:
            tesseract_path: Chemin vers tesseract.exe (None = PATH système)
            language:       Code langue Tesseract (ex: 'fra', 'eng')
            template:       TableTemplate — structure du tableau à extraire.
                            Si None, utilise le modèle bornier standard.
            on_column_mapping: Callback(candidate_blocks, template_columns,
                            image_path) -> Optional[Dict[str, List[int]]].
                            Appelé quand le template a plus de
                            Config.MAX_AUTO_COLUMNS colonnes, pour demander
                            un classement manuel bloc→colonne à l'utilisateur.
                            None = pas d'interaction (comportement standard).
        """
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        self.language = language

        # Résoudre le modèle
        if template is None:
            from template import DEFAULT_TEMPLATE
            self._tpl = DEFAULT_TEMPLATE
        else:
            self._tpl = template

        self._col_keywords = [c.upper() for c in self._tpl.columns]

        # Mapping manuel colonnes/blocs — mis en cache par template pour tout
        # le run (évite de redemander à chaque image d'un lot de 50-300 images)
        self._on_column_mapping = on_column_mapping
        self._cached_column_mapping: Optional[Dict[str, List[int]]] = None
        self._cached_mapping_key: Optional[tuple] = None

    # ------------------------------------------------------------------
    # Étape 1 : Prétraitement
    # ------------------------------------------------------------------

    # Kernel d'accentuation des bords : renforce les contours après débruitage
    _SHARPEN_KERNEL = np.array(
        [[0, -1,  0],
         [-1,  5, -1],
         [0, -1,  0]], dtype=np.float32
    )

    def _preprocess(self, image_path: Path) -> Tuple[np.ndarray, int]:
        """Charge, met à l'échelle et binarise l'image.

        Pipeline :
          gris → upscale (si < 1400 px) → CLAHE → débruitage non-local
          → accentuation des bords → Otsu → deskew.

        Ordre choisi car le débruitage fastNlMeans efface les contours fins
        des caractères ; l'accentuation les restaure avant la binarisation.
        """
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Image non trouvée: {image_path}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        if w < 1400:
            scale = 1400 / w
            gray = cv2.resize(
                gray, None, fx=scale, fy=scale,
                interpolation=cv2.INTER_CUBIC
            )
        # CLAHE (clipLimit=2.5) : améliore le contraste sans sur-amplifier le bruit
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        # Débruitage bilatéral : préserve les bords des caractères, 400× plus rapide
        # que fastNlMeansDenoising sur des images 2000+ px.
        gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
        # Accentuation des contours : compense le lissage introduit par le débruitage
        gray = cv2.filter2D(gray, -1, self._SHARPEN_KERNEL)
        # Binarisation Otsu : stable sur fond homogène (scans industriels)
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        binary = self._deskew(binary)
        return binary, binary.shape[1]

    def _deskew(self, binary: np.ndarray) -> np.ndarray:
        """
        Corrige l'inclinaison de l'image via les lignes horizontales du tableau.
        Utilise la morphologie (pas les pixels blancs bruts) pour robustesse.
        """
        h, w = binary.shape[:2]
        inverted = cv2.bitwise_not(binary)
        kern = cv2.getStructuringElement(
            cv2.MORPH_RECT, (max(w // 30, 20), 1)
        )
        mask = cv2.erode(inverted, kern, iterations=2)
        mask = cv2.dilate(mask, kern, iterations=3)
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        angles = []
        for cnt in contours:
            if cv2.contourArea(cnt) > w * 0.15:
                rect = cv2.minAreaRect(cnt)
                angle = rect[-1]
                if angle < -45:
                    angle += 90
                if abs(angle) < 10:
                    angles.append(angle)
        if not angles:
            return binary
        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.3:
            return binary
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        return cv2.warpAffine(
            binary, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    # ------------------------------------------------------------------
    # Étape 2 : OCR
    # ------------------------------------------------------------------

    # Whitelists de caractères autorisés par type de colonne.
    # OEM 1 (LSTM pur) respecte mieux ces listes que OEM 3.
    _COL_WHITELISTS: Dict[str, str] = {
        'BORNE':       'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-/. ',
        'COULEUR':     'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ',
        'SIGNAL':      ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
                        '0123456789_.-/+()\'"*# '),
        'JARRETIERES': 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-/. ',
        'TENANT':      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-/. ',
        # JAR : uniquement chiffres + lettres majuscules (patron 4 chiffres + 1 lettre)
        'JAR':         '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        'ABOUTISSANT': 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-/. ',
    }

    # Patrons de validation par colonne. Une cellule qui ne respecte pas son patron
    # déclenche un re-OCR par bande (ROI), même si elle n'est pas vide.
    _COL_PATTERNS: Dict[str, re.Pattern] = {
        # JAR doit commencer par au moins un chiffre (ex : 0001R, 0002W)
        'JAR': re.compile(r'^\d'),
    }

    def _ocr_elements(self, image: np.ndarray, psm: int = 6) -> List[Dict]:
        """Retourne tous les mots détectés avec leur position."""
        config = f'--oem 1 --psm {psm} -l {self.language}'
        data = pytesseract.image_to_data(
            image, config=config,
            output_type=pytesseract.Output.DICT
        )
        elements = []
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            try:
                conf = int(data['conf'][i])
            except (TypeError, ValueError):
                conf = 0
            if text and conf > 15:
                x, y = data['left'][i], data['top'][i]
                w, h = data['width'][i], data['height'][i]
                elements.append({
                    'text': text,
                    'x': x, 'y': y, 'w': w, 'h': h,
                    'cx': x + w // 2,
                    'cy': y + h // 2,
                    'conf': conf,
                })
        return elements

    def _reocr_cell(
        self,
        binary: np.ndarray,
        y_min: int, y_max: int,
        x_min: int, x_max: int,
        col_name: str,
    ) -> Tuple[str, int]:
        """Re-OCR d'une cellule avec PSM 7 + whitelist propre à la colonne.

        Retourne (texte_nettoyé, confiance_0_100).
        Utilisé uniquement sur les cellules dont la confiance < seuil.
        """
        crop = binary[y_min:y_max, x_min:x_max]
        if crop.size == 0:
            return '', 0
        h_c, w_c = crop.shape[:2]
        # Upscale si la cellule est trop petite (< 20 px de hauteur = police illisible)
        if h_c < 20:
            scale = max(2.0, 30 / h_c)
            crop = cv2.resize(crop, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)
        col_upper = col_name.upper()
        whitelist = self._COL_WHITELISTS.get(col_upper, '')
        _TECH_COLS = {
            'BORNE', 'JAR', 'JARRETIERES',
            'TENANT', 'ABOUTISSANT', 'COULEUR',
        }
        lang = (
            getattr(Config, 'OCR_LANGUAGE_TECHNICAL', 'eng')
            if col_upper in _TECH_COLS
            else self.language
        )
        config = f'--oem 3 --psm 7 -l {lang}'
        if getattr(Config, 'OCR_DISABLE_DICT', True):
            config += ' -c load_system_dawg=0 -c load_freq_dawg=0'
        if whitelist:
            config += f' -c tessedit_char_whitelist={whitelist}'
        data = pytesseract.image_to_data(
            crop, config=config, output_type=pytesseract.Output.DICT
        )
        words, confs = [], []
        for i in range(len(data['text'])):
            t = data['text'][i].strip()
            try:
                c = int(data['conf'][i])
            except (TypeError, ValueError):
                c = 0
            if t and c > 0:
                words.append(t)
                confs.append(c)
        if not words:
            return '', 0
        return self._clean_cell(' '.join(words)), int(sum(confs) / len(confs))

    # ------------------------------------------------------------------
    # Étape 2b : OCR grille — suppression traits, découpe cellule/cellule
    # ------------------------------------------------------------------

    def _remove_table_lines(
        self,
        binary: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Supprime les traits H/V du tableau via morphologie.
        Retourne (image_nettoyée_sans_traits, masque_traits_horizontaux).

        L'image nettoyée est passée à Tesseract pour lire le texte.
        Le masque HORIZONTAL (pas vertical) sert à détecter les séparateurs
        de lignes — les traits verticaux polluaient la détection par lignes.
        """
        h, w = binary.shape[:2]
        inv = cv2.bitwise_not(binary)

        # Traits horizontaux — noyau proportionnel à la largeur
        h_len = max(w // 12, 30)
        h_kern = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
        h_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, h_kern, iterations=2)
        h_lines = cv2.dilate(h_lines, np.ones((3, 1), np.uint8), iterations=1)

        # Traits verticaux — noyau proportionnel à la hauteur
        v_len = max(h // 12, 25)
        v_kern = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        v_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, v_kern, iterations=2)
        v_lines = cv2.dilate(v_lines, np.ones((1, 3), np.uint8), iterations=1)

        all_lines = cv2.add(h_lines, v_lines)

        # Soustraire les traits et léger ré-épaississement des caractères
        clean_inv = cv2.subtract(inv, all_lines)
        clean_inv = cv2.dilate(
            clean_inv, np.ones((2, 1), np.uint8), iterations=1
        )
        # Retourner l'image nettoyée ET le masque H seul (pas all_lines)
        return cv2.bitwise_not(clean_inv), h_lines

    def _detect_row_bounds(
        self,
        h_lines_mask: np.ndarray,
        img_w: int,
        min_span: float = 0.15,
    ) -> List[int]:
        """
        Retourne les y-coordonnées des traits horizontaux (séparateurs de lignes).

        h_lines_mask : masque HORIZONTAL uniquement (pas de traits verticaux).
        min_span     : fraction minimale de la largeur que chaque trait doit
                       couvrir (0.15 = 15 %, assez permissif pour les scans).
        """
        threshold = max(int(img_w * min_span), 20)
        row_sums = np.sum(h_lines_mask > 128, axis=1)
        candidates = np.where(row_sums > threshold)[0]
        if len(candidates) == 0:
            return []

        bounds = []
        cluster = [int(candidates[0])]
        for y in candidates[1:]:
            if y - cluster[-1] <= 8:
                cluster.append(int(y))
            else:
                bounds.append(int(np.mean(cluster)))
                cluster = [int(y)]
        bounds.append(int(np.mean(cluster)))
        return bounds

    def _ocr_cell_technical(
        self,
        crop: np.ndarray,
        col_name: str,
        psm: int = 7,
    ) -> Tuple[str, int]:
        """
        OCR d'une cellule individuelle.
        - PSM 7 (ligne de texte) avec repli PSM 13 si aucun résultat
        - Désactive les dictionnaires linguistiques pour les colonnes de codes
        - Whitelist propre à la colonne
        """
        if crop is None or crop.size == 0:
            return '', 0
        h_c, w_c = crop.shape[:2]
        if h_c < 6 or w_c < 4:
            return '', 0

        # Upscale si trop petite (police illisible en dessous de 25 px)
        if h_c < 25:
            scale = max(2.0, 35 / h_c)
            crop = cv2.resize(
                crop, None, fx=scale, fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )

        # Padding pour éviter la coupure des bords de caractères
        crop = cv2.copyMakeBorder(
            crop, 4, 4, 6, 6, cv2.BORDER_CONSTANT, value=255
        )

        col_upper = col_name.upper()
        whitelist = self._COL_WHITELISTS.get(col_upper, '')

        # Colonnes de codes techniques → langue eng + sans dictionnaire
        _TECH_COLS = {
            'BORNE', 'JAR', 'JARRETIERES',
            'TENANT', 'ABOUTISSANT', 'COULEUR',
        }
        if col_upper in _TECH_COLS:
            lang = getattr(Config, 'OCR_LANGUAGE_TECHNICAL', 'eng')
        else:
            lang = self.language  # SIGNAL : texte français naturel

        config = f'--oem 3 --psm {psm} -l {lang}'
        if getattr(Config, 'OCR_DISABLE_DICT', True):
            config += ' -c load_system_dawg=0 -c load_freq_dawg=0'
        if whitelist:
            config += f' -c tessedit_char_whitelist={whitelist}'

        data = pytesseract.image_to_data(
            crop, config=config,
            output_type=pytesseract.Output.DICT,
        )
        words, confs = [], []
        for i in range(len(data['text'])):
            t = data['text'][i].strip()
            try:
                c = int(data['conf'][i])
            except (TypeError, ValueError):
                c = 0
            if t and c > 0:
                words.append(t)
                confs.append(c)

        if not words and psm == 7:
            # Repli PSM 13 (ligne brute, sans segmentation)
            return self._ocr_cell_technical(crop, col_name, psm=13)

        if not words:
            return '', 0
        return self._clean_cell(' '.join(words)), int(sum(confs) / len(confs))

    def _vote_cell(
        self,
        crop: np.ndarray,
        col_name: str,
    ) -> Tuple[str, int]:
        """
        Vote multi-passes pour une cellule.
        Passes : image originale · agrandi ×2 · seuillage adaptatif.
        Retourne le meilleur résultat selon la confiance et le patron de colonne.
        """
        if not getattr(Config, 'OCR_CELL_VOTE', True):
            return self._ocr_cell_technical(crop, col_name)

        candidates = []

        t1, c1 = self._ocr_cell_technical(crop, col_name)
        if t1:
            candidates.append((t1, c1))

        # Passe 2 : ×2
        enlarged = cv2.resize(
            crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC
        )
        t2, c2 = self._ocr_cell_technical(enlarged, col_name)
        if t2 and t2 != t1:
            candidates.append((t2, c2))

        # Passe 3 : seuillage adaptatif
        h_v, w_v = crop.shape[:2]
        if h_v > 12 and w_v > 8:
            try:
                adapt = cv2.adaptiveThreshold(
                    crop, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2,
                )
                t3, c3 = self._ocr_cell_technical(adapt, col_name)
                if t3 and t3 not in (t1, t2):
                    candidates.append((t3, c3))
            except Exception:
                pass

        if not candidates:
            return '', 0

        # Préférer les candidats conformes au patron, puis la meilleure confiance
        for text, conf in sorted(candidates, key=lambda x: -x[1]):
            if self._cell_matches_col_pattern(text, col_name):
                return text, conf
        return max(candidates, key=lambda x: x[1])

    def _extract_via_grid(
        self,
        clean_binary: np.ndarray,
        row_bounds: List[int],
        col_bounds: List[int],
        col_names: List[str],
        data_start_y: int = 0,
    ) -> List[Dict]:
        """
        Découpe chaque cellule (ligne × colonne) et OCR-ise individuellement.
        Retourne des dicts {'type': 'data', 'cells': [...], 'confidence': [...]}.

        data_start_y : première ordonnée après l'en-tête du tableau.
        """
        img_h, img_w = clean_binary.shape[:2]
        n_cols = len(col_names)

        # Intervalles verticaux (lignes de données)
        data_bnds = [y for y in row_bounds if y >= data_start_y]
        if not data_bnds:
            return []
        all_y = [data_start_y] + data_bnds + [img_h]
        row_intervals: List[Tuple[int, int]] = []
        for i in range(len(all_y) - 1):
            y0, y1 = all_y[i] + 1, all_y[i + 1] - 1
            if y1 - y0 >= 6:
                row_intervals.append((y0, y1))

        # Intervalles horizontaux (colonnes)
        col_intervals: List[Tuple[int, int]] = []
        for ci in range(n_cols):
            x0 = col_bounds[ci] + 1
            x1 = (col_bounds[ci + 1] - 1
                  if ci + 1 < len(col_bounds) else img_w - 1)
            col_intervals.append((max(0, x0), min(img_w, x1)))

        rows_out: List[Dict] = []
        for (y0, y1) in row_intervals:
            cells, confs = [], []
            for ci, (x0, x1) in enumerate(col_intervals):
                col_name = col_names[ci] if ci < len(col_names) else ''
                crop = clean_binary[y0:y1, x0:x1]
                text, conf = self._vote_cell(crop, col_name)
                # Marquer les cellules dont la confiance est faible ET dont le contenu
                # ne correspond pas au format de colonne — signale une relecture humaine.
                if (text
                        and conf < getattr(Config, 'OCR_REOCR_THRESHOLD', 60)
                        and not self._cell_matches_col_pattern(text, col_name)
                        and '[A_VERIFIER]' not in text):
                    text = text + ' [A_VERIFIER]'
                cells.append(text)
                confs.append(conf)
            if any(cells):
                rows_out.append({
                    'type': 'data',
                    'cells': cells,
                    'confidence': confs,
                })
            elif getattr(Config, 'OCR_PRESERVE_SPACING', True):
                rows_out.append({'type': 'blank', 'count': 1})
        return rows_out

    def _cell_matches_col_pattern(self, text: str, col_name: str) -> bool:
        """Retourne False si le contenu d'une cellule viole le patron attendu de la colonne.
        Une violation déclenche un re-OCR par bande ROI même si la cellule n'est pas vide.
        """
        if not text or not col_name:
            return True
        pat = self._COL_PATTERNS.get(col_name.upper())
        if pat is None:
            return True
        return bool(pat.match(text.strip()))

    # ------------------------------------------------------------------
    # Scoring adaptatif de réaffectation de colonnes
    # ------------------------------------------------------------------

    # Regex compilées une seule fois (classe, pas instance) pour le scoring JAR.
    _JAR_FULL_RE = re.compile(r'^\d{3,5}[A-Za-z]$')
    _JAR_DIGIT_RE = re.compile(r'^\d+$')

    def _col_format_score(self, text: str, col_name: str) -> float:
        """
        Évalue à quel point `text` ressemble au format attendu de `col_name`.

        Retourne un score 0.0–1.0 basé uniquement sur la forme du contenu,
        indépendamment de la position visuelle (weight = 25 %).
        """
        if not text:
            return 0.0
        col = col_name.upper()

        if col in ('JAR', 'JARRETIERES'):
            if self._JAR_FULL_RE.match(text.strip()):
                return 1.0
            if self._JAR_DIGIT_RE.match(text.strip()):
                return 0.7
            return 0.2

        if col == 'COULEUR':
            upper = text.strip().upper()
            if upper in self._COULEURS_FR:
                return 1.0
            # Mot court uniquement alphabétique → candidat couleur possible
            if len(upper) <= 8 and upper.isalpha():
                return 0.7
            return 0.3

        if col in ('BORNE', 'TENANT'):
            # Codes courts : 1–4 mots, chaque mot alphanumérique 1–6 chars
            parts = text.strip().split()
            if (1 <= len(parts) <= 4
                    and all(re.match(r'^[A-Za-z0-9\-/\.]{1,6}$', p) for p in parts)):
                return 0.9
            return 0.4

        if col == 'ABOUTISSANT':
            # 1 à 3 blocs alphanumériques séparés par espaces
            parts = text.strip().split()
            if 1 <= len(parts) <= 3:
                return 0.8
            return 0.4

        if col == 'SIGNAL':
            # Accepte quasi tout ; le minimum est 3 caractères
            return 0.8 if len(text.strip()) >= 3 else 0.5

        # Colonne inconnue : score neutre
        return 0.5

    def _col_length_score(self, text: str, col_name: str) -> float:
        """
        Évalue si la longueur de `text` est cohérente avec `col_name`.

        Retourne un score 0.0–1.0 (weight = 5 %).
        Les bornes sont douces : la décroissance est linéaire au-delà du plage normale.
        """
        if not text:
            return 0.0
        n = len(text.strip())
        col = col_name.upper()

        if col in ('JAR', 'JARRETIERES'):
            # Format canonique : 3–7 caractères (ex : "785N", "0836B")
            if 3 <= n <= 7:
                return 1.0
            return max(0.1, 1.0 - abs(n - 5) * 0.15)

        if col == 'SIGNAL':
            return 1.0 if n >= 2 else 0.3

        # BORNE, TENANT, COULEUR, ABOUTISSANT : 2–15 chars idéal
        if 2 <= n <= 15:
            return 1.0
        if n < 2:
            return 0.3
        # Au-delà de 15, décroissance progressive
        return max(0.1, 1.0 - (n - 15) * 0.05)

    def _col_dict_score(self, text: str, col_name: str) -> float:
        """
        Mesure la présence de `text` dans le dictionnaire OCR appris (lecture seule).

        Correspondance exacte → 1.0, préfixe commun ≥ 3 chars → 0.5, rien → 0.0.
        Weight = 15 %.
        """
        if not text:
            return 0.0
        stripped = text.strip().upper()
        known = get_dictionary().get_all(col_name.upper())
        if not known:
            return 0.0
        known_upper = [v.upper() for v in known]
        if stripped in known_upper:
            return 1.0
        # Correspondance par préfixe ≥ 3 chars
        prefix = stripped[:3]
        if any(v.startswith(prefix) for v in known_upper):
            return 0.5
        return 0.0

    def _col_visual_score(
        self,
        word_x: int,
        word_w: int,
        col_bounds: List[int],
        col_idx: int,
    ) -> float:
        """
        Mesure l'alignement visuel entre le mot et la zone de la colonne cible.

        Utilise les bornes pixel issues de `_col_boundaries()`.
        Weight = 40 %.

        Règles (de la plus forte à la plus faible) :
        - Mot entièrement contenu dans la zone → 1.0
        - Centroïde dans la zone              → 0.8
        - Bord gauche dans la zone             → 0.6
        - Hors zone                            → 0.1
        """
        x_left = word_x
        x_right = word_x + word_w
        cx = (x_left + x_right) / 2

        # Calculer les limites gauche/droite de la colonne cible
        c_left = col_bounds[col_idx]
        c_right = (col_bounds[col_idx + 1]
                   if col_idx + 1 < len(col_bounds)
                   else col_bounds[-1] + 9999)

        fully_inside = c_left <= x_left and x_right <= c_right
        if fully_inside:
            return 1.0
        centroid_inside = c_left <= cx < c_right
        if centroid_inside:
            return 0.8
        left_inside = c_left <= x_left < c_right
        if left_inside:
            return 0.6
        return 0.1

    def _col_coherence_score(
        self,
        text: str,
        col_name: str,
        neighbor_cells: List[List[str]],
        col_idx: int,
    ) -> float:
        """
        Évalue la cohérence de `text` avec les valeurs de la même colonne dans les
        lignes voisines déjà traitées.

        `neighbor_cells` : liste de listes de cellules (jusqu'à 3 lignes précédentes).
        Weight = 10 %.
        """
        if not neighbor_cells or not text:
            return 0.5   # score neutre quand pas d'historique
        col = col_name.upper()

        # Collecter les valeurs voisines pour cette colonne
        neighbor_vals = [
            row[col_idx].strip()
            for row in neighbor_cells
            if col_idx < len(row) and row[col_idx].strip()
        ]
        if not neighbor_vals:
            return 0.5

        if col in ('JAR', 'JARRETIERES'):
            # Vérifier la consécutivité des numéros de jarretières (±5)
            def _jar_num(s: str) -> Optional[int]:
                m = re.match(r'^(\d+)', s)
                return int(m.group(1)) if m else None

            cur = _jar_num(text.strip())
            if cur is None:
                return 0.3
            nums = [_jar_num(v) for v in neighbor_vals]
            nums = [n for n in nums if n is not None]
            if nums and any(abs(cur - n) <= 5 for n in nums):
                return 1.0
            return 0.3

        if col in ('BORNE', 'TENANT', 'ABOUTISSANT'):
            # Partager un préfixe de 2+ chars avec au moins un voisin → cohérent
            stripped = text.strip().upper()
            prefix2 = stripped[:2]
            for v in neighbor_vals:
                if v.upper().startswith(prefix2):
                    return 0.8
            return 0.4

        # SIGNAL, COULEUR, inconnues : score neutre
        return 0.5

    def _score_total(
        self,
        text: str,
        col_name: str,
        word_x: int,
        word_w: int,
        col_bounds: List[int],
        col_idx: int,
        neighbor_cells: Optional[List[List[str]]] = None,
    ) -> float:
        """
        Score pondéré combinant les 5 dimensions d'évaluation.

        Poids : visuel 40 %, format 25 %, dictionnaire 15 %, cohérence 10 %,
        longueur 5 %.  Le 5 % restant (non-perte) est géré dans `_rebalance_line`.
        """
        s_visual = self._col_visual_score(word_x, word_w, col_bounds, col_idx)
        s_format = self._col_format_score(text, col_name)
        s_dict = self._col_dict_score(text, col_name)
        s_coh = self._col_coherence_score(
            text, col_name, neighbor_cells or [], col_idx)
        s_len = self._col_length_score(text, col_name)

        return (
            0.40 * s_visual
            + 0.25 * s_format
            + 0.15 * s_dict
            + 0.10 * s_coh
            + 0.05 * s_len
        )

    def _rebalance_line(
        self,
        cells: List[str],
        confs: List[int],
        split_flags: List[bool],
        col_names: List[str],
        line_elems: List[Dict],
        bounds: List[int],
        neighbor_cells: Optional[List[List[str]]] = None,
    ) -> Tuple[List[str], List[int], List[bool], str, List[Dict]]:
        """
        Rééquilibre l'affectation des mots aux colonnes pour les mots situés
        en zone frontière entre deux colonnes adjacentes.

        L'affectation initiale issue de `_line_to_cells` est conservée sauf si
        un mot de bordure obtient un score nettement meilleur dans la colonne
        adjacente (différence > 0.25).

        Retourne (cells, confs, split_flags, confidence_label, alternatives) :
        - confidence_label : 'haute' | 'moyenne' | 'faible'
        - alternatives     : liste de dicts {col_idx, text, score} pour les mots
                             dont l'affectation était ambiguë (débogage)
        """
        n_cols = len(cells)
        # Pas de rebalancement si une seule colonne ou aucun élément
        if n_cols <= 1 or not line_elems or not bounds or len(bounds) < 2:
            return cells, confs, split_flags, 'haute', []

        new_cells = list(cells)
        new_confs = list(confs)
        new_splits = list(split_flags)
        alternatives: List[Dict] = []
        low_confidence_tokens: List[int] = []

        for elem in line_elems:
            x_start = elem.get('x', 0)
            word_w = elem.get('w', 1)
            text = elem.get('text', '').strip()
            if not text:
                continue

            # Identifier la colonne courante du mot (même logique que _line_to_cells)
            cur_col = n_cols - 1
            for i in range(len(bounds) - 1):
                if bounds[i] <= x_start < bounds[i + 1]:
                    cur_col = i
                    break

            # Largeur de la colonne courante (pour calculer le seuil de frontière)
            col_w = (
                (bounds[cur_col + 1] - bounds[cur_col])
                if cur_col + 1 < len(bounds)
                else (word_w * 5)   # estimation si pas de borne droite
            )
            border_threshold = col_w * 0.10   # 10 % de la largeur

            # Mot en zone limite gauche : possibilité de basculer vers col-1
            near_left = (x_start - bounds[cur_col]) < border_threshold
            # Mot en zone limite droite : possibilité de basculer vers col+1
            x_right = x_start + word_w
            right_bound = bounds[cur_col + 1] if cur_col + 1 < len(bounds) else x_right + 1
            near_right = (right_bound - x_right) < border_threshold

            if not (near_left or near_right):
                continue  # mot bien centré, pas de rebalancement nécessaire

            cur_col_name = col_names[cur_col] if cur_col < len(col_names) else ''
            score_cur = self._score_total(
                text, cur_col_name, x_start, word_w, bounds, cur_col, neighbor_cells)

            best_col = cur_col
            best_score = score_cur

            # Tester colonne de gauche
            if near_left and cur_col > 0 and not split_flags[cur_col - 1]:
                adj_name = col_names[cur_col - 1] if cur_col - 1 < len(col_names) else ''
                s = self._score_total(
                    text, adj_name, x_start, word_w, bounds, cur_col - 1, neighbor_cells)
                if s > best_score:
                    best_score = s
                    best_col = cur_col - 1

            # Tester colonne de droite
            if near_right and cur_col < n_cols - 1 and not split_flags[cur_col + 1]:
                adj_name = col_names[cur_col + 1] if cur_col + 1 < len(col_names) else ''
                s = self._score_total(
                    text, adj_name, x_start, word_w, bounds, cur_col + 1, neighbor_cells)
                if s > best_score:
                    best_score = s
                    best_col = cur_col + 1

            # Seuil de déplacement : le gain doit être significatif (> 0.25)
            # et la perte non totale (score_cur > 0.05) pour éviter de déplacer
            # un mot qui ne ressemble à rien dans les deux cas.
            MOVE_THRESHOLD = 0.25
            if best_col != cur_col and (best_score - score_cur) > MOVE_THRESHOLD:
                alternatives.append({
                    'col_from': cur_col,
                    'col_to': best_col,
                    'text': text,
                    'score_from': round(score_cur, 3),
                    'score_to': round(best_score, 3),
                })
                # Retirer le texte de l'ancienne colonne et l'ajouter dans la nouvelle
                old_val = new_cells[cur_col]
                # Supprimer uniquement ce token du texte source (pas toute la cellule)
                removed = re.sub(r'\b' + re.escape(text) + r'\b', '', old_val).strip()
                new_cells[cur_col] = removed
                new_cells[best_col] = (
                    (new_cells[best_col] + ' ' + text).strip()
                    if new_cells[best_col] else text
                )

                # Confiance ambiguë : signaler
                low_confidence_tokens.append(best_col)

            elif near_left or near_right:
                # Mot en frontière mais pas déplacé → score ambigu, signaler
                delta = best_score - score_cur
                if delta > 0.05:   # légèrement ambigu
                    low_confidence_tokens.append(cur_col)

        # Déterminer le niveau de confiance global
        n_ambiguous = len(set(low_confidence_tokens))
        if n_ambiguous == 0:
            confidence_label = 'haute'
        elif n_ambiguous <= 1:
            confidence_label = 'moyenne'
        else:
            confidence_label = 'faible'

        # Marquer les tokens ambigus si confiance faible (aide à la relecture)
        if confidence_label == 'faible':
            for ci in set(low_confidence_tokens):
                if 0 <= ci < len(new_cells) and new_cells[ci]:
                    if '[A_VERIFIER]' not in new_cells[ci]:
                        new_cells[ci] = new_cells[ci] + ' [A_VERIFIER]'

        return new_cells, new_confs, new_splits, confidence_label, alternatives

    # ------------------------------------------------------------------
    # Étape 3 : Regroupement en lignes
    # ------------------------------------------------------------------

    def _group_lines(self, elements: List[Dict]) -> List[List[Dict]]:
        """Regroupe les mots OCR en lignes horizontales."""
        if not elements:
            return []
        heights = [e['h'] for e in elements if e['h'] > 0]
        tol = max(8, int(np.median(heights) * 0.6)) if heights else 12

        sorted_elems = sorted(elements, key=lambda e: e['cy'])
        lines, cur_line = [], [sorted_elems[0]]
        cur_y = sorted_elems[0]['cy']

        for elem in sorted_elems[1:]:
            if abs(elem['cy'] - cur_y) <= tol:
                cur_line.append(elem)
                cur_y = int(np.mean([e['cy'] for e in cur_line]))
            else:
                lines.append(sorted(cur_line, key=lambda e: e['x']))
                cur_line = [elem]
                cur_y = elem['cy']
        lines.append(sorted(cur_line, key=lambda e: e['x']))
        return lines

    # ------------------------------------------------------------------
    # Étape 4 : Détection de l'en-tête et des frontières de colonnes
    # ------------------------------------------------------------------

    def _find_header_idx(self, lines: List[List[Dict]]) -> Optional[int]:
        """
        Trouve la ligne contenant les mots-clés de colonnes du modèle.

        Utilise des frontières de mot pour éviter les faux positifs :
        "JAR" ne doit pas matcher "JARRETIERES", ni "BORNE" matcher "BORNIER".
        """
        keywords = self._col_keywords

        def _kw_in_text(kw: str, text: str) -> bool:
            return bool(
                re.search(r'(?<![A-Z0-9])' + re.escape(kw) + r'(?![A-Z0-9])',
                          text)
            )

        for i, line in enumerate(lines):
            full = ' '.join(e['text'].upper() for e in line)
            hits = sum(
                1 for h in keywords
                if _kw_in_text(h, full)
                or any(_kw_in_text(h, e['text'].upper()) for e in line)
            )
            if hits >= max(2, len(keywords) // 2):
                return i
        return None

    def _col_boundaries(
        self, header_line: List[Dict], img_w: int
    ) -> Tuple[List[int], List[str]]:
        """
        Calcule les frontières de colonnes à partir des mots de l'en-tête.
        Retourne toujours (len(keywords)+1 bounds, keywords) — même si certains
        mots-clés sont absents de l'image, leurs positions sont interpolées
        linéairement entre les colonnes voisines détectées.
        """
        keywords = self._col_keywords
        n = len(keywords)

        # Chercher la position de chaque mot-clé dans l'en-tête
        # On mémorise cx (centre), mais aussi x_left et x_right (bords du mot).
        # Pour deux colonnes visuellement proches (ex. JARRETIERES/ABOUTISSANT),
        # utiliser le bord droit de la col i et le bord gauche de la col i+1
        # place la frontière dans le vide réel entre les deux mots.
        positions: Dict[str, int] = {}
        pos_left:  Dict[str, int] = {}   # bord gauche du mot dans l'en-tête
        pos_right: Dict[str, int] = {}   # bord droit  du mot dans l'en-tête
        for elem in header_line:
            up = elem['text'].upper()
            for hdr in keywords:
                if hdr in up and hdr not in positions:
                    positions[hdr] = elem['cx']
                    pos_left[hdr] = elem['x']
                    pos_right[hdr] = elem['x'] + elem['w']

        if len(positions) >= max(2, n // 2):
            # Liste de positions dans l'ordre du modèle (None si absent)
            pos_list: List[Optional[int]] = [positions.get(k) for k in keywords]
            known = [(i, p) for i, p in enumerate(pos_list) if p is not None]

            # Interpoler / extrapoler les positions manquantes
            for i in range(n):
                if pos_list[i] is not None:
                    continue
                left = [(ki, kp) for ki, kp in known if ki < i]
                right = [(ki, kp) for ki, kp in known if ki > i]
                if left and right:
                    li, lp = left[-1]
                    ri, rp = right[0]
                    pos_list[i] = int(lp + (rp - lp) * (i - li) / (ri - li))
                elif len(left) >= 2:
                    (li2, lp2), (li1, lp1) = left[-2], left[-1]
                    step = (lp1 - lp2) / max(li1 - li2, 1)
                    pos_list[i] = int(lp1 + step * (i - li1))
                elif len(right) >= 2:
                    (ri1, rp1), (ri2, rp2) = right[0], right[1]
                    step = (rp2 - rp1) / max(ri2 - ri1, 1)
                    pos_list[i] = int(rp1 - step * (ri1 - i))
                else:
                    pos_list[i] = img_w * i // n

            # ── Correction ordre visuel ───────────────────────────────────
            # Sur certains scans (ex : REPARTITEUR), les mots-clés de l'en-tête
            # apparaissent de droite à gauche par rapport à l'ordre du template.
            # Si pos_list n'est pas croissant, trier keywords + positions ensemble
            # pour que les frontières soient toujours monotones.
            detected_pos = [p for p in pos_list if p is not None]
            if detected_pos != sorted(detected_pos):
                pairs = sorted(
                    zip(keywords, pos_list),
                    key=lambda kp: kp[1] if kp[1] is not None else img_w,
                )
                keywords = [k for k, _ in pairs]
                pos_list = [p for _, p in pairs]
                # Reconstruire pos_left/pos_right dans le nouvel ordre
                pos_left = {
                    k: pos_left.get(k, (pos_list[i] or 0) - 15)
                    for i, k in enumerate(keywords)
                }
                pos_right = {
                    k: pos_right.get(k, (pos_list[i] or 0) + 15)
                    for i, k in enumerate(keywords)
                }

            bounds = [0]
            for i in range(n - 1):
                kw_i = keywords[i]
                kw_i1 = keywords[i + 1]
                x_r = pos_right.get(kw_i,  (pos_list[i] or 0) + 15)
                x_l = pos_left.get(kw_i1, (pos_list[i + 1] or img_w) - 15)
                if x_r < x_l:
                    # Gap visible entre les deux mots → frontière au milieu du gap
                    bounds.append((x_r + x_l) // 2)
                else:
                    # Mots qui se touchent → midpoint des centres (fallback)
                    bounds.append(
                        ((pos_list[i] or 0) + (pos_list[i + 1] or img_w)) // 2
                    )
            bounds.append(img_w)
            return bounds, list(keywords)

        # Repli : colonnes égales sur toute la largeur
        step = img_w // n
        return [i * step for i in range(n + 1)], list(keywords)

    # ------------------------------------------------------------------
    # Étape 5 : Classification des lignes
    # ------------------------------------------------------------------

    def _classify_line(self, line: List[Dict]) -> str:
        """Retourne 'section', 'footer' ou 'data' selon le modèle actif."""
        text = ' '.join(e['text'].upper() for e in line)
        # Version compacte sans espaces ni points — détecte "P . E . T ."
        # fragmenté par l'OCR en tokens séparés ("P", ".", "E", ".", "T", ".")
        text_compact = re.sub(r'[\s.]+', '', text)

        kw = self._tpl.section_keyword.upper()
        if kw in text or kw[:min(10, len(kw))] in text:
            return 'section'
        kw_words = [w for w in kw.split() if len(w) >= 3]
        if kw_words and all(w[:4] in text for w in kw_words):
            return 'section'

        if not self._tpl.has_footer:
            return 'data'

        for m in self._tpl.footer_detect_keywords:
            if m.upper() in text:
                return 'footer'
            # Vérification compacte : "P.E.T" → "PET" dans le texte sans espaces/points
            m_compact = re.sub(r'[\s.]+', '', m.upper())
            if len(m_compact) >= 3 and m_compact in text_compact:
                return 'footer'

        tokens = {e['text'].upper() for e in line}
        mti = set(t.upper() for t in self._tpl.footer_mti_tokens)
        if tokens <= (mti | {'|', '-', '.', ':'}):
            return 'footer'
        return 'data'

    # ------------------------------------------------------------------
    # Étape 6 : Affectation des mots aux colonnes
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_cell(val: str) -> str:
        """
        Supprime les artefacts OCR courants d'une valeur de cellule.

        - Retire |, [, ] en début/fin (séparateurs et crochets OCR)
        - Normalise O→0 dans les codes alphanumériques courts (ex: "O1K"→"01K")
        - Retourne '' si aucun caractère alphanumérique
        - Retourne '' si ≥ 5 caractères identiques consécutifs (bruit scanner)
        """
        if not val:
            return ''
        cleaned = val.strip()
        # Retirer les délimiteurs de tableau lus par OCR en bord de valeur
        for ch in ('|', '[', ']'):
            cleaned = cleaned.strip(ch)
        cleaned = cleaned.strip()
        if not cleaned:
            return ''
        # Correction des artefacts OCR universels (€→E, l→1 entre chiffres, etc.)
        cleaned = BornierTableExtractor._fix_common_ocr(cleaned)
        if not cleaned:
            return ''
        if not any(c.isalnum() for c in cleaned):
            return ''
        if re.search(r'(.)\1{4,}', cleaned):
            return ''
        # O/0 confusion dans les codes alphanumériques courts (≤ 12 chars par mot).
        # Ex: "O1K" → "01K", "O1A" → "01A" (suffixes de bornes électriques).
        # Sécurité : s'applique mot par mot, uniquement si le mot contient des chiffres.

        def _fix_o0(word: str) -> str:
            if len(word) > 12 or not any(c.isdigit() for c in word):
                return word
            # O en début de mot suivi d'un chiffre
            w = re.sub(r'^[Oo](?=\d)', '0', word)
            # O entre deux chiffres
            w = re.sub(r'(?<=\d)[Oo](?=\d)', '0', w)
            return w
        cleaned = ' '.join(_fix_o0(w) for w in cleaned.split())
        return cleaned

    # Table de remplacement des artefacts OCR Tesseract.
    # Toutes les valeurs sont en escape sequences ASCII pour eviter les
    # conversions automatiques de guillemets par l’editeur.
    _OCR_CHAR_FIXES: list = [
        ("€", "E"),   # euro -> E
        ("\xa3",   "E"),   # livre sterling -> E
        ("\xa2",   "C"),   # cent -> C
        ("\xa0",   " "),   # espace insecable -> espace normal
        ("’", "’"),   # guillemet courbe droit -> apostrophe droite
        ("Œ", "0"),   # OE ligature majuscule (Tesseract lit 0 comme Oe)
        ("œ", "0"),   # oe ligature minuscule
        ("\xc7",   "C"),   # C cedille -> C (codes industriels)
        ("\xe7",   "c"),   # c cedille -> c
    ]

    @staticmethod
    def _fix_common_ocr(val: str) -> str:
        """Corrige les artefacts OCR universels, independamment du contexte colonne."""
        if not val:
            return val
        for bad, good in BornierTableExtractor._OCR_CHAR_FIXES:
            val = val.replace(bad, good)
        # Degre (\xb0) -> 0 uniquement entre caracteres alphanumeriques
        val = re.sub("\xb0(?=\\w)", "0", val)
        val = re.sub("(?<=\\w)\xb0", "0", val)
        # l minuscule -> 1 dans les sequences numeriques
        val = re.sub(r"(?<=\d)l(?=\d)", "1", val)
        val = re.sub(r"(?<=\d)l\b", "1", val)
        val = re.sub(r"\bl(?=\d)", "1", val)
        return val

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Distance d'édition (Levenshtein) entre deux chaînes."""
        m, n = len(a), len(b)
        if m < n:
            a, b, m, n = b, a, n, m
        row = list(range(n + 1))
        for i in range(1, m + 1):
            prev, row[0] = row[0], i
            for j in range(1, n + 1):
                old = row[j]
                cost = 0 if a[i - 1] == b[j - 1] else 1
                row[j] = min(row[j] + 1, row[j - 1] + 1, prev + cost)
                prev = old
        return row[n]

    def _correct_by_col(self, val: str, col_name: str) -> str:
        """
        Corrections post-OCR spécifiques par type de colonne.
        Appelé après _clean_cell() — val est déjà débarrassé des délimiteurs.
        """
        if not val:
            return val
        col_up = col_name.upper()

        # ── COULEUR : correspondance floue sur vocabulaire restreint ────────
        if 'COULEUR' in col_up:
            # 0→O uniquement pour les couleurs (NOIR, ORANGE, etc. contiennent des lettres)
            candidate = self._fix_common_ocr(val.upper()).replace('0', 'O')
            if candidate in self._COULEURS_FR:
                return candidate
            best, best_d = None, 3
            for color in self._COULEURS_FR:
                d = self._levenshtein(candidate, color)
                if d < best_d:
                    best_d, best = d, color
            if best and best_d <= 2:
                return best
            return val

        # ── SIGNAL : 4 en tête de mot → A pour termes électriques connus ───
        if 'SIGNAL' in col_up:
            words = val.split()
            fixed = []
            for w in words:
                if w and w[0] == '4' and len(w) >= 3:
                    cand = 'A' + w[1:].upper()
                    if any(cand.startswith(pref) for pref in self._SIGNAL_A_STARTS):
                        w = 'A' + w[1:]
                fixed.append(w)
            return ' '.join(fixed)

        return val

    # ------------------------------------------------------------------
    # Mapping manuel colonnes/blocs (Config.MAX_AUTO_COLUMNS dépassé)
    # ------------------------------------------------------------------

    def _candidate_blocks_from_header(
        self, lines: List[List[Dict]], h_idx: int,
    ) -> List[Dict]:
        """Blocs bruts de la ligne d'en-tête, triés de gauche à droite."""
        return sorted(
            (
                {'text': e['text'], 'x': e['x'], 'x2': e['x'] + e['w']}
                for e in lines[h_idx]
            ),
            key=lambda b: b['x'],
        )

    def _resoudre_mapping_manuel(
        self, lines: List[List[Dict]], h_idx: int, image_path: Path,
    ) -> Optional[Dict[str, List[int]]]:
        """Déclenche (ou réutilise depuis le cache) le mapping manuel
        bloc→colonne quand le template dépasse Config.MAX_AUTO_COLUMNS.

        Le cache est clé sur les mots-clés du template courant : un seul
        appel au callback par template distinct pour tout le run — évite
        de redemander à chaque image d'un lot de plusieurs centaines.
        """
        n_cols_tpl = len(self._col_keywords)
        if n_cols_tpl <= Config.MAX_AUTO_COLUMNS or self._on_column_mapping is None:
            return None

        cache_key = tuple(self._col_keywords)
        if cache_key == self._cached_mapping_key:
            return self._cached_column_mapping

        candidate_blocks = self._candidate_blocks_from_header(lines, h_idx)
        mapping = self._on_column_mapping(
            candidate_blocks, list(self._tpl.columns), image_path
        )
        self._cached_column_mapping = mapping
        self._cached_mapping_key = cache_key
        return mapping

    @staticmethod
    def _block_bounds_from_candidates(
        candidate_blocks: List[Dict], img_w: int,
    ) -> List[int]:
        """Frontières pixel entre blocs bruts détectés (milieu des écarts)."""
        bounds = [0]
        for i in range(len(candidate_blocks) - 1):
            mid = (candidate_blocks[i]['x2'] + candidate_blocks[i + 1]['x']) // 2
            bounds.append(mid)
        bounds.append(img_w)
        return bounds

    def _build_row_via_mapping(
        self, line: List[Dict], candidate_blocks: List[Dict], img_w: int,
        mapping: Dict[str, List[int]], col_names: List[str],
    ) -> Tuple[List[str], List[int], List[bool]]:
        """Construit les cellules finales (n_cols_tpl) en fusionnant les
        blocs bruts détectés selon le mapping validé par l'utilisateur.

        Retourne (cellules, confiances, split_flags) — même forme que
        _line_to_cells() pour rester compatible avec le reste du pipeline.
        """
        block_bounds = self._block_bounds_from_candidates(candidate_blocks, img_w)
        n_blocks = len(candidate_blocks)
        raw_cells, raw_confs, _ = self._line_to_cells(line, block_bounds, n_blocks)

        cells, confs, split_flags = [], [], []
        for col_name in col_names:
            indices = mapping.get(col_name, [])
            texte = ' '.join(
                raw_cells[i] for i in indices if 0 <= i < n_blocks
            ).strip()
            texte = self._correct_by_col(texte, col_name)
            confs_i = [raw_confs[i] for i in indices if 0 <= i < n_blocks]
            cells.append(texte)
            confs.append(int(sum(confs_i) / len(confs_i)) if confs_i else 100)
            split_flags.append(False)
        return cells, confs, split_flags

    def _line_to_cells(
        self, line: List[Dict], bounds: List[int], n_cols: int,
        col_names: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[int], List[bool]]:
        """Affecte chaque mot à une colonne selon son bord gauche (x).

        Utiliser x (bord gauche) au lieu de cx (centre) évite qu'un mot
        large commençant dans une colonne soit attribué à la suivante.

        Découpage sur "|" : dans les tableaux répartiteurs, OCR fusionne
        parfois la valeur JAR et la valeur ABOUTISSANT en un seul token
        séparé par "|" (la ligne verticale lue comme caractère).
        On découpe systématiquement et on préfixe la partie droite dans
        la colonne suivante, même si elle contient déjà du texte.

        col_names : liste de noms de colonnes (optionnel) — active les
        corrections post-OCR spécifiques par colonne (_correct_by_col).

        Retourne (cellules_nettoyées, confiances, split_flags) :
        - confiance 0-100 par colonne (100 si vide)
        - split_flags[i] = True si la colonne i a été remplie par le split
          d'un token fusionné → ne pas re-OCR (la valeur vient déjà du split)
        """
        cells = [''] * n_cols
        conf_sum = [0] * n_cols
        conf_cnt = [0] * n_cols
        for elem in line:
            x_start = elem['x']
            col = n_cols - 1
            for i in range(len(bounds) - 1):
                if bounds[i] <= x_start < bounds[i + 1]:
                    col = i
                    break
            cells[col] = (cells[col] + ' ' + elem['text']).strip()
            conf_sum[col] += elem.get('conf', 0)
            conf_cnt[col] += 1

        # Découpage sur séparateurs OCR fréquents entre deux colonnes adjacentes.
        # La ligne verticale du tableau est souvent lue comme |, !, /, { ou [.
        # "0001R|B702A", "0006W!B702A", "0113R/{C105A" → JAR + ABOUTISSANT séparés.
        # On essaie d'abord les séparateurs explicites, puis un pattern regex
        # (chiffres+R/W immédiatement suivi d'une lettre majuscule) en dernier recours.
        _SEP_CHARS = ('|', '!', '/{', '/[', '/{', '{[')
        _JAR_RE = re.compile(r'^(\d{3,5}[RrWw])[^A-Za-z0-9]+([A-Z]\w)')
        split_flags = [False] * n_cols
        for i in range(n_cols - 1):
            cell = cells[i]
            left = right = None
            # Séparateurs explicites
            for sep in _SEP_CHARS:
                if sep in cell:
                    idx = cell.index(sep)
                    left = cell[:idx].strip()
                    right = cell[idx + len(sep):].strip().lstrip('[').lstrip(']').strip()
                    break
            # Regex : numéro jarretière collé à une référence borne (ex: "0006WB702A")
            if left is None:
                m = _JAR_RE.match(cell)
                if m:
                    cut = m.start(2)
                    left = cell[:cut].strip()
                    right = cell[cut:].strip()
            if left is not None and right:
                # Retirer les caractères non-alphanumériques parasites en tête du côté droit
                right = re.sub(r'^[^A-Za-z0-9]+', '', right)
                cells[i] = left
                # Les deux colonnes issues du split ne doivent pas être re-OCR-isées :
                # leur confiance héritée du token fusionné est sous-estimée.
                split_flags[i] = True
                if right:
                    cells[i + 1] = (right + ' ' + cells[i + 1]).strip() \
                                   if cells[i + 1] else right
                    split_flags[i + 1] = True

        cleaned = [self._clean_cell(c) for c in cells]
        if col_names:
            cleaned = [
                self._correct_by_col(v, col_names[i] if i < len(col_names) else '')
                for i, v in enumerate(cleaned)
            ]
        cell_confs = [
            int(conf_sum[i] / conf_cnt[i]) if conf_cnt[i] else 100
            for i in range(n_cols)
        ]
        return cleaned, cell_confs, split_flags

    # ------------------------------------------------------------------
    # Étape 7 : Extraction des métadonnées du pied de page
    # ------------------------------------------------------------------

    def _extract_meta(
        self, footer_lines: List[List[Dict]]
    ) -> Dict[str, str]:
        """
        Extrait BORNIER, PAGE, P.E.T., INDICE, NO_PLAN depuis le pied.

        Améliorations vs version précédente :
        - PET capture les noms multi-mots (ex: "EPEULE MONTESQUIEU")
        - BORNIER accepte des noms alphanumériques étendus (ex: "BOVKI", "B702A")
        - NO_PLAN capture le texte avant les pipes/INDICE
        """
        text = ' '.join(
            e['text'] for line in footer_lines for e in line
        ).upper()
        meta = {}
        patterns = [
            # P.E.T. : capture jusqu'au mot BORNIER ou fin de ligne
            ('PET', (
                r'P\.?E\.?T\.?\s*[:\s]+\s*'
                r'([A-Z][A-Z0-9\s]{1,40}?)'
                r'(?=\s+BORNIER|\s*\||$)'
            )),
            # BORNIER : nom alphanumérique avec tiret (ex: AA, B702A, Q3067TS, QC37V1)
            ('BORNIER', r'BORNIER\s*[:\s]+\s*([A-Z0-9][A-Z0-9\-]{1,14})'),
            # NO PLAN
            ('NO_PLAN', (
                r'(?:NO|N°)\s*PLAN\s*[:\s]+\s*'
                r'([\w\s]+?)(?=\s*\||\s*INDICE|$)'
            )),
            # INDICE : accepte chiffre ou lettre O (confusion OCR fréquente)
            ('INDICE', r'INDICE\s*[:\s]+\s*([0-9O])'),
            ('PAGE',   r'PAGE\s*[:\s]+\s*(\d+)'),
        ]
        for key, pat in patterns:
            m = re.search(pat, text)
            if m:
                meta[key] = m.group(1).strip()
        # Normaliser 'O' → '0' pour INDICE ; défaut à '0' si absent
        meta['INDICE'] = meta.get('INDICE', '0').replace('O', '0')

        # Champs personnalisés définis dans footer_extract_fields (ex: CABLE, TYPE)
        _standard = {'PET', 'BORNIER', 'NO_PLAN', 'INDICE', 'PAGE'}
        for fdef in self._tpl.footer_extract_fields:
            key = fdef.get('key', '').upper()
            label = fdef.get('label', '').upper()
            if not key or not label or key in _standard or key in meta:
                continue
            # Pattern générique : LABEL : VALEUR (jusqu'au pipe ou autre label)
            label_re = re.sub(r'\.', r'\\.?', re.escape(label))
            label_re = label_re.replace(r'\ ', r'\\s+')
            m = re.search(
                rf'{label_re}\s*[:\s]+\s*([A-Z0-9/][A-Z0-9\s\-/]{{0,50}}?)'
                rf'(?=\s*\||\s*[A-Z]{{3,}}\s*[:\s]|$)',
                text
            )
            if m:
                meta[key] = m.group(1).strip()

        return meta

    def _count_data_rows(self, result: Dict) -> int:
        """Retourne le nombre de lignes de données (type 'data') du résultat."""
        return sum(
            1 for r in result.get('rows', []) if r.get('type') == 'data'
        )

    @staticmethod
    def _compute_blur_score(image_path: Path) -> float:
        """
        Calcule le pourcentage de flou via la variance Laplacienne.
        Retourne entre 0.0 (image nette) et 100.0 (très floue).
        """
        img = cv2.imread(str(image_path))
        if img is None:
            return 0.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        threshold = 100.0
        blur_pct = max(
            0.0,
            min(100.0, (1.0 - min(variance, threshold) / threshold) * 100.0)
        )
        return round(blur_pct, 1)

    # ------------------------------------------------------------------
    # Journal debug OCR
    # ------------------------------------------------------------------

    def _write_ocr_log(
        self,
        image_path: Path,
        elements: List[Dict],
        lines: List[List[Dict]],
        bounds: List[int],
        col_names: List[str],
        detection_method: str,
        rows: List[Dict],
        blur_pct: float,
    ) -> None:
        """Écrit le journal détaillé de ce que Tesseract a vu pour cette image.

        Activé via Config.OCR_DEBUG_LOG = True.
        Fichier : Config.OCR_DEBUG_LOG_PATH ou 'ocr_debug.log' dans le répertoire courant.
        """
        import datetime
        log_path = (
            Path(Config.OCR_DEBUG_LOG_PATH)
            if Config.OCR_DEBUG_LOG_PATH
            else Path.cwd() / 'ocr_debug.log'
        )
        with open(log_path, 'a', encoding='utf-8') as f:
            sep = '─' * 72
            f.write(f'\n{sep}\n')
            f.write(f'Image : {image_path.name}   '
                    f'[{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]\n')
            f.write(f'Flou  : {blur_pct:.1f}%   '
                    f'Méthode colonnes : {detection_method}\n')
            f.write(f'Colonnes détectées : {col_names}\n')
            f.write(f'Frontières (px)    : {bounds}\n')
            f.write(f'{sep}\n')

            f.write('── TEXTE BRUT TESSERACT (tous les mots, avec confiance) ──\n')
            for elem in elements:
                f.write(
                    f'  [{elem["conf"]:3d}%] '
                    f'x={elem["x"]:4d} y={elem["y"]:4d} '
                    f'w={elem["w"]:3d} h={elem["h"]:2d}  '
                    f'"{elem["text"]}"\n'
                )

            f.write('── LIGNES REGROUPÉES ──\n')
            for i, line in enumerate(lines):
                words = [(e['text'], e['conf']) for e in line]
                f.write(f'  Ligne {i+1:2d}: '
                        + '  '.join(f'"{w}"({c}%)' for w, c in words) + '\n')

            f.write('── AFFECTATION FINALE PAR COLONNE ──\n')
            for j, row in enumerate(rows):
                if row['type'] == 'data':
                    confs = row.get('confidence', [])
                    pairs = [
                        f'{col_names[k] if k < len(col_names) else "?"}='
                        f'"{row["cells"][k]}"({confs[k] if k < len(confs) else "?"}%)'
                        for k in range(len(row['cells']))
                    ]
                    f.write(f'  Ligne {j+1:2d}: ' + '  |  '.join(pairs) + '\n')
                elif row['type'] == 'section':
                    f.write(f'  Section : "{row["text"]}"\n')
            f.write(f'{sep}\n')

    # ------------------------------------------------------------------
    # Reconstruction de l'espacement intra-cellule
    # ------------------------------------------------------------------

    def _reconstruct_intra_cell_spacing(
        self,
        line: List[Dict],
        bounds: List[int],
        n_cols: int,
        cells: List[str],
    ) -> List[str]:
        """
        Insère des espaces proportionnels entre les mots d'une même colonne.

        Objectif : reproduire l'espacement visuel entre les sous-blocs d'une colonne
        (ex: TENANT = "TGV   TE203A   C12" plutôt que "TGV TE203A C12").

        Condition de sécurité : la reconstruction n'est appliquée que si le nombre
        de mots OCR originaux correspond au nombre de tokens dans la cellule corrigée
        — évite les reconstructions incohérentes après rebalancement ou re-OCR.
        """
        if not getattr(Config, 'OCR_PRESERVE_INTRA_CELL_SPACING', True):
            return cells

        # Regrouper les mots OCR par colonne selon le bord gauche (x)
        col_elems: List[List[Dict]] = [[] for _ in range(n_cols)]
        for elem in line:
            x_start = elem['x']
            col = n_cols - 1
            for i in range(len(bounds) - 1):
                if bounds[i] <= x_start < bounds[i + 1]:
                    col = i
                    break
            col_elems[col].append(elem)

        new_cells = list(cells)
        for ci in range(n_cols):
            elems = sorted(col_elems[ci], key=lambda e: e['x'])
            if len(elems) <= 1 or not cells[ci]:
                continue

            corrected_tokens = cells[ci].split()
            if len(corrected_tokens) != len(elems):
                # Nombre de tokens modifié par corrections — reconstruction non fiable
                continue

            # Largeur moyenne d'un caractère dans cette zone de colonne
            char_widths = [
                e['w'] / max(len(e['text']), 1)
                for e in elems if e['text'].strip()
            ]
            if not char_widths:
                continue
            avg_cw = max(1.0, float(np.mean(char_widths)))

            # Reconstruction avec espacement proportionnel (plafonné à 12 espaces)
            parts = [corrected_tokens[0]]
            for j in range(1, len(elems)):
                prev_e = elems[j - 1]
                curr_e = elems[j]
                pixel_gap = curr_e['x'] - (prev_e['x'] + prev_e['w'])
                n_sp = max(1, min(12, round(pixel_gap / avg_cw)))
                parts.append(' ' * n_sp)
                parts.append(corrected_tokens[j])

            new_cells[ci] = ''.join(parts)

        return new_cells

    # ------------------------------------------------------------------
    # Détection TATR (Microsoft Table Transformer) — optionnelle
    # ------------------------------------------------------------------

    def _load_tatr(self) -> bool:
        """
        Charge le modèle TATR une seule fois par session (cache de classe).
        Retourne True si le modèle est prêt, False si indisponible.
        """
        if BornierTableExtractor._tatr_available is not None:
            return BornierTableExtractor._tatr_available
        try:
            from transformers import (
                AutoImageProcessor,
                TableTransformerForObjectDetection,
            )
            from config import Config
            name = getattr(Config, 'TATR_MODEL_NAME',
                           'microsoft/table-transformer-structure-recognition')
            BornierTableExtractor._tatr_processor = (
                AutoImageProcessor.from_pretrained(name)
            )
            BornierTableExtractor._tatr_model = (
                TableTransformerForObjectDetection.from_pretrained(name)
            )
            BornierTableExtractor._tatr_model.eval()
            BornierTableExtractor._tatr_available = True
            logger.info("✓ TATR chargé — détection de colonnes IA activée")
        except Exception as exc:
            BornierTableExtractor._tatr_available = False
            logger.debug(f"TATR non disponible : {exc}")
        return BornierTableExtractor._tatr_available

    def _detect_col_bounds_tatr(
        self, image_path: Path, img_w: int, n_cols: int
    ) -> Optional[List[int]]:
        """
        Détecte les frontières de colonnes via Microsoft Table Transformer.

        Algorithme histogramme de couverture :
        - Chaque boîte TATR ajoute son score à tous les pixels qu'elle couvre.
        - Les n_cols-1 vallées les plus profondes de l'histogramme lissé
          correspondent aux espaces entre colonnes réelles.
        - Si l'histogramme est trop plat (< 15 % de variation), TATR n'apporte
          pas d'information utile → retourne None, morpho/weighted prend le relais.

        Retourne None si TATR est désactivé, non installé, ou échoue.
        """
        from config import Config
        if not getattr(Config, 'USE_TATR', False):
            return None
        if not self._load_tatr():
            return None

        try:
            import torch
            from PIL import Image as PILImage

            model = BornierTableExtractor._tatr_model
            processor = BornierTableExtractor._tatr_processor
            # Seuil bas pour récupérer le maximum de fragments TATR
            conf = max(0.1, getattr(Config, 'TATR_CONFIDENCE', 0.5) - 0.2)

            pil_img = PILImage.open(str(image_path)).convert("RGB")
            orig_w, orig_h = pil_img.size
            inputs = processor(images=pil_img, return_tensors="pt")

            with torch.no_grad():
                outputs = model(**inputs)

            target_sizes = torch.tensor([[orig_h, orig_w]])
            results = processor.post_process_object_detection(
                outputs, threshold=conf, target_sizes=target_sizes
            )[0]

            # Identifier le label "table column" (hors en-tête)
            col_label_id = None
            for lid, lname in model.config.id2label.items():
                if 'column' in lname.lower() and 'header' not in lname.lower():
                    col_label_id = lid
                    break
            if col_label_id is None:
                return None

            # Collecter les segments (x1, x2, score)
            segments: List[Tuple[float, float, float]] = []
            for score, label, box in zip(
                results['scores'], results['labels'], results['boxes']
            ):
                if label.item() == col_label_id:
                    x1, _, x2, _ = box.tolist()
                    segments.append((x1, x2, float(score)))

            if len(segments) < 2:
                return None

            # Mise à l'échelle PIL → image binarisée redimensionnée
            scale = img_w / orig_w

            # ── Histogramme de couverture pondéré ────────────────────────
            # Chaque pixel reçoit la somme des scores des boîtes qui le couvrent.
            # Les endroits peu couverts = espaces entre colonnes réelles.
            coverage = np.zeros(img_w, dtype=np.float32)
            for x1, x2, sc in segments:
                xi1 = max(0, int(x1 * scale))
                xi2 = min(img_w, int(x2 * scale))
                if xi2 > xi1:
                    coverage[xi1:xi2] += sc

            # Lissage : fenêtre mobile ~2 % de la largeur
            smooth_k = max(3, img_w // 50)
            if smooth_k % 2 == 0:
                smooth_k += 1
            coverage = np.convolve(
                coverage, np.ones(smooth_k) / smooth_k, mode='same'
            )

            # ── Critère de qualité : histogramme doit avoir des vallées nettes ─
            # Si la variation est < 15 % du maximum, l'histogramme est trop plat
            # → TATR ne peut pas localiser les frontières → retourner None.
            lo = img_w // 20        # 5 % depuis le bord gauche
            hi = img_w - img_w // 20  # 5 % depuis le bord droit
            region = coverage[lo:hi]
            r_max = float(region.max())
            r_min = float(region.min())
            if r_max == 0 or (r_max - r_min) < r_max * 0.15:
                logger.debug(
                    f"TATR ({image_path.name}) : histogramme plat "
                    f"(var={r_max - r_min:.2f}) → repli"
                )
                return None

            # ── Détection des n_cols-1 vallées les plus profondes ────────
            n_valleys = n_cols - 1
            min_sep = max(1, img_w // 20)   # 5 % de largeur min entre vallées
            valleys: List[int] = []
            used = np.zeros(len(region), dtype=bool)

            for _ in range(n_valleys):
                temp = region.copy()
                temp[used] = r_max + 1.0
                idx = int(np.argmin(temp))
                valleys.append(lo + idx)
                # Masquer la zone autour de cette vallée
                i_lo = max(0, idx - min_sep)
                i_hi = min(len(used), idx + min_sep + 1)
                used[i_lo:i_hi] = True

            if len(valleys) < n_valleys:
                return None

            valleys.sort()
            bounds = [0] + valleys + [img_w]

            if len(bounds) != n_cols + 1:
                return None

            logger.debug(
                f"TATR histogramme : {n_cols} colonnes, "
                f"frontières={valleys} dans {image_path.name}"
            )
            return bounds

        except Exception as exc:
            logger.debug(f"TATR erreur ({image_path.name}) : {exc}")
            return None

    def _detect_col_bounds_morpho(
        self, binary: np.ndarray, img_w: int, n_cols: int
    ) -> Optional[List[int]]:
        """
        Détecte les frontières de colonnes via les lignes verticales du tableau.
        Essaie 4 hauteurs de noyau progressivement plus courtes (h//3 → h//6)
        pour détecter les lignes partielles ou atténuées sur les scans.
        Retourne [0, x1, …, img_w] dès que n_cols-1 séparateurs sont trouvés,
        sinon None.
        """
        h = binary.shape[0]
        inverted = cv2.bitwise_not(binary)

        # Essai progressif : noyau strict (h//3) → très souple (h//15)
        # Les valeurs basses permettent de détecter des lignes courtes ou
        # partielles sur des pages dont le tableau ne couvre que la moitié.
        for kern_h in [max(10, h // 3), max(10, h // 4), max(8, h // 5),
                       max(6, h // 6), max(4, h // 10), max(3, h // 15)]:
            kern_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kern_h))
            mask = cv2.erode(inverted, kern_v, iterations=1)
            mask = cv2.dilate(mask, kern_v, iterations=2)

            projection = np.sum(mask, axis=0).astype(np.float32)
            projection = np.convolve(projection, np.ones(5) / 5, mode='same')

            if projection.max() == 0:
                continue
            # Seuil abaissé à 0.25 pour capturer les lignes plus légères
            threshold_v = projection.max() * 0.25
            cur_peaks: List[int] = []
            in_peak, peak_start = False, 0
            for i, val in enumerate(projection):
                if val >= threshold_v and not in_peak:
                    in_peak, peak_start = True, i
                elif val < threshold_v and in_peak:
                    in_peak = False
                    cur_peaks.append((peak_start + i) // 2)

            inner = [p for p in cur_peaks if img_w * 0.05 < p < img_w * 0.95]
            if len(inner) >= n_cols - 1:
                inner = sorted(inner)
                if len(inner) > n_cols - 1:
                    step = (len(inner) - 1) / max(n_cols - 2, 1)
                    inner = [inner[int(round(i * step))] for i in range(n_cols - 1)]
                return [0] + inner + [img_w]

        return None

    def _detect_col_bounds_whitespace(
        self, elements: List[Dict], img_w: int, n_cols: int
    ) -> Optional[List[int]]:
        """
        Détecte les frontières de colonnes par analyse des zones sans texte.

        Construit un histogramme horizontal de densité de texte, puis repère
        les n_cols-1 vallées les plus profondes (= espaces entre colonnes).
        Utilisé en repli entre la détection morphologique et la pondération
        par largeur de template.

        Retourne None si le texte est uniformément distribué (pas de séparation
        nette détectable).
        """
        if not elements or img_w < 100:
            return None

        density = np.zeros(img_w, dtype=np.float32)
        for elem in elements:
            x1 = max(0, elem['x'])
            x2 = min(img_w, elem['x'] + elem['w'])
            if x2 > x1:
                density[x1:x2] += 1

        smooth_k = max(3, img_w // 60)
        if smooth_k % 2 == 0:
            smooth_k += 1
        density = np.convolve(density, np.ones(smooth_k) / smooth_k, mode='same')

        # Zone intérieure uniquement (5 % à 95 %) pour éviter les bords
        lo, hi = img_w // 20, img_w - img_w // 20
        region = density[lo:hi]
        r_max = float(region.max())
        if r_max == 0:
            return None

        # Si le texte est trop uniformément distribué, les vallées sont peu marquées
        if float(region.min()) > r_max * 0.65:
            return None

        n_valleys = n_cols - 1
        min_sep = max(1, img_w // 20)
        valleys: List[int] = []
        used = np.zeros(len(region), dtype=bool)

        for _ in range(n_valleys):
            temp = region.copy()
            temp[used] = r_max + 1.0
            idx = int(np.argmin(temp))
            valleys.append(lo + idx)
            i_lo = max(0, idx - min_sep)
            i_hi = min(len(used), idx + min_sep + 1)
            used[i_lo:i_hi] = True

        if len(valleys) < n_valleys:
            return None

        valleys.sort()
        bounds = [0] + valleys + [img_w]
        if len(bounds) != n_cols + 1:
            return None
        return bounds

    def _detect_col_bounds_hough(
        self, binary: np.ndarray, img_w: int, n_cols: int
    ) -> Optional[List[int]]:
        """
        Détecte les frontières de colonnes via la transformée de Hough probabiliste.
        Repli entre morpho et whitespace : fonctionne sur les lignes légères,
        tiretées ou couvrant seulement une partie de la hauteur de page.
        """
        h = binary.shape[0]
        inverted = cv2.bitwise_not(binary)
        edges = cv2.Canny(inverted, 30, 100, apertureSize=3)

        # Longueur minimale : 1/8 de la hauteur (souple pour tableaux partiels)
        min_len = max(20, h // 8)
        lines = cv2.HoughLinesP(
            edges, rho=1, theta=np.pi / 180,
            threshold=60,
            minLineLength=min_len,
            maxLineGap=max(10, h // 25),
        )
        if lines is None:
            return None

        # Garder uniquement les lignes quasi-verticales (pente > 3:1 h/v)
        v_xs = []
        for seg in lines:
            x1, y1, x2, y2 = seg[0]
            dy = abs(y2 - y1)
            dx = abs(x2 - x1)
            if dy > 0 and dx / dy < 0.35:
                v_xs.append((x1 + x2) // 2)

        if not v_xs:
            return None

        # Clustering par proximité (tolérance 1 % de la largeur)
        v_xs.sort()
        tol = max(8, img_w // 80)
        clusters: List[int] = []
        cur = [v_xs[0]]
        for x in v_xs[1:]:
            if x - cur[-1] <= tol:
                cur.append(x)
            else:
                clusters.append(int(np.mean(cur)))
                cur = [x]
        clusters.append(int(np.mean(cur)))

        # Filtrer les bords (5 % de chaque côté)
        inner = sorted(x for x in clusters if img_w * 0.05 < x < img_w * 0.95)

        if len(inner) >= n_cols - 1:
            inner = inner[:n_cols - 1]
            return [0] + inner + [img_w]
        return None

    def _col_boundaries_fused(
        self,
        header_line: List[Dict],
        img_w: int,
        tatr_bounds: List[int],
    ) -> Tuple[List[int], List[str]]:
        """
        Fusionne les frontières TATR avec les positions OCR de l'en-tête.

        Stratégie frontière par frontière :
        - Si les deux mots-clés adjacents sont trouvés ET qu'un gap visible
          sépare leurs bords → mid-gap (précision OCR maximale).
        - Sinon → frontière TATR (robustesse structurelle).

        Avantage clé : TATR sépare visuellement les colonnes très proches
        (JARRETIERES / ABOUTISSANT) même quand l'OCR les fusionne en un bloc.
        """
        keywords = self._col_keywords
        n = len(keywords)

        pos_left:  Dict[str, int] = {}
        pos_right: Dict[str, int] = {}
        for elem in header_line:
            up = elem['text'].upper()
            for hdr in keywords:
                if hdr in up and hdr not in pos_left:
                    pos_left[hdr] = elem['x']
                    pos_right[hdr] = elem['x'] + elem['w']

        bounds = [0]
        for i in range(n - 1):
            kw_i = keywords[i]
            kw_i1 = keywords[i + 1]

            # Gap OCR visible entre les deux mots → frontière précise
            if kw_i in pos_right and kw_i1 in pos_left:
                x_r = pos_right[kw_i]
                x_l = pos_left[kw_i1]
                if x_r < x_l:
                    bounds.append((x_r + x_l) // 2)
                    continue

            # Sinon : frontière TATR (structure visuelle)
            bounds.append(tatr_bounds[i + 1])

        bounds.append(img_w)
        return bounds, list(keywords)

    # ------------------------------------------------------------------
    # Pipeline principal
    # ------------------------------------------------------------------

    def extract(self, image_path: Path, feedback: str = None) -> Dict:
        """
        Extraction complète : image → dict structuré.

        Pipeline :
          1. Prétraitement (redimensionnement, binarisation, deskew)
          2. TATR (étape 2.5) — avant l'OCR, frontières visuelles brutes
          3. OCR Tesseract (PSM 6, repli PSM 4)
          4. Regroupement en lignes, détection de l'en-tête
          5. Frontières finales :
               TATR + en-tête → fusion (meilleur des deux mondes)
               en-tête seul   → bords des mots-clés
               TATR seul      → histogramme de couverture
               morpho         → lignes verticales
               weighted       → proportionnel aux largeurs du modèle
          6. Classification et affectation des mots aux colonnes
          7. Extraction des métadonnées du pied de page

        Retourne:
            success          : bool
            headers          : liste des noms de colonnes
            rows             : liste de dicts {'type': 'data'|'section', ...}
            metadata         : dict BORNIER, PAGE, PET, INDICE, NO_PLAN
            detection_method : 'header' | 'tatr' | 'morpho' | 'weighted'
                               | 'claude-vision' | 'docling'
        """
        # ── Délégation vers les moteurs alternatifs ────────────────────────
        _mode = getattr(Config, 'OCR_MODE', 'tesseract').lower().strip()
        if _mode == 'claude':
            from claude_ocr import ClaudeVisionExtractor
            return ClaudeVisionExtractor(self._tpl).extract(image_path)
        elif _mode == 'docling':
            from docling_ocr import DoclingExtractor
            return DoclingExtractor(self._tpl).extract(image_path)
        # ── Suite : pipeline Tesseract (défaut) ────────────────────────────
        # Sauvegarder le template original pour le restaurer après l'appel.
        # L'auto-détection (bloc "h_idx is None") peut muter self._tpl et
        # self._col_keywords pour cette image — sans restauration, toutes les
        # images suivantes de la même session hériteraient du template détecté.
        _orig_tpl = self._tpl
        _orig_kws = self._col_keywords
        try:
            blur_pct = self._compute_blur_score(image_path)
            binary, img_w = self._preprocess(image_path)
            n_cols_tpl = len(self._col_keywords)

            # ── Étape 2 : OCR ─────────────────────────────────────────────
            elements = self._ocr_elements(binary)
            if len(elements) < 10:
                elements = self._ocr_elements(binary, psm=4)
            if not elements:
                return {'success': False, 'error': 'Aucun texte détecté'}

            lines = self._group_lines(elements)
            h_idx = self._find_header_idx(lines)

            # Auto-détection du template : si l'en-tête ne correspond pas au
            # template sélectionné, essayer tous les templates connus.
            # Cas typique : image REPARTITEUR traitée avec template "Bornier standard".
            if h_idx is None:
                try:
                    from template import TemplateManager as _TM
                    for _tpl in _TM()._templates.values():
                        if _tpl.columns == self._tpl.columns:
                            continue
                        _kws = [c.upper() for c in _tpl.columns]
                        for _i, _line in enumerate(lines):
                            _full = ' '.join(e['text'].upper() for e in _line)
                            _hits = sum(
                                1 for k in _kws
                                if k in _full or any(k in e['text'].upper() for e in _line)
                            )
                            if _hits >= max(2, len(_kws) // 2):
                                # Meilleur template trouvé → on bascule dessus
                                self._tpl = _tpl
                                self._col_keywords = _kws
                                h_idx = _i
                                break
                        if h_idx is not None:
                            break
                except Exception:
                    pass

            # ── Étape 2b : mapping manuel si trop de colonnes template ─────
            manual_mapping = None
            if h_idx is not None:
                manual_mapping = self._resoudre_mapping_manuel(
                    lines, h_idx, image_path
                )

            # ── Étape 3 : frontières de colonnes ──────────────────────────
            # Priorité : en-tête OCR > TATR > morpho > pondéré
            # L'en-tête donne les meilleures frontières quand il est lisible.
            # TATR n'intervient qu'en repli car il produit des zones erronées
            # sur les tableaux à colonnes étroites (JAR. ≈ 12 % de la largeur).
            if h_idx is not None:
                bounds, col_names = self._col_boundaries(
                    lines[h_idx], img_w
                )
                detection_method = 'header'
                data_lines = lines[h_idx + 1:]

            else:
                col_names = list(self._col_keywords)
                tatr_bounds = self._detect_col_bounds_tatr(
                    image_path, img_w, n_cols_tpl
                )
                if tatr_bounds is not None:
                    bounds = tatr_bounds
                    detection_method = 'tatr'
                else:
                    morph_bounds = self._detect_col_bounds_morpho(
                        binary, img_w, n_cols_tpl
                    )
                    if morph_bounds is not None:
                        bounds = morph_bounds
                        detection_method = 'morpho'
                    else:
                        hough_bounds = self._detect_col_bounds_hough(
                            binary, img_w, n_cols_tpl
                        )
                        if hough_bounds is not None:
                            bounds = hough_bounds
                            detection_method = 'hough'
                        else:
                            ws_bounds = self._detect_col_bounds_whitespace(
                                elements, img_w, n_cols_tpl
                            )
                            if ws_bounds is not None:
                                bounds = ws_bounds
                                detection_method = 'whitespace'
                            else:
                                col_ws = [self._tpl.col_width(k) for k in col_names]
                                total_w = sum(col_ws) or n_cols_tpl
                                cum = 0
                                bounds = [0]
                                for cw in col_ws[:-1]:
                                    cum += cw
                                    bounds.append(int(img_w * cum / total_w))
                                bounds.append(img_w)
                                detection_method = 'weighted'
                data_lines = lines

            n_cols = len(col_names)
            rows: List[Dict] = []
            footer_lines: List[List[Dict]] = []

            # ── Mode grille : OCR cellule par cellule ──────────────────
            # Tentative : supprimer les traits, détecter les séparateurs de
            # lignes, puis OCR-iser chaque cellule individuellement avec PSM 7.
            # Si la grille n'est pas détectée (< 3 séparateurs), on bascule
            # automatiquement vers l'approche classique (mots + positions).
            _used_grid = False
            if getattr(Config, 'OCR_CELL_BY_CELL', True):
                try:
                    clean_bin, lines_mask = self._remove_table_lines(binary)
                    row_bnds = self._detect_row_bounds(lines_mask, img_w)

                    # Calculer data_start_y avant le filtre
                    data_start_y = 0
                    if (h_idx is not None
                            and h_idx < len(lines)
                            and lines[h_idx]):
                        data_start_y = max(
                            e['y'] + e['h'] for e in lines[h_idx]
                        )

                    # N'activer le mode grille que si les séparateurs sont
                    # bien répartis DANS la zone de données (pas seulement
                    # en bas dans le footer). Condition : au moins 5
                    # séparateurs entre data_start_y et 90 % de la hauteur.
                    img_h_px = binary.shape[0]
                    data_zone = [
                        y for y in row_bnds
                        if data_start_y < y < img_h_px * 0.88
                    ]

                    if len(data_zone) >= 5:
                        grid_rows = self._extract_via_grid(
                            clean_bin, row_bnds, bounds,
                            col_names, data_start_y,
                        )
                        if len(grid_rows) >= 2:
                            rows = grid_rows
                            _used_grid = True
                            # Collecter quand même les pieds de page
                            for line in data_lines:
                                if self._classify_line(line) == 'footer':
                                    footer_lines.append(line)
                except Exception as _grid_err:
                    logger.debug(
                        f"Mode grille désactivé ({_grid_err}) — repli classique"
                    )

            if not _used_grid:
                # Blocs bruts de l'en-tête — utilisés uniquement si un mapping
                # manuel est actif (fusion des blocs vers les colonnes finales)
                header_blocks = (
                    self._candidate_blocks_from_header(lines, h_idx)
                    if manual_mapping is not None and h_idx is not None
                    else None
                )
                # Préparation de la détection des écarts verticaux entre blocs
                _preserve_sp = getattr(Config, 'OCR_PRESERVE_SPACING', True)
                _prev_data_y_max = None
                if _preserve_sp and elements:
                    _all_h = [e['h'] for e in elements if e['h'] > 0]
                    _med_h = int(np.median(_all_h)) if _all_h else 0
                    _sp_thr = getattr(Config, 'OCR_SPACING_THRESHOLD', 1.6) * _med_h
                else:
                    _med_h, _sp_thr = 0, 0

                for line in data_lines:
                    ltype = self._classify_line(line)
                    if ltype == 'footer':
                        footer_lines.append(line)
                    elif ltype == 'section':
                        rows.append({
                            'type': 'section',
                            'text': ' '.join(e['text'] for e in line)
                        })
                    else:
                        # Détection de l'écart vertical avec la ligne de données précédente
                        if _sp_thr > 0 and _prev_data_y_max is not None:
                            _cur_y_min = min(e['y'] for e in line)
                            _gap = _cur_y_min - _prev_data_y_max
                            if _gap > _sp_thr:
                                _n_blanks = min(3, max(1, round(_gap / _med_h) - 1))
                                rows.append({'type': 'blank', 'count': _n_blanks})

                        if manual_mapping is not None and header_blocks:
                            # Mapping manuel actif : les colonnes finales sont
                            # une fusion de blocs bruts choisie par l'utilisateur.
                            # bounds (pixel template) ne correspond plus à cette
                            # structure — rebalance/re-OCR/reconstruct-spacing
                            # (conçus pour des frontières 1:1 avec col_names)
                            # sont donc sautés : l'utilisateur a déjà résolu
                            # l'ambiguïté, on ne la remet pas en question.
                            cells, confs, split_flags = self._build_row_via_mapping(
                                line, header_blocks, img_w,
                                manual_mapping, col_names,
                            )
                        else:
                            cells, confs, split_flags = self._line_to_cells(
                                line, bounds, n_cols, col_names=col_names)
                            # Scoring adaptatif : réaffecter les mots en zone
                            # limite entre deux colonnes pour corriger les
                            # segmentations fragiles.
                            cells, confs, split_flags, _rb_conf, _rb_alts = (
                                self._rebalance_line(
                                    cells, confs, split_flags, col_names,
                                    line, bounds,
                                    neighbor_cells=[
                                        r['cells'] for r in rows[-3:]
                                        if r.get('type') == 'data'
                                    ],
                                )
                            )
                            if _rb_alts:
                                logger.debug(
                                    "rebalance: %d mot(s) déplacé(s) — confiance=%s",
                                    len(_rb_alts), _rb_conf,
                                )
                            # Re-OCR par bande ROI — trois déclencheurs :
                            # 1. Cellule à faible confiance (mauvaise lecture)
                            # 2. Cellule vide sur une ligne non vide → données
                            #    peut-être déversées dans la colonne voisine
                            # 3. Contenu qui viole le patron attendu
                            #    (ex : JAR doit commencer par un chiffre)
                            row_has_data = any(c for c in cells)

                            def _cn(ci):
                                return col_names[ci] if ci < len(col_names) else ''

                            any_empty = row_has_data and any(
                                not cells[ci] for ci in range(n_cols)
                            )
                            any_low_conf = any(
                                confs[ci] < Config.OCR_REOCR_THRESHOLD
                                and cells[ci] and not split_flags[ci]
                                for ci in range(n_cols)
                            )
                            any_violation = row_has_data and any(
                                cells[ci] and not split_flags[ci]
                                and not self._cell_matches_col_pattern(
                                    cells[ci], _cn(ci))
                                for ci in range(n_cols)
                            )
                            needs_reocr = Config.OCR_PER_COLUMN and (
                                any_empty or any_low_conf or any_violation)
                            if needs_reocr:
                                y_min = max(0, min(e['y'] for e in line) - 2)
                                y_max = min(
                                    binary.shape[0],
                                    max(e['y'] + e['h'] for e in line) + 2,
                                )
                                for ci in range(n_cols):
                                    if split_flags[ci]:
                                        continue
                                    is_low_conf = (
                                        confs[ci] < Config.OCR_REOCR_THRESHOLD
                                        and cells[ci]
                                    )
                                    is_empty = not cells[ci]
                                    is_violation = (
                                        cells[ci] and not
                                        self._cell_matches_col_pattern(
                                            cells[ci], _cn(ci))
                                    )
                                    should_reocr = (
                                        is_low_conf or is_violation
                                        or (any_empty and row_has_data)
                                    )
                                    if not should_reocr:
                                        continue
                                    x_min = bounds[ci]
                                    x_max = (
                                        bounds[ci + 1]
                                        if ci + 1 < len(bounds)
                                        else binary.shape[1]
                                    )
                                    new_text, new_conf = self._reocr_cell(
                                        binary, y_min, y_max,
                                        x_min, x_max, _cn(ci),
                                    )
                                    if new_text and (
                                        is_empty or is_violation
                                        or new_conf > confs[ci]
                                    ):
                                        cells[ci] = new_text
                                        confs[ci] = new_conf
                            if any(c for c in cells):
                                cells = self._reconstruct_intra_cell_spacing(
                                    line, bounds, n_cols, cells
                                )
                        if any(c for c in cells):
                            rows.append({
                                'type': 'data',
                                'cells': cells,
                                'confidence': confs,
                            })
                            _prev_data_y_max = max(
                                e['y'] + e['h'] for e in line
                            )

            result_dict = {
                'success': True,
                'headers': col_names,
                'rows': rows,
                'metadata': self._extract_meta(footer_lines),
                'image_path': str(image_path),
                'blur_pct': blur_pct,
                'detection_method': detection_method,
            }
            if Config.OCR_DEBUG_LOG:
                try:
                    self._write_ocr_log(
                        image_path, elements, lines,
                        bounds, col_names, detection_method, rows, blur_pct
                    )
                except Exception:
                    pass
            return result_dict
        except Exception as e:
            logger.error(f"Erreur extraction {image_path.name}: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            self._tpl = _orig_tpl
            self._col_keywords = _orig_kws

    # ------------------------------------------------------------------
    # Génération Excel
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Helpers partagés (Excel + classeur combiné)
    # ------------------------------------------------------------------

    def _fill_worksheet(self, ws, result: Dict,
                        start_row: int = 1,
                        page_size: int = 48,
                        dictionary=None,
                        bornier_name: str = None,
                        pet_name: str = None) -> int:
        """
        Remplit un onglet Excel à partir de start_row.

        Si le tableau dépasse page_size lignes, les lignes supplémentaires
        occupent les pages suivantes ; le pied de page figure uniquement
        sur la dernière page. Les sauts de page sont posés uniquement entre les
        tableaux (dans generer_classeur.py), jamais à l'intérieur d'un tableau.

        Retourne le numéro de la première ligne disponible après ce bloc.
        """
        headers = result.get('headers', self.EXPECTED_HEADERS)
        rows = result.get('rows', [])
        meta = dict(result.get('metadata', {}))
        if bornier_name and not meta.get('BORNIER'):
            meta['BORNIER'] = bornier_name
        if pet_name and not meta.get('PET'):
            meta['PET'] = pet_name
        n_cols = len(headers)
        blur_pct = result.get('blur_pct', 0.0)
        # Claude Vision, Log Replay et Hybrid : données fidèles, aucune correction
        _skip_dict = result.get('detection_method') in (
            'claude-vision', 'log-replay', 'hybrid'
        )

        # ── Calcul de la hauteur du bloc ─────────────────────────────
        # Le tableau occupe un multiple entier de page_size pour garantir
        # que chaque page A4 est complète.  Un tableau de 50 lignes avec
        # page_size=48 occupe 2×48=96 lignes (pas seulement 53).
        import math as _math
        footer_rows = 2 if self._tpl.has_footer else 0
        # Les entrées 'blank' peuvent représenter N lignes visuelles chacune
        n_visible_rows = sum(
            r.get('count', 1) if r.get('type') == 'blank' else 1
            for r in rows
        )
        n_rows_needed = 1 + n_visible_rows + footer_rows
        n_pages = max(1, _math.ceil(n_rows_needed / page_size))
        total_rows = n_pages * page_size
        end_row = start_row + total_rows   # premier rang du prochain bornier
        footer_r = end_row - 2             # début du pied (si has_footer)

        # ── Styles ────────────────────────────────────────────────────
        thin = Side(style='thin')
        dashed = Side(style='dashed')
        ns = Side(style=None)
        full_b = Border(left=thin, right=thin, top=thin, bottom=thin)
        data_b = Border(left=thin, right=thin, top=ns, bottom=ns)
        sect_b = Border(left=thin, right=thin, top=dashed, bottom=ns)

        bold = Font(bold=True)
        bold_ital = Font(bold=True, italic=True)
        center = Alignment(horizontal='center', vertical='center',
                           wrap_text=True)
        left_top = Alignment(horizontal='left', vertical='top',
                             wrap_text=False)
        vcenter = Alignment(horizontal='left', vertical='center')
        hfill = PatternFill('solid', fgColor='D9D9D9')

        # ── Largeurs de colonnes (une seule fois, à la 1re page) ──────
        if start_row == 1:
            for ci, hdr in enumerate(headers, 1):
                ws.column_dimensions[get_column_letter(ci)].width = (
                    self._tpl.col_width(hdr)
                )

        # ── Hauteur de ligne pour tout le bloc ────────────────────────
        row_height = 12.6
        for ri in range(start_row, end_row):
            ws.row_dimensions[ri].height = row_height

        # ── En-tête ───────────────────────────────────────────────────
        # Remplissage orange si le tableau source est trop flou (> 80 %)
        _BLUR_THRESHOLD = 80.0
        header_fill = (
            PatternFill('solid', fgColor='FFA500')
            if blur_pct > _BLUR_THRESHOLD
            else hfill
        )
        for ci, hdr in enumerate(headers, 1):
            c = ws.cell(row=start_row, column=ci, value=hdr)
            c.font = bold
            c.alignment = center
            c.fill = header_fill
            c.border = full_b

        # ── Marquage FLOU : commentaire + remplissage orange (> 80 %) ─
        if blur_pct > _BLUR_THRESHOLD:
            ws.cell(row=start_row, column=1).comment = Comment(
                f'TABLEAU FLOU ({blur_pct:.0f}%) — vérifier la source image',
                'TriosSeconverter'
            )

        # ── Données et sections (sans troncature) ─────────────────────
        cur = start_row + 1
        for row_data in rows:
            if row_data['type'] == 'blank':
                n_skip = row_data.get('count', 1)
                for _bi in range(cur, cur + n_skip):
                    for _ci in range(1, n_cols + 1):
                        ws.cell(row=_bi, column=_ci).border = data_b
                cur += n_skip
                continue
            if row_data['type'] == 'section':
                ws.merge_cells(start_row=cur, start_column=1,
                               end_row=cur, end_column=n_cols)
                c = ws.cell(row=cur, column=1, value=row_data['text'])
                c.font = bold_ital
                c.alignment = left_top
                c.border = sect_b
            else:
                confs = row_data.get('confidence', [])
                for ci, val in enumerate(
                    row_data.get('cells', []), 1
                ):
                    if ci > n_cols:   # ne jamais écrire au-delà des colonnes du template
                        break
                    if dictionary and val and not _skip_dict:
                        col_name = (
                            headers[ci - 1]
                            if ci - 1 < len(headers) else ''
                        )
                        val, _ = dictionary.correct(col_name, val)
                    # La cellule peut être une MergedCell si une ligne de section
                    # précédente a fusionné cette ligne (dépassement de page_size).
                    # On défusionne la plage concernée avant d'écrire.
                    try:
                        c = ws.cell(row=cur, column=ci, value=val)
                    except AttributeError:
                        for mr in list(ws.merged_cells.ranges):
                            if (mr.min_row <= cur <= mr.max_row
                                    and mr.min_col <= ci <= mr.max_col):
                                ws.unmerge_cells(str(mr))
                                break
                        c = ws.cell(row=cur, column=ci, value=val)
                    c.alignment = left_top
                    c.border = data_b
                    cell_conf = confs[ci - 1] if ci - 1 < len(confs) else 100
                    if val and cell_conf < 60:
                        c.fill = PatternFill('solid', fgColor='FFFF99')
                        c.comment = Comment(
                            f'Confiance OCR : {cell_conf}%\nVérifier cette valeur.',
                            'TriosSeconverter',
                        )
            cur += 1

        # ── Rembourrage : bordures sur les lignes vides avant le pied ─
        pad_end = footer_r if self._tpl.has_footer else end_row
        for ri in range(cur, pad_end):
            for ci in range(1, n_cols + 1):
                ws.cell(row=ri, column=ci).border = data_b

        # ── Pied de page ──────────────────────────────────────────────
        if not self._tpl.has_footer:
            return end_row

        row1_txt = self._tpl.render_footer_row1(meta)
        row2_txt = self._tpl.render_footer_row2(meta)

        # — Cellule gauche : fusionnée sur 2 lignes —
        ws.merge_cells(start_row=footer_r, start_column=1,
                       end_row=footer_r + 1, end_column=1)
        mti = ws.cell(row=footer_r, column=1,
                      value=self._tpl.footer_left_label)
        mti.font = bold
        mti.alignment = Alignment(horizontal='center', vertical='center')
        ws.cell(footer_r, 1).border = Border(
            left=thin, right=thin, top=thin, bottom=ns)
        ws.cell(footer_r + 1, 1).border = Border(
            left=thin, right=thin, top=ns, bottom=thin)

        # — Ligne 1 du pied (cols 2 à n_cols) —
        if n_cols > 1:
            ws.merge_cells(start_row=footer_r, start_column=2,
                           end_row=footer_r, end_column=n_cols)
        ws.cell(footer_r, 2, value=row1_txt).alignment = vcenter
        for ci in range(2, n_cols + 1):
            ws.cell(footer_r, ci).border = Border(
                left=thin if ci == 2 else ns,
                right=thin if ci == n_cols else ns,
                top=thin, bottom=thin,
            )

        # — Ligne 2 du pied (cols 2 à n_cols) —
        if n_cols > 1:
            ws.merge_cells(start_row=footer_r + 1, start_column=2,
                           end_row=footer_r + 1, end_column=n_cols)
        ws.cell(footer_r + 1, 2, value=row2_txt).alignment = vcenter
        for ci in range(2, n_cols + 1):
            ws.cell(footer_r + 1, ci).border = Border(
                left=thin if ci == 2 else ns,
                right=thin if ci == n_cols else ns,
                top=ns, bottom=thin,
            )

        return end_row

    def to_excel(self, result: Dict, output_path: Path) -> None:
        """Génère un fichier Excel pour un seul bornier."""
        wb = Workbook()
        ws = wb.active
        meta = result.get('metadata', {})
        ws.title = (meta.get('BORNIER') or 'Bornier')[:31]
        self._fill_worksheet(ws, result, start_row=1)
        wb.save(str(output_path))
        logger.info(f"✓ Excel créé: {output_path.name}")

    # ------------------------------------------------------------------
    # Helpers partagés (Word + document combiné)
    # ------------------------------------------------------------------

    def _add_table_to_doc(self, doc, result: Dict) -> None:
        """
        Ajoute un tableau de bornier à un document Word existant.
        Pied de page : M T I col 1, P.E.T./NO PLAN cols 2-n.
        """
        headers = result.get('headers', self.EXPECTED_HEADERS)
        rows = result.get('rows', [])
        meta = result.get('metadata', {})
        n_cols = len(headers)

        footer_rows = 2 if self._tpl.has_footer else 0
        n_visible_rows = sum(
            r.get('count', 1) if r.get('type') == 'blank' else 1
            for r in rows
        )
        n_table_rows = 1 + n_visible_rows + footer_rows
        table = doc.add_table(rows=n_table_rows, cols=n_cols)
        table.style = 'Table Grid'

        # En-têtes
        for ci, hdr in enumerate(headers):
            cell = table.rows[0].cells[ci]
            cell.text = hdr
            if cell.paragraphs[0].runs:
                cell.paragraphs[0].runs[0].bold = True

        # Données / sections / blancs
        ri = 1
        for row_data in rows:
            if row_data['type'] == 'blank':
                ri += row_data.get('count', 1)
            elif row_data['type'] == 'section':
                rc = table.rows[ri].cells
                merged = rc[0].merge(rc[n_cols - 1])
                merged.text = row_data['text']
                if merged.paragraphs[0].runs:
                    merged.paragraphs[0].runs[0].bold = True
                ri += 1
            else:
                for ci, val in enumerate(row_data.get('cells', [])):
                    if ci < n_cols:
                        table.rows[ri].cells[ci].text = val
                ri += 1

        if not self._tpl.has_footer:
            return   # pas de pied de page

        fi = 1 + n_visible_rows
        row1_txt = self._tpl.render_footer_row1(meta)
        row2_txt = self._tpl.render_footer_row2(meta)

        f1_col0 = table.rows[fi].cells[0]
        f2_col0 = table.rows[fi + 1].cells[0]
        f1_col1 = table.rows[fi].cells[1] if n_cols > 1 else f1_col0
        f1_coln = table.rows[fi].cells[n_cols - 1]
        f2_col1 = table.rows[fi + 1].cells[1] if n_cols > 1 else f2_col0
        f2_coln = table.rows[fi + 1].cells[n_cols - 1]

        # Cellule gauche fusionnée verticalement
        mti = f1_col0.merge(f2_col0)
        mti.text = self._tpl.footer_left_label
        if mti.paragraphs[0].runs:
            mti.paragraphs[0].runs[0].bold = True

        # Ligne 1 du pied
        if n_cols > 2:
            pet_cell = f1_col1.merge(f1_coln)
        else:
            pet_cell = f1_col1
        pet_cell.text = row1_txt

        # Ligne 2 du pied
        if n_cols > 2:
            plan_cell = f2_col1.merge(f2_coln)
        else:
            plan_cell = f2_col1
        plan_cell.text = row2_txt

    def to_word(self, result: Dict, output_path: Path) -> None:
        """Génère un document Word pour un seul bornier."""
        doc = Document()
        self._add_table_to_doc(doc, result)
        doc.save(str(output_path))
        logger.info(f"✓ Word créé: {output_path.name}")

    def process(self, image_path: Path, output_dir: Path,
                save_excel: bool = True,
                save_word: bool = True) -> Dict:
        """Traite une image et génère les fichiers de sortie."""
        result = self.extract(image_path)
        if not result['success']:
            return result
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = image_path.stem
        if save_excel:
            ep = output_dir / f"{stem}_table.xlsx"
            self.to_excel(result, ep)
            result['excel_path'] = str(ep)
        if save_word:
            wp = output_dir / f"{stem}_table.docx"
            self.to_word(result, wp)
            result['word_path'] = str(wp)
        return result


class BatchOCRProcessor:
    """
    Classe pour traiter plusieurs images en batch.
    """

    def __init__(self, tesseract_path: Optional[str] = None, language: str = "fra"):
        """
        Initialise le processeur batch.

        Args:
            tesseract_path: Chemin vers Tesseract
            language: Langue pour l'OCR
        """
        self.processor = OCRTableProcessor(tesseract_path, language)

    def process_folder(self, input_folder: Path,
                       output_folder: Path,
                       image_extensions: List[str] = None,
                       save_excel: bool = False) -> List[Dict]:
        """
        Traite toutes les images d'un dossier.

        Args:
            input_folder: Dossier contenant les images
            output_folder: Dossier de sortie pour les documents Word
            image_extensions: Extensions d'images à traiter
            save_excel: Créer également un fichier Excel pour chaque image

        Returns:
            Liste des résultats de traitement
        """
        if image_extensions is None:
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']

        logger.info(f"📁 Traitement du dossier: {input_folder}")

        # Créer le dossier de sortie
        output_folder.mkdir(parents=True, exist_ok=True)

        results = []

        # Traiter chaque image (seulement les fichiers, pas les dossiers)
        for image_file in input_folder.iterdir():
            if image_file.is_file() and image_file.suffix.lower() in image_extensions:
                output_file = output_folder / f"{image_file.stem}_table.docx"
                result = self.processor.process_image_to_table(
                    image_file,
                    output_file,
                    save_excel=save_excel
                )
                results.append(result)

        logger.info(f"✓ Traitement batch terminé: {len(results)} images traitées")
        return results
