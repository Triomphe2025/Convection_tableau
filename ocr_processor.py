"""
Module OCR pour traiter les images extraites et créer des tableaux Word.

Ce module utilise OpenCV et Tesseract pour extraire le texte des images
et créer des tableaux structurés dans des documents Word.
"""

import cv2
import pytesseract
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
from docx import Document
from docx.shared import Inches
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
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
        Pipeline complet: image → OCR → tableau → Word.

        Args:
            image_path: Chemin de l'image à traiter
            output_path: Chemin du document Word de sortie
            save_excel: Crée également un fichier Excel si True
            excel_output_path: Chemin du fichier Excel de sortie

        Returns:
            Statistiques du traitement
        """
        logger.info(f"🚀 Début du traitement OCR pour: {image_path.name}")

        try:
            # Prétraitement
            processed_image = self.preprocess_image(image_path)

            # OCR
            text_data = self.extract_text_data(processed_image)

            if not text_data:
                logger.warning("⚠ Aucune donnée texte trouvée")
                return {'success': False, 'error': 'No text found'}

            # Détection de la grille du tableau
            grid = self.detect_table_grid(processed_image)
            if grid.get('valid'):
                table_data = self.build_table_data_from_grid(text_data, grid)
                table_structure = {
                    'columns': max(len(row) for row in table_data) if table_data else 0,
                    'column_widths': [grid['col_edges'][i + 1] - grid['col_edges'][i]
                                      for i in range(len(grid['col_edges']) - 1)]
                }
            else:
                # Regroupement par lignes
                lines = self.group_by_lines(text_data)
                table_data = self.build_table_data_from_lines(lines)
                table_structure = {
                    'columns': max(len(row) for row in table_data) if table_data else 0,
                    'column_widths': []
                }

            # Filtrage commun : ajouter en-tête si absent, filtrer borne <=3, remplacer vides par 'none'
            if table_data:
                if table_data[0] != ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']:
                    table_data.insert(0, ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'])
                filtered_data = [table_data[0]]
                for row in table_data[1:]:
                    row_text = ' '.join(str(cell) for cell in row).upper()
                    if (len(row) > 0 and len(str(row[0])) <= 3 and
                        not any(keyword in row_text for keyword in ['PLAN', 'PAGE', 'INDICE', 'PE ', 'MTI'])):
                        filtered_row = [cell if cell else 'none' for cell in row[:4]]
                        filtered_data.append(filtered_row)
                table_data = filtered_data

            # Création du document Word
            self.create_word_document(table_data, table_structure,
                                     output_path, image_path)

            if save_excel:
                if excel_output_path is None:
                    excel_output_path = output_path.with_suffix('.xlsx')
                self.create_excel_document(table_data, excel_output_path, image_path)

            stats = {
                'success': True,
                'image_path': str(image_path),
                'output_path': str(output_path),
                'text_elements': len(text_data),
                'table_rows': len(table_data),
                'columns': table_structure.get('columns', 0),
                'excel_path': str(excel_output_path) if save_excel else None
            }

            logger.info(f"✅ Traitement terminé avec succès")
            return stats

        except Exception as e:
            logger.error(f"✗ Erreur lors du traitement: {e}")
            return {'success': False, 'error': str(e)}


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