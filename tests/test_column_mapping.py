"""
Tests unitaires — mapping manuel colonnes/blocs (Config.MAX_AUTO_COLUMNS).

Couvre :
  - Config.MAX_AUTO_COLUMNS
  - BornierTableExtractor._resoudre_mapping_manuel (déclenchement + cache)
  - BornierTableExtractor._candidate_blocks_from_header
  - BornierTableExtractor._block_bounds_from_candidates
  - BornierTableExtractor._build_row_via_mapping
  - Converter → propagation du callback on_column_mapping

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_column_mapping.py -v
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from ocr_processor import BornierTableExtractor
from template import TableTemplate
from config import Config


def _make_extractor(template=None, on_column_mapping=None):
    return BornierTableExtractor(
        tesseract_path=Config.TESSERACT_PATH,
        language=Config.OCR_LANGUAGE,
        template=template,
        on_column_mapping=on_column_mapping,
    )


def _template(n_cols: int, name: str = "Test") -> TableTemplate:
    cols = [f"COL{i}" for i in range(1, n_cols + 1)]
    return TableTemplate(name=name, columns=cols)


def _make_header_line(items):
    """items : liste de (x, w, text) — imite une ligne d'en-tête OCR."""
    return [
        {'text': t, 'x': x, 'w': w, 'cx': x + w // 2, 'y': 10, 'h': 20, 'conf': 90}
        for x, w, t in items
    ]


# ══════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════

class TestMaxAutoColumnsConfig(unittest.TestCase):

    def test_max_auto_columns_defaut(self):
        self.assertEqual(Config.MAX_AUTO_COLUMNS, 4)


# ══════════════════════════════════════════════════════════════════════
# _resoudre_mapping_manuel — déclenchement, non-régression, cache
# ══════════════════════════════════════════════════════════════════════

class TestResoudreMappingManuel(unittest.TestCase):

    def test_pas_de_callback_retourne_none(self):
        """Sans callback fourni, aucun mapping n'est demandé (comportement standard)."""
        ext = _make_extractor(template=_template(5))
        header = _make_header_line([(i * 100, 50, f'B{i}') for i in range(5)])
        result = ext._resoudre_mapping_manuel([header], 0, Path('img.png'))
        self.assertIsNone(result)

    def test_4_colonnes_ou_moins_ne_declenche_pas_callback(self):
        """Non-régression : le template standard (4 col.) ne demande jamais de mapping."""
        mock_cb = MagicMock(return_value={'COL1': [0]})
        ext = _make_extractor(template=_template(4), on_column_mapping=mock_cb)
        header = _make_header_line([(i * 100, 50, f'B{i}') for i in range(4)])
        result = ext._resoudre_mapping_manuel([header], 0, Path('img.png'))
        mock_cb.assert_not_called()
        self.assertIsNone(result)

    def test_plus_de_4_colonnes_declenche_callback(self):
        """Template à 5 colonnes → callback appelé avec les bons arguments."""
        mock_cb = MagicMock(return_value={'COL1': [0], 'COL2': [1]})
        tpl = _template(5)
        ext = _make_extractor(template=tpl, on_column_mapping=mock_cb)
        header = _make_header_line([(i * 100, 50, f'B{i}') for i in range(6)])
        result = ext._resoudre_mapping_manuel([header], 0, Path('img.png'))

        mock_cb.assert_called_once()
        candidate_blocks, template_columns, image_path = mock_cb.call_args[0]
        self.assertEqual(len(candidate_blocks), 6)
        self.assertEqual(template_columns, tpl.columns)
        self.assertEqual(result, {'COL1': [0], 'COL2': [1]})

    def test_cache_reutilise_meme_template(self):
        """Le callback n'est appelé qu'une fois pour un même template dans le run."""
        mock_cb = MagicMock(return_value={'COL1': [0]})
        ext = _make_extractor(template=_template(5), on_column_mapping=mock_cb)
        header = _make_header_line([(i * 100, 50, f'B{i}') for i in range(6)])
        ext._resoudre_mapping_manuel([header], 0, Path('img1.png'))
        ext._resoudre_mapping_manuel([header], 0, Path('img2.png'))
        self.assertEqual(mock_cb.call_count, 1)

    def test_annulation_utilisateur_retourne_none_sans_crash(self):
        """Callback retourne None (annulation) → pas de crash, None propagé."""
        mock_cb = MagicMock(return_value=None)
        ext = _make_extractor(template=_template(5), on_column_mapping=mock_cb)
        header = _make_header_line([(i * 100, 50, f'B{i}') for i in range(6)])
        result = ext._resoudre_mapping_manuel([header], 0, Path('img.png'))
        self.assertIsNone(result)
        mock_cb.assert_called_once()


# ══════════════════════════════════════════════════════════════════════
# _candidate_blocks_from_header
# ══════════════════════════════════════════════════════════════════════

class TestCandidateBlocksFromHeader(unittest.TestCase):

    def test_tries_par_position_x(self):
        ext = _make_extractor()
        header = _make_header_line([(300, 40, 'C'), (0, 40, 'A'), (150, 40, 'B')])
        blocks = ext._candidate_blocks_from_header([header], 0)
        self.assertEqual([b['text'] for b in blocks], ['A', 'B', 'C'])
        self.assertEqual(blocks[0]['x'], 0)
        self.assertEqual(blocks[0]['x2'], 40)


# ══════════════════════════════════════════════════════════════════════
# _block_bounds_from_candidates
# ══════════════════════════════════════════════════════════════════════

class TestBlockBoundsFromCandidates(unittest.TestCase):

    def test_frontieres_au_milieu_des_ecarts(self):
        blocks = [
            {'text': 'A', 'x': 0, 'x2': 100},
            {'text': 'B', 'x': 200, 'x2': 300},
        ]
        bounds = BornierTableExtractor._block_bounds_from_candidates(blocks, 500)
        self.assertEqual(bounds, [0, 150, 500])

    def test_bloc_unique(self):
        blocks = [{'text': 'A', 'x': 0, 'x2': 100}]
        bounds = BornierTableExtractor._block_bounds_from_candidates(blocks, 200)
        self.assertEqual(bounds, [0, 200])


# ══════════════════════════════════════════════════════════════════════
# _build_row_via_mapping — fusion et ordre
# ══════════════════════════════════════════════════════════════════════

class TestBuildRowViaMapping(unittest.TestCase):

    def setUp(self):
        self.ext = _make_extractor(template=_template(4))

    def _line(self, items):
        return [
            {'text': t, 'x': x, 'w': w, 'cx': x + w // 2, 'y': 40, 'h': 20, 'conf': 90}
            for x, w, t in items
        ]

    def test_fusionne_dans_ordre(self):
        """mapping={'COL3': [2, 3]} → cellule finale = concat bloc 2 + bloc 3 dans cet ordre."""
        blocks = [
            {'text': 'BORNE', 'x': 0, 'x2': 100},
            {'text': 'COULEUR', 'x': 150, 'x2': 250},
            {'text': 'SIG1', 'x': 300, 'x2': 400},
            {'text': 'SIG2', 'x': 450, 'x2': 550},
        ]
        line = self._line([
            (10, 50, '01A'), (160, 50, 'ROUGE'),
            (310, 50, 'ALPHA'), (460, 50, 'BETA'),
        ])
        mapping = {'COL1': [0], 'COL2': [1], 'COL3': [2, 3], 'COL4': []}
        cells, confs, flags = self.ext._build_row_via_mapping(
            line, blocks, 600, mapping, ['COL1', 'COL2', 'COL3', 'COL4'],
        )
        self.assertEqual(cells[0], '01A')
        self.assertEqual(cells[1], 'ROUGE')
        self.assertEqual(cells[2], 'ALPHA BETA')
        self.assertEqual(cells[3], '')
        self.assertEqual(len(confs), 4)
        self.assertEqual(len(flags), 4)
        self.assertFalse(any(flags))

    def test_ordre_inverse_donne_texte_inverse(self):
        """L'ordre des indices dans mapping détermine l'ordre de concaténation."""
        blocks = [
            {'text': 'X', 'x': 0, 'x2': 100},
            {'text': 'Y', 'x': 150, 'x2': 250},
        ]
        line = self._line([(10, 50, 'PREMIER'), (160, 50, 'SECOND')])
        cells_normal, _, _ = self.ext._build_row_via_mapping(
            line, blocks, 300, {'COL1': [0, 1]}, ['COL1'],
        )
        cells_inverse, _, _ = self.ext._build_row_via_mapping(
            line, blocks, 300, {'COL1': [1, 0]}, ['COL1'],
        )
        self.assertEqual(cells_normal[0], 'PREMIER SECOND')
        self.assertEqual(cells_inverse[0], 'SECOND PREMIER')

    def test_colonne_sans_bloc_assigne_reste_vide(self):
        blocks = [{'text': 'X', 'x': 0, 'x2': 100}]
        line = self._line([(10, 50, 'VAL')])
        cells, confs, _ = self.ext._build_row_via_mapping(
            line, blocks, 200, {}, ['COL1'],
        )
        self.assertEqual(cells[0], '')
        self.assertEqual(confs[0], 100)

    def test_indice_hors_bornes_ignore_sans_crash(self):
        """Un indice de bloc inexistant (ex: 99) référencé dans le mapping
        utilisateur est ignoré silencieusement — pas de crash, pas d'IndexError."""
        blocks = [{'text': 'A', 'x': 0, 'x2': 100}]
        line = self._line([(10, 50, 'A')])
        cells, confs, _ = self.ext._build_row_via_mapping(
            line, blocks, 200, {'COL1': [0], 'COL2': [99]}, ['COL1', 'COL2'],
        )
        self.assertEqual(cells[0], 'A')
        self.assertEqual(cells[1], '')   # indice 99 ignoré, pas d'erreur
        self.assertEqual(confs[1], 100)

    def test_meme_indice_partage_par_deux_colonnes(self):
        """Le même bloc assigné à deux colonnes différentes est dupliqué dans
        les deux — comportement toléré, aucune exclusivité n'est imposée."""
        blocks = [{'text': 'PARTAGE', 'x': 0, 'x2': 100}]
        line = self._line([(10, 50, 'PARTAGE')])
        cells, _, _ = self.ext._build_row_via_mapping(
            line, blocks, 200, {'COL1': [0], 'COL2': [0]}, ['COL1', 'COL2'],
        )
        self.assertEqual(cells[0], 'PARTAGE')
        self.assertEqual(cells[1], 'PARTAGE')

    def test_mapping_vide_produit_cellules_toutes_vides(self):
        """Mapping {} (rien assigné) → toutes les cellules vides. Combiné au
        garde-fou `if any(c for c in cells)` de extract(), la ligne entière
        sera silencieusement exclue du tableau final — comportement à
        documenter côté UX (avertir l'utilisateur avant validation vide)."""
        blocks = [{'text': 'A', 'x': 0, 'x2': 100}]
        line = self._line([(10, 50, 'A')])
        cells, _, _ = self.ext._build_row_via_mapping(
            line, blocks, 200, {}, ['COL1', 'COL2'],
        )
        self.assertEqual(cells, ['', ''])
        self.assertFalse(any(c for c in cells))


# ══════════════════════════════════════════════════════════════════════
# Converter — propagation du callback
# ══════════════════════════════════════════════════════════════════════

class TestConverterPropagatesCallback(unittest.TestCase):

    def test_converter_stocke_callback(self):
        from converter import Converter
        mock_cb = MagicMock()
        conv = Converter(
            word_file=Path('dummy.docx'),
            output_dir=Path('out'),
            on_column_mapping=mock_cb,
        )
        self.assertIs(conv._on_column_mapping, mock_cb)

    def test_converter_defaut_none(self):
        from converter import Converter
        conv = Converter(word_file=Path('dummy.docx'), output_dir=Path('out'))
        self.assertIsNone(conv._on_column_mapping)


if __name__ == '__main__':
    unittest.main()
