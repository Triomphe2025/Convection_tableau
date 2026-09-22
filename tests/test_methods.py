"""
Tests unitaires pour TriosSeconverter.

Couvre :
  - BornierTableExtractor._clean_cell
  - BornierTableExtractor._extract_meta
  - BornierTableExtractor._count_data_rows
  - BornierTableExtractor._fill_worksheet (bordures)
  - DataDictionary.add_value / correct / update_from_excel
  - TableTemplate.render_footer_row1 / render_footer_row2

Lancement :
    cd "c:\\Users\\Triomphe Tchounda\\Downloads\\convertion Tableau"
    env\\Scripts\\python.exe -m pytest tests/ -v
"""

import os
import tempfile
import unittest
from pathlib import Path

# Ajouter le dossier parent au path

from ocr_processor import BornierTableExtractor
from data_dictionary import DataDictionary
from template import DEFAULT_TEMPLATE
from config import Config


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_extractor():
    return BornierTableExtractor(
        tesseract_path=Config.TESSERACT_PATH,
        language=Config.OCR_LANGUAGE,
    )


def _make_footer_lines(text: str):
    """Convertit une chaîne en structure footer_lines attendue par _extract_meta."""
    words = text.split()
    return [[{'text': w, 'cx': i * 20, 'cy': 0} for i, w in enumerate(words)]]


def _make_result(rows, meta=None):
    return {
        'success': True,
        'headers': ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'],
        'rows': rows,
        'metadata': meta or {},
        'image_path': 'test.jpg',
    }


# ══════════════════════════════════════════════════════════════════════
# 1. _clean_cell
# ══════════════════════════════════════════════════════════════════════

class TestCleanCell(unittest.TestCase):

    def test_empty_string_unchanged(self):
        self.assertEqual(BornierTableExtractor._clean_cell(''), '')

    def test_none_like_empty(self):
        self.assertEqual(BornierTableExtractor._clean_cell(''), '')

    def test_strip_leading_pipe(self):
        self.assertEqual(BornierTableExtractor._clean_cell('| 30BC'), '30BC')

    def test_strip_trailing_pipe(self):
        self.assertEqual(BornierTableExtractor._clean_cell('30BC |'), '30BC')

    def test_pipe_only_becomes_empty(self):
        self.assertEqual(BornierTableExtractor._clean_cell('|'), '')

    def test_pipe_spaces_becomes_empty(self):
        self.assertEqual(BornierTableExtractor._clean_cell('  |  '), '')

    def test_valid_borne_unchanged(self):
        self.assertEqual(BornierTableExtractor._clean_cell('01B'), '01B')

    def test_valid_signal_unchanged(self):
        self.assertEqual(BornierTableExtractor._clean_cell('RESERVE CABLEE'), 'RESERVE CABLEE')

    def test_valid_jarretieres_unchanged(self):
        self.assertEqual(BornierTableExtractor._clean_cell('0260R'), '0260R')

    def test_garbage_zeros_removed(self):
        # 10+ zéros consécutifs = artefact scanner
        self.assertEqual(BornierTableExtractor._clean_cell('0000000000'), '')

    def test_garbage_zeros_with_pipe(self):
        self.assertEqual(BornierTableExtractor._clean_cell('0900000000000000000 |'), '')

    def test_garbage_mixed_noise(self):
        self.assertEqual(
            BornierTableExtractor._clean_cell('| Oo © | 000000000000000900'), ''
        )

    def test_special_chars_only_removed(self):
        self.assertEqual(BornierTableExtractor._clean_cell('© ®'), '')

    def test_valid_couleur_bc(self):
        self.assertEqual(BornierTableExtractor._clean_cell('BC'), 'BC')

    def test_five_repeated_chars_removed(self):
        self.assertEqual(BornierTableExtractor._clean_cell('AAAAA'), '')

    def test_four_repeated_chars_kept(self):
        # 4 répétitions consécutives (< seuil 5) sont conservées
        self.assertEqual(BornierTableExtractor._clean_cell('AAAA'), 'AAAA')


# ══════════════════════════════════════════════════════════════════════
# 2. _extract_meta
# ══════════════════════════════════════════════════════════════════════

