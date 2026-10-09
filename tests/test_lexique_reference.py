"""
Lexique de référence (lexique_reference.py) : codes tirés des Excel déjà corrigés par
l'utilisateur (feuille « Listing »), document mesuré exclu.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_lexique_reference.py -v
"""
import tempfile
import unittest
from pathlib import Path

import openpyxl

from lexique_reference import charger_lexique, formes


def _classeur(dossier, nom, lignes):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Listing'
    ws.append(['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL'])
    for ligne in lignes:
        ws.append(list(ligne))
    ws.append(['M A T R A', 'P.E.T. : BOURG     BORNIER : P113TC', None, None])
    wb.save(dossier / nom)


class TestFormes(unittest.TestCase):

    def test_cellule_entiere_et_mots_de_4_caracteres(self):
        self.assertEqual(formes('OC FS 14 50 + OCFSCS'),
                         {'OC FS 14 50 + OCFSCS', 'OCFSCS'})

    def test_espaces_ramenes_a_un(self):
        self.assertEqual(formes('PA     01'), {'PA 01'})

    def test_court_ou_vide(self):
        self.assertEqual(formes('BC'), set())
        self.assertEqual(formes(None), set())


class TestChargerLexique(unittest.TestCase):

    def test_codes_des_listings_sans_en_tete_ni_pied(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _classeur(d, '223111PE013.xlsx', [('PA     01', '0001N', 'P310TS 10', 'OC FS 14 50')])
            lexique = charger_lexique(d)
        self.assertIn('OC FS 14 50', lexique)
        self.assertIn('P310TS', lexique)
        self.assertNotIn('TENANT', lexique)
        self.assertFalse([f for f in lexique if 'BORNIER' in f or 'P.E.T' in f])

    def test_document_mesure_exclu(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _classeur(d, '223111PE013.xlsx', [('PA 01', '0001N', 'P310TS 10', 'OC FS 14 50')])
            _classeur(d, '223111PE011_corrige.xlsx', [('PH 01', '', '', 'CC FS 14 50')])
            lexique = charger_lexique(d, exclure='223111PE011')
        self.assertIn('OC FS 14 50', lexique)
        self.assertNotIn('CC FS 14 50', lexique)

    def test_dossier_absent_lexique_vide(self):
        self.assertEqual(charger_lexique(Path('dossier_absent_xyz')), set())


if __name__ == '__main__':
    unittest.main()
