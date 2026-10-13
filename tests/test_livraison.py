"""
Livraison v1.8 (étape 10) : fichiers livrés et fichiers de l'utilisateur.

Ressources lues dans l'exe (_MEIPASS) ou à côté du code ; Tesseract cherché dans les chemins
habituels ; modèles livrés relus à chaque version, modèles de l'utilisateur gardés dans son
dossier ; lexique compilé au build (formes seules) + classeurs ajoutés ; Docling absent dit
clairement ; Tesseract absent dit au journal sans arrêter une conversion.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_livraison.py -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

import config
from config import Config, chemin_ressource, trouver_tesseract


def _classeur(dossier: Path, nom: str, lignes):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Listing'
    ws.append(['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL'])
    for ligne in lignes:
        ws.append(list(ligne))
    wb.save(dossier / nom)


class TestRessources(unittest.TestCase):

    def test_a_cote_du_code_en_developpement(self):
        self.assertEqual(chemin_ressource('templates.json'),
                         Path(config.__file__).parent / 'templates.json')

    def test_dans_l_exe(self):
        with patch.object(sys, '_MEIPASS', '/appli', create=True):
            self.assertEqual(chemin_ressource('templates.json'), Path('/appli/templates.json'))

    def test_dossier_utilisateur_sous_localappdata(self):
        self.assertEqual(Config.DOSSIER_UTILISATEUR.name, 'TriosSeconverter')


class TestTesseract(unittest.TestCase):

    def test_chemin_configure_existant(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'tesseract.exe'
            exe.write_bytes(b'')
            self.assertEqual(trouver_tesseract(str(exe), ()), str(exe))

    def test_chemin_habituel_si_le_configure_manque(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / 'tesseract.exe'
            exe.write_bytes(b'')
            with patch.dict('os.environ', {'TESSERACT_PATH': ''}):
                self.assertEqual(trouver_tesseract(str(Path(tmp) / 'absent.exe'), (str(exe),)),
                                 str(exe))

    def test_introuvable(self):
        with patch.dict('os.environ', {'TESSERACT_PATH': ''}), \
                patch('shutil.which', return_value=None):
            self.assertIsNone(trouver_tesseract('C:/absent/tesseract.exe', ('C:/absent2.exe',)))

    def test_absent_une_ligne_au_journal_sans_arret(self):
        from converter import Converter
        from template import DEFAULT_TEMPLATE
        journal = []
        conv = Converter(word_file=Path('x.pdf'), output_dir=Path(tempfile.gettempdir()),
                         template=DEFAULT_TEMPLATE, on_log=journal.append)
        with patch.object(Config, 'TESSERACT_TROUVE', False), \
                patch.object(Config, 'OCR_MODE', 'tesseract'):
            conv._verifier_moteurs()
        self.assertEqual(sum('Tesseract OCR introuvable' in m for m in journal), 1)


class TestModeles(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.utilisateur = Path(self._tmp.name) / 'templates.json'
        self._patch = patch.object(Config, 'MODELES_UTILISATEUR', self.utilisateur)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _gestion(self):
        from template import TemplateManager
        return TemplateManager()

    def test_modeles_livres_presents_et_proteges(self):
        g = self._gestion()
        for nom in ('Bornier standard', 'Répartiteur', 'REPARTITEUR', 'REPARTITEUR 2'):
            self.assertTrue(g.est_livre(nom), nom)
        g.delete('REPARTITEUR 2')
        self.assertIn('REPARTITEUR 2', g.names())

    def test_modele_utilisateur_garde_dans_son_dossier(self):
        from template import TableTemplate
        g = self._gestion()
        g.add_or_update(TableTemplate(name='MON MODELE', columns=['A', 'B']))
        donnees = json.loads(self.utilisateur.read_text('utf-8'))
        self.assertEqual(list(donnees), ['MON MODELE'])
        self.assertEqual(self._gestion().get('MON MODELE').columns, ['A', 'B'])

    def test_nouvelle_version_met_a_jour_le_modele_livre(self):
        from template import TableTemplate
        ancien = TableTemplate(name='REPARTITEUR 2', columns=['ANCIENNE', 'VERSION'])
        perso = TableTemplate(name='MON MODELE', columns=['A'])
        self.utilisateur.write_text(json.dumps(
            {'REPARTITEUR 2': ancien.to_dict(), 'MON MODELE': perso.to_dict()}), 'utf-8')
        g = self._gestion()
        self.assertEqual(g.get('REPARTITEUR 2').columns,
                         ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT'])
        self.assertEqual(g.get('MON MODELE').columns, ['A'])

    def test_supprimer_un_modele_utilisateur(self):
        from template import TableTemplate
        g = self._gestion()
        g.add_or_update(TableTemplate(name='A JETER', columns=['A']))
        g.delete('A JETER')
        self.assertNotIn('A JETER', self._gestion().names())


class TestLexiqueCompile(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        racine = Path(self._tmp.name)
        self.reference, self.ajouts = racine / 'reference', racine / 'ajouts'
        self.reference.mkdir()
        self.ajouts.mkdir()
        _classeur(self.reference, 'PE013.xlsx', [('PH A104 01', '0815B', 'PH TA106 01', 'SIG')])
        self.compile = racine / 'lexique_compile.json'

    def tearDown(self):
        self._tmp.cleanup()

    def test_compile_egal_a_la_lecture_directe(self):
        from lexique_reference import charger_lexique, compiler_lexique
        contenu = compiler_lexique(self.reference, self.compile)
        self.assertEqual(set(contenu['sources']['PE013.xlsx']['formes']),
                         charger_lexique(self.reference))
        self.assertEqual(len(contenu['sources']['PE013.xlsx']['empreinte']), 64)

    def test_lexique_complet_compile_plus_ajouts(self):
        from lexique_reference import compiler_lexique, lexique_complet
        compiler_lexique(self.reference, self.compile)
        _classeur(self.ajouts, 'PE133.xlsx', [('D3T 01A', '0815B', 'D3T 02A', 'SIG')])
        formes, bilan = lexique_complet(self.compile, self.ajouts)
        self.assertIn('PH A104 01', formes)
        self.assertIn('D3T 01A', formes)
        self.assertIn('formes intégrées (1 classeurs', bilan)
        self.assertIn('ajoutée(s)', bilan)

    def test_sans_compile_en_developpement_lecture_directe(self):
        from lexique_reference import lexique_complet
        formes, bilan = lexique_complet(self.compile, self.ajouts, self.reference)
        self.assertIn('PH A104 01', formes)
        self.assertIn('non compilés', bilan)

    def test_rien_du_tout(self):
        from lexique_reference import lexique_complet
        formes, bilan = lexique_complet(self.compile, self.ajouts)
        self.assertEqual(formes, set())
        self.assertIn('aucune forme intégrée', bilan)


class TestDocling(unittest.TestCase):

    def test_message_dans_l_exe(self):
        from docling_ocr import message_docling_absent
        with patch.object(sys, '_MEIPASS', '/appli', create=True):
            self.assertIn("n'est pas inclus", message_docling_absent())

    def test_conversion_refusee_si_absent(self):
        from converter import Converter
        from template import DEFAULT_TEMPLATE
        conv = Converter(word_file=Path('x.pdf'), output_dir=Path(tempfile.gettempdir()),
                         template=DEFAULT_TEMPLATE, on_log=lambda m: None)
        with patch.object(Config, 'OCR_MODE', 'docling'), \
                patch('docling_ocr.docling_disponible', return_value=False):
            with self.assertRaises(RuntimeError):
                conv._verifier_moteurs()


if __name__ == '__main__':
    unittest.main()