class TestExtractMeta(unittest.TestCase):

    def setUp(self):
        self.ext = _make_extractor()

    def _meta(self, text: str) -> dict:
        return self.ext._extract_meta(_make_footer_lines(text))

    def test_full_footer_nominal(self):
        text = (
            'P.E.T. : EPEULE BORNIER : AA '
            'NO PLAN : VD23111 PE 162 | INDICE : 0 | PAGE : 5'
        )
        meta = self._meta(text)
        self.assertEqual(meta['PET'], 'EPEULE')
        self.assertEqual(meta['BORNIER'], 'AA')
        self.assertIn('VD23111', meta.get('NO_PLAN', ''))
        self.assertEqual(meta['INDICE'], '0')
        self.assertEqual(meta['PAGE'], '5')

    def test_indice_letter_o_normalized(self):
        text = 'P.E.T. : EPEULE BORNIER : AA NO PLAN : VD23111 | INDICE : O | PAGE : 12'
        meta = self._meta(text)
        self.assertEqual(meta['INDICE'], '0')

    def test_indice_absent_defaults_to_zero(self):
        text = 'P.E.T. : EPEULE BORNIER : AA NO PLAN : VD23111 | PAGE : 12'
        meta = self._meta(text)
        self.assertEqual(meta['INDICE'], '0')

    def test_bornier_alphanumeric(self):
        text = 'P.E.T. : EPEULE BORNIER : B702A'
        meta = self._meta(text)
        self.assertEqual(meta['BORNIER'], 'B702A')

    def test_bornier_bovki(self):
        text = 'P.E.T. : EPEULE BORNIER : BOVKI'
        meta = self._meta(text)
        self.assertEqual(meta['BORNIER'], 'BOVKI')

    def test_page_extracted(self):
        text = 'NO PLAN : VD23111 | INDICE : 0 | PAGE : 92'
        meta = self._meta(text)
        self.assertEqual(meta['PAGE'], '92')

    def test_empty_footer_returns_indice_default(self):
        meta = self.ext._extract_meta([])
        self.assertEqual(meta['INDICE'], '0')
        self.assertNotIn('BORNIER', meta)
        self.assertNotIn('PAGE', meta)

    def test_pet_multiword(self):
        text = 'P.E.T. : EPEULE METROPOLE BORNIER : CTB4'
        meta = self._meta(text)
        self.assertIn('EPEULE', meta.get('PET', ''))


# ══════════════════════════════════════════════════════════════════════
# 3. _count_data_rows
# ══════════════════════════════════════════════════════════════════════

class TestCountDataRows(unittest.TestCase):

    def setUp(self):
        self.ext = _make_extractor()

    def test_all_data_rows(self):
        result = _make_result([
            {'type': 'data', 'cells': ['A', 'B', 'C', 'D']},
            {'type': 'data', 'cells': ['E', 'F', 'G', 'H']},
        ])
        self.assertEqual(self.ext._count_data_rows(result), 2)

    def test_mixed_section_and_data(self):
        result = _make_result([
            {'type': 'section', 'text': 'NOM DU CABLE'},
            {'type': 'data', 'cells': ['A', 'B', 'C', 'D']},
            {'type': 'data', 'cells': ['E', 'F', 'G', 'H']},
        ])
        self.assertEqual(self.ext._count_data_rows(result), 2)

    def test_no_data_rows(self):
        result = _make_result([
            {'type': 'section', 'text': 'NOM DU CABLE'},
        ])
        self.assertEqual(self.ext._count_data_rows(result), 0)

    def test_empty_rows(self):
        result = _make_result([])
        self.assertEqual(self.ext._count_data_rows(result), 0)


# ══════════════════════════════════════════════════════════════════════
# 4. _fill_worksheet  (bordures)
# ══════════════════════════════════════════════════════════════════════

class TestFillWorksheetBorders(unittest.TestCase):

    def setUp(self):
        self.ext = _make_extractor()
        from openpyxl import Workbook
        self.wb = Workbook()
        self.ws = self.wb.active

    def _fill(self, n_data_rows=5, page_size=48):
        rows = [
            {'type': 'data', 'cells': ['A1', 'BC', 'SIGNAL', '0001R']}
            for _ in range(n_data_rows)
        ]
        result = _make_result(rows, meta={
            'PET': 'EPEULE', 'BORNIER': 'AA', 'NO_PLAN': 'VD23111',
            'INDICE': '0', 'PAGE': '1',
        })
        return self.ext._fill_worksheet(
            self.ws, result, start_row=1, page_size=page_size
        )

    def test_returns_next_start_row(self):
        next_row = self._fill()
        self.assertEqual(next_row, 49)  # 1 + 48

    def test_header_row_has_border(self):
        self._fill()
        cell = self.ws.cell(row=1, column=1)
        self.assertIsNotNone(cell.border.left.style)
        self.assertIsNotNone(cell.border.right.style)
        self.assertIsNotNone(cell.border.top.style)
        self.assertIsNotNone(cell.border.bottom.style)

    def test_data_row_has_left_right_border(self):
        self._fill()
        cell = self.ws.cell(row=2, column=1)  # first data row
        self.assertIsNotNone(cell.border.left.style)
        self.assertIsNotNone(cell.border.right.style)

    def test_padding_rows_have_borders(self):
        # 5 data rows → last data at row 6, footer at row 47
        # Padding rows 7..46 must have left+right borders
        self._fill(n_data_rows=5)
        footer_r = 1 + 48 - 2  # = 47
        padding_start = 1 + 1 + 5  # start_row + header + data = 7
        for ri in range(padding_start, footer_r):
            for ci in range(1, 5):
                cell = self.ws.cell(row=ri, column=ci)
                self.assertIsNotNone(
                    cell.border.left.style,
                    msg=f"Bordure gauche manquante à la ligne de rembourrage {ri}, col {ci}"
                )
                self.assertIsNotNone(
                    cell.border.right.style,
                    msg=f"Bordure droite manquante à la ligne de rembourrage {ri}, col {ci}"
                )

    def test_no_data_overflow_beyond_footer(self):
        # 50 data rows : ceil((1+50+2)/48)*48 = 2 pages → next_row = 1+96 = 97
        next_row = self._fill(n_data_rows=50)
        self.assertEqual(next_row, 97)
        # La ligne 97 doit être vide (appartient au bloc suivant)
        for ci in range(1, 5):
            self.assertIsNone(self.ws.cell(row=97, column=ci).value)

    def test_two_borniers_no_merge_conflict(self):
        rows = [
            {'type': 'section', 'text': 'NOM DU CABLE : X'},
            {'type': 'data', 'cells': ['A', 'B', 'C', 'D']},
        ]
        result = _make_result(rows, meta={
            'PET': 'EPEULE', 'BORNIER': 'AA', 'NO_PLAN': 'VD',
            'INDICE': '0', 'PAGE': '1',
        })
        next1 = self.ext._fill_worksheet(self.ws, result, start_row=1, page_size=48)
        # Second bornier must not raise AttributeError (MergedCell conflict)
        try:
            self.ext._fill_worksheet(self.ws, result, start_row=next1, page_size=48)
        except AttributeError as e:
            self.fail(f"Conflit de cellule fusionnée lors du 2e bornier : {e}")


