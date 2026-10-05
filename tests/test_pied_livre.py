"""
Décision B1 — pied livré : la lecture reste telle qu'imprimée, l'Excel livré
normalise le N° PLAN (espacements différents d'une page à l'autre), numérote les
pages quand AUCUNE n'en porte, et reprend les libellés du modèle de sortie.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_pied_livre.py -v
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import openpyxl

import pdf_extractor as pe
from config import Config
from generer_classeur import generer_excel, pied_livre
from pied_page import (analyser_pied, inserer_valeur, libelles_modele, remplacer_libelles,
                       remplacer_valeur)
from template import TemplateManager

ALERTE_PAGE = "PAGE non imprimée dans tout le document : pages numérotées dans l'ordre"


def _page(pied, page_num=1):
    meta = dict(analyser_pied(pied), PIED_BRUT=list(pied))
    return {'success': True, 'headers': ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'],
            'metadata': meta, 'image_path': f'page_{page_num}', 'detection_method': 'pdf-grille',
            'rows': [{'type': 'data', 'cells': ['A1', '', 'LIG', '0733B'],
                      'confidence': [100] * 4}]}


def _pe012(*plans):
    return [_page(['P.E.T. : SAINT PHILIBERT     BORNIER : AA',
                   f'NO PLAN : {plan}       INDICE : R'], i + 1) for i, plan in enumerate(plans)]


class TestLibellesModele(unittest.TestCase):

    def test_libelles_des_formats(self):
        tpl = TemplateManager().get('REPARTITEUR 2')
        libelles = libelles_modele([tpl.footer_row1_format, tpl.footer_row2_format])
        self.assertEqual(libelles['NO_PLAN'], 'N° PLAN')
        self.assertEqual(libelles['PAGE'], 'PAGE')

    def test_remplacer_libelles_valeurs_gardees(self):
        lignes = ['PET : SAINT MAURICE     JARRETIERAGE', 'NO PLAN : 223 111 PE 012  INDICE : R']
        self.assertEqual(remplacer_libelles(lignes, {'PET': 'P.E.T.', 'NO_PLAN': 'N° PLAN'}),
                         ['P.E.T. : SAINT MAURICE     JARRETIERAGE',
                          'N° PLAN : 223 111 PE 012  INDICE : R'])


class TestRemplacerValeur(unittest.TestCase):

    def test_valeur_multi_mots_jusqu_au_libelle_suivant(self):
        self.assertEqual(remplacer_valeur(['NO PLAN : 223 111 PE 012       INDICE : R'],
                                          'NO_PLAN', '223111PE012'),
                         ['NO PLAN : 223111PE012       INDICE : R'])

    def test_valeur_avant_un_separateur(self):
        self.assertEqual(remplacer_valeur(['N° PLAN : 223111 PE 012  | INDICE : R'],
                                          'NO_PLAN', '223111PE012'),
                         ['N° PLAN : 223111PE012  | INDICE : R'])

    def test_libelle_absent_inchange(self):
        self.assertEqual(remplacer_valeur(['INDICE : R'], 'NO_PLAN', 'X'), ['INDICE : R'])


class TestInsererEnFin(unittest.TestCase):

    def test_page_ajoutee_en_fin_de_derniere_ligne(self):
        self.assertEqual(inserer_valeur(['CABLE : X', 'N° PLAN : P  INDICE : R'], 'PAGE', 'PAGE',
                                        '3', en_fin=True),
                         ['CABLE : X', 'N° PLAN : P  INDICE : R     PAGE : 3'])


class TestPiedLivre(unittest.TestCase):

    FORMATS = ['P.E.T.   :     {PET:<50}BORNIER :    {BORNIER}',
               'NO PLAN    :   {NO_PLAN:<37}|  INDICE : {INDICE:<8}|  PAGE :   {PAGE}']

    def test_plan_a_espacements_differents_livre_sans_espaces(self):
        pages, journal = pied_livre(_pe012('223 111 PE 012', '223111 PE 012'), self.FORMATS)
        self.assertEqual([p['metadata']['NO_PLAN'] for p in pages], ['223111PE012'] * 2)
        self.assertTrue(all('223111PE012' in p['metadata']['PIED_BRUT'][1] for p in pages))

    def test_plan_toujours_imprime_pareil_inchange(self):
        pages, _ = pied_livre(_pe012('6A23111 PE 133', '6A23111 PE 133'), self.FORMATS)
        self.assertEqual([p['metadata']['NO_PLAN'] for p in pages], ['6A23111 PE 133'] * 2)

    def test_aucune_page_numerotee_numerotation_et_une_ligne(self):
        pages, journal = pied_livre(_pe012('223 111 PE 012', '223 111 PE 012', '223 111 PE 012'),
                                    self.FORMATS)
        self.assertEqual([p['metadata']['PAGE'] for p in pages], ['1', '2', '3'])
        self.assertTrue(all('PAGE' in p['metadata']['DEDUITS'] for p in pages))
        self.assertTrue(pages[2]['metadata']['PIED_BRUT'][-1].endswith('PAGE : 3'))
        self.assertEqual([lg for lg in journal if lg.startswith('⚠')], [f"⚠ {ALERTE_PAGE}"])

    def test_certaines_pages_numerotees_rien_deduit(self):
        pages = _pe012('223 111 PE 012', '223 111 PE 012')
        pages[0]['metadata']['PAGE'] = '12'
        pages, journal = pied_livre(pages, self.FORMATS)
        self.assertNotIn('PAGE', pages[1]['metadata'])
        self.assertFalse([lg for lg in journal if 'PAGE' in lg])

    def test_libelles_du_modele_de_sortie(self):
        pages, _ = pied_livre([_page(['PET : SAINT MAURICE  JARRETIERAGE',
                                      'NO PLAN : P  INDICE : R  PAGE 16'])], self.FORMATS)
        brut = pages[0]['metadata']['PIED_BRUT']
        self.assertTrue(brut[0].startswith('P.E.T. : SAINT MAURICE'))
        self.assertIn('PAGE 16', brut[1])

    def test_entree_non_modifiee(self):
        import copy
        pages = _pe012('223 111 PE 012', '223111 PE 012')
        avant = copy.deepcopy(pages)
        pied_livre(pages, self.FORMATS)
        self.assertEqual(pages, avant)


class TestExcelLivre(unittest.TestCase):

    def test_page_deduite_coloree_commentee_et_une_seule_alerte(self):
        tpl = TemplateManager().get('Bornier standard')
        journal = []
        with tempfile.TemporaryDirectory() as tmp:
            sortie = Path(tmp) / 's.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                generer_excel(_pe012('223 111 PE 012', '223111 PE 012'), pe.PdfTableExtractor(tpl),
                              sortie, on_log=journal.append)
            ws = openpyxl.load_workbook(sortie).worksheets[0]
            pieds = [c for c in ws['B'] if isinstance(c.value, str) and 'INDICE' in c.value]
        self.assertEqual(len(pieds), 2)
        self.assertTrue(pieds[1].value.endswith('PAGE : 2'))
        self.assertIn('223111PE012', pieds[0].value)
        self.assertEqual(pieds[1].fill.fgColor.rgb, '00' + Config.COULEUR_DEDUIT)
        self.assertIn('numérotée', pieds[1].comment.text)
        alertes = [m.strip() for m in journal if '⚠' in m]
        self.assertIn(f"⚠ {ALERTE_PAGE}", alertes)
        self.assertFalse([a for a in alertes if 'illisible' in a or 'PAGE absent' in a])


if __name__ == '__main__':
    unittest.main()
