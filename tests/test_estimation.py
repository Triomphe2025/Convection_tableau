"""
estimation.py (phase 1B, étape 3) : estimation avant lancement — pages par nature, pages déjà
faites, tokens, coût et durée, SANS rastériser ni lancer Tesseract.

Fixtures fabriquées (PDF de pages scan via une image pleine page, journaux .jsonl fabriqués) ;
la correspondance des natures est vérifiée contre l'analyse réelle du converter
(pdf_extractor.diagnostiquer_page) sur les vrais PDF de tests/fixtures.
"""
import io
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
import estimation

FIXTURES = Path(__file__).parent / 'fixtures'


def _png(octets=8):
    """Petit PNG blanc (Pillow) pour couvrir une page → nature SCAN."""
    from PIL import Image
    tampon = io.BytesIO()
    Image.new('RGB', (octets, octets), 'white').save(tampon, format='PNG')
    return tampon.getvalue()


def _pdf_scan(chemin, n):
    """PDF de n pages couvertes d'une image (aucun texte) → chaque page classée SCAN."""
    import fitz
    png = _png()
    doc = fitz.open()
    for _ in range(n):
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=png)
    doc.save(str(chemin))
    doc.close()


def _journal(chemin, modele, usages, horodatages=None):
    """Écrit un journal .jsonl : une ligne success par usage (input, output)."""
    with open(chemin, 'w', encoding='utf-8') as f:
        for i, (entree, sortie) in enumerate(usages):
            ligne = {'model': modele, 'success': True,
                     'usage': {'input_tokens': entree, 'output_tokens': sortie}}
            if horodatages:
                ligne['ts'] = horodatages[i]
            f.write(json.dumps(ligne) + '\n')