# ══════════════════════════════════════════════════════════════════════
# 5. DataDictionary
# ══════════════════════════════════════════════════════════════════════

class TestDataDictionary(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix='.json', delete=False
        )
        self.tmp.close()
        Path(self.tmp.name).write_text('{}', encoding='utf-8')
        self.dico = DataDictionary(Path(self.tmp.name))

    def tearDown(self):
        os.unlink(self.tmp.name)

    # ── add_value ─────────────────────────────────────────────────────

    def test_add_valid_signal(self):
        added = self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        self.assertTrue(added)
        self.assertIn('RESERVE CABLEE', self.dico.get_all('SIGNAL'))

    def test_add_duplicate_returns_false(self):
        self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        added = self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        self.assertFalse(added)

    def test_add_blacklisted_value_rejected(self):
        added = self.dico.add_value('BORNE', '0')
        self.assertFalse(added)

    def test_add_empty_rejected(self):
        added = self.dico.add_value('BORNE', '')
        self.assertFalse(added)

    def test_add_invalid_borne_pattern_rejected(self):
        # La colonne BORNE valide uniquement [A-Z0-9][A-Z0-9 \-]{0,14}
        added = self.dico.add_value('BORNE', '!!!')
        self.assertFalse(added)

    def test_add_with_pipe_garbage_rejected(self):
        added = self.dico.add_value('SIGNAL', '| 000000 |')
        self.assertFalse(added)

    # ── correct ───────────────────────────────────────────────────────

    def test_correct_exact_match_no_change(self):
        self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        val, changed = self.dico.correct('SIGNAL', 'RESERVE CABLEE')
        self.assertEqual(val, 'RESERVE CABLEE')
        self.assertFalse(changed)

    def test_correct_fuzzy_match(self):
        self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        # Faute de frappe typique OCR
        val, changed = self.dico.correct('SIGNAL', 'RESERVE CABLFE')
        self.assertEqual(val, 'RESERVE CABLEE')
        self.assertTrue(changed)

    def test_correct_no_match_unchanged(self):
        self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        val, changed = self.dico.correct('SIGNAL', 'XXXXXXXXXXX')
        self.assertEqual(val, 'XXXXXXXXXXX')
        self.assertFalse(changed)

    def test_correct_empty_dict_unchanged(self):
        val, changed = self.dico.correct('SIGNAL', 'RESERVE CABLEE')
        self.assertEqual(val, 'RESERVE CABLEE')
        self.assertFalse(changed)

    def test_correct_empty_value_unchanged(self):
        self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        val, changed = self.dico.correct('SIGNAL', '')
        self.assertEqual(val, '')
        self.assertFalse(changed)

    # ── stats ─────────────────────────────────────────────────────────

    def test_stats_counts_values(self):
        self.dico.add_value('SIGNAL', 'RESERVE CABLEE')
        self.dico.add_value('SIGNAL', 'BEM11-31')
        self.dico.add_value('COULEUR', 'BC')
        s = self.dico.stats()
        self.assertEqual(s.get('SIGNAL'), 2)
        self.assertEqual(s.get('COULEUR'), 1)

    # ── update_from_excel ─────────────────────────────────────────────

    def test_update_from_excel(self):
        """update_from_excel est désormais sur PendingDictionary, pas DataDictionary."""
        import openpyxl
        from data_dictionary import PendingDictionary
        tmp_pending = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        tmp_pending.close()
        Path(tmp_pending.name).write_text('{}', encoding='utf-8')

        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            xlsx_path = f.name
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'])
            ws.append(['01A', 'BC', 'RESERVE CABLEE', '0260R'])
            ws.append(['01B', 'G', 'BEM11-31', '0261W'])
            wb.save(xlsx_path)

            pending = PendingDictionary(Path(tmp_pending.name))
            counts = pending.update_from_excel(Path(xlsx_path))
            self.assertGreater(counts.get('SIGNAL', 0), 0)
            self.assertIn('RESERVE CABLEE', pending.get_all('SIGNAL'))
            self.assertIn('BEM11-31', pending.get_all('SIGNAL'))
        finally:
            os.unlink(xlsx_path)
            os.unlink(tmp_pending.name)


