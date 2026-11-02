"""
Pages vectorielles en police sans table Unicode (polices_illisibles + pdf_extractor) :
en-tête et pied décodés en local, page lue en couche texte, aucun appel API.

Fixture : 223111PE052, 4 pages — p. 1 page de garde, p. 2 P313TS (en-tête et pied en
Comic Sans sans table Unicode), p. 3 PE (même police, lisible : la référence), p. 4 QMICF
(lettres Q et F absentes de la référence : lues par Tesseract). Avant le correctif, les pages 2 et
4 étaient écartées (« pas d'en-tête du modèle ») et absentes du classeur.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_polices_illisibles.py -v
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

import pdf_extractor as pe
import polices_illisibles as pi
from config import Config
from converter import Converter
from template import DEFAULT_TEMPLATE

FIXTURES = Path(__file__).parent / 'fixtures'
PE052 = FIXTURES / '223111PE052_extrait_polices_sans_unicode.pdf'


def _vision_interdite(*args, **kwargs):
    raise AssertionError("appel au moteur vision (API) alors qu'aucun n'est attendu")


def _lire(numero, **reglages):
    """extract_page_grille de la page `numero` (1-based) d'un document ouvert pour l'essai :
    le décodage est gardé avec le document, un réglage différent veut un document neuf."""
    anciens = {k: getattr(Config, k) for k in reglages}
    for k, v in reglages.items():
        setattr(Config, k, v)
    try:
        with fitz.open(str(PE052)) as doc:
            return pe.PdfTableExtractor(DEFAULT_TEMPLATE).extract_page_grille(
                doc[numero - 1], numero - 1)
    finally:
        for k, v in anciens.items():
            setattr(Config, k, v)


def _cellules(r):
    return [[' '.join(c.split()) for c in row['cells']]
            for row in r['rows'] if row.get('type') == 'data']


class TestCaracteresIllisibles(unittest.TestCase):

    def test_codes_bruts_et_fffd(self):
        self.assertTrue(pi.illisible(1))
        self.assertTrue(pi.illisible(0xFFFD))
        self.assertFalse(pi.illisible(ord('A')))
        # 9, 10, 13 : blancs dans un texte normal, lettres dans un span illisible.
        self.assertFalse(pi.illisible(9))
        self.assertTrue(pi.code_brut(9))

    def test_diagnostic_compte_les_illisibles(self):
        with fitz.open(str(PE052)) as doc:
            self.assertEqual(pe.diagnostiquer_page(doc[0])['illisibles'], 0)
            self.assertGreater(pe.diagnostiquer_page(doc[1])['illisibles'], 100)
            self.assertEqual(pe.diagnostiquer_page(doc[2])['illisibles'], 0)


class TestEmpreintesGlyphes(unittest.TestCase):

    def test_meme_dessin_dans_deux_sous_ensembles_de_la_police(self):
        # Comic Sans de la p. 2 (sans Unicode) et de la p. 4 : deux sous-ensembles distincts
        # de la même police, encodés différemment ; les lettres communes ont la même empreinte.
        with fitz.open(str(PE052)) as doc:
            polices = {}
            for numero in (1, 3):
                for police in doc[numero].get_fonts():
                    if police[3].endswith('+ComicSansMS'):
                        polices[numero] = pi.empreintes_glyphes(doc.extract_font(police[0])[3])
        communes = set(polices[1].values()) & set(polices[3].values()) - {'', None}
        self.assertGreaterEqual(len(communes), 15)

    def test_police_non_truetype(self):
        self.assertIsNone(pi.empreintes_glyphes(b'%!PS-AdobeFont-1.0'))


class TestPageEnPoliceSansUnicode(unittest.TestCase):

    def test_page_lue_entete_et_pied_decodes(self):
        r = _lire(2)
        self.assertTrue(r['success'], r.get('error'))
        self.assertEqual(r['detection_method'], 'pdf-grille')
        meta = r['metadata']
        self.assertEqual(meta['BORNIER'], 'P313TS')
        self.assertEqual(meta['INDICE'], 'TP2')
        self.assertEqual(meta['PET'], 'PONT SUPERIEUR')
        self.assertEqual(meta['NO_PLAN'], '223111 PE 052')
        self.assertEqual(meta.get('LOGO'), 'SIEMENS')

    def test_corps_lu_tel_quel_dans_la_couche_texte(self):
        lignes = _cellules(_lire(2))
        self.assertEqual(len(lignes), 44)
        self.assertEqual(lignes[0], ['10', '', 'COMMUN TS GR1 313TS', '0098N'])
        self.assertEqual(lignes[9], ['20', '', 'COMMUN TS GR2 313TS', '0077N 0115N 0116N'])
        # Faute de frappe de l'original gardée : le texte n'est pas corrigé.
        self.assertIn(['32', '', 'TS FIN DE SERVIVCE Q1', '0017N'], lignes)
        self.assertEqual(lignes[-1], ['P4', '', 'RESERVE NON CABLEE', ''])

    def test_sans_tesseract_les_lettres_de_la_reference_suffisent(self):
        # P313TS : toutes ses lettres figurent dans le texte lisible de la p. 3.
        r = _lire(2, TESSERACT_TROUVE=False)
        self.assertTrue(r['success'])
        self.assertEqual(r['metadata']['BORNIER'], 'P313TS')
        self.assertFalse(r['a_verifier'])

    def test_lettre_absente_de_la_reference_sans_tesseract_devient_un_point_d_interrogation(self):
        r = _lire(4, TESSERACT_TROUVE=False)
        self.assertTrue(r['success'])
        # Jamais une lettre inventée : « ? », signalé dans A VERIFIER.
        self.assertEqual(r['metadata']['BORNIER'], '?MIC?')
        messages = [a['message'] for a in r['a_verifier']]
        self.assertTrue(any('non reconnu' in m and 'Tesseract introuvable' in m
                            for m in messages), messages)

    @unittest.skipUnless(Config.TESSERACT_TROUVE, "Tesseract absent de ce poste")
    def test_lettre_absente_de_la_reference_lue_par_tesseract(self):
        r = _lire(4)
        self.assertTrue(r['success'])
        self.assertEqual(r['metadata']['BORNIER'], 'QMICF')
        self.assertEqual(r['metadata']['INDICE'], 'TP3')
        self.assertEqual(len(_cellules(r)), 60)

    def test_page_de_garde_toujours_ecartee(self):
        r = _lire(1)
        self.assertFalse(r['success'])
        self.assertIn("pas d'en-tête du modèle", r['error'])

    def test_reglage_desactive_comportement_v18(self):
        r = _lire(2, PDF_DECODER_POLICES_ILLISIBLES=False)
        self.assertFalse(r['success'])

    def test_rien_pour_decoder_motif_explicite(self):
        with patch.object(pi.DecodageDocument, 'REFERENCE_INTERNE', False):
            r = _lire(2, TESSERACT_TROUVE=False)
        self.assertFalse(r['success'])
        self.assertIn('Tesseract introuvable', r['error'])

    def test_page_deja_lisible_inchangee(self):
        r = _lire(3)
        self.assertTrue(r['success'])
        self.assertEqual(r['metadata']['BORNIER'], 'PE')
        self.assertFalse(r['a_verifier'])


class TestRoutageSansAppelApi(unittest.TestCase):

    def setUp(self):
        self._modes = (Config.OCR_MODE, Config.PDF_ROUTAGE_VECTORIEL, Config.TESSERACT_TROUVE)
        Config.OCR_MODE = 'claude'
        Config.PDF_ROUTAGE_VECTORIEL = True
        # Sans Tesseract : la référence interne suffit pour les pages 2 et 3 ; la p. 4 sort
        # avec « ?MIC? » signalé. Aucun moteur vision n'est appelé dans aucun cas.
        Config.TESSERACT_TROUVE = False
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = []

    def tearDown(self):
        Config.OCR_MODE, Config.PDF_ROUTAGE_VECTORIEL, Config.TESSERACT_TROUVE = self._modes
        self._tmp.cleanup()

    def test_pages_lues_en_couche_texte_sans_vision(self):
        conv = Converter(word_file=PE052, output_dir=Path(self._tmp.name) / 'sortie',
                         template=DEFAULT_TEMPLATE, on_log=self.logs.append)
        conv.output_dir.mkdir(parents=True, exist_ok=True)
        with patch.object(Converter, '_activer_log_claude'), \
                patch('claude_ocr.ClaudeVisionExtractor', _vision_interdite):
            results, _ = conv._extraire_pdf_comme_images()
        self.assertEqual([r['detection_method'] for r in results], ['pdf-grille'] * 4)
        self.assertEqual([r['success'] for r in results], [False, True, True, True])
        self.assertEqual([r['metadata'].get('BORNIER') for r in results[1:]],
                         ['P313TS', 'PE', '?MIC?'])
        self.assertTrue(any('Page 2/4 :' in m and 'police sans table Unicode' in m
                            and 'sans appel API' in m for m in self.logs), self.logs)
        self.assertFalse(any('Page 3/4 :' in m and 'police sans table Unicode' in m
                             for m in self.logs))


if __name__ == '__main__':
    unittest.main()
