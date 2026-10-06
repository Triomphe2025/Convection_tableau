"""
Commit A dans le convertisseur : positions d'origine posées sur les pages lues par
Claude (faux client, réponse enregistrée, Tesseract en local), lecture Tesseract gardée
dans le cache de l'appli (jamais à côté des fichiers de l'utilisateur), réutilisée sans
2e OCR ; sans PDF (rejeu d'un journal), une ligne au journal.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_positions_converter.py -v
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import openpyxl

from config import Config
from converter import Converter
import positions_scan
from positions_scan import LecturePage
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'
REPONSE_P15 = next(json.loads(lg)['raw'] for lg in
                   (FIX / 'positions_reponses_claude.jsonl').read_text('utf-8').splitlines()
                   if json.loads(lg)['document'].startswith('6A23111PE133'))


class _FauxClient:
    def __init__(self, api_key=None):
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        return SimpleNamespace(
            id='msg_faux', content=[SimpleNamespace(type='text', text=REPONSE_P15)],
            stop_reason='end_turn', model=kwargs['model'],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0))


@contextlib.contextmanager
def _mode_claude():
    noms = ('OCR_MODE', 'CLAUDE_API_KEY')
    avant = {n: getattr(Config, n) for n in noms}
    Config.OCR_MODE, Config.CLAUDE_API_KEY = 'claude', 'cle-factice'
    try:
        yield
    finally:
        for n, v in avant.items():
            setattr(Config, n, v)


@unittest.skipUnless(Path(Config.TESSERACT_PATH).exists(), "Tesseract absent")
class TestConversionPdf(unittest.TestCase):

    @classmethod
    def _convertir(cls, sortie):
        journal = []
        with _mode_claude(), patch('anthropic.Anthropic', _FauxClient), \
                patch.object(Config, 'POSITIONS_CACHE_DOSSIER', cls.cache), \
                contextlib.redirect_stdout(io.StringIO()):
            resultat = Converter(word_file=cls.pdf, output_dir=cls.dossier / sortie,
                                 template=TemplateManager().get('REPARTITEUR'),
                                 on_log=journal.append).run()
        return resultat, journal

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dossier = Path(cls._tmp.name)
        cls.cache = cls.dossier / 'cache_appli'
        cls.pdf = cls.dossier / 'pe133_p15.pdf'
        with fitz.open(str(FIX / '6A23111PE133_extrait_8pages.pdf')) as src, fitz.open() as un:
            un.insert_pdf(src, from_page=5, to_page=5)
            un.save(str(cls.pdf))
        cls.resultat, cls.journal = cls._convertir('sortie')
        ws = openpyxl.load_workbook(cls.resultat['excel']).worksheets[0]
        cls.tenants = [ws.cell(row=r, column=1).value for r in range(2, 58)]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_bilan_au_journal(self):
        lignes = [m for m in self.journal if "positions d'origine p. 1 :" in m]
        self.assertEqual(len(lignes), 1)
        self.assertIn('0 déplacé(s)', lignes[0])

    def test_positions_dans_l_excel(self):
        self.assertIn('P111TC    26', self.tenants)
        self.assertIn('RM         03B', self.tenants)

    def test_lecture_dans_le_cache_de_l_appli_pas_a_cote_des_fichiers(self):
        fichiers = list(self.cache.glob('*.json'))
        self.assertEqual(len(fichiers), 1)
        donnees = json.loads(fichiers[0].read_text('utf-8'))
        self.assertGreater(len(LecturePage.depuis_dict(donnees).mots), 100)
        self.assertEqual(list((self.dossier / 'sortie').rglob('*.json')), [])

    def test_deuxieme_conversion_sans_deuxieme_ocr(self):
        with patch.object(positions_scan, 'lire_page',
                          side_effect=AssertionError('2e OCR')) as lire:
            _, journal = self._convertir('sortie_2')
        lire.assert_not_called()
        self.assertTrue([m for m in journal if "positions d'origine p. 1 :" in m])


class TestRejeuSansPdf(unittest.TestCase):

    def test_une_ligne_au_journal(self):
        journal = []
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'x_claude.jsonl'
            source.write_text(json.dumps({'image': 'page_006.png', 'success': True,
                                          'raw': REPONSE_P15}) + '\n', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                Converter(word_file=source, output_dir=Path(tmp) / 'sortie',
                          template=TemplateManager().get('REPARTITEUR'),
                          on_log=journal.append).run()
        self.assertIn("  positions d'origine non recalculées : rejeu sans le PDF", journal)


if __name__ == '__main__':
    unittest.main()
