"""
Test doré des 3 pages TP2 sans cadre de 223400PE137 (pages document 32, 33, 49)
contre la vérité terrain v3, construite par une méthode indépendante.

Chaîne complète, sans OCR ni réseau : grille de la couche texte
(PdfTableExtractor.extract_page_grille) → classeur Excel (generer_excel) →
relecture (lire_xlsx) → mesure. Les positions de l'original font partie du
résultat attendu : un espace de trop dans un TENANT est une erreur.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_mesurer_precision_tp2_golden.py -v
"""
import contextlib
import copy
import io
import re
import tempfile
import unittest
from pathlib import Path

import fitz

import mesure_precision as mp
from generer_classeur import generer_excel
from mesurer_precision import lire_verite_excel, lire_xlsx
from pdf_extractor import PdfTableExtractor
from template import TemplateManager

FIXTURES = Path(__file__).parent / 'fixtures'
PE137 = FIXTURES / '223400PE137.pdf'
VERITE_TP2 = FIXTURES / '223400PE137_TP2_verite.xlsx'
PAGES_TP2 = (37, 38, 51)   # pages PDF ; pages document 32, 33, 49


def _sortie_tp2() -> list:
    """Pages TP2 converties puis relues depuis le classeur, comme en production."""
    modele = TemplateManager().get('REPARTITEUR')
    lecteur = PdfTableExtractor(modele)
    with fitz.open(str(PE137)) as doc:
        resultats = [lecteur.extract_page_grille(doc[n - 1], n - 1) for n in PAGES_TP2]
    with tempfile.TemporaryDirectory() as tmp:
        classeur = Path(tmp) / 'tp2.xlsx'
        with contextlib.redirect_stdout(io.StringIO()):
            generer_excel(resultats, lecteur, classeur)
        return lire_xlsx(classeur)


class TestVeriteTp2V3(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pages, cls.colonnes = lire_verite_excel(VERITE_TP2)
        cls.lignes = [ligne['cells'] for page in cls.pages for ligne in page['rows']]

    def test_167_lignes_sur_3_pages(self):
        self.assertEqual([len(p['rows']) for p in self.pages], [55, 56, 56])

    def test_deuxieme_champ_du_tenant_en_colonne_10(self):
        colonnes = {[m.start() for m in re.finditer(r'\S+', c[0])][1] for c in self.lignes}
        self.assertEqual(colonnes, {10})

    def test_petite_police_a_7_espaces(self):
        tenants = {c[0] for c in self.lignes} | {c[2] for c in self.lignes}
        for valeur in ('D_T       02A', 'D_T       01B', 'D_S       01B'):
            self.assertIn(valeur, tenants)

    def test_lignes_pet_en_donnees(self):
        pet = [c for c in self.lignes if 'PET' in c[3]]
        self.assertEqual(len(pet), 4)


class TestSortieContreVeriteTp2(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reference, cls.colonnes = lire_verite_excel(VERITE_TP2)
        cls.sortie = _sortie_tp2()
        cls.rapport = mp.mesurer(cls.reference, cls.sortie, cls.colonnes)

    def test_trois_pages_appariees(self):
        self.assertEqual(len(self.rapport.pages_appariees), 3)
        self.assertEqual(self.rapport.pages_ref_orphelines, [])
        self.assertEqual(self.rapport.pages_conv_orphelines, [])

    def test_zero_cellule_fausse(self):
        self.assertEqual(self.rapport.ecarts_cellules, [])
        self.assertEqual(self.rapport.nb_cellules_comparees, 668)

    def test_zero_position_fausse(self):
        self.assertEqual(self.rapport.ecarts_positions, [])

    def test_zero_pied_faux_ni_ligne_orpheline(self):
        self.assertEqual(self.rapport.ecarts_pieds, [])
        self.assertEqual(self.rapport.lignes_orphelines, [])

    def test_un_espace_de_trop_dans_le_tenant_est_detecte(self):
        # « D_T       02A » (7 espaces) devenu « D_T        02A » (8) : même texte
        # une fois les espaces réduits, mais le 2e champ passe en colonne 11.
        sortie = copy.deepcopy(self.sortie)
        cible = next(
            ligne for page in sortie for ligne in page['rows']
            if ligne['cells'][0] == 'D_T       02A'
        )
        cible['cells'][0] = 'D_T        02A'
        rapport = mp.mesurer(self.reference, sortie, self.colonnes)
        self.assertEqual(rapport.ecarts_cellules, [])
        self.assertEqual(len(rapport.ecarts_positions), 1)
        ecart = rapport.ecarts_positions[0]
        self.assertEqual(ecart.colonne, 'TENANT')
        self.assertEqual((ecart.decalages_ref, ecart.decalages_conv), ((0, 10), (0, 11)))


if __name__ == '__main__':
    unittest.main()
