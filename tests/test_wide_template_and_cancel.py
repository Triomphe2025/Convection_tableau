"""
Tests unitaires — avertissement/confirmation template large (moteurs vision)
et bouton d'arrêt coopératif de la conversion.

Couvre :
  - Converter._verifier_template_large (log + confirmation engine-agnostic)
  - Converter._extraire_avec_progres (arrêt coopératif via cancel_event)
  - PdfTableExtractor.extract_all (arrêt coopératif via cancel_check)

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_wide_template_and_cancel.py -v
"""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import Config
from converter import Converter
from template import TableTemplate


def _template(n_cols: int, name: str = "Large") -> TableTemplate:
    cols = [f"COL{i}" for i in range(1, n_cols + 1)]
    return TableTemplate(name=name, columns=cols)


# ══════════════════════════════════════════════════════════════════════
# Converter._verifier_template_large
# ══════════════════════════════════════════════════════════════════════

class TestVerifierTemplateLarge(unittest.TestCase):

    def setUp(self):
        self._orig_mode = Config.OCR_MODE
        self._logs = []

    def tearDown(self):
        Config.OCR_MODE = self._orig_mode

    def _make_converter(self, template, **kwargs):
        return Converter(
            word_file=Path('dummy.docx'), output_dir=Path('out'),
            template=template, on_log=self._logs.append, **kwargs
        )

    def test_log_avertissement_tous_moteurs(self):
        """Le log d'avertissement apparaît quel que soit le moteur OCR actif."""
        for mode in ('tesseract', 'claude', 'ollama', 'docling', 'agent', 'hybrid'):
            Config.OCR_MODE = mode
            self._logs.clear()
            conv = self._make_converter(_template(5))
            conv._verifier_template_large()
            self.assertTrue(
                any('5 colonnes' in m for m in self._logs),
                f"Avertissement absent pour le moteur {mode}",
            )

    def test_pas_de_log_si_4_colonnes_ou_moins(self):
        """Non-régression : template standard (4 colonnes) → jamais d'avertissement."""
        Config.OCR_MODE = 'claude'
        conv = self._make_converter(_template(4))
        conv._verifier_template_large()
        self.assertEqual(self._logs, [])

    def test_confirm_appele_uniquement_si_moteur_non_tesseract(self):
        Config.OCR_MODE = 'tesseract'
        mock_cb = MagicMock(return_value=True)
        conv = self._make_converter(_template(5), on_wide_template_confirm=mock_cb)
        conv._verifier_template_large()
        mock_cb.assert_not_called()

    def test_confirm_appele_si_moteur_vision_et_template_large(self):
        Config.OCR_MODE = 'claude'
        mock_cb = MagicMock(return_value=True)
        tpl = _template(5)
        conv = self._make_converter(tpl, on_wide_template_confirm=mock_cb)
        conv._verifier_template_large()
        mock_cb.assert_called_once_with(tpl.columns, 'claude')

    def test_confirm_refuse_leve_runtimeerror(self):
        Config.OCR_MODE = 'claude'
        mock_cb = MagicMock(return_value=False)
        conv = self._make_converter(_template(5), on_wide_template_confirm=mock_cb)
        with self.assertRaises(RuntimeError):
            conv._verifier_template_large()

    def test_confirm_absent_ne_bloque_pas(self):
        """Callback None, moteur vision, template large → pas d'exception, juste le log."""
        Config.OCR_MODE = 'claude'
        conv = self._make_converter(_template(5), on_wide_template_confirm=None)
        conv._verifier_template_large()
        self.assertTrue(any('5 colonnes' in m for m in self._logs))


# ══════════════════════════════════════════════════════════════════════
# Converter._extraire_avec_progres — arrêt coopératif
# ══════════════════════════════════════════════════════════════════════

class TestExtraireAvecProgresCancelEvent(unittest.TestCase):

    def _make_images_dir(self, n: int) -> Path:
        tmp = tempfile.mkdtemp()
        img_dir = Path(tmp)
        for i in range(n):
            (img_dir / f"img{i}.png").write_bytes(b'\x89PNG\r\n\x1a\n')
        return img_dir

    def test_cancel_event_stoppe_boucle(self):
        """Event settée pendant la 2e image → seules 2 images traitées, résultats partiels."""
        from ocr_processor import BornierTableExtractor
        img_dir = self._make_images_dir(5)
        cancel_event = threading.Event()
        call_count = [0]

        def fake_extract(self_ext, image_path, feedback=None):
            call_count[0] += 1
            if call_count[0] == 2:
                cancel_event.set()
            return {
                'success': True, 'headers': [], 'rows': [],
                'detection_method': 'header',
            }

        conv = Converter(
            word_file=Path('dummy.docx'), output_dir=img_dir / 'out',
            cancel_event=cancel_event,
        )
        with patch.object(BornierTableExtractor, 'extract', fake_extract):
            results, _ = conv._extraire_avec_progres(img_dir, 0)

        self.assertEqual(len(results), 2)

    def test_sans_cancel_event_traite_tout(self):
        """Non-régression : cancel_event=None → toutes les images traitées."""
        from ocr_processor import BornierTableExtractor
        img_dir = self._make_images_dir(3)

        def fake_extract(self_ext, image_path, feedback=None):
            return {
                'success': True, 'headers': [], 'rows': [],
                'detection_method': 'header',
            }

        conv = Converter(word_file=Path('dummy.docx'), output_dir=img_dir / 'out')
        with patch.object(BornierTableExtractor, 'extract', fake_extract):
            results, _ = conv._extraire_avec_progres(img_dir, 0)

        self.assertEqual(len(results), 3)

    def test_est_annule_sans_event_retourne_false(self):
        conv = Converter(word_file=Path('dummy.docx'), output_dir=Path('out'))
        self.assertFalse(conv._est_annule())

    def test_est_annule_avec_event_settee(self):
        ev = threading.Event()
        ev.set()
        conv = Converter(
            word_file=Path('dummy.docx'), output_dir=Path('out'), cancel_event=ev,
        )
        self.assertTrue(conv._est_annule())


# ══════════════════════════════════════════════════════════════════════
# PdfTableExtractor.extract_all — arrêt coopératif
# ══════════════════════════════════════════════════════════════════════

class TestPdfExtractAllCancelCheck(unittest.TestCase):

    def _make_pdf(self, n_pages: int) -> Path:
        import fitz
        doc = fitz.open()
        for _ in range(n_pages):
            doc.new_page(width=200, height=200)
        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        doc.save(str(tmp_path))
        doc.close()
        return tmp_path

    def test_cancel_check_stoppe_boucle(self):
        from pdf_extractor import PdfTableExtractor
        pdf_path = self._make_pdf(5)
        call_count = [0]

        def fake_extract_page(self_ext, page, page_num):
            call_count[0] += 1
            return {'success': True, 'headers': [], 'rows': []}

        try:
            ext = PdfTableExtractor()
            with patch.object(PdfTableExtractor, '_extract_page', fake_extract_page):
                results, _ = ext.extract_all(
                    pdf_path, cancel_check=lambda: call_count[0] >= 2
                )
            self.assertEqual(len(results), 2)
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_sans_cancel_check_traite_tout(self):
        from pdf_extractor import PdfTableExtractor
        pdf_path = self._make_pdf(3)

        def fake_extract_page(self_ext, page, page_num):
            return {'success': True, 'headers': [], 'rows': []}

        try:
            ext = PdfTableExtractor()
            with patch.object(PdfTableExtractor, '_extract_page', fake_extract_page):
                results, _ = ext.extract_all(pdf_path)
            self.assertEqual(len(results), 3)
        finally:
            pdf_path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
