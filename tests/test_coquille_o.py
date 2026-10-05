"""
Décision B3 — coquille O/0 : dans le numéro de borne (2e sous-champ de TENANT,
ABOUTISSANT ou BORNE) uniquement, « O1A » → « 01A », cellule orange commentée,
une alerte par cellule. Jamais ailleurs ; la lecture reste telle qu'imprimée.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_coquille_o.py -v
"""
import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path

import fitz
import openpyxl

from config import Config
from generer_classeur import corriger_coquilles_o, corriger_numero_borne, generer_excel
from mesure_precision import mesurer
from mesurer_precision import lire_attentes, lire_verite_excel, lire_xlsx
from mesure_precision import comparer_alertes
from pdf_extractor import PdfTableExtractor
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'
PE133 = FIX / '6A23111PE133_extrait_8pages.pdf'
VERITE = FIX / '6A23111PE133_extrait_verite.xlsx'
COLONNES = ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL']


def _page(*lignes):
    return {'success': True, 'headers': COLONNES, 'metadata': {'PAGE': '18'},
            'detection_method': 'pdf-grille', 'image_path': 'p',
            'rows': [{'type': 'data', 'cells': list(c), 'confidence': [100] * 4}
                     for c in lignes]}


class TestCorrigerNumeroBorne(unittest.TestCase):

    def test_coquilles_de_6a23111pe133(self):
        for lu, attendu in (('D3T O1A', 'D3T 01A'), ('D3T O1B', 'D3T 01B'),
                            ('D6T O1B', 'D6T 01B'), ('D62T O1A', 'D62T 01A'),
                            ('B16T O12', 'B16T 012'), ('X O5', 'X 05')):
            with self.subTest(lu=lu):
                self.assertEqual(corriger_numero_borne(lu), (attendu, lu.split()[1]))

    def test_espacement_conserve(self):
        self.assertEqual(corriger_numero_borne('D3T   O1A')[0], 'D3T   01A')

    def test_inchanges(self):
        for lu in ('OC21-37', 'QG 09', '0VG (EAS)', 'D3T 01A', 'O1A', 'D3T O1A X',
                   'D3T OA1', 'D3T O123', 'D3T OK', 'D3T O1AB', '', 'OCFS15-38'):
            with self.subTest(lu=lu):
                self.assertEqual(corriger_numero_borne(lu), (lu, None))


class TestCorrigerCoquillesO(unittest.TestCase):

    def test_seules_les_colonnes_de_borne(self):
        pages = [_page(('D3T O1A', 'O1A', 'D62T O1A', 'X O1A'))]
        resultats, alertes = corriger_coquilles_o(pages, Config.CORRECTION_O_COLONNES)
        self.assertEqual(resultats[0]['rows'][0]['cells'], ['D3T 01A', 'O1A', 'D62T 01A', 'X O1A'])
        self.assertEqual(resultats[0]['rows'][0]['corrections_o'], {0: 'O1A', 2: 'O1A'})
        self.assertEqual(len(alertes), 2)
        self.assertIn("Corrigé O → 0 : l'original porte « D3T O1A »", alertes[0])
        self.assertIn('page 18', alertes[0])

    def test_inchanges_sans_alerte(self):
        pages = [_page(('OC21-37', '0953B', 'QG 09', '0VG (EAS)'))]
        resultats, alertes = corriger_coquilles_o(pages, Config.CORRECTION_O_COLONNES)
        self.assertEqual(resultats[0]['rows'][0]['cells'], ['OC21-37', '0953B', 'QG 09',
                                                            '0VG (EAS)'])
        self.assertNotIn('corrections_o', resultats[0]['rows'][0])
        self.assertEqual(alertes, [])

    def test_colonne_borne_du_modele_standard(self):
        page = _page(('B16T O1A', 'ROUGE', 'LIG', '0733B'))
        page['headers'] = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
        resultats, _ = corriger_coquilles_o([page], Config.CORRECTION_O_COLONNES)
        self.assertEqual(resultats[0]['rows'][0]['cells'][0], 'B16T 01A')

    def test_entree_non_modifiee(self):
        pages = [_page(('D3T O1A', '', '', ''))]
        avant = copy.deepcopy(pages)
        corriger_coquilles_o(pages, Config.CORRECTION_O_COLONNES)
        self.assertEqual(pages, avant)


def _pe133_p8():
    tpl = TemplateManager().get('REPARTITEUR')
    lecteur = PdfTableExtractor(tpl)
    with fitz.open(str(PE133)) as doc:
        resultat = lecteur.extract_page_grille(doc[7], 7)
    return tpl, lecteur, resultat


class TestPE133Page8(unittest.TestCase):
    """Les 4 cellules O1A de la page 8 : lecture inchangée, Excel corrigé et signalé."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, lecteur, cls.lu = _pe133_p8()
        cls.journal = []
        with tempfile.TemporaryDirectory() as tmp:
            sortie = Path(tmp) / 's.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                generer_excel([cls.lu], lecteur, sortie, on_log=cls.journal.append)
            ws = openpyxl.load_workbook(sortie).worksheets[0]
            cls.marquees = {(c.column_letter, ' '.join(c.value.split()),
                             c.comment.text.split('\n')[0])
                            for ligne in ws.iter_rows() for c in ligne
                            if c.fill.fgColor.rgb == '00' + Config.COULEUR_CORRIGE}
            cls.converti = lire_xlsx(sortie)

    def test_lecture_reste_telle_qu_imprimee(self):
        lues = sorted(' '.join(r['cells'][k].split()) for r in self.lu['rows']
                      if r['type'] == 'data' for k in (0, 2) if ' O1' in r['cells'][k])
        self.assertEqual(lues, ['D3T O1A', 'D3T O1B', 'D62T O1A', 'D6T O1B'])

    def test_quatre_cellules_orange_commentees(self):
        self.assertEqual(self.marquees, {
            ('A', 'D3T 01A', "corrigé : l'original porte O1A"),
            ('A', 'D3T 01B', "corrigé : l'original porte O1B"),
            ('A', 'D6T 01B', "corrigé : l'original porte O1B"),
            ('C', 'D62T 01A', "corrigé : l'original porte O1A")})

    def test_plus_aucun_ecart_de_cellule_contre_la_verite(self):
        verite, colonnes = lire_verite_excel(VERITE)
        page8 = verite[-1:]          # pages d'extrait 4 à 8 : la dernière
        rapport = mesurer(page8, self.converti, colonnes)
        self.assertEqual(rapport.ecarts_cellules, [])

    def test_alertes_attendues_emises_et_aucune_fausse_sur_la_correction(self):
        attendues = lire_attentes(VERITE)['alertes']
        emises = [lg.split('⚠', 1)[1].strip() for lg in self.journal if '⚠' in lg]
        manquantes, fausses = comparer_alertes(attendues, emises)
        self.assertEqual(manquantes, [])
        self.assertFalse([f for f in fausses if 'Corrigé' in f])

    def test_numeros_de_ligne_de_la_verite(self):
        lignes = [lg for lg in self.journal if 'Corrigé O → 0' in lg]
        self.assertEqual([lg.split('ligne ')[1].split(',')[0] for lg in lignes],
                         ['3', '4', '8', '24'])


if __name__ == '__main__':
    unittest.main()
