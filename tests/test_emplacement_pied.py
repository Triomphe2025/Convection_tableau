"""
Emplacement de champ occupé par un texte sans libellé (décision du 2026-10-05) :
le champ n'est pas absent, il est remplacé — pas d'alerte « BORNIER absent », et
le texte reste recopié à sa place dans le pied de l'Excel livré. Règle générale
(tout texte sans libellé à l'emplacement, PIED_EMPLACEMENTS), pas un cas JARRETIERAGE.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_emplacement_pied.py -v
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import fitz
import openpyxl

from claude_ocr import _parse_pipe_response
from generer_classeur import alertes_pied, generer_excel
from pdf_extractor import PdfTableExtractor
from pied_page import analyser_pied
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'
PE133 = FIX / '6A23111PE133_extrait_8pages.pdf'
PE012 = FIX / '223111PE012_extrait_10pages.pdf'
LIGNE2 = 'N° PLAN : 6A23111 PE 133 | INDICE : R | PAGE : 6'


class TestAnalyserPiedEmplacement(unittest.TestCase):

    def test_texte_fixe_du_modele_page_vectorielle(self):
        meta = analyser_pied(['PET : SAINT MAURICE                         JARRETIERAGE', LIGNE2],
                             decor={'JARRETIERAGE'})
        self.assertEqual(meta['PET'], 'SAINT MAURICE')
        self.assertEqual(meta['EMPLACEMENT_BORNIER'], 'JARRETIERAGE')

    def test_texte_fixe_du_modele_recopie_par_claude_a_un_espace(self):
        meta = analyser_pied(['P.E.T. : SAINT MAURICE JARRETIERAGE', LIGNE2],
                             decor={'JARRETIERAGE'})
        self.assertEqual(meta['PET'], 'SAINT MAURICE')
        self.assertEqual(meta['EMPLACEMENT_BORNIER'], 'JARRETIERAGE')

    def test_tout_texte_sans_libelle_apres_un_grand_blanc(self):
        meta = analyser_pied(['P.E.T. : SAINT X        REPARTITION GENERALE', LIGNE2])
        self.assertEqual(meta['PET'], 'SAINT X')
        self.assertEqual(meta['EMPLACEMENT_BORNIER'], 'REPARTITION GENERALE')
        self.assertNotIn('COMPLEMENT', meta)

    def test_bornier_imprime_avec_son_libelle(self):
        meta = analyser_pied(['PET : SAINT PHILIBERT                  BORNIER : B0VKI', LIGNE2])
        self.assertEqual((meta['PET'], meta['BORNIER']), ('SAINT PHILIBERT', 'B0VKI'))
        self.assertNotIn('EMPLACEMENT_BORNIER', meta)

    def test_un_espace_sans_mot_fixe_rien_n_est_devine(self):
        meta = analyser_pied(['P.E.T. : SAINT MAURICE REPARTITION', LIGNE2])
        self.assertEqual(meta['PET'], 'SAINT MAURICE REPARTITION')
        self.assertNotIn('EMPLACEMENT_BORNIER', meta)

    def test_seulement_a_l_emplacement_configure(self):
        meta = analyser_pied(['P.E.T. : SAINT X', 'NO PLAN : 6A23111 PE 133        TEXTE LIBRE'],
                             emplacements={'BORNIER': 'PET'})
        self.assertNotIn('EMPLACEMENT_BORNIER', meta)
        self.assertEqual(meta['NO_PLAN'], '6A23111 PE 133 TEXTE LIBRE')

    def test_emplacement_vide(self):
        meta = analyser_pied(['P.E.T. : SAINT MAURICE', LIGNE2], decor={'JARRETIERAGE'})
        self.assertNotIn('EMPLACEMENT_BORNIER', meta)


class TestAlertesPiedEmplacement(unittest.TestCase):

    def _page(self, num, **meta):
        return {'metadata': dict(meta, PAGE=num), 'image_path': num}

    def test_emplacement_occupe_n_est_pas_absent(self):
        pages = [self._page('6', PET='X', EMPLACEMENT_BORNIER='JARRETIERAGE'),
                 self._page('12', PET='X', EMPLACEMENT_BORNIER='JARRETIERAGE')]
        self.assertFalse([a for a in alertes_pied(pages, pages, ['PET', 'BORNIER'])
                          if 'BORNIER' in a])

    def test_page_sans_rien_reste_signalee(self):
        pages = [self._page('6', PET='X', EMPLACEMENT_BORNIER='JARRETIERAGE'),
                 self._page('12', PET='X')]
        self.assertIn("champ BORNIER absent du pied, laissé vide : page(s) 12",
                      alertes_pied(pages, pages, ['PET', 'BORNIER']))


class TestExcelLivrePE133(unittest.TestCase):
    """Pages vectorielles 7-8 et réponses Claude au format du passage réel du 2026-10-05."""

    @classmethod
    def setUpClass(cls):
        tpl = TemplateManager().get('REPARTITEUR')
        lecteur = PdfTableExtractor(tpl)
        with fitz.open(str(PE133)) as doc:
            pages = [lecteur.extract_page_grille(doc[i], i) for i in (6, 7)]
        for num in ('6', '12'):
            reponse = '\n'.join([
                'TYPE_PAGE: listing', 'P111TC 26 | 0785B | P111TC 28 | 0VG (EAS)',
                f'META: {{"PAGE": "{num}", "BORNIER": "", "PET": "SAINT MAURICE"}}',
                'PIED_BRUT: P.E.T. : SAINT MAURICE JARRETIERAGE',
                f'PIED_BRUT: N° PLAN : 6A23111 PE 133 | INDICE : R | PAGE : {num}',
                'LOGO: M A T R A'])
            rows, meta, _ = _parse_pipe_response(reponse, tpl)
            pages.append({'success': True, 'headers': list(tpl.columns), 'metadata': meta,
                          'rows': rows, 'image_path': f'p{num}',
                          'detection_method': 'claude-vision'})
        cls.journal = []
        with tempfile.TemporaryDirectory() as tmp:
            sortie = Path(tmp) / 's.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                generer_excel(pages, lecteur, sortie, on_log=cls.journal.append)
            ws = openpyxl.load_workbook(sortie).worksheets[0]
            cls.lignes_pet = [c.value for c in ws['B']
                              if isinstance(c.value, str) and c.value.startswith('P.E.T.')]

    def test_aucune_alerte_bornier(self):
        self.assertFalse([m for m in self.journal if 'BORNIER' in m])

    def test_jarretierage_a_sa_place_dans_chaque_pied(self):
        self.assertEqual(len(self.lignes_pet), 4)
        for ligne in self.lignes_pet:
            self.assertTrue(ligne.startswith('P.E.T. : SAINT MAURICE'), ligne)
            self.assertTrue(ligne.endswith('JARRETIERAGE'), ligne)


class TestPE012Inchange(unittest.TestCase):

    def test_bornier_lu_sur_la_grille(self):
        lecteur = PdfTableExtractor(TemplateManager().get('Bornier standard'))
        with fitz.open(str(PE012)) as doc:
            meta = lecteur.extract_page_grille(doc[4], 4)['metadata']
        self.assertEqual((meta['PET'], meta['BORNIER']), ('SAINT PHILIBERT', 'B0VKI'))
        self.assertNotIn('EMPLACEMENT_BORNIER', meta)


if __name__ == '__main__':
    unittest.main()
