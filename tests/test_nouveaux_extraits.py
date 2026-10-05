"""
Jeux d'essai 6A23111PE133 (8 pages) et 223111PE012 (10 pages), vérités validées.

Sans appel API : routage de chaque page contre la feuille « Pages » (colonne « Appel
Claude attendu ») ; image envoyée à Claude ≤ CLAUDE_IMAGE_MAX_PX pour les pages à
mediabox géante ; lecture des vérités par le banc (sections, pied sur deux niveaux,
alertes attendues, garde) ; pages vectorielles grille → Excel → mesure.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_nouveaux_extraits.py -v
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import fitz
import openpyxl

from config import Config
from generer_classeur import generer_excel
from mesure_precision import mesurer
from mesurer_precision import (lire_attentes, lire_verite_excel, lire_xlsx,
                               positions_contre_pdf)
from pdf_extractor import OCR_INVISIBLE, SCAN, PdfTableExtractor, diagnostiquer_page
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'
PE133 = ('6A23111PE133', FIX / '6A23111PE133_extrait_8pages.pdf', 'REPARTITEUR', (6, 7))
PE012 = ('223111PE012', FIX / '223111PE012_extrait_10pages.pdf', 'Bornier standard', (4, 8, 9))


def _verite(nom):
    return FIX / f'{nom}_extrait_verite.xlsx'


class TestRoutageContreLaFeuillePages(unittest.TestCase):

    def _controler(self, nom, pdf):
        attendus = {r[0]: str(r[4]) for r in openpyxl.load_workbook(_verite(nom), data_only=True)[
            'Pages'].iter_rows(min_row=2, values_only=True) if r[0]}
        with fitz.open(str(pdf)) as doc:
            for i, page in enumerate(doc):
                appel = diagnostiquer_page(page)['nature'] in (SCAN, OCR_INVISIBLE)
                self.assertEqual(appel, attendus[i + 1].startswith('oui'),
                                 f"{nom} page {i + 1} : attendu « {attendus[i + 1]} »")

    def test_6a23111pe133(self):
        self._controler(PE133[0], PE133[1])

    def test_223111pe012_pages_tournees_et_geantes(self):
        self._controler(PE012[0], PE012[1])
        with fitz.open(str(PE012[1])) as doc:
            self.assertEqual([doc[i].rotation for i in (1, 2)], [90, 90])
            self.assertEqual([round(doc[i].rect.width) for i in (3, 5)], [2481, 2481])


class TestMediaboxGeante(unittest.TestCase):
    """Pages 4 et 6 de 223111PE012 (2481 × 3505 pt) : image envoyée ≤ CLAUDE_IMAGE_MAX_PX."""

    def test_image_envoyee_bornee(self):
        import base64

        from PIL import Image

        from claude_ocr import _preparer_image_claude
        with fitz.open(str(PE012[1])) as doc, tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / 'p4.png'
            doc[3].get_pixmap(matrix=fitz.Matrix(3, 3)).save(str(png))   # rendu du convertisseur
            donnees, _ = _preparer_image_claude(png, Config.CLAUDE_IMAGE_MAX_PX)
        taille = Image.open(io.BytesIO(base64.b64decode(donnees))).size
        self.assertEqual(max(taille), Config.CLAUDE_IMAGE_MAX_PX)


class TestLectureDesVerites(unittest.TestCase):

    def test_colonnes_et_sections(self):
        pages, colonnes = lire_verite_excel(_verite('223111PE012'))
        self.assertEqual(colonnes, ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'])
        sections = [r['text'] for p in pages for r in p['rows'] if r['type'] == 'section']
        self.assertIn('NOM DU CABLE : WPHR/A105', sections)
        self.assertEqual(len(sections), 9)

    def test_pied_sur_deux_niveaux(self):
        pages, _ = lire_verite_excel(_verite('223111PE012'))
        page = pages[0]
        self.assertIn('N° PLAN : 223111PE012', page['pied_texte'][0])
        self.assertIn('PAGE : 1', page['pied_texte'][0])
        self.assertIn('N° PLAN : 223 111 PE 012', page['pied_lu'][0])
        self.assertNotIn('PAGE', page['pied_lu'][0].replace('N° PLAN', ''))
        self.assertEqual(page['libelles_stricts'], ['LOGO', 'N° PLAN', 'PAGE'])
        self.assertNotIn('REMARQUE', ' '.join(page['pied_texte']).upper())

    def test_texte_fixe_a_part(self):
        pages, _ = lire_verite_excel(_verite('6A23111PE133'))
        self.assertEqual(pages[0]['pied_autre'], ['JARRETIERAGE'])

    def test_attentes_6a23111pe133(self):
        attentes = lire_attentes(_verite('6A23111PE133'))
        self.assertEqual(len(attentes['alertes']), 4)
        self.assertIn("« D3T O1A »", attentes['alertes'][0])
        self.assertEqual(attentes['revisions'], ['00', '01', '02', 'R', 'R1', 'TP1', '03', 'TP2'])
        self.assertEqual(attentes['indices_pages'], ['R', 'R', 'R', 'TP2', '03'])

    def test_attentes_223111pe012(self):
        attentes = lire_attentes(_verite('223111PE012'))
        self.assertEqual(len(attentes['alertes']), 1)
        self.assertIn('PAGE non imprimée dans tout le document', attentes['alertes'][0])
        self.assertEqual(attentes['revisions'][:3], ['R', 'R1', 'R2'])
        self.assertIn('TP4', attentes['revisions'])

    def test_alerte_de_223111pe012_ecrite_comme_au_journal(self):
        from generer_classeur import ALERTE_PAGE_NUMEROTEE
        self.assertEqual(lire_attentes(_verite('223111PE012'))['alertes'],
                         [ALERTE_PAGE_NUMEROTEE])

    def test_attentes_223111pe011_sans_page_de_garde(self):
        attentes = lire_attentes(FIX / '223111PE011_extrait_verite.xlsx')
        self.assertEqual(attentes['alertes'], [
            "champ TYPE absent du pied, laissé vide : page(s) 104",
            "contrôle INDICE impossible : aucune liste de révisions lue sur une page de garde"])
        self.assertIsNone(attentes['revisions'])

    def test_ancienne_verite_sans_ces_feuilles(self):
        attentes = lire_attentes(FIX / '223400PE137_TP2_verite.xlsx')
        self.assertIsNone(attentes['alertes'])
        self.assertIsNone(attentes['revisions'])


def _vectorielles(cas):
    nom, pdf, modele, pages = cas
    tpl = TemplateManager().get(modele)
    lecteur = PdfTableExtractor(tpl)
    with fitz.open(str(pdf)) as doc:
        resultats = [lecteur.extract_page_grille(doc[i], i) for i in pages]
    with tempfile.TemporaryDirectory() as tmp:
        classeur = Path(tmp) / 's.xlsx'
        with contextlib.redirect_stdout(io.StringIO()):
            generer_excel(resultats, lecteur, classeur, on_log=lambda m: None)
        converti = lire_xlsx(classeur)
    verite, colonnes = lire_verite_excel(_verite(nom))
    rapport = mesurer(verite, converti, colonnes)
    positions_contre_pdf(rapport, converti, pdf, colonnes, template=tpl)
    return rapport


class TestPagesVectorielles(unittest.TestCase):
    """Pages vectorielles (sans OCR) contre la vérité : contenu, sections, positions."""

    def test_6a23111pe133_aucun_ecart_de_tableau(self):
        # Décision B3 : les 4 coquilles O1A de la p. 8 sont corrigées dans l'Excel.
        rapport = _vectorielles(PE133)
        self.assertEqual(rapport.ecarts_cellules, [])
        self.assertEqual(rapport.lignes_orphelines, [])
        self.assertEqual(rapport.ecarts_positions, [])

    def test_223111pe012_aucun_ecart_de_tableau(self):
        rapport = _vectorielles(PE012)
        self.assertEqual(rapport.ecarts_cellules, [])
        self.assertEqual(rapport.lignes_orphelines, [])
        self.assertEqual(rapport.ecarts_positions, [])
        self.assertEqual(len(rapport.pages_positions_geometriques), 3)


if __name__ == '__main__':
    unittest.main()


class TestGrillePoliceProportionnelle(unittest.TestCase):
    """Pied en police proportionnelle : l'espace entre deux mots d'un même span est gardé."""

    def _ligne_plan(self, pdf, page):
        from pdf_extractor import grille_page
        with fitz.open(str(pdf)) as doc:
            return next(lg for lg in grille_page(doc[page]) if 'PLAN' in lg)

    def test_numero_de_plan_de_6a23111pe133(self):
        self.assertIn('N° PLAN : 6A23111 PE 133', ' '.join(self._ligne_plan(PE133[1], 6).split()))

    def test_numero_de_plan_de_223111pe012(self):
        self.assertIn('223111 PE 012', ' '.join(self._ligne_plan(PE012[1], 4).split()))
