"""
Tests de Converter.verifier_conversion et de ses aides privées, sans Tesseract
ni PDF réel : les lectures sont fabriquées ou simulées.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_converter_verification.py -v
"""

import contextlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import converter as module_converter
from config import Config
from converter import Converter, _mode_ocr_tesseract, main
from ocr_processor import BornierTableExtractor
from verificateur import A_VERIFIER, Ecart, RapportVerification

COLONNES = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']


def _ligne(cells, conf=None):
    return {'type': 'data', 'cells': list(cells), 'confidence': conf or [100] * len(cells)}


def _page(rows):
    return {'success': True, 'headers': COLONNES, 'rows': rows, 'metadata': {}}


def _lecture_scan():
    return [_page([
        _ligne(['07', '2 I', 'EP. STAT/TS NIVEAU TROP BAS', '0022B'], [95, 80, 90, 92]),
        _ligne(['08', '2 M', 'EP.STAT/TS DISCORDANCE', 'POMPE 0033B'], [96, 74, 91, 90]),
        _ligne(['09', '3 G', 'EP. STAT/TS FUSION FUSIBLE', '0023B'], [95, 80, 90, 92]),
    ])]


def _lecture_convertie():
    return [_page([
        _ligne(['07', '2 I', 'EP.STAT/TS NIVEAU TROP BAS', '0022B']),
        _ligne(['08', '2 M', 'EP.STAT/TS DISCONTINUOSITE POMPE', '0033B']),
        _ligne(['09', '3 G', 'EP.STAT/TS FUSION FUSIBLE', '0023B']),
    ])]


def _converter(**kwargs):
    logs = []
    conv = Converter(
        word_file=Path('scan.pdf'), output_dir=Path('sortie'),
        on_log=logs.append, **kwargs,
    )
    return conv, logs


class TestVerifierConversion(unittest.TestCase):

    def test_divergence_discordance_trouvee(self):
        conv, logs = _converter()
        rapport = conv.verifier_conversion(_lecture_scan(), _lecture_convertie())
        self.assertEqual(len(rapport.a_verifier), 1)
        self.assertIn('DISCORDANCE', rapport.a_verifier[0].valeur_ref)
        self.assertTrue(any('divergence(s) à vérifier' in m for m in logs))

    def test_utilise_les_resultats_de_la_derniere_conversion(self):
        conv, _ = _converter()
        conv._derniers_resultats = _lecture_convertie()
        rapport = conv.verifier_conversion(reference=_lecture_scan())
        self.assertEqual(len(rapport.a_verifier), 1)

    def test_sans_conversion_en_memoire_leve_runtimeerror(self):
        conv, _ = _converter()
        with self.assertRaises(RuntimeError):
            conv.verifier_conversion(reference=_lecture_scan())

    def test_distance_levenshtein_du_projet_injectee(self):
        conv, _ = _converter()
        with patch('verificateur.verifier') as faux:
            faux.return_value = RapportVerification()
            conv.verifier_conversion(_lecture_scan(), _lecture_convertie())
        self.assertIs(faux.call_args.kwargs['distance'], BornierTableExtractor._levenshtein)
        self.assertEqual(faux.call_args.kwargs['colonnes'], COLONNES)
        self.assertIn('SIGNAL', faux.call_args.kwargs['valeurs_connues'])

    def test_pages_sans_partenaire_signalees_dans_le_journal(self):
        conv, logs = _converter()
        with patch('verificateur.verifier') as faux:
            faux.return_value = RapportVerification(pages_ref_orphelines=[4])
            conv.verifier_conversion(_lecture_scan(), _lecture_convertie())
        self.assertTrue(any('Pages sans partenaire' in m for m in logs))

    def test_lecture_de_reference_ne_declenche_aucun_callback_interactif(self):
        validation = MagicMock()
        mapping = MagicMock()
        conv, _ = _converter(on_validation=validation, on_column_mapping=mapping)
        conv.verifier_conversion(_lecture_scan(), _lecture_convertie())
        validation.assert_not_called()
        mapping.assert_not_called()


class TestRunConserveLesResultats(unittest.TestCase):

    def test_run_memorise_les_resultats_pour_la_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            conv = Converter(word_file=Path(tmp), output_dir=Path(tmp) / 'out')
            resultats = _lecture_convertie()
            with patch.object(Converter, '_extraire_depuis_images',
                              return_value=(resultats, MagicMock())), \
                    patch.object(module_converter, 'generer_excel'):
                conv.run()
        self.assertIs(conv._derniers_resultats, resultats)

    def test_aucun_resultat_avant_run(self):
        conv, _ = _converter()
        self.assertIsNone(conv._derniers_resultats)


class TestModeOcrTesseract(unittest.TestCase):

    def setUp(self):
        self._ancien = Config.OCR_MODE

    def tearDown(self):
        Config.OCR_MODE = self._ancien

    def test_force_tesseract_puis_restaure(self):
        Config.OCR_MODE = 'claude'
        with _mode_ocr_tesseract():
            self.assertEqual(Config.OCR_MODE, 'tesseract')
        self.assertEqual(Config.OCR_MODE, 'claude')

    def test_restaure_meme_en_cas_d_exception(self):
        Config.OCR_MODE = 'claude'
        with self.assertRaises(ValueError):
            with _mode_ocr_tesseract():
                raise ValueError('boum')
        self.assertEqual(Config.OCR_MODE, 'claude')


class TestChargerPivots(unittest.TestCase):

    def setUp(self):
        self._ancien = Config.OCR_MODE

    def tearDown(self):
        Config.OCR_MODE = self._ancien

    def test_liste_et_dict_passent_tels_quels(self):
        conv, _ = _converter()
        pages = _lecture_scan()
        self.assertEqual(conv._charger_pivots(pages), pages)
        self.assertEqual(conv._charger_pivots(pages[0]), [pages[0]])

    def test_fichier_absent_leve_filenotfounderror(self):
        conv, _ = _converter()
        with self.assertRaises(FileNotFoundError):
            conv._charger_pivots('/chemin/inexistant.pdf')

    def test_format_non_supporte_leve_valueerror(self):
        conv, _ = _converter()
        with tempfile.TemporaryDirectory() as tmp:
            fichier = Path(tmp) / 'notes.txt'
            fichier.write_text('x', encoding='utf-8')
            with self.assertRaises(ValueError):
                conv._charger_pivots(fichier)

    def test_pdf_lu_par_tesseract_meme_si_le_mode_courant_est_claude(self):
        Config.OCR_MODE = 'claude'
        vus = {}

        class FauxExtracteur:
            def __init__(self, template=None):
                pass

            def extract_all(self, chemin, cancel_check=None):
                vus['mode'] = Config.OCR_MODE
                return [{'success': True, 'rows': []}], self

        conv, _ = _converter()
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'doc.pdf'
            pdf.write_bytes(b'%PDF-1.4')
            with patch('pdf_extractor.PdfTableExtractor', FauxExtracteur):
                resultat = conv._charger_pivots(pdf)
        self.assertEqual(vus['mode'], 'tesseract')
        self.assertEqual(Config.OCR_MODE, 'claude')
        self.assertEqual(len(resultat), 1)

    def test_jsonl_relu_sans_appel_api(self):
        conv, _ = _converter()
        faux = MagicMock()
        faux.return_value.replay_all.return_value = [{'success': True}]
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp) / 'log.jsonl'
            journal.write_text('', encoding='utf-8')
            with patch('claude_ocr.LogReplayer', faux):
                self.assertEqual(conv._charger_pivots(journal), [{'success': True}])

    def test_dossier_d_images_lu_par_tesseract(self):
        conv, _ = _converter()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'bornier_1.png').write_bytes(b'x')
            with patch.object(Converter, '_lire_images_tesseract',
                              return_value=[{'success': True}]) as lecture:
                self.assertEqual(conv._charger_pivots(Path(tmp)), [{'success': True}])
        self.assertEqual(len(lecture.call_args.args[0]), 1)


class TestImagesDuDossier(unittest.TestCase):

    def test_tri_numerique_et_filtre_des_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            for nom in ('bornier_10.png', 'bornier_2.png', 'bornier_1.jpg', 'notes.txt'):
                (Path(tmp) / nom).write_bytes(b'x')
            noms = [p.name for p in Converter._images_du_dossier(Path(tmp))]
        self.assertEqual(noms, ['bornier_1.jpg', 'bornier_2.png', 'bornier_10.png'])

    def test_dossier_vide(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(Converter._images_du_dossier(Path(tmp)), [])


class TestLireImagesTesseract(unittest.TestCase):

    def _images(self, n):
        return [Path(f"img{i}.png") for i in range(n)]

    def test_une_lecture_par_image(self):
        conv, _ = _converter()
        with patch.object(module_converter, 'BornierTableExtractor') as classe:
            classe.return_value.extract.side_effect = lambda p: {'success': True, 'p': p.name}
            resultats = conv._lire_images_tesseract(self._images(3))
        self.assertEqual([r['p'] for r in resultats], ['img0.png', 'img1.png', 'img2.png'])

    def test_liste_vide(self):
        conv, _ = _converter()
        with patch.object(module_converter, 'BornierTableExtractor'):
            self.assertEqual(conv._lire_images_tesseract([]), [])

    def test_arret_cooperatif(self):
        arret = threading.Event()
        conv, _ = _converter(cancel_event=arret)

        def lecture(_chemin):
            arret.set()
            return {'success': True}

        with patch.object(module_converter, 'BornierTableExtractor') as classe:
            classe.return_value.extract.side_effect = lecture
            resultats = conv._lire_images_tesseract(self._images(5))
        self.assertEqual(len(resultats), 1)


class TestLigneDeCommande(unittest.TestCase):

    def _rapport(self, avec_ecart):
        rapport = RapportVerification()
        if avec_ecart:
            rapport.ajouter([Ecart(1, 1, 1, 1, 'SIGNAL', 'a', 'b', A_VERIFIER)])
        return rapport

    def test_code_retour_1_si_divergence(self):
        with patch.object(Converter, 'verifier_conversion', return_value=self._rapport(True)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['verifier', 'scan.pdf', 'converti.pdf']), 1)

    def test_code_retour_0_sans_divergence(self):
        with patch.object(Converter, 'verifier_conversion', return_value=self._rapport(False)):
            with contextlib.redirect_stdout(io.StringIO()) as sortie:
                self.assertEqual(main(['verifier', 'scan.pdf', 'converti.pdf']), 0)
        self.assertIn('concordance', sortie.getvalue())

    def test_rapport_ecrit_dans_un_fichier(self):
        with tempfile.TemporaryDirectory() as tmp:
            cible = Path(tmp) / 'rapport.txt'
            with patch.object(Converter, 'verifier_conversion',
                              return_value=self._rapport(True)):
                with contextlib.redirect_stdout(io.StringIO()):
                    main(['verifier', 'a.pdf', 'b.pdf', '--rapport', str(cible)])
            self.assertIn('À VÉRIFIER', cible.read_text(encoding='utf-8'))

    def test_arguments_manquants_quittent_avec_erreur(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(['verifier', 'seul.pdf'])


if __name__ == '__main__':
    unittest.main()
