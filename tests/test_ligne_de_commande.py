"""
Ligne de commande (ligne_de_commande.py) : état de l'installation, conversion d'un PDF
vectoriel, reformatage, erreur dite au journal avec un code de sortie.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_ligne_de_commande.py -v
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import openpyxl

from ligne_de_commande import main

FIX = Path(__file__).parent / 'fixtures'


def _lancer(*args):
    with contextlib.redirect_stdout(io.StringIO()):
        return main(list(args))


class TestLigneDeCommande(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self._tmp.name)
        self.journal = self.dossier / 'journal.txt'

    def tearDown(self):
        self._tmp.cleanup()

    def _lire_journal(self):
        return self.journal.read_text('utf-8')

    def test_infos(self):
        self.assertEqual(_lancer('--journal', str(self.journal), 'infos'), 0)
        texte = self._lire_journal()
        for attendu in ('Tesseract :', 'Dossier utilisateur :', 'Lexique :', 'REPARTITEUR 2'):
            self.assertIn(attendu, texte)

    def test_convertir_un_pdf_vectoriel(self):
        code = _lancer('--journal', str(self.journal), 'convertir',
                       str(FIX / '223111PE022_extrait_surimpression.pdf'),
                       str(self.dossier / 'sortie'), '--modele', 'Bornier standard',
                       '--mode', 'tesseract')
        self.assertEqual(code, 0)
        excel = self.dossier / 'sortie' / '223111PE022_extrait_surimpression.xlsx'
        self.assertTrue(excel.exists())
        self.assertIn('Excel :', self._lire_journal())

    def test_formater(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Borniers'
        ws.append(['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES'])
        ws.append(['01', '1 G', 'SIG', '0815N'])
        ws.append(['SIEMENS', 'P.E.T. : BOURG   BORNIER : PK'])
        ws.append(['N° PLAN : 223111PE022', '', 'INDICE : TP4', ''])
        source = self.dossier / 'source.xlsx'
        wb.save(source)
        self.assertEqual(_lancer('formater', str(source), str(self.dossier / 'r.xlsx')), 0)
        self.assertTrue((self.dossier / 'r.xlsx').exists())

    def test_erreur_au_journal_code_2(self):
        code = _lancer('--journal', str(self.journal), 'formater',
                       str(self.dossier / 'absent.xlsx'), str(self.dossier / 'r.xlsx'))
        self.assertEqual(code, 2)
        self.assertIn('✗', self._lire_journal())


if __name__ == '__main__':
    unittest.main()
