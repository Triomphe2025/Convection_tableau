"""
Lignes de section (« NOM DU CABLE : … ») sur les pages lues par Claude (décision du
2026-10-05) : le prompt demande de les recopier telles qu'imprimées, à leur place,
précédées de SECTION: ; le parseur en fait des lignes 'section' du format pivot.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_sections_claude.py -v
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from claude_ocr import LogReplayer, _build_prompt, _parse_pipe_response
from generer_classeur import generer_excel
from mesurer_precision import lire_verite_excel, lire_xlsx
from pdf_extractor import PdfTableExtractor
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'
TPL = TemplateManager().get('Bornier standard')
REPONSE = '\n'.join([
    'TYPE_PAGE: listing',
    'SECTION: NOM DU CABLE : WPHR/A105',
    '01 | 1 B | EMISSION PHONIE | 2127N 1034N',
    '02 | 2 BC | EMISSION PHONIE | 1035N 2128N',
    'SECTION: NOM DU CABLE : BRPH01/PH01',
    '03 | 3 J | BLINDAGE PHONIE EM PH | ',
    'META: {"PAGE": "", "BORNIER": "C105A", "PET": "SAINT PHILIBERT"}',
    'PIED_BRUT: P.E.T. : SAINT PHILIBERT BORNIER : C105A',
    'PIED_BRUT: NO PLAN : 223 111 PE 012 | INDICE : R4',
    'LOGO: M A T R A',
])


class TestPrompt(unittest.TestCase):

    def test_sections_demandees_telles_qu_imprimees(self):
        prompt = _build_prompt(TPL)
        self.assertIn('SECTION: NOM DU CABLE :', prompt)
        self.assertIn('telle qu', prompt)
        self.assertNotIn('Ne pas inclure les lignes de séparation', prompt)

    def test_mot_de_section_du_modele(self):
        tpl = TemplateManager().get('REPARTITEUR')
        self.assertIn(f'SECTION: {tpl.section_keyword} :', _build_prompt(tpl))


class TestParseur(unittest.TestCase):

    def test_section_a_sa_place(self):
        rows, _, _ = _parse_pipe_response(REPONSE, TPL)
        self.assertEqual([r['type'] for r in rows],
                         ['section', 'data', 'data', 'section', 'data'])
        self.assertEqual(rows[0], {'type': 'section', 'text': 'NOM DU CABLE : WPHR/A105'})
        self.assertEqual(rows[1]['cells'], ['01', '1 B', 'EMISSION PHONIE', '2127N 1034N'])

    def test_section_vide_ignoree(self):
        rows, _, _ = _parse_pipe_response('TYPE_PAGE: listing\nSECTION:\nA1 | | B | C', TPL)
        self.assertEqual([r['type'] for r in rows], ['data'])

    def test_pied_inchange(self):
        _, meta, _ = _parse_pipe_response(REPONSE, TPL)
        self.assertEqual((meta['BORNIER'], meta['LOGO']), ('C105A', 'M A T R A'))


class TestRejeuDuJournal(unittest.TestCase):

    def test_sections_retrouvees_depuis_la_reponse_brute(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / 'x_claude.jsonl'
            entree = {'image': 'page_008.png', 'success': True, 'raw': REPONSE}
            journal.write_text(json.dumps(entree) + '\n', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                resultats = LogReplayer(journal, TPL).replay_all()
        self.assertEqual([r['type'] for r in resultats[0]['rows']][:1], ['section'])


class TestExcelContreLaVerite(unittest.TestCase):

    def test_section_livree_comme_dans_la_verite(self):
        rows, meta, _ = _parse_pipe_response(REPONSE, TPL)
        page = {'success': True, 'headers': list(TPL.columns), 'metadata': meta, 'rows': rows,
                'image_path': 'page_008.png', 'detection_method': 'claude-vision'}
        with tempfile.TemporaryDirectory() as tmp:
            sortie = Path(tmp) / 's.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                generer_excel([page], PdfTableExtractor(TPL), sortie, on_log=lambda m: None)
            livrees = [r['text'] for r in lire_xlsx(sortie)[0]['rows'] if r['type'] == 'section']
        verite, _ = lire_verite_excel(FIX / '223111PE012_extrait_verite.xlsx')
        attendues = {r['text'] for p in verite for r in p['rows'] if r['type'] == 'section'}
        self.assertEqual(livrees, ['NOM DU CABLE : WPHR/A105', 'NOM DU CABLE : BRPH01/PH01'])
        self.assertTrue(set(livrees) <= attendues)


if __name__ == '__main__':
    unittest.main()