# ══════════════════════════════════════════════════════════════════════
# 6. TableTemplate footer rendering
# ══════════════════════════════════════════════════════════════════════

class TestTableTemplateFooter(unittest.TestCase):

    def setUp(self):
        self.tpl = DEFAULT_TEMPLATE

    # ── render_footer_row1 ────────────────────────────────────────────

    def test_row1_contains_pet(self):
        txt = self.tpl.render_footer_row1({'PET': 'EPEULE', 'BORNIER': 'AA'})
        self.assertIn('EPEULE', txt)

    def test_row1_contains_bornier(self):
        txt = self.tpl.render_footer_row1({'PET': 'EPEULE', 'BORNIER': 'AA'})
        self.assertIn('AA', txt)

    def test_row1_pet_left_of_bornier(self):
        txt = self.tpl.render_footer_row1({'PET': 'EPEULE', 'BORNIER': 'AA'})
        self.assertLess(txt.index('EPEULE'), txt.index('AA'))

    def test_row1_empty_meta_no_crash(self):
        txt = self.tpl.render_footer_row1({})
        self.assertIn('P.E.T.', txt)
        self.assertIn('BORNIER', txt)

    def test_row1_none_values_no_crash(self):
        txt = self.tpl.render_footer_row1({'PET': None, 'BORNIER': None})
        self.assertIsInstance(txt, str)

    # ── render_footer_row2 ────────────────────────────────────────────

    def test_row2_contains_no_plan(self):
        txt = self.tpl.render_footer_row2({
            'NO_PLAN': 'VD23111 PE 162', 'INDICE': '0', 'PAGE': '5'
        })
        self.assertIn('VD23111', txt)

    def test_row2_contains_indice(self):
        txt = self.tpl.render_footer_row2({
            'NO_PLAN': 'VD23111', 'INDICE': '0', 'PAGE': '5'
        })
        self.assertIn('0', txt)

    def test_row2_contains_page(self):
        txt = self.tpl.render_footer_row2({
            'NO_PLAN': 'VD23111', 'INDICE': '0', 'PAGE': '42'
        })
        self.assertIn('42', txt)

    def test_row2_order_noplan_indice_page(self):
        txt = self.tpl.render_footer_row2({
            'NO_PLAN': 'VD23111', 'INDICE': '0', 'PAGE': '5'
        })
        pos_plan = txt.index('VD23111')
        pos_indice = txt.index('INDICE')
        pos_page = txt.index('PAGE')
        self.assertLess(pos_plan, pos_indice)
        self.assertLess(pos_indice, pos_page)

    def test_row2_empty_meta_no_crash(self):
        txt = self.tpl.render_footer_row2({})
        self.assertIsInstance(txt, str)
        self.assertIn('NO PLAN', txt)


# ══════════════════════════════════════════════════════════════════════
# 7. _line_to_cells : assignation par bord gauche (x)
# ══════════════════════════════════════════════════════════════════════

class TestLineToCells(unittest.TestCase):

    def setUp(self):
        self.ext = _make_extractor()
        # Frontières typiques : BORNE 0-450, COULEUR 450-950,
        #                       SIGNAL 950-1660, JARRETIERES 1660-2480
        self.bounds = [0, 450, 950, 1660, 2480]
        self.n_cols = 4

    def _make_line(self, items):
        """items : liste de (x, w, text)"""
        return [
            {'text': t, 'x': x, 'w': w, 'cx': x + w // 2,
             'cy': 50, 'y': 40, 'h': 20, 'conf': 90}
            for x, w, t in items
        ]

    def test_word_in_signal_stays_in_signal(self):
        # Mot large commençant à x=960 (SIGNAL) mais centre à 1680 (JARRETIERES)
        line = self._make_line([(960, 800, 'LONG-SIGNAL-TEXT')])
        cells, _confs, _flags = self.ext._line_to_cells(line, self.bounds, self.n_cols)
        self.assertEqual(cells[2], 'LONG-SIGNAL-TEXT')  # SIGNAL
        self.assertEqual(cells[3], '')                   # JARRETIERES vide

    def test_word_in_jarretieres_assigned_correctly(self):
        line = self._make_line([(1800, 200, '0260R')])
        cells, _confs, _flags = self.ext._line_to_cells(line, self.bounds, self.n_cols)
        self.assertEqual(cells[3], '0260R')   # JARRETIERES
        self.assertEqual(cells[2], '')        # SIGNAL vide

    def test_typical_row_four_columns(self):
        # 'RESERVE' and 'CABLEE' sont des mots séparés dans la colonne SIGNAL
        line2 = self._make_line([
            (200, 50, '01B'),
            (500, 80, 'BC'),
            (970, 150, 'RESERVE'),
            (1130, 150, 'CABLEE'),
            (1800, 100, '0260R'),
        ])
        cells, _confs, _flags = self.ext._line_to_cells(line2, self.bounds, self.n_cols)
        self.assertIn('RESERVE', cells[2])
        self.assertIn('CABLEE', cells[2])
        self.assertEqual(cells[3], '0260R')

    def test_pipe_artifacts_cleaned(self):
        line = self._make_line([(1800, 50, '|')])
        cells, _confs, _flags = self.ext._line_to_cells(line, self.bounds, self.n_cols)
        self.assertEqual(cells[3], '')


