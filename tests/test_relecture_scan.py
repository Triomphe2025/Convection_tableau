"""
relecture_scan.py : relecture indépendante d'un scan pour la vérification.

Fonctions pures testées sur des données fabriquées ; la lecture Tesseract réelle
sur une page du scan 6A 23111PE102 est sautée si Tesseract est absent.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_relecture_scan.py -v
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import relecture_scan as rs
from config import Config

COLONNES = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']
SCAN = Path(__file__).parent / 'fixtures' / 'scan_6A23111PE102_15p.pdf'


def _ligne(*cellules):
    return {'type': 'data', 'cells': list(cellules), 'confidence': [90] * len(cellules)}


class TestNormaliserCle(unittest.TestCase):

    def test_ponctuation_accents_espaces_retires(self):
        self.assertEqual(rs.normaliser_cle("‘ c14"), 'C14')
        self.assertEqual(rs.normaliser_cle('JARRÉTIÈRES'), 'JARRETIERES')

    def test_vide(self):
        self.assertEqual(rs.normaliser_cle(None), '')


class TestEstLigneDeDonnees(unittest.TestCase):

    def test_cles_lues_avec_confusions(self):
        for cle in ('A01', 'AO1', 'All', 'col', 'cO7', 'Pl', '34', '12B'):
            self.assertTrue(rs.est_ligne_de_donnees(_ligne(cle, 'B', 'X', '')), cle)

    def test_entete_section_et_pied_ecartes(self):
        for cellules in (('BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'),
                         ('NOM DU', 'CABLE : GAT/C105', '', ''),
                         ('MATRA', '|- 2', '2', '|')):
            self.assertFalse(rs.est_ligne_de_donnees(_ligne(*cellules)), cellules)

    def test_cle_illisible_ligne_gardee(self):
        self.assertTrue(rs.est_ligne_de_donnees(_ligne('', '', 'RESERVE NON CABLEE', '')))

    def test_cle_illisible_pied_ou_trait_ecarte(self):
        self.assertFalse(rs.est_ligne_de_donnees(_ligne('', 'P.E.T. + GARE', 'TRAMWAY', '')))
        self.assertFalse(rs.est_ligne_de_donnees(_ligne('', '', '——', '')))


class TestEstEntete(unittest.TestCase):

    def test_entete_sans_borne_lue(self):
        self.assertTrue(rs.est_entete(_ligne('', 'COULEUR', 'SIGNAL', 'JARRETIERES'), COLONNES))

    def test_donnee_qui_contient_un_mot_de_colonne(self):
        self.assertFalse(rs.est_entete(_ligne('12', 'B', 'SIGNAL ABSENT', ''), COLONNES))


class TestBornes(unittest.TestCase):

    def _mot(self, texte, x0, x1, y=10):
        return (x0, y, x1, y + 10, texte, 95)

    def test_entete_lue(self):
        mots = [self._mot('BORNE', 0, 40), self._mot('COULEUR', 100, 160),
                self._mot('SIGNAL', 300, 360), self._mot('JARRETIERES', 600, 700)]
        self.assertEqual(rs.bornes_entete(mots, COLONNES), [0.0, 75.0, 230.0, 490.0, 1e9])

    def test_entete_incomplete(self):
        self.assertIsNone(rs.bornes_entete([self._mot('BORNE', 0, 40)], COLONNES))

    def test_traits_du_cadre_prioritaires(self):
        traits = [5.0, 100.0, 250.0, 500.0, 800.0]
        self.assertEqual(rs.bornes_colonnes(traits, [], COLONNES), traits)

    def test_trop_peu_de_traits_repli_sur_l_entete(self):
        self.assertIsNone(rs.bornes_colonnes([5.0, 800.0], [], COLONNES))


class TestTraitsVerticaux(unittest.TestCase):

    def test_deux_traits(self):
        gris = np.full((400, 300), 255, dtype=np.uint8)
        gris[:, 50:53] = 0
        gris[:, 200:203] = 0
        traits = rs.traits_verticaux(gris)
        self.assertEqual([round(t) for t in traits], [51, 201])

    def test_page_blanche(self):
        self.assertIsNone(rs.traits_verticaux(np.full((400, 300), 255, dtype=np.uint8)))


class TestGrouperLignes(unittest.TestCase):

    def test_deux_lignes(self):
        mots = [(0, 100, 20, 120, 'A', 90), (50, 104, 70, 124, 'B', 90),
                (0, 200, 20, 220, 'C', 90)]
        self.assertEqual([[m[4] for m in lg] for lg in rs.grouper_lignes(mots, 12)],
                         [['A', 'B'], ['C']])


class TestLigneEnCellules(unittest.TestCase):

    def test_rangement_par_le_centre_et_confiance_moyenne(self):
        ligne = [(10, 0, 30, 10, 'A01', 90), (110, 0, 130, 10, 'B', 80),
                 (310, 0, 360, 10, 'RESERVE', 70), (370, 0, 420, 10, 'CABLEE', 90)]
        resultat = rs.ligne_en_cellules(ligne, [0, 100, 300, 600, 1e9], 4)
        self.assertEqual(resultat['cells'], ['A01', 'B', 'RESERVE CABLEE', ''])
        self.assertEqual(resultat['confidence'], [90, 80, 80, 100])


class TestRelireImage(unittest.TestCase):

    def test_page_sans_tableau(self):
        image = Image.new('RGB', (600, 400), 'white')
        ImageDraw.Draw(image).text((50, 50), 'PAGE DE GARDE', fill='black')
        if not Path(Config.TESSERACT_PATH).exists():
            self.skipTest('Tesseract absent')
        self.assertFalse(rs.relire_image(image, COLONNES)['success'])


@unittest.skipUnless(Path(Config.TESSERACT_PATH).exists(), 'Tesseract absent')
class TestRelirePdfScanReel(unittest.TestCase):
    """Page 10 du scan 6A 23111PE102 : « DISCORDANCE » lu, cadre et clés reconnus."""

    @classmethod
    def setUpClass(cls):
        import fitz
        cls._tmp = tempfile.TemporaryDirectory()
        cls.chemin = Path(cls._tmp.name) / 'page10.pdf'
        with fitz.open(str(SCAN)) as doc:
            extrait = fitz.open()
            extrait.insert_pdf(doc, from_page=9, to_page=9)
            extrait.save(str(cls.chemin))
        cls.pages = rs.relire_pdf(cls.chemin, COLONNES)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_une_page_28_lignes(self):
        self.assertEqual(len(self.pages), 1)
        self.assertEqual(len(self.pages[0]['rows']), 28)

    def test_discordance_lue(self):
        signaux = [r['cells'][2] for r in self.pages[0]['rows']]
        self.assertTrue(any('DISCORDANCE' in s for s in signaux))

    def test_arret_cooperatif(self):
        self.assertEqual(rs.relire_pdf(self.chemin, COLONNES, annule=lambda: True), [])


if __name__ == '__main__':
    unittest.main()