class TestNaturesCommeConverter(unittest.TestCase):
    """La nature estimée = la règle réelle du converter, sans rastériser."""

    def test_pdf_fabrique_pages_scan(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            pdf = Path(d) / 'scan.pdf'
            _pdf_scan(pdf, 3)
            assert estimation.natures(pdf) == ['scan', 'scan', 'scan']

    def test_correspond_a_diagnostiquer_page_sur_les_fixtures(self):
        import fitz
        from pdf_extractor import classer_page
        pdfs = sorted(FIXTURES.glob('*.pdf'))
        assert pdfs, "aucun PDF de fixture"
        for pdf in pdfs:
            doc = fitz.open(str(pdf))
            try:
                attendu = [classer_page(page) for page in doc]
            finally:
                doc.close()
            assert estimation.natures(pdf) == attendu, pdf.name


class TestMoyennesModele(unittest.TestCase):

    def setUp(self):
        estimation.reinitialiser_cache()

    def test_moyenne_depuis_journal(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _journal(Path(d) / 'a_claude.jsonl', 'M', [(100, 10), (300, 30)])
            with patch.object(Config, 'ESTIMATION_JOURNAUX_DOSSIER', Path(d)):
                m = estimation.moyennes_modele('M')
        assert m['source'] == 'journaux'
        assert m['tokens'] == (200.0, 20.0)

    def test_repli_constante_si_aucun_journal(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with patch.object(Config, 'ESTIMATION_JOURNAUX_DOSSIER', Path(d)):
                m = estimation.moyennes_modele('M')
        assert m['source'] == 'constante'
        assert m['tokens'] == tuple(Config.ESTIMATION_TOKENS_PAR_PAGE_DEFAUT)

    def test_secondes_depuis_horodatages(self):
        import tempfile
        ts = ['2026-10-09T10:00:00', '2026-10-09T10:00:08', '2026-10-09T10:00:14']
        with tempfile.TemporaryDirectory() as d:
            _journal(Path(d) / 'a_claude.jsonl', 'M', [(1, 1), (1, 1), (1, 1)], ts)
            with patch.object(Config, 'ESTIMATION_JOURNAUX_DOSSIER', Path(d)):
                m = estimation.moyennes_modele('M')
        assert m['secondes'] == 7.0   # moyenne de 8 s et 6 s

    def test_memoisation_une_fois_par_session(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            journal = Path(d) / 'a_claude.jsonl'
            _journal(journal, 'M', [(100, 10)])
            with patch.object(Config, 'ESTIMATION_JOURNAUX_DOSSIER', Path(d)):
                premier = estimation.moyennes_modele('M')
                journal.unlink()                      # le journal disparaît
                second = estimation.moyennes_modele('M')   # mais c'est mémoïsé
        assert premier == second
        assert second['source'] == 'journaux'


class TestEstimer(unittest.TestCase):

    def setUp(self):
        estimation.reinitialiser_cache()
        self._tmp = __import__('tempfile').TemporaryDirectory()
        self.dossier = Path(self._tmp.name)
        # Journaux vides → tokens de repli (constante) : maths déterministes.
        self._p = patch.object(Config, 'ESTIMATION_JOURNAUX_DOSSIER', self.dossier / 'vide')
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self._tmp.cleanup()

    def _pdf(self, n):
        pdf = self.dossier / f'doc_{n}.pdf'
        _pdf_scan(pdf, n)
        return pdf

    def test_cout_claude_depuis_tokens_et_prix(self):
        pdf = self._pdf(4)
        res = estimation.estimer(pdf, None, profil='claude', modele='claude-opus-5-5')
        entree, sortie = Config.ESTIMATION_TOKENS_PAR_PAGE_DEFAUT
        pe, ps = Config.CLAUDE_PRIX_MODELES['claude-opus-5-5']
        attendu = 4 * (entree * pe + sortie * ps) / 1_000_000
        assert res['pages']['scan'] == 4
        assert res['pages_a_lire'] == 4
        assert abs(res['cout_usd'] - attendu) < 1e-9
        assert res['approche'] is True

    def test_lot_moitie_prix(self):
        pdf = self._pdf(4)
        normal = estimation.estimer(pdf, None, profil='claude', modele='claude-opus-5-5')
        lot = estimation.estimer(pdf, None, profil='claude', modele='claude-opus-5-5', lot=True)
        assert abs(lot['cout_usd'] - normal['cout_usd'] / 2) < 1e-9

    def test_profil_tesseract_cout_nul_duree_tesseract(self):
        pdf = self._pdf(5)
        res = estimation.estimer(pdf, None, profil='tesseract')
        assert res['cout_usd'] == 0.0
        attendu = 5 * Config.ESTIMATION_SECONDES_PAR_PAGE['tesseract']
        assert res['duree']['secondes'] == attendu

    def test_profil_non_api_cout_nul(self):
        pdf = self._pdf(3)
        for profil in ('cad', 'formatage', 'log-replay'):
            res = estimation.estimer(pdf, None, profil=profil)
            assert res['cout_usd'] == 0.0, profil

    def test_cache_connu_depuis_journal_partiel(self):
        pdf = self._pdf(5)
        sortie = self.dossier / 'sortie'
        sortie.mkdir()
        # 2 pages déjà faites pour ce document (même radical) et ce modèle.
        _journal(sortie / f'{pdf.stem}_claude.jsonl', 'claude-opus-5-5', [(1, 1), (1, 1)])
        res = estimation.estimer(pdf, None, profil='claude', modele='claude-opus-5-5',
                                 dossier_sortie=sortie)
        assert res['cache_connu'] is True
        assert res['pages_en_cache'] == 2
        assert res['pages_a_lire'] == 3   # 5 scan - 2 déjà faites

    def test_cache_inconnu_sans_dossier(self):
        pdf = self._pdf(5)
        res = estimation.estimer(pdf, None, profil='claude', modele='claude-opus-5-5')
        assert res['cache_connu'] is False
        assert res['pages_en_cache'] == 0

    def test_duree_lot_texte_sans_chiffre(self):
        pdf = self._pdf(2)
        res = estimation.estimer(pdf, None, profil='claude', modele='claude-opus-5-5', lot=True)
        assert res['duree']['secondes'] is None
        assert res['duree']['texte'] == Config.ESTIMATION_DUREE_LOT_TEXTE

    def test_modele_defaut_est_celui_de_config(self):
        pdf = self._pdf(1)
        res = estimation.estimer(pdf, None, profil='claude')
        assert res['modele'] == Config.CLAUDE_OCR_MODEL

    def test_source_tokens_dans_le_retour(self):
        pdf = self._pdf(1)
        res = estimation.estimer(pdf, None, profil='claude', modele='claude-opus-5-5')
        assert res['source_tokens'] == 'constante'

    def test_journal_jsonl_total_lignes_cout_nul(self):
        chemin = self.dossier / 'doc_claude.jsonl'
        _journal(chemin, 'claude-opus-5-5', [(1, 1), (1, 1), (1, 1)])
        res = estimation.estimer(chemin, None, profil='log-replay')
        assert res['pages']['total'] == 3
        assert res['cout_usd'] == 0.0


class TestBudget(unittest.TestCase):

    def test_moins_de_2s_sur_720_pages(self):
        import tempfile
        estimation.reinitialiser_cache()
        with tempfile.TemporaryDirectory() as d:
            pdf = Path(d) / 'gros.pdf'
            _pdf_scan(pdf, 720)
            with patch.object(Config, 'ESTIMATION_JOURNAUX_DOSSIER', Path(d) / 'vide'):
                debut = time.perf_counter()
                res = estimation.estimer(pdf, None, profil='claude',
                                         modele='claude-opus-5-5')
                duree = time.perf_counter() - debut
        assert res['pages']['total'] == 720
        assert duree < 2.0, f"{duree:.2f}s"


if __name__ == '__main__':
    unittest.main()
