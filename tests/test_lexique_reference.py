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


class TestAjouterAuLexique(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        racine = Path(self._tmp.name)
        self.lexique, self.depot = racine / 'lexique', racine / 'depot'
        self.lexique.mkdir()
        self.depot.mkdir()
        _classeur(self.lexique, 'PE013.xlsx', [('PH A104 01', '0815B', 'PH TA106 01', 'SIG')])

    def tearDown(self):
        self._tmp.cleanup()

    def test_copie_et_formes_ajoutees(self):
        from lexique_reference import ajouter_au_lexique
        _classeur(self.depot, 'PE133.xlsx', [('PH A104 01', '0815B', 'D3T 01A', 'SIG')])
        bilan = ajouter_au_lexique(self.depot / 'PE133.xlsx', self.lexique)
        self.assertTrue((self.lexique / 'PE133.xlsx').exists())
        self.assertEqual(bilan['ajoutees'], 1)          # « D3T 01A » seul est nouveau
        self.assertIn('D3T 01A', charger_lexique(self.lexique))

    def test_sans_feuille_listing_refuse_rien_copie(self):
        from lexique_reference import ajouter_au_lexique
        wb = openpyxl.Workbook()
        wb.active.title = 'Borniers'
        wb.save(self.depot / 'brut.xlsx')
        with self.assertRaises(ValueError) as erreur:
            ajouter_au_lexique(self.depot / 'brut.xlsx', self.lexique)
        self.assertIn('Listing', str(erreur.exception))
        self.assertFalse((self.lexique / 'brut.xlsx').exists())

    def test_pas_un_xlsx(self):
        from lexique_reference import ajouter_au_lexique
        (self.depot / 'note.txt').write_text('x', encoding='utf-8')
        with self.assertRaises(ValueError):
            ajouter_au_lexique(self.depot / 'note.txt', self.lexique)

    def test_meme_nom_demande_confirmation_puis_remplace(self):
        from lexique_reference import ajouter_au_lexique
        _classeur(self.depot, 'PE013.xlsx', [('PH A105 02', '0816B', 'PH TA106 02', 'SIG')])
        with self.assertRaises(FileExistsError):
            ajouter_au_lexique(self.depot / 'PE013.xlsx', self.lexique)
        bilan = ajouter_au_lexique(self.depot / 'PE013.xlsx', self.lexique, remplacer=True)
        self.assertTrue(bilan['remplace'])
        self.assertIn('PH A105 02', charger_lexique(self.lexique))
        self.assertNotIn('PH A104 01', charger_lexique(self.lexique))

    def test_dictionnaire_jamais_touche(self):
        import data_dictionary
        from lexique_reference import ajouter_au_lexique
        fichier = data_dictionary.get_dictionary().path
        avant = fichier.read_bytes() if fichier.exists() else None
        _classeur(self.depot, 'PE133.xlsx', [('D3T 01A', '0815B', 'D3T 02A', 'SIG')])
        ajouter_au_lexique(self.depot / 'PE133.xlsx', self.lexique)
        self.assertEqual(fichier.read_bytes() if fichier.exists() else None, avant)