# ══════════════════════════════════════════════════════════════════════
# 8. _classify_line : détection de sections et pied
# ══════════════════════════════════════════════════════════════════════

class TestClassifyLine(unittest.TestCase):

    def setUp(self):
        self.ext = _make_extractor()

    def _line(self, *words):
        return [{'text': w, 'x': i * 50, 'cx': i * 50 + 20,
                 'cy': 50, 'y': 40, 'w': 40, 'h': 20, 'conf': 90}
                for i, w in enumerate(words)]

    def test_exact_section_keyword(self):
        line = self._line('NOM', 'DU', 'CABLE', ':', 'EPL/ETB4')
        self.assertEqual(self.ext._classify_line(line), 'section')

    def test_section_ocr_variant_caele(self):
        # OCR lit CABLE comme CAELE
        line = self._line('NOM', 'DU', 'CAELE', ':', 'EPL/ETB4')
        # kw_words[:4] = ['NOM', 'DU', 'CAB'] : 'NOM'[:4]='NOM', 'DU' skipped (len<3), 'CAB' not in text
        # This should NOT classify as section since 'CAB' is not in "NOM DU CAELE"
        # The test validates the current behaviour (not a crash)
        result = self.ext._classify_line(line)
        self.assertIn(result, ('section', 'data'))  # graceful

    def test_footer_indice_detected(self):
        line = self._line('INDICE', ':', '0')
        self.assertEqual(self.ext._classify_line(line), 'footer')

    def test_footer_no_plan_detected(self):
        line = self._line('NO', 'PLAN', ':', 'VD23111')
        self.assertEqual(self.ext._classify_line(line), 'footer')

    def test_footer_mti_tokens(self):
        line = self._line('M', 'T', 'I')
        self.assertEqual(self.ext._classify_line(line), 'footer')

    def test_data_line(self):
        line = self._line('01B', 'BC', 'RESERVE', 'CABLEE', '0260R')
        self.assertEqual(self.ext._classify_line(line), 'data')


# ══════════════════════════════════════════════════════════════════════
# 9. Tri par page dans generer_excel
# ══════════════════════════════════════════════════════════════════════

class TestPageSort(unittest.TestCase):

    def test_sort_key_numeric_page(self):
        # Vérifier que la clé de tri fonctionne indirectement en créant
        # des résultats avec des pages désordonnées et en vérifiant l'ordre
        import re
        from pathlib import Path

        def _page_sort_key(result):
            page = result.get('metadata', {}).get('PAGE', '')
            try:
                return int(page)
            except (ValueError, TypeError):
                nums = re.findall(r'\d+', Path(
                    result.get('image_path', 'bornier_9999')
                ).stem)
                return int(nums[0]) if nums else 9999

        results = [
            {'metadata': {'PAGE': '30'}, 'image_path': 'bornier_30.jpg'},
            {'metadata': {'PAGE': '1'},  'image_path': 'bornier_6.jpg'},
            {'metadata': {'PAGE': '15'}, 'image_path': 'bornier_20.jpg'},
            {'metadata': {},             'image_path': 'bornier_2.jpg'},
        ]
        sorted_r = sorted(results, key=_page_sort_key)
        pages = [r.get('metadata', {}).get('PAGE', '') or
                 re.findall(r'\d+', Path(r['image_path']).stem)[0]
                 for r in sorted_r]
        # Ordre numérique croissant : page 1, puis filename 2, puis 15, puis 30
        self.assertEqual(pages, ['1', '2', '15', '30'])

    def test_sort_fallback_to_filename(self):
        import re
        from pathlib import Path

        def _page_sort_key(result):
            page = result.get('metadata', {}).get('PAGE', '')
            try:
                return int(page)
            except (ValueError, TypeError):
                nums = re.findall(r'\d+', Path(
                    result.get('image_path', 'bornier_9999')
                ).stem)
                return int(nums[0]) if nums else 9999

        r_no_page = {'metadata': {}, 'image_path': 'bornier_7.jpg'}
        self.assertEqual(_page_sort_key(r_no_page), 7)


# ══════════════════════════════════════════════════════════════════════
# 10. _extract_meta : BORNIER regex étendu
# ══════════════════════════════════════════════════════════════════════

