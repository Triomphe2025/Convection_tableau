"""
Décision B2 — logo tel qu'imprimé sur 223111PE012 : « SIEMENS » reste collé,
« M A T R A » reste espacé, de la lecture jusqu'à la cellule gauche du pied de l'Excel.

Pages vectorielles (SIEMENS) : grille → Excel. Pages scannées (MATRA) : réponses
Claude fabriquées, sans appel API.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_logo_pe012.py -v
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import fitz
import openpyxl

from claude_ocr import _parse_pipe_response
from generer_classeur import generer_excel
from mesurer_precision import lire_xlsx
from pdf_extractor import PdfTableExtractor
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'
PDF = FIX / '223111PE012_extrait_10pages.pdf'
VERITE = FIX / '223111PE012_extrait_verite.xlsx'
PAGES_VECTORIELLES = (5, 9, 10)          # numéros d'extrait

PIED_P1 = ['P.E.T. : SAINT PHILIBERT     BORNIER : AA',
           'N° PLAN : 223 111 PE 012       INDICE : R']


def _logos_verite():
    ws = openpyxl.load_workbook(VERITE, data_only=True)['Verite_pieds']
    return {r[0]: r[2] for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}


def _logos_excel(resultats, tpl):
    with tempfile.TemporaryDirectory() as tmp:
        sortie = Path(tmp) / 's.xlsx'
        with contextlib.redirect_stdout(io.StringIO()):
            generer_excel(resultats, PdfTableExtractor(tpl), sortie, on_log=lambda m: None)
        pages = lire_xlsx(sortie)
    return [next((lg.split(':', 1)[1].strip() for lg in p['pied_texte']
                  if lg.startswith('LOGO :')), '') for p in pages]


def _reponse(logo_ligne, pied=PIED_P1):
    lignes = ['TYPE_PAGE: listing', 'A1 |  | LIG | 0733B']
    lignes += [f'PIED_BRUT: {lg}' for lg in pied]
    if logo_ligne is not None:
        lignes.append(f'LOGO: {logo_ligne}')
    return '\n'.join(lignes)


def _page_claude(reponse, tpl):
    rows, meta, _ = _parse_pipe_response(reponse, tpl)
    return {'success': True, 'headers': list(tpl.columns), 'metadata': meta,
            'rows': rows, 'image_path': 'p', 'detection_method': 'claude-vision'}


class TestSiemensColleSurLesPagesVectorielles(unittest.TestCase):

    def test_verite_attend_siemens_colle(self):
        verite = _logos_verite()
        self.assertEqual([verite[p] for p in PAGES_VECTORIELLES], ['SIEMENS'] * 3)

    def test_grille_puis_excel(self):
        tpl = TemplateManager().get('Bornier standard')
        lecteur = PdfTableExtractor(tpl)
        with fitz.open(str(PDF)) as doc:
            resultats = [lecteur.extract_page_grille(doc[p - 1], p - 1)
                         for p in PAGES_VECTORIELLES]
        self.assertEqual([r['metadata'].get('LOGO') for r in resultats], ['SIEMENS'] * 3)
        self.assertEqual(_logos_excel(resultats, tpl), ['SIEMENS'] * 3)


class TestMatraEspaceSurLesPagesScannees(unittest.TestCase):

    def setUp(self):
        self.tpl = TemplateManager().get('Bornier standard')

    def test_verite_attend_matra_espace(self):
        verite = _logos_verite()
        self.assertEqual([verite[p] for p in (4, 6, 7, 8)], ['M A T R A'] * 4)

    def test_ligne_logo_espacee_gardee_jusqu_a_l_excel(self):
        page = _page_claude(_reponse('M A T R A'), self.tpl)
        self.assertEqual(page['metadata']['LOGO'], 'M A T R A')
        self.assertEqual(_logos_excel([page], self.tpl), ['M A T R A'])

    def test_logo_vertical_recopie_dans_le_pied_sans_ligne_logo(self):
        pied = ['| M |  P.E.T. : SAINT PHILIBERT     BORNIER : AA', '| A |', '| T |',
                '| R |  N° PLAN : 223 111 PE 012       INDICE : R', '| A |']
        page = _page_claude(_reponse(None, pied), self.tpl)
        self.assertEqual(page['metadata']['LOGO'], 'M A T R A')
        self.assertNotIn('M', ' '.join(page['metadata']['PIED_BRUT']).split())

    def test_siemens_lu_par_claude_reste_colle(self):
        page = _page_claude(_reponse('SIEMENS'), self.tpl)
        self.assertEqual(page['metadata']['LOGO'], 'SIEMENS')
        self.assertEqual(_logos_excel([page], self.tpl), ['SIEMENS'])

    def test_aucune_forme_convertie_en_l_autre(self):
        for lu in ('SIEMENS', 'M A T R A', 'MATRA', 'S I E M E N S'):
            with self.subTest(lu=lu):
                self.assertEqual(_page_claude(_reponse(lu), self.tpl)['metadata']['LOGO'], lu)


if __name__ == '__main__':
    unittest.main()
