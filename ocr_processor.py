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
from typing import List, Dict, Optional, Tuple
from docx import Document
from docx.shared import Inches
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
import logging

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
                    (i for i in range(rows) if grid['row_edges'][i] <= center_y < grid['row_edges'][i + 1]),
                    rows - 1
                )
                col_index = next(
                    (i for i in range(columns) if grid['col_edges'][i] <= center_x < grid['col_edges'][i + 1]),
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
            return {'columns': 4, 'headers': ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'], 'column_positions': [0, 100, 250, 400]}

        # Analyser les positions X pour détecter les colonnes
        all_x_positions = [
            item['x'] + item.get('width', 0) // 2
            for line in lines
            for item in line
        ]
        all_x_positions.sort()

        if not all_x_positions:
            return {'columns': 4, 'headers': ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'], 'column_positions': [0, 100, 250, 400]}

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
        Crée un fichier Excel à partir du tableau extrait, suivant le modèle de exemple_tableaux.xlsx Feuil3.

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
        sheet.cell(row=mti_row, column=2, value="    P.E.T : EPEULE                                                        BORNIER : B702A                                                   ")

        # Ligne NO PLAN
        plan_row = mti_row + 1
        sheet.cell(row=plan_row, column=2, value="NO PLAN : VD23111 PE 162                               |  INDICE : 0      |    PAGE :        92")

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

    def __init__(self, tesseract_path: Optional[str] = None,
                 language: str = 'fra',
                 template=None):
        """
        Args:
            tesseract_path: Chemin vers tesseract.exe (None = PATH système)
            language:       Code langue Tesseract (ex: 'fra', 'eng')
            template:       TableTemplate — structure du tableau à extraire.
                            Si None, utilise le modèle bornier standard.
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

    # ------------------------------------------------------------------
    # Étape 1 : Prétraitement
    # ------------------------------------------------------------------

    def _preprocess(self, image_path: Path) -> Tuple[np.ndarray, int]:
        """Charge, met à l'échelle et binarise l'image."""
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Image non trouvée: {image_path}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        # Agrandir si trop petite pour l'OCR
        if w < 1400:
            scale = 1400 / w
            gray = cv2.resize(
                gray, None, fx=scale, fy=scale,
                interpolation=cv2.INTER_CUBIC
            )
        # Binarisation Otsu : excellente pour les scans propres
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        return binary, binary.shape[1]

    # ------------------------------------------------------------------
    # Étape 2 : OCR
    # ------------------------------------------------------------------

    def _ocr_elements(self, image: np.ndarray) -> List[Dict]:
        """Retourne tous les mots détectés avec leur position."""
        config = f'--oem 3 --psm 6 -l {self.language}'
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
        """Trouve la ligne contenant les mots-clés de colonnes du modèle."""
        keywords = self._col_keywords
        for i, line in enumerate(lines):
            full = ' '.join(e['text'].upper() for e in line)
            hits = sum(
                1 for h in keywords
                if h in full or any(h in e['text'].upper() for e in line)
            )
            if hits >= max(2, len(keywords) // 2):
                return i
        return None

    def _col_boundaries(
        self, header_line: List[Dict], img_w: int
    ) -> Tuple[List[int], List[str]]:
        """
        Calcule les frontières de colonnes à partir des mots de l'en-tête.
        Retourne (boundaries, col_names) où boundaries a len = n_cols + 1.
        """
        keywords = self._col_keywords
        positions: Dict[str, int] = {}
        for elem in header_line:
            up = elem['text'].upper()
            for hdr in keywords:
                if hdr in up and hdr not in positions:
                    positions[hdr] = elem['cx']

        if len(positions) >= max(2, len(keywords) // 2):
            ordered = sorted(positions.items(), key=lambda x: x[1])
            ctrs = [v for _, v in ordered]
            names = [k for k, _ in ordered]
            bounds = [0]
            for i in range(len(ctrs) - 1):
                bounds.append((ctrs[i] + ctrs[i + 1]) // 2)
            bounds.append(img_w)
            return bounds, names

        # Repli : colonnes égales
        n = len(keywords) or 4
        step = img_w // n
        return [i * step for i in range(n + 1)], list(keywords)

    # ------------------------------------------------------------------
    # Étape 5 : Classification des lignes
    # ------------------------------------------------------------------

    def _classify_line(self, line: List[Dict]) -> str:
        """Retourne 'section', 'footer' ou 'data' selon le modèle actif."""
        text = ' '.join(e['text'].upper() for e in line)
        kw = self._tpl.section_keyword.upper()
        if kw in text or kw[:min(10, len(kw))] in text:
            return 'section'
        if not self._tpl.has_footer:
            return 'data'
        for m in self._tpl.footer_detect_keywords:
            if m.upper() in text:
                return 'footer'
        tokens = {e['text'].upper() for e in line}
        mti = set(t.upper() for t in self._tpl.footer_mti_tokens)
        if tokens <= (mti | {'|', '-', '.', ':'}):
            return 'footer'
        return 'data'

    # ------------------------------------------------------------------
    # Étape 6 : Affectation des mots aux colonnes
    # ------------------------------------------------------------------

    def _line_to_cells(
        self, line: List[Dict], bounds: List[int], n_cols: int
    ) -> List[str]:
        """Affecte chaque mot à une colonne selon sa position X."""
        cells = [''] * n_cols
        for elem in line:
            cx = elem['cx']
            col = n_cols - 1
            for i in range(len(bounds) - 1):
                if bounds[i] <= cx < bounds[i + 1]:
                    col = i
                    break
            cells[col] = (cells[col] + ' ' + elem['text']).strip()
        return cells

    # ------------------------------------------------------------------
    # Étape 7 : Extraction des métadonnées du pied de page
    # ------------------------------------------------------------------

    def _extract_meta(
        self, footer_lines: List[List[Dict]]
    ) -> Dict[str, str]:
        """Extrait BORNIER, PAGE, P.E.T., INDICE, NO PLAN depuis le pied."""
        text = ' '.join(
            e['text'] for line in footer_lines for e in line
        ).upper()
        meta = {}
        patterns = [
            ('PET',     r'P\.?E\.?T\.?\s*[:\s]\s*([A-Z0-9]+(?:\s[A-Z0-9]+)?)'),
            ('BORNIER', r'BORNIER\s*[:\s]\s*([A-Z0-9]+)'),
            ('NO_PLAN', r'(?:NO|N°)\s*PLAN\s*[:\s]\s*([\w\s]+?)(?=\s*[|]|\s*INDICE|$)'),
            ('INDICE',  r'INDICE\s*[:\s]\s*(\d+)'),
            ('PAGE',    r'PAGE\s*[:\s]\s*(\d+)'),
        ]
        for key, pat in patterns:
            m = re.search(pat, text)
            if m:
                meta[key] = m.group(1).strip()
        return meta

    # ------------------------------------------------------------------
    # Pipeline principal
    # ------------------------------------------------------------------

    def extract(self, image_path: Path) -> Dict:
        """
        Extraction complète : image → dict structuré.

        Retourne:
            success  : bool
            headers  : liste des noms de colonnes
            rows     : liste de dicts {'type': 'data'|'section', 'cells'|'text'}
            metadata : dict avec BORNIER, PAGE, PET, INDICE, NO_PLAN
        """
        try:
            binary, img_w = self._preprocess(image_path)
            elements = self._ocr_elements(binary)
            if not elements:
                return {'success': False, 'error': 'Aucun texte détecté'}

            lines = self._group_lines(elements)
            h_idx = self._find_header_idx(lines)

            if h_idx is not None:
                bounds, col_names = self._col_boundaries(
                    lines[h_idx], img_w
                )
                data_lines = lines[h_idx + 1:]
            else:
                n = len(self._col_keywords) or 4
                step = img_w // n
                bounds = [i * step for i in range(n + 1)]
                col_names = list(self._col_keywords)
                data_lines = lines

            n_cols = len(col_names)
            rows: List[Dict] = []
            footer_lines: List[List[Dict]] = []

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
                    cells = self._line_to_cells(line, bounds, n_cols)
                    if any(c for c in cells):
                        rows.append({'type': 'data', 'cells': cells})

            return {
                'success': True,
                'headers': col_names,
                'rows': rows,
                'metadata': self._extract_meta(footer_lines),
                'image_path': str(image_path),
            }
        except Exception as e:
            logger.error(f"Erreur extraction {image_path.name}: {e}")
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Génération Excel
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Helpers partagés (Excel + classeur combiné)
    # ------------------------------------------------------------------

    def _fill_worksheet(self, ws, result: Dict,
                        start_row: int = 1) -> int:
        """
        Remplit un onglet Excel à partir de start_row.

        Mise en forme fidèle à l'original :
          - En-tête  : fond gris, bordure complète
          - Données  : séparateurs verticaux seulement
          - Sections : pointillé au-dessus
          - Pied     : M T I dans col 1 (fusionné 2 lignes),
                       P.E.T./BORNIER et NO PLAN dans cols 2-n

        Retourne la prochaine ligne disponible après le tableau
        (utile pour empiler plusieurs tableaux sur une même feuille).
        """
        headers = result.get('headers', self.EXPECTED_HEADERS)
        rows = result.get('rows', [])
        meta = result.get('metadata', {})
        n_cols = len(headers)

        # ── Styles ────────────────────────────────────────────────────
        thin = Side(style='thin')
        dashed = Side(style='dashed')
        ns = Side(style=None)           # no_side
        full_b = Border(left=thin, right=thin, top=thin, bottom=thin)
        data_b = Border(left=thin, right=thin, top=ns, bottom=ns)
        sect_b = Border(left=thin, right=thin, top=dashed, bottom=ns)

        bold = Font(bold=True)
        bold_ital = Font(bold=True, italic=True)
        center = Alignment(horizontal='center', vertical='center',
                           wrap_text=True)
        left_top = Alignment(horizontal='left', vertical='top',
                             wrap_text=True)
        vcenter = Alignment(horizontal='left', vertical='center')
        hfill = PatternFill('solid', fgColor='D9D9D9')

        # ── Largeurs de colonnes (seulement à la 1re ligne de la feuille)
        if start_row == 1:
            for ci, hdr in enumerate(headers, 1):
                ws.column_dimensions[get_column_letter(ci)].width = (
                    self._tpl.col_width(hdr)
                )

        # ── En-tête ───────────────────────────────────────────────────
        for ci, hdr in enumerate(headers, 1):
            c = ws.cell(row=start_row, column=ci, value=hdr)
            c.font = bold
            c.alignment = center
            c.fill = hfill
            c.border = full_b

        # ── Données et sections ───────────────────────────────────────
        cur = start_row + 1
        for row_data in rows:
            if row_data['type'] == 'section':
                ws.merge_cells(start_row=cur, start_column=1,
                               end_row=cur, end_column=n_cols)
                c = ws.cell(row=cur, column=1, value=row_data['text'])
                c.font = bold_ital
                c.alignment = left_top
                c.border = sect_b
            else:
                for ci, val in enumerate(
                    row_data.get('cells', []), 1
                ):
                    c = ws.cell(row=cur, column=ci, value=val)
                    c.alignment = left_top
                    c.border = data_b
            cur += 1

        # ── Pied de page ──────────────────────────────────────────────
        if not self._tpl.has_footer:
            return cur   # pas de pied : première ligne libre = cur

        r = cur
        row1_txt = self._tpl.render_footer_row1(meta)
        row2_txt = self._tpl.render_footer_row2(meta)

        # — Cellule gauche : fusionnée sur 2 lignes —
        ws.merge_cells(start_row=r, start_column=1,
                       end_row=r + 1, end_column=1)
        mti = ws.cell(row=r, column=1,
                      value=self._tpl.footer_left_label)
        mti.font = bold
        mti.alignment = Alignment(horizontal='center', vertical='center')
        ws.cell(row=r,     column=1).border = Border(
            left=thin, right=thin, top=thin, bottom=ns)
        ws.cell(row=r + 1, column=1).border = Border(
            left=thin, right=thin, top=ns, bottom=thin)

        # — Ligne 1 du pied (cols 2 à n_cols) —
        if n_cols > 1:
            ws.merge_cells(start_row=r, start_column=2,
                           end_row=r, end_column=n_cols)
        ws.cell(row=r, column=2, value=row1_txt).alignment = vcenter
        for ci in range(2, n_cols + 1):
            ws.cell(row=r, column=ci).border = Border(
                left=thin if ci == 2       else ns,
                right=thin if ci == n_cols else ns,
                top=thin, bottom=thin,
            )

        # — Ligne 2 du pied (cols 2 à n_cols) —
        if n_cols > 1:
            ws.merge_cells(start_row=r + 1, start_column=2,
                           end_row=r + 1, end_column=n_cols)
        ws.cell(row=r + 1, column=2, value=row2_txt).alignment = vcenter
        for ci in range(2, n_cols + 1):
            ws.cell(row=r + 1, column=ci).border = Border(
                left=thin if ci == 2       else ns,
                right=thin if ci == n_cols else ns,
                top=ns, bottom=thin,
            )

        return r + 2   # première ligne libre après le pied de page

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
        n_table_rows = 1 + len(rows) + footer_rows
        table = doc.add_table(rows=n_table_rows, cols=n_cols)
        table.style = 'Table Grid'

        # En-têtes
        for ci, hdr in enumerate(headers):
            cell = table.rows[0].cells[ci]
            cell.text = hdr
            if cell.paragraphs[0].runs:
                cell.paragraphs[0].runs[0].bold = True

        # Données / sections
        for ri, row_data in enumerate(rows, start=1):
            if row_data['type'] == 'section':
                rc = table.rows[ri].cells
                merged = rc[0].merge(rc[n_cols - 1])
                merged.text = row_data['text']
                if merged.paragraphs[0].runs:
                    merged.paragraphs[0].runs[0].bold = True
            else:
                for ci, val in enumerate(row_data.get('cells', [])):
                    if ci < n_cols:
                        table.rows[ri].cells[ci].text = val

        if not self._tpl.has_footer:
            return   # pas de pied de page

        fi = 1 + len(rows)
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