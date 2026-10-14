"""
Images de travail (dossiers_travail.py) : dans le dossier de l'appli, un dossier par document,
jamais à côté du PDF de l'utilisateur ni dans son dossier de sortie ; purge des plus anciens.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_dossiers_travail.py -v
"""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from config import Config
from converter import Converter
from dossiers_travail import dossier_travail, purger
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'


class _Base(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.travail = self.tmp / 'travail'
        self._patch = patch.object(Config, 'TRAVAIL_DOSSIER', self.travail)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _vieillir(self, dossier: Path, jours: float):
        t = time.time() - jours * 86400
        os.utime(dossier, (t, t))


class TestDossierTravail(_Base):

    def test_dossier_dans_l_appli_pas_a_cote_du_document(self):
        doc = self.tmp / 'clients' / 'PE011.pdf'
        d = dossier_travail(doc, 'ocr_pages')
        self.assertTrue(d.is_dir())
        self.assertEqual(d.parent.parent, self.travail)
        self.assertTrue(d.parent.name.startswith('PE011_'))
        self.assertFalse((self.tmp / 'clients').exists())

    def test_meme_nom_dans_deux_dossiers_separes(self):
        a = dossier_travail(self.tmp / 'a' / 'doc.pdf')
        b = dossier_travail(self.tmp / 'b' / 'doc.pdf')
        self.assertNotEqual(a, b)

    def test_meme_document_meme_dossier(self):
        doc = self.tmp / 'doc.pdf'
        self.assertEqual(dossier_travail(doc, 'x').parent, dossier_travail(doc, 'y').parent)

    def test_sans_sorte_dossier_du_document(self):
        doc = self.tmp / 'doc.pdf'
        self.assertEqual(dossier_travail(doc), dossier_travail(doc, 'x').parent)


class TestPurger(_Base):

    def _document(self, nom: str, octets: int = 10, jours: float = 0) -> Path:
        d = dossier_travail(self.tmp / f'{nom}.pdf')
        (d / 'page_1.png').write_bytes(b'x' * octets)
        self._vieillir(d, jours)
        return d

    def test_trop_vieux_supprime(self):
        recent = self._document('recent')
        vieux = self._document('vieux', jours=Config.TRAVAIL_AGE_MAX_JOURS + 1)
        self.assertEqual(purger(Config.TRAVAIL_AGE_MAX_JOURS, 10 ** 9), 1)
        self.assertFalse(vieux.exists())
        self.assertTrue(recent.exists())

    def test_taille_depassee_plus_anciens_d_abord(self):
        a = self._document('a', 100, jours=3)
        b = self._document('b', 100, jours=2)
        c = self._document('c', 100, jours=1)
        self.assertEqual(purger(30, 150), 2)
        self.assertEqual([a.exists(), b.exists(), c.exists()], [False, False, True])

    def test_document_en_cours_jamais_supprime(self):
        en_cours = self._document('en_cours', 100, jours=60)
        self.assertEqual(purger(7, 0, garder=en_cours), 0)
        self.assertTrue(en_cours.exists())

    def test_ouverture_purge_les_autres(self):
        vieux = self._document('vieux', jours=Config.TRAVAIL_AGE_MAX_JOURS + 1)
        dossier_travail(self.tmp / 'nouveau.pdf')
        self.assertFalse(vieux.exists())

    def test_dossier_absent_rien_a_faire(self):
        self.assertEqual(purger(7, 0), 0)


class TestConversionTesseract(_Base):
    """Conversion Tesseract d'une page scannée : rien à côté du PDF, rien dans la sortie."""

    def test_aucune_image_chez_l_utilisateur(self):
        source = self.tmp / 'documents'
        source.mkdir()
        pdf = source / 'scan.pdf'
        with fitz.open(str(FIX / '6A23111PE133_extrait_8pages.pdf')) as doc, fitz.open() as un:
            un.insert_pdf(doc, from_page=3, to_page=3)
            un.save(str(pdf))
        sortie = self.tmp / 'sortie'
        with patch.object(Config, 'OCR_MODE', 'tesseract'):
            Converter(word_file=pdf, output_dir=sortie,
                      template=TemplateManager().get('REPARTITEUR'),
                      on_log=lambda m: None).run()
        self.assertEqual(sorted(p.name for p in source.iterdir()), ['scan.pdf'])
        self.assertEqual([p.name for p in sortie.iterdir() if p.is_dir()], [])
        images = list(dossier_travail(pdf).rglob('*.png'))
        self.assertTrue(images, "les images de travail sont dans le dossier de l'appli")
        shutil.rmtree(self.travail, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