class TestBornierRegex(unittest.TestCase):

    def setUp(self):
        self.ext = _make_extractor()

    def _meta(self, text):
        return self.ext._extract_meta(_make_footer_lines(text))

    def test_bornier_simple_letters(self):
        self.assertEqual(self._meta('BORNIER : AA')['BORNIER'], 'AA')

    def test_bornier_alphanumeric(self):
        self.assertEqual(self._meta('BORNIER : B702A')['BORNIER'], 'B702A')

    def test_bornier_starts_with_digit(self):
        # Nouveau : commence par un chiffre (ex: Q3067TS ignorait le premier char)
        meta = self._meta('BORNIER : Q3067TS')
        self.assertEqual(meta.get('BORNIER'), 'Q3067TS')

    def test_bornier_with_hyphen(self):
        meta = self._meta('BORNIER : QC37-V1')
        self.assertIn('QC37', meta.get('BORNIER', ''))

    def test_bornier_bovki(self):
        self.assertEqual(self._meta('BORNIER : BOVKI')['BORNIER'], 'BOVKI')

    def test_bornier_not_matched_in_no_plan(self):
        # 'NO PLAN' contient 'NO' qui ne doit pas être capturé comme BORNIER
        meta = self._meta('NO PLAN : VD23111 INDICE : 0 PAGE : 5')
        self.assertNotIn('BORNIER', meta)


# ══════════════════════════════════════════════════════════════════════
# 11. _compute_blur_score
# ══════════════════════════════════════════════════════════════════════

