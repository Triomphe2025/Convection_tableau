"""
Commit A dans le convertisseur : positions d'origine posées sur les pages lues par
Claude (faux client, réponse enregistrée, Tesseract en local), lecture Tesseract gardée
en cache (<document>_tesseract.json) ; sans PDF (rejeu d'un journal), une ligne au journal.

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
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        dossier = Path(cls._tmp.name)
        pdf = dossier / 'pe133_p15.pdf'
        with fitz.open(str(FIX / '6A23111PE133_extrait_8pages.pdf')) as src, fitz.open() as un:
            un.insert_pdf(src, from_page=5, to_page=5)
            un.save(str(pdf))
        cls.journal = []
        with _mode_claude(), patch('anthropic.Anthropic', _FauxClient), \
                contextlib.redirect_stdout(io.StringIO()):
            cls.resultat = Converter(word_file=pdf, output_dir=dossier / 'sortie',
                                     template=TemplateManager().get('REPARTITEUR'),
                                     on_log=cls.journal.append).run()
        cls.cache = dossier / 'sortie' / 'pe133_p15_tesseract.json'
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

    def test_lecture_tesseract_en_cache(self):
        donnees = json.loads(self.cache.read_text('utf-8'))
        self.assertEqual(list(donnees), ['1'])
        self.assertGreater(len(LecturePage.depuis_dict(donnees['1']).mots), 100)


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
