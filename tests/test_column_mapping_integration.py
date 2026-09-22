"""
Tests d'intégration — mapping manuel colonnes/blocs.

Deux niveaux :
  - Intégration PARTIELLE : le mécanisme Event/callback thread-safe
    (identique au pattern utilisé dans interface.py._on_column_mapping),
    simulé sans lancer Tkinter.
  - Intégration GLOBALE : BornierTableExtractor.extract() bout-en-bout,
    OCR interne mocké (déterministe, sans dépendance à la précision réelle
    de Tesseract), pour vérifier que le résultat final reste conforme
    (mêmes en-têtes, même nombre de colonnes) quand un mapping manuel
    est appliqué.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_column_mapping_integration.py -v
"""

import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from ocr_processor import BornierTableExtractor
from template import TableTemplate


def _template(n_cols: int, name: str = "Test") -> TableTemplate:
    cols = [f"COL{i}" for i in range(1, n_cols + 1)]
    return TableTemplate(name=name, columns=cols)


# ══════════════════════════════════════════════════════════════════════
# Intégration partielle : mécanisme Event/callback thread-safe
# ══════════════════════════════════════════════════════════════════════

class TestMecanismeEventThreadSafe(unittest.TestCase):
    """
    Reproduit le pattern exact utilisé par interface.py._on_column_mapping
    (Event LOCAL par appel + after(0, ...) simulé) sans dépendance Tkinter,
    pour vérifier que le thread worker se débloque bien après la réponse
    utilisateur et récupère la bonne valeur.
    """

    def test_worker_se_debloque_apres_reponse_utilisateur(self):
        received = []

        def fake_show_dialog_then_respond(callback):
            # Simule l'ouverture asynchrone d'une dialog Tkinter (after(0, ...))
            # puis la validation utilisateur après un court délai.
            def _later():
                time.sleep(0.05)
                callback({'COL1': [0, 1]})
            threading.Thread(target=_later, daemon=True).start()

        def on_column_mapping(candidate_blocks, template_columns, image_path):
            local_event = threading.Event()
            local_result_box = [None]

            def _callback(mapping_result):
                local_result_box[0] = mapping_result
                local_event.set()

            fake_show_dialog_then_respond(_callback)
            local_event.wait(timeout=5)
            return local_result_box[0]

        def _worker():
            result = on_column_mapping([{'text': 'A'}], ['COL1'], Path('x.png'))
            received.append(result)

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=5)

        self.assertFalse(t.is_alive(), "Le thread worker est resté bloqué")
        self.assertEqual(received, [{'COL1': [0, 1]}])

    def test_timeout_ne_bloque_pas_indefiniment_si_pas_de_reponse(self):
        def on_column_mapping(candidate_blocks, template_columns, image_path):
            local_event = threading.Event()
            local_result_box = [None]
            # Personne ne répond jamais (fenêtre fermée sans callback) —
            # le wait(timeout=...) doit quand même rendre la main.
            local_event.wait(timeout=0.2)
            return local_result_box[0]

        start = time.time()
        result = on_column_mapping([], [], Path('x.png'))
        elapsed = time.time() - start

        self.assertIsNone(result)
        self.assertLess(elapsed, 1.0, "Le mécanisme aurait dû rendre la main rapidement")


# ══════════════════════════════════════════════════════════════════════
# Intégration globale : extract() bout-en-bout avec mapping simulé
# ══════════════════════════════════════════════════════════════════════

class TestPipelineCompletAvecMappingSimule(unittest.TestCase):

    def _make_elements(self, items, y, h=20):
        return [
            {'text': t, 'x': x, 'w': w, 'y': y, 'h': h,
             'cx': x + w // 2, 'cy': y + h // 2, 'conf': 90}
            for x, w, t in items
        ]

    def test_pipeline_complet_avec_mapping_simule(self):
        """5 colonnes template + 6 blocs détectés → mapping manuel appliqué,
        le résultat final garde la forme standard (n_cols_tpl colonnes)."""
        tpl = _template(5)
        mapping_used = {
            'COL1': [0], 'COL2': [1], 'COL3': [2, 3], 'COL4': [4], 'COL5': [5],
        }
        mock_cb = MagicMock(return_value=mapping_used)
        ext = BornierTableExtractor(template=tpl, on_column_mapping=mock_cb)

        # En-tête : le texte de chaque bloc correspond exactement à un mot-clé
        # du template pour que _find_header_idx() la reconnaisse comme en-tête.
        header = self._make_elements(
            [(i * 120, 60, f'COL{i + 1}') for i in range(6)], y=10,
        )
        data_row = self._make_elements(
            [(i * 120, 60, f'V{i}') for i in range(6)], y=60,
        )
        fake_binary = np.full((120, 760), 255, dtype=np.uint8)

        with patch.object(ext, '_preprocess', return_value=(fake_binary, 760)), \
             patch.object(ext, '_compute_blur_score', return_value=0.0), \
             patch.object(ext, '_ocr_elements', return_value=header + data_row):
            result = ext.extract(Path('dummy_image.png'))

        self.assertTrue(result['success'], result.get('error'))
        self.assertEqual(result['headers'], tpl.columns)
        mock_cb.assert_called_once()

        data_rows = [r for r in result['rows'] if r.get('type') == 'data']
        self.assertEqual(len(data_rows), 1)
        # Forme inchangée : toujours n_cols_tpl (5) cellules, quel que soit
        # le nombre de blocs bruts détectés (6) fusionnés en amont.
        self.assertEqual(len(data_rows[0]['cells']), 5)
        self.assertEqual(data_rows[0]['cells'][2], 'V2 V3')   # COL3 = fusion blocs 2+3

    def test_pipeline_template_standard_4_colonnes_sans_callback(self):
        """Non-régression bout-en-bout : template standard (4 col.), pas de
        callback fourni → aucune interaction, comportement inchangé."""
        tpl = _template(4)
        ext = BornierTableExtractor(template=tpl, on_column_mapping=None)

        header = self._make_elements(
            [(i * 150, 60, f'COL{i + 1}') for i in range(4)], y=10,
        )
        data_row = self._make_elements(
            [(i * 150, 60, f'V{i}') for i in range(4)], y=60,
        )
        fake_binary = np.full((120, 650), 255, dtype=np.uint8)

        with patch.object(ext, '_preprocess', return_value=(fake_binary, 650)), \
             patch.object(ext, '_compute_blur_score', return_value=0.0), \
             patch.object(ext, '_ocr_elements', return_value=header + data_row):
            result = ext.extract(Path('dummy_image.png'))

        self.assertTrue(result['success'], result.get('error'))
        self.assertEqual(result['headers'], tpl.columns)
        data_rows = [r for r in result['rows'] if r.get('type') == 'data']
        self.assertEqual(len(data_rows), 1)
        self.assertEqual(len(data_rows[0]['cells']), 4)


if __name__ == '__main__':
    unittest.main()
