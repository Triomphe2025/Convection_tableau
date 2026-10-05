"""
Numéros de page : suffixe lettre accepté, jamais renuméroté, jamais retrié en silence.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_numeros_page.py -v
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import fitz
import openpyxl

import pdf_extractor as pe
from generer_classeur import alertes_sequence_pages, cle_numero_page, generer_excel
from ocr_processor import BornierTableExtractor
from template import DEFAULT_TEMPLATE, TemplateManager

FIXTURES = Path(__file__).parent / 'fixtures'
EXTRAIT = FIXTURES / '223111PE011_extrait_10pages.pdf'


def _res(page, signal='X', image=None):
    return {
        'success': True, 'headers': list(DEFAULT_TEMPLATE.columns),
        'metadata': {'PAGE': page}, 'image_path': image or f'page_{page}.png',
        'detection_method': 'claude-vision',
        'rows': [{'type': 'data', 'cells': ['01', 'BLANC', signal, '0109R'],
                  'confidence': [100] * 4}],
    }


def _meta_pied(extracteur, texte):
    return extracteur._extract_meta([[(0, 0, 0, 0, texte)]])


class TestCleNumeroPage(unittest.TestCase):

    def test_numero_simple(self):
        self.assertEqual(cle_numero_page('44'), (44, ''))

    def test_suffixe_minuscule_et_majuscule(self):
        self.assertEqual(cle_numero_page('122a'), (122, 'a'))
        self.assertEqual(cle_numero_page('44B'), (44, 'b'))

    def test_122a_entre_122_et_123(self):
        self.assertLess(cle_numero_page('122'), cle_numero_page('122a'))
        self.assertLess(cle_numero_page('122a'), cle_numero_page('123'))

    def test_illisible(self):
        for valeur in ('', None, 'A12', '12ab', '1 2'):
            self.assertIsNone(cle_numero_page(valeur), valeur)


class TestAlertesSequencePages(unittest.TestCase):

    def test_sequence_croissante_avec_suffixes_sans_alerte(self):
        pages = [_res(p) for p in ('9', '52', '119', '122', '122a', '123')]
        self.assertEqual(alertes_sequence_pages(pages), [])

    def test_recul_signale(self):
        alertes = alertes_sequence_pages([_res('45'), _res('44B')])
        self.assertEqual(alertes, ["séquence non croissante : page 44B après page 45 "
                                   "(ordre du document conservé)"])

    def test_repetition_signalee(self):
        alertes = alertes_sequence_pages([_res('12'), _res('12')])
        self.assertEqual(len(alertes), 1)
        self.assertIn('répétée', alertes[0])

    def test_numero_vide_signale_avec_sa_source(self):
        alertes = alertes_sequence_pages([_res('', image='x/page_007.png')])
        self.assertEqual(alertes, ["numéro de page illisible (vide) : page_007.png"])

    def test_page_illisible_ne_casse_pas_la_suite(self):
        self.assertEqual(len(alertes_sequence_pages([_res('3'), _res(''), _res('4')])), 1)


class TestGenererExcelOrdreEtNumeros(unittest.TestCase):

    def _classeur(self, resultats):
        messages = []
        with tempfile.TemporaryDirectory() as tmp:
            sortie = Path(tmp) / 's.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                generer_excel(resultats, BornierTableExtractor(template=DEFAULT_TEMPLATE),
                              sortie, on_log=messages.append)
            valeurs = [
                str(v) for ligne in openpyxl.load_workbook(sortie).worksheets[0].iter_rows(
                    values_only=True) for v in ligne if v is not None
            ]
        return messages, valeurs

    def test_ordre_du_document_conserve_et_alerte(self):
        messages, valeurs = self._classeur([_res('3', 'TROIS'), _res('1', 'UN')])
        self.assertLess(valeurs.index('TROIS'), valeurs.index('UN'))
        self.assertTrue(any('page 1 après page 3' in m for m in messages))

    def test_pages_3_1_2_restent_en_3_1_2_avec_alerte_de_recul(self):
        # Les trois borniers de l'instantané de test_non_regression_xlsx, dans
        # l'ordre 3-1-2 que cet instantané utilisait avant l'étape 6 pour tester le tri.
        from tests.test_non_regression_xlsx import resultats_synthetiques
        b1, b2, b3 = resultats_synthetiques()
        messages, valeurs = self._classeur([b3, b1, b2])
        positions = [valeurs.index(v) for v in ('ALIM 24V', 'COMMUN TS GR3 105TS', 'TC IDPO1')]
        self.assertEqual(positions, sorted(positions), "ordre 3-1-2 non conservé")
        # Depuis l'étape 7, d'autres contrôles (révisions, champs absents) écrivent
        # aussi des alertes : seules celles de séquence concernent l'ordre.
        alertes = [m.strip() for m in messages if '⚠' in m and 'séquence' in m]
        self.assertEqual(alertes, ["⚠ séquence non croissante : page 1 après page 3 "
                                   "(ordre du document conservé)"])

    def test_suffixe_conserve_dans_le_pied(self):
        _, valeurs = self._classeur([_res('122'), _res('122a')])
        self.assertTrue(any('122a' in v for v in valeurs))

    def test_numero_vide_non_invente_depuis_l_image(self):
        messages, valeurs = self._classeur([_res('', image='bornier_57.png')])
        # « BORNIER : bornier_57 » (nom de repli) est hors sujet : seul PAGE compte.
        pied_page = [v.split('PAGE', 1)[1] for v in valeurs if 'PAGE' in v]
        self.assertTrue(pied_page)
        self.assertFalse(any('57' in v for v in pied_page))
        # Décision B1 : aucune page numérotée → numérotation dans l'ordre (« 1 »), une
        # seule ligne au journal, jamais le numéro du nom d'image.
        self.assertTrue(any(v.split()[-1] == '1' for v in pied_page))
        self.assertTrue(any('PAGE non imprimée dans tout le document' in m for m in messages))


class TestLectureSuffixe(unittest.TestCase):

    def test_pdf_casse_d_origine(self):
        ex = pe.PdfTableExtractor(TemplateManager().get('REPARTITEUR 2'))
        self.assertEqual(_meta_pied(ex, 'INDICE : TP3 PAGE : 122a')['PAGE'], '122a')
        self.assertEqual(_meta_pied(ex, 'PAGE: 44B')['PAGE'], '44B')

    def test_pdf_libelle_suivant_non_pris_dans_le_numero(self):
        ex = pe.PdfTableExtractor(TemplateManager().get('REPARTITEUR 2'))
        self.assertEqual(_meta_pied(ex, 'PAGE : 92 P.E.T. : GRAND-BUT')['PAGE'], '92')

    def test_grille_page_122a_de_223111PE011(self):
        tpl = TemplateManager().get('REPARTITEUR 2')
        with fitz.open(str(EXTRAIT)) as doc:
            resultat = pe.PdfTableExtractor(tpl).extract_page_grille(doc[8], 8)
        self.assertEqual(resultat['metadata']['PAGE'], '122a')

    def test_tesseract_suffixe_garde_en_majuscule(self):
        ex = BornierTableExtractor(template=DEFAULT_TEMPLATE)
        meta = ex._extract_meta([[{'text': 'INDICE : 0 | PAGE : 122a'}]])
        self.assertEqual(meta['PAGE'], '122A')


if __name__ == '__main__':
    unittest.main()
