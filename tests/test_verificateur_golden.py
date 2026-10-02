"""
Test doré de la vérification de conversion sur le cas réel 6A 23111PE102.

Deux lectures figées dans tests/fixtures/ :
  - scan_lecture_tesseract.json : le scan (15 p., sans couche texte) relu par
    relecture_scan (Tesseract psm 6, 300 DPI, colonnes sur les traits du cadre) —
    la lecture INDÉPENDANTE du moteur de conversion, seule capable de contredire
    Claude. Régénérée le 2026-10-02 par Converter._charger_pivots(relecture=True) ;
  - journal_claude_6A23111PE102.jsonl : la conversion Claude Vision du même scan
    (rejouée sans appel API), donc le scénario réel du produit ;
  - final_lecture_pdf.json : le PDF final (13 p.) relu par pdf_extractor.
Les PDF d'origine sont conservés à côté pour régénérer ces lectures.

Sur la page 10 du scan on lit « EP.STAT/TS DISCORDANCE POMPE » ; Claude a lu, et
le document final porte, « DISCONTINUOSITE ». Les tests sont déterministes
(aucune liste blanche, aucun OCR) ; la relecture Tesseract complète (~5 min) est
réservée à VERIF_TEST_LENT=1.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_verificateur_golden.py -v
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import fitz

from claude_ocr import LogReplayer
from config import Config
from converter import Converter
from ocr_processor import BornierTableExtractor
from template import DEFAULT_TEMPLATE
from verificateur import verifier

FIXTURES = Path(__file__).parent / 'fixtures'
COLONNES = list(DEFAULT_TEMPLATE.columns)
PDF_SCAN = FIXTURES / 'scan_6A23111PE102_15p.pdf'
PDF_FINAL = FIXTURES / 'final_6A23111PE102_13p.pdf'
JOURNAL = FIXTURES / 'journal_claude_6A23111PE102.jsonl'


def _json(nom):
    return json.loads((FIXTURES / nom).read_text(encoding='utf-8'))


def _rapport(conv):
    return verifier(
        _json('scan_lecture_tesseract.json'), conv, colonnes=COLONNES,
        distance=BornierTableExtractor._levenshtein,
    )


def _divergence_discordance(rapport):
    return [
        e for e in rapport.a_verifier
        if 'DISCORDANCE' in e.valeur_ref.upper() and 'DISCONTINUOSI' in e.valeur_conv.upper()
    ]


class TestFixtures(unittest.TestCase):

    def test_pdf_d_origine_presents_avec_le_bon_nombre_de_pages(self):
        with fitz.open(PDF_SCAN) as scan, fitz.open(PDF_FINAL) as final:
            self.assertEqual((len(scan), len(final)), (15, 13))

    def test_le_scan_n_a_pas_de_couche_texte(self):
        with fitz.open(PDF_SCAN) as scan:
            self.assertEqual(sum(len(scan[i].get_text('words')) for i in range(3)), 0)

    def test_lectures_figees_coherentes(self):
        self.assertEqual(len(_json('scan_lecture_tesseract.json')), 15)
        self.assertEqual(len(_json('final_lecture_pdf.json')), 13)


class TestCasReelScanContreJournalClaude(unittest.TestCase):
    """Scénario du produit : relecture Tesseract du scan contre la conversion."""

    @classmethod
    def setUpClass(cls):
        cls.rapport = _rapport(LogReplayer(JOURNAL, DEFAULT_TEMPLATE).replay_all())

    def test_divergence_discordance_trouvee(self):
        trouvees = _divergence_discordance(self.rapport)
        self.assertEqual(len(trouvees), 1)
        self.assertEqual((trouvees[0].page_ref, trouvees[0].ligne_ref), (10, 8))

    def test_pages_appariees_malgre_les_paginations_differentes(self):
        self.assertEqual(len(self.rapport.pages_appariees), 11)
        # Pages 1 à 4 du scan (gardes, sommaire) : aucune ligne à clé de borne,
        # donc pas des tableaux — elles ne restent plus « sans partenaire ».
        self.assertEqual(self.rapport.pages_ref_orphelines, [])
        self.assertEqual(self.rapport.pages_conv_orphelines, [])

    def test_criteres_du_cahier_des_charges(self):
        """Cibles : au plus 20 alertes, concordance >= 98 % (mesuré : 7, 98,9 %).

        Lignes orphelines comptées comme alertes ; aucune tolérance de similarité.
        Les 7 restantes : 5 vraies erreurs de Claude (48V lu 4H, DISCONTINUOSITE,
        lignes fusionnées page 13) et « CABLEE » lu sur sa propre ligne page 11.
        """
        self.assertLessEqual(len(self.rapport.a_verifier), 20)
        self.assertGreaterEqual(self.rapport.concordance, 0.98)

    def test_vraies_erreurs_de_claude_signalees(self):
        valeurs = [(e.valeur_ref, e.valeur_conv) for e in self.rapport.a_verifier]
        self.assertIn(('EP. STAT/TS MANQUE 48V', 'G EP. STAT/TS MANQUE 4H'), valeurs)
        self.assertIn(('', '02 B 0015B'), valeurs)


class TestCasReelScanContrePdfFinal(unittest.TestCase):
    """Cas de la spécification : le scan contre le document final relu."""

    @classmethod
    def setUpClass(cls):
        cls.rapport = _rapport(_json('final_lecture_pdf.json'))

    def test_divergence_discordance_trouvee(self):
        trouvees = _divergence_discordance(self.rapport)
        self.assertEqual([(e.page_ref, e.ligne_ref) for e in trouvees], [(10, 8)])

    def test_pages_appariees(self):
        self.assertEqual(len(self.rapport.pages_appariees), 11)

    def test_criteres_du_cahier_des_charges(self):
        """Même couple que outils_reference/pdf_table_compare.py (mesuré : 4, 99,6 %)."""
        self.assertLessEqual(len(self.rapport.a_verifier), 20)
        self.assertGreaterEqual(self.rapport.concordance, 0.98)


class TestConverterSurLeCasReel(unittest.TestCase):

    def test_verifier_conversion_journal_rejoue_sans_tesseract(self):
        conv = Converter(word_file=PDF_SCAN, output_dir=Path('.'))
        rapport = conv.verifier_conversion(
            reference=_json('scan_lecture_tesseract.json'), converti=JOURNAL,
        )
        self.assertEqual(
            [(e.page_ref, e.ligne_ref) for e in _divergence_discordance(rapport)], [(10, 8)],
        )

    @unittest.skipUnless(Path(Config.TESSERACT_PATH).exists(), "Tesseract absent")
    def test_lecture_du_pdf_final_par_le_converter(self):
        conv = Converter(word_file=PDF_FINAL, output_dir=Path('.'))
        with tempfile.TemporaryDirectory() as tmp:
            copie = Path(tmp) / 'final.pdf'
            shutil.copy(PDF_FINAL, copie)
            pages = conv._charger_pivots(copie)
        self.assertEqual(len(pages), 13)
        self.assertEqual(sum(1 for p in pages if p.get('success')), 11)


@unittest.skipUnless(
    os.environ.get('VERIF_TEST_LENT') == '1' and Path(Config.TESSERACT_PATH).exists(),
    "Relecture Tesseract de 15 pages (~5 min) : définir VERIF_TEST_LENT=1",
)
class TestRelectureTesseractComplete(unittest.TestCase):

    def test_de_bout_en_bout_depuis_les_pdf(self):
        conv = Converter(word_file=PDF_SCAN, output_dir=Path('.'))
        with tempfile.TemporaryDirectory() as tmp:
            scan = Path(tmp) / 'scan.pdf'
            shutil.copy(PDF_SCAN, scan)
            rapport = conv.verifier_conversion(reference=scan, converti=JOURNAL)
        trouvees = _divergence_discordance(rapport)
        self.assertEqual(len(trouvees), 1)


if __name__ == '__main__':
    unittest.main()