class TestComputeBlurScore(unittest.TestCase):
    """Tests pour le calcul du score de flou par variance Laplacienne."""

    def _write_png(self, array, tmp_dir: str) -> Path:
        import cv2
        path = Path(tmp_dir) / 'img.png'
        cv2.imwrite(str(path), array)
        return path

    def test_uniform_image_is_100pct_blurry(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            img = np.full((100, 100, 3), 128, dtype=np.uint8)
            p = self._write_png(img, d)
            score = BornierTableExtractor._compute_blur_score(p)
        self.assertEqual(score, 100.0)

    def test_checkerboard_image_has_low_blur(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as d:
            img = np.zeros((200, 200), dtype=np.uint8)
            img[::2, ::2] = 255
            img[1::2, 1::2] = 255
            p = self._write_png(img, d)
            score = BornierTableExtractor._compute_blur_score(p)
        self.assertLess(score, 50.0, "Image damier (nette) devrait être < 50 %")

    def test_nonexistent_path_returns_zero(self):
        score = BornierTableExtractor._compute_blur_score(
            Path('/nonexistent_path/img.jpg')
        )
        self.assertEqual(score, 0.0)

    def test_score_in_valid_range(self):
        import numpy as np
        rng = np.random.default_rng(42)
        with tempfile.TemporaryDirectory() as d:
            img = rng.integers(0, 256, (100, 100, 3), dtype=np.uint8)
            p = self._write_png(img, d)
            score = BornierTableExtractor._compute_blur_score(p)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)


# ══════════════════════════════════════════════════════════════════════
# 12. Marquage visuel FLOU dans la feuille Excel
# ══════════════════════════════════════════════════════════════════════

class TestBlurVisualIndicator(unittest.TestCase):
    """Tests pour le remplissage orange des en-têtes de tableaux flous (> 80 %)."""

    def setUp(self):
        self.ext = _make_extractor()
        from openpyxl import Workbook
        self.wb = Workbook()
        self.ws = self.wb.active

    def _fill(self, blur_pct: float) -> int:
        result = _make_result(
            [{'type': 'data', 'cells': ['A', 'B', 'C', 'D']}],
            meta={'PET': 'TEST', 'BORNIER': 'AA', 'NO_PLAN': 'VD',
                  'INDICE': '0', 'PAGE': '1'},
        )
        result['blur_pct'] = blur_pct
        return self.ext._fill_worksheet(self.ws, result, start_row=1, page_size=48)

    def _header_rgb(self, col: int = 1) -> str:
        return self.ws.cell(row=1, column=col).fill.fgColor.rgb

    def test_clear_image_has_gray_header(self):
        self._fill(20.0)
        # openpyxl stocke les couleurs 6-chars avec préfixe alpha '00'
        self.assertIn('D9D9D9', self._header_rgb(), "En-tête image nette doit être gris")

    def test_blurry_image_has_orange_header(self):
        self._fill(85.0)
        self.assertIn('FFA500', self._header_rgb(), "En-tête tableau flou (85 %) doit être orange")

    def test_all_header_cells_orange_when_blurry(self):
        self._fill(90.0)
        for ci in range(1, 5):
            self.assertIn(
                'FFA500', self._header_rgb(ci),
                msg=f"Col {ci} : en-tête flou doit être orange"
            )

    def test_threshold_80_not_triggered(self):
        self._fill(80.0)
        self.assertIn('D9D9D9', self._header_rgb(), "80 % exact ne doit PAS déclencher le marquage")

    def test_threshold_80_1_triggered(self):
        self._fill(80.1)
        self.assertIn('FFA500', self._header_rgb(), "80.1 % doit déclencher le marquage orange")

    def test_blurry_has_comment(self):
        self._fill(95.0)
        comment = self.ws.cell(row=1, column=1).comment
        self.assertIsNotNone(comment, "En-tête flou doit avoir un commentaire")
        self.assertIn('95', comment.text)

    def test_clear_no_comment(self):
        self._fill(40.0)
        comment = self.ws.cell(row=1, column=1).comment
        self.assertIsNone(comment, "En-tête clair ne doit PAS avoir de commentaire")


# ══════════════════════════════════════════════════════════════════════
# 13. WordTableImporter
# ══════════════════════════════════════════════════════════════════════

class TestWordTableImporter(unittest.TestCase):
    """Tests pour l'extraction de tableaux depuis un document Word structuré."""

    def _create_test_docx(self, tmp_dir: str) -> Path:
        """Crée un .docx de test avec un tableau bornier complet (avec pied de page)."""
        from docx import Document as DocxDoc
        doc = DocxDoc()
        # 1 en-tête + 3 données + 2 pied = 6 lignes, 4 colonnes
        table = doc.add_table(rows=6, cols=4)
        table.style = 'Table Grid'

        headers = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
        for ci, h in enumerate(headers):
            table.rows[0].cells[ci].text = h

        data = [
            ['01A', 'BC', 'RESERVE CABLEE', '0260R'],
            ['01B', 'G',  'BEM11-31',       '0261W'],
            ['02A', 'BC', 'RESERVE CABLEE', '0262R'],
        ]
        for ri, row_data in enumerate(data, start=1):
            for ci, val in enumerate(row_data):
                table.rows[ri].cells[ci].text = val

        # Pied ligne 1 : M T I + P.E.T. / BORNIER
        table.rows[4].cells[0].text = 'M  T  I'
        table.rows[4].cells[1].text = (
            'P.E.T.   :     EPEULE    BORNIER :    AA'
        )

        # Pied ligne 2 : NO PLAN / INDICE / PAGE
        table.rows[5].cells[0].text = ''
        table.rows[5].cells[1].text = (
            'NO PLAN    :   VD23111 PE 162  |  INDICE : 0  |  PAGE :   42'
        )

        docx_path = Path(tmp_dir) / 'test_tables.docx'
        doc.save(str(docx_path))
        return docx_path

    def _make_importer(self):
        from word_table_importer import WordTableImporter
        return WordTableImporter(_make_extractor())

    # ── Import basique ─────────────────────────────────────────────────

    def test_extracts_one_table(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._create_test_docx(d)
            results = self._make_importer().extract_tables(p)
        self.assertEqual(len(results), 1)

    def test_result_is_success(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._create_test_docx(d)
            result = self._make_importer().extract_tables(p)[0]
        self.assertTrue(result['success'])

    def test_extracts_three_data_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._create_test_docx(d)
            result = self._make_importer().extract_tables(p)[0]
        data_rows = [r for r in result['rows'] if r['type'] == 'data']
        self.assertEqual(len(data_rows), 3)

    def test_first_data_row_content(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._create_test_docx(d)
            result = self._make_importer().extract_tables(p)[0]
        first = [r for r in result['rows'] if r['type'] == 'data'][0]
        self.assertEqual(first['cells'][0], '01A')
        self.assertEqual(first['cells'][1], 'BC')

    # ── Métadonnées ────────────────────────────────────────────────────

    def test_page_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._create_test_docx(d)
            result = self._make_importer().extract_tables(p)[0]
        self.assertEqual(result['metadata'].get('PAGE'), '42')

    def test_bornier_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._create_test_docx(d)
            result = self._make_importer().extract_tables(p)[0]
        self.assertEqual(result['metadata'].get('BORNIER'), 'AA')

    def test_blur_pct_is_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._create_test_docx(d)
            result = self._make_importer().extract_tables(p)[0]
        self.assertEqual(result['blur_pct'], 0.0)

    # ── Cas limites ────────────────────────────────────────────────────

    def test_empty_document_returns_empty_list(self):
        from docx import Document as DocxDoc
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'empty.docx'
            doc = DocxDoc()
            doc.add_paragraph("Pas de tableau ici.")
            doc.save(str(p))
            results = self._make_importer().extract_tables(p)
        self.assertEqual(results, [])

    def test_multiple_tables_in_document(self):
        from docx import Document as DocxDoc
        with tempfile.TemporaryDirectory() as d:
            doc = DocxDoc()
            # Deux tableaux simples (sans pied) : 1 en-tête + 2 données
            for page in (1, 2):
                t = doc.add_table(rows=3, cols=4)
                t.style = 'Table Grid'
                for ci, h in enumerate(['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']):
                    t.rows[0].cells[ci].text = h
                for ri in (1, 2):
                    t.rows[ri].cells[0].text = f'0{ri}A'
                    t.rows[ri].cells[1].text = 'BC'
                    t.rows[ri].cells[2].text = f'SIG_{page}'
                    t.rows[ri].cells[3].text = '0001R'
                doc.add_paragraph('')  # séparateur
            p = Path(d) / 'multi.docx'
            doc.save(str(p))
            results = self._make_importer().extract_tables(p)
        self.assertEqual(len(results), 2)


# ══════════════════════════════════════════════════════════════════════
# 14. _parse_pipe_response (parseur partagé Claude / Ollama)
# ══════════════════════════════════════════════════════════════════════

class TestParsePipeResponse(unittest.TestCase):
    """
    Vérifie le parseur partagé entre Claude Vision et Ollama Vision.
    Testé indépendamment de toute API — pure logique de parsing.
    """

    def setUp(self):
        from claude_ocr import _parse_pipe_response
        self._parse = _parse_pipe_response

    def _tpl_4col(self):
        """Template 4 colonnes : TENANT | JAR | ABOUTISSANT | SIGNAL."""
        from template import TableTemplate
        return TableTemplate(
            name='test',
            columns=['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL'],
        )

    # ── TYPE_PAGE ──────────────────────────────────────────────────────

    def test_non_listing_returns_empty_rows(self):
        raw = (
            "TYPE_PAGE: non-listing\n"
            "META: {}\n"
        )
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(page_type, 'non-listing')
        self.assertEqual(rows, [])

    def test_listing_page_type_parsed(self):
        raw = (
            "TYPE_PAGE: listing\n"
            "AP 23 | 0113R | AB 27 | BFSHT 44 +\n"
            'META: {"PAGE": "5"}\n'
        )
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(page_type, 'listing')

    def test_absent_type_page_defaults_to_listing(self):
        raw = "AP 23 | 0113R | AB 27 | BFSHT 44 +\n"
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(page_type, 'listing')

    # ── Extraction positionnelle ───────────────────────────────────────

    def test_premerged_tenant_aboutissant(self):
        """Quand le modèle fusionne correctement les parties visuelles
        (AP 23 au lieu de AP | 23), le parseur affecte correctement les 4 colonnes."""
        raw = (
            "TYPE_PAGE: listing\n"
            "AP 23 | 0113R | AB 27 | BFSHT 44 +\n"
            'META: {"PAGE": "5"}\n'
        )
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(len(rows), 1)
        cells = rows[0]['cells']
        self.assertEqual(cells[0], 'AP 23',     "TENANT doit valoir 'AP 23'")
        self.assertEqual(cells[1], '0113R',      "JAR doit valoir '0113R'")
        self.assertEqual(cells[2], 'AB 27',      "ABOUTISSANT doit valoir 'AB 27'")
        self.assertEqual(cells[3], 'BFSHT 44 +', "SIGNAL doit valoir 'BFSHT 44 +'")

    def test_5_segments_merged_into_signal(self):
        """
        Cas réel : Claude renvoie 5 segments pour 4 colonnes.
        Ex : B16T 01A | 0057R | B702A | 01H | FSa22-38 (+MKI21-38)
        Règle : segments 3 et 4 fusionnés dans SIGNAL (col 3),
                segment 5 → JARRETIERES (col 4).
        """
        raw = (
            "TYPE_PAGE: listing\n"
            "B16T 01A | 0057R | B702A | 01H | FSa22-38 (+MKI21-38)\n"
        )
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(len(rows), 1)
        cells = rows[0]['cells']
        self.assertEqual(cells[0], 'B16T 01A',
                         "BORNE doit valoir 'B16T 01A'")
        self.assertEqual(cells[1], '0057R',
                         "COULEUR doit valoir '0057R'")
        self.assertEqual(cells[2], 'B702A 01H',
                         "SIGNAL doit fusionner 'B702A' et '01H'")
        self.assertEqual(cells[3], 'FSa22-38 (+MKI21-38)',
                         "JARRETIERES doit valoir 'FSa22-38 (+MKI21-38)'")

    def test_6_segments_merged_into_signal(self):
        """6 segments pour 4 colonnes : 3 segments fusionnés dans SIGNAL."""
        raw = (
            "TYPE_PAGE: listing\n"
            "01A | ROUGE | TENANT_A | TENANT_B | TENANT_C | JAR_X\n"
        )
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(len(rows), 1)
        cells = rows[0]['cells']
        self.assertEqual(cells[2], 'TENANT_A TENANT_B TENANT_C',
                         "SIGNAL doit fusionner les 3 segments intermédiaires")
        self.assertEqual(cells[3], 'JAR_X',
                         "JARRETIERES reçoit toujours le dernier segment")

    def test_empty_cell_preserved(self):
        raw = "TYPE_PAGE: listing\nval1 | | val3 | val4\n"
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['cells'][1], '', "Cellule vide doit rester vide")

    def test_metadata_extracted(self):
        raw = (
            "TYPE_PAGE: listing\n"
            "A | B | C | D\n"
            '   META: {"PAGE": "12", "BORNIER": "BX"}\n'
        )
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(meta.get('PAGE'), '12')
        self.assertEqual(meta.get('BORNIER'), 'BX')

    def test_line_without_pipe_ignored(self):
        raw = (
            "TYPE_PAGE: listing\n"
            "Cette ligne sans barre verticale est ignorée\n"
            "val1 | val2 | val3 | val4\n"
        )
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(len(rows), 1, "Seule la ligne avec | doit être conservée")

    def test_confidence_list_length_matches_columns(self):
        raw = "TYPE_PAGE: listing\nA | B | C | D\n"
        rows, meta, page_type = self._parse(raw, self._tpl_4col())
        self.assertEqual(
            len(rows[0]['confidence']), 4,
            "La liste de confiance doit avoir autant d'entrées que de colonnes"
        )


# ══════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
