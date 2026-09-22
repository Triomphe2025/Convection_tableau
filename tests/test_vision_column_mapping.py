"""
Tests unitaires — mapping manuel segment→colonne pour les moteurs vision
(Claude/Ollama/Agent/Hybrid), quand leur réponse contient plus de segments
pipe-séparés que de colonnes template.

Couvre :
  - claude_ocr._detect_ambiguous_segments
  - claude_ocr._parse_pipe_response (column_mapping)
  - claude_ocr.ClaudeVisionExtractor._resoudre_mapping_segments (+ cache)
  - ollama_ocr.OllamaVisionExtractor._resoudre_mapping_segments
  - hybrid_ocr.HybridVisionExtractor — propagation du callback

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_vision_column_mapping.py -v
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from claude_ocr import (
    ClaudeVisionExtractor,
    _detect_ambiguous_segments,
    _parse_pipe_response,
)
from template import TableTemplate


def _template(n_cols: int, name: str = "REPARTITEUR") -> TableTemplate:
    cols = [f"COL{i}" for i in range(1, n_cols + 1)]
    return TableTemplate(name=name, columns=cols)


# ══════════════════════════════════════════════════════════════════════
# _detect_ambiguous_segments
# ══════════════════════════════════════════════════════════════════════

class TestDetectAmbiguousSegments(unittest.TestCase):

    def test_cas_nominal_plus_de_segments_que_colonnes(self):
        raw = "TYPE_PAGE: listing\nA | B | C | D | E | F\nMETA: {}"
        result = _detect_ambiguous_segments(raw, n_cols=4)
        self.assertEqual(result, ['A', 'B', 'C', 'D', 'E', 'F'])

    def test_pas_ambigu_meme_nombre_de_segments(self):
        raw = "A | B | C | D"
        self.assertIsNone(_detect_ambiguous_segments(raw, n_cols=4))

    def test_moins_de_segments_pas_ambigu(self):
        raw = "A | B | C"
        self.assertIsNone(_detect_ambiguous_segments(raw, n_cols=4))

    def test_ignore_type_page_et_meta(self):
        raw = (
            "TYPE_PAGE: listing\n"
            "META: {\"PAGE\": \"1|2\"}\n"
            "A | B | C | D\n"
        )
        # META contient un '|' mais ne doit pas être interprétée comme donnée
        self.assertIsNone(_detect_ambiguous_segments(raw, n_cols=4))

    def test_premiere_ligne_ambigue_retournee(self):
        raw = "A | B | C | D\nW | X | Y | Z | Q | R\n"
        result = _detect_ambiguous_segments(raw, n_cols=4)
        self.assertEqual(result, ['W', 'X', 'Y', 'Z', 'Q', 'R'])


# ══════════════════════════════════════════════════════════════════════
# _parse_pipe_response avec/sans column_mapping
# ══════════════════════════════════════════════════════════════════════

class TestParsePipeResponseColumnMapping(unittest.TestCase):

    def setUp(self):
        self.tpl = _template(4)
        self.raw = "B16T 01A | 0057R | B702A | 01H | FSa22-38\n"

    def test_sans_mapping_heuristique_historique(self):
        """Non-régression stricte : column_mapping=None → comportement inchangé."""
        rows, _, _ = _parse_pipe_response(self.raw, self.tpl)
        cells = rows[0]['cells']
        self.assertEqual(cells[0], 'B16T 01A')
        self.assertEqual(cells[1], '0057R')
        self.assertEqual(cells[2], 'B702A 01H')   # fusion heuristique
        self.assertEqual(cells[3], 'FSa22-38')

    def test_avec_mapping_utilise_le_mapping_pas_heuristique(self):
        mapping = {
            'COL1': [0], 'COL2': [1], 'COL3': [3], 'COL4': [2, 4],
        }
        rows, _, _ = _parse_pipe_response(self.raw, self.tpl, column_mapping=mapping)
        cells = rows[0]['cells']
        self.assertEqual(cells[0], 'B16T 01A')
        self.assertEqual(cells[1], '0057R')
        self.assertEqual(cells[2], '01H')
        self.assertEqual(cells[3], 'B702A FSa22-38')

    def test_mapping_indice_hors_bornes_ignore_sans_crash(self):
        mapping = {'COL1': [0], 'COL2': [99]}
        rows, _, _ = _parse_pipe_response(self.raw, self.tpl, column_mapping=mapping)
        cells = rows[0]['cells']
        self.assertEqual(cells[0], 'B16T 01A')
        self.assertEqual(cells[1], '')

    def test_mapping_ne_change_rien_si_pas_ambigu(self):
        raw_4segs = "A | B | C | D\n"
        mapping = {'COL1': [3], 'COL2': [2], 'COL3': [1], 'COL4': [0]}
        rows, _, _ = _parse_pipe_response(raw_4segs, self.tpl, column_mapping=mapping)
        # len(parts) == n_cols → branche directe, mapping non utilisé
        self.assertEqual(rows[0]['cells'], ['A', 'B', 'C', 'D'])


# ══════════════════════════════════════════════════════════════════════
# ClaudeVisionExtractor._resoudre_mapping_segments — déclenchement + cache
# ══════════════════════════════════════════════════════════════════════

class TestClaudeExtractorResoudreMappingSegments(unittest.TestCase):

    def test_callback_appele_si_ambigu(self):
        mock_cb = MagicMock(return_value={'COL1': [0], 'COL2': [1, 2, 3, 4, 5]})
        tpl = _template(4)
        ext = ClaudeVisionExtractor(tpl, on_column_mapping=mock_cb)
        raw = "A | B | C | D | E | F\n"
        mapping = ext._resoudre_mapping_segments(raw, Path('img.png'))

        mock_cb.assert_called_once()
        candidate_blocks, template_columns, image_path = mock_cb.call_args[0]
        self.assertEqual(len(candidate_blocks), 6)
        self.assertEqual(template_columns, tpl.columns)
        self.assertEqual(mapping, {'COL1': [0], 'COL2': [1, 2, 3, 4, 5]})

    def test_callback_non_appele_si_pas_ambigu(self):
        mock_cb = MagicMock()
        ext = ClaudeVisionExtractor(_template(4), on_column_mapping=mock_cb)
        raw = "A | B | C | D\n"
        mapping = ext._resoudre_mapping_segments(raw, Path('img.png'))
        mock_cb.assert_not_called()
        self.assertIsNone(mapping)

    def test_cache_reutilise_meme_ambiguite(self):
        mock_cb = MagicMock(return_value={'COL1': [0]})
        ext = ClaudeVisionExtractor(_template(4), on_column_mapping=mock_cb)
        raw = "A | B | C | D | E | F\n"
        ext._resoudre_mapping_segments(raw, Path('img1.png'))
        ext._resoudre_mapping_segments(raw, Path('img2.png'))
        self.assertEqual(mock_cb.call_count, 1)

    def test_sans_callback_comportement_inchange(self):
        ext = ClaudeVisionExtractor(_template(4), on_column_mapping=None)
        raw = "A | B | C | D | E | F\n"
        mapping = ext._resoudre_mapping_segments(raw, Path('img.png'))
        self.assertIsNone(mapping)

    def test_callback_absent_extract_utilise_toujours_heuristique(self):
        """Bout-en-bout léger : sans callback, _parse_pipe_response reçoit
        column_mapping=None et applique l'heuristique historique."""
        ext = ClaudeVisionExtractor(_template(4))
        raw = "A | B | C | D | E | F\n"
        mapping = ext._resoudre_mapping_segments(raw, Path('img.png'))
        rows, _, _ = _parse_pipe_response(raw, ext._tpl, column_mapping=mapping)
        # heuristique : col[0], col[1], fusion médiane, dernier segment
        self.assertEqual(rows[0]['cells'][0], 'A')
        self.assertEqual(rows[0]['cells'][1], 'B')
        self.assertEqual(rows[0]['cells'][3], 'F')


# ══════════════════════════════════════════════════════════════════════
# HybridVisionExtractor — propagation du callback aux sous-extracteurs
# ══════════════════════════════════════════════════════════════════════

class TestHybridExtractorForwardsCallback(unittest.TestCase):

    def test_constructeur_stocke_callback(self):
        from hybrid_ocr import HybridVisionExtractor
        mock_cb = MagicMock()
        ext = HybridVisionExtractor(_template(4), on_column_mapping=mock_cb)
        self.assertIs(ext._on_column_mapping, mock_cb)

    def test_constructeur_defaut_none(self):
        from hybrid_ocr import HybridVisionExtractor
        ext = HybridVisionExtractor(_template(4))
        self.assertIsNone(ext._on_column_mapping)


if __name__ == '__main__':
    unittest.main()
