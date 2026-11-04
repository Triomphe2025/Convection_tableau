"""
Branchement du mode lot dans le convertisseur (Converter._lire_en_lot + _extraire_avec_progres),
sans reseau : un faux client sert a la fois messages.create (appel normal) et messages.batches
(lot). Verifie l'exigence centrale : meme document lu en mode normal puis en mode lot, avec les
memes reponses, donne un classeur Excel strictement identique. Verifie aussi que les pages deja
en cache sont retirees du lot (aucun lot si toutes y sont) et qu'une page en erreur dans le lot
est relue en appel normal apres le lot.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_lot_converter.py -v
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import claude_ocr as co
from config import Config
from converter import Converter
from generer_classeur import generer_excel
from template import TemplateManager


def _texte(page: int) -> str:
    """Reponse Claude distincte par page (valeurs et numero de page differents)."""
    return (
        "TYPE_PAGE: listing\n"
        f"A{page} | B{page} | C{page} | D{page}\n"
        f'META: {{"PAGE": "{page}", "BORNIER": "", "PET": "", "NO_PLAN": "", "INDICE": ""}}\n'
    )


def _message(texte: str, ident: str):
    return SimpleNamespace(
        id=ident, content=[SimpleNamespace(type='text', text=texte)],
        stop_reason='end_turn', model=Config.CLAUDE_OCR_MODEL,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=50,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


def _compteurs(succeeded=0, processing=0, errored=0, expired=0, canceled=0):
    return SimpleNamespace(succeeded=succeeded, processing=processing,
                           errored=errored, expired=expired, canceled=canceled)


class FauxUnifie:
    """anthropic.Anthropic simule : messages.create (appel normal) ET messages.batches (lot).

    Les reponses (`textes`, dans l'ordre de page trie) sont partagees : la page i recoit la
    meme reponse par l'un ou l'autre chemin, donc un Excel identique est attendu.
    """

    textes: list = []          # reponse par page, ordre trie
    types: dict = {}           # index de page -> type non 'succeeded' (lot)
    appels_create = 0          # nombre d'appels normaux (create)
    requests: list = []        # requetes passees au lot
    etats = ['ended']
    _i_etat = 0

    class _Batches:
        def create(self, requests):
            FauxUnifie.requests = list(requests)
            return SimpleNamespace(id='batch_x', processing_status='in_progress',
                                   request_counts=_compteurs(processing=len(requests)))

        def retrieve(self, batch_id):
            i = FauxUnifie._i_etat
            FauxUnifie._i_etat += 1
            statut = FauxUnifie.etats[min(i, len(FauxUnifie.etats) - 1)]
            return SimpleNamespace(
                id=batch_id, processing_status=statut,
                request_counts=_compteurs(succeeded=len(FauxUnifie.requests)))

        def results(self, batch_id):
            for idx, req in enumerate(FauxUnifie.requests):
                type_ = FauxUnifie.types.get(idx, 'succeeded')
                if type_ == 'succeeded':
                    res = SimpleNamespace(
                        type='succeeded', message=_message(FauxUnifie.textes[idx], f'lot_{idx}'))
                else:
                    res = SimpleNamespace(type=type_)
                yield SimpleNamespace(custom_id=req['custom_id'], result=res)

        def cancel(self, batch_id):
            pass

    def __init__(self, api_key=None, **kw):
        self.messages = SimpleNamespace(
            create=self._create, stream=self._stream, batches=FauxUnifie._Batches())

    def _create(self, **kw):
        i = FauxUnifie.appels_create
        FauxUnifie.appels_create += 1
        texte = FauxUnifie.textes[i] if i < len(FauxUnifie.textes) else FauxUnifie.textes[-1]
        return _message(texte, f'api_{i}')

    def _stream(self, **kw):
        raise AssertionError("pas de streaming dans ces tests")


def _cellules(path: Path) -> dict:
    """Valeurs de toutes les cellules de toutes les feuilles d'un classeur."""
    from openpyxl import load_workbook
    wb = load_workbook(path)
    return {ws.title: [[c.value for c in row] for row in ws.iter_rows()]
            for ws in wb.worksheets}


class _Base(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        noms = ('CLAUDE_CACHE_LECTURES', 'CLAUDE_FORCER_RELECTURE', 'CLAUDE_CACHE_DOSSIER',
                'CLAUDE_OCR_MODEL', 'CLAUDE_EFFORT', 'CLAUDE_THINKING', 'CLAUDE_API_KEY',
                'OCR_MODE', 'CLAUDE_RETRY_DELAIS', 'CLAUDE_LOT_POLL_SECONDES', 'CLAUDE_MODE_LOT')
        self._sauve = {n: getattr(Config, n) for n in noms}
        Config.CLAUDE_CACHE_LECTURES = True
        Config.CLAUDE_FORCER_RELECTURE = False
        Config.CLAUDE_OCR_MODEL = 'claude-sonnet-5-5'
        Config.CLAUDE_EFFORT = 'medium'
        Config.CLAUDE_API_KEY = 'cle-de-test'
        Config.OCR_MODE = 'claude'
        Config.CLAUDE_RETRY_DELAIS = ()
        Config.CLAUDE_LOT_POLL_SECONDES = 0
        FauxUnifie.textes = [_texte(1), _texte(2), _texte(3)]
        FauxUnifie.types = {}
        FauxUnifie.appels_create = 0
        FauxUnifie.requests = []
        FauxUnifie.etats = ['ended']
        FauxUnifie._i_etat = 0
        self.template = TemplateManager().get('REPARTITEUR')

    def tearDown(self):
        for n, v in self._sauve.items():
            setattr(Config, n, v)
        self._tmp.cleanup()

    def _images(self, n=3) -> Path:
        d = self.tmp / 'images'
        d.mkdir(exist_ok=True)
        for k in range(1, n + 1):
            Image.new('RGB', (200, 150), (k * 40, k * 10, 0)).save(d / f'page_{k}.png')
        return d

    def _raz_client(self):
        FauxUnifie.appels_create = 0
        FauxUnifie.requests = []
        FauxUnifie._i_etat = 0

    def _convertir(self, images_dir: Path, nom: str, mode_lot: bool):
        """Lit le dossier d'images et genere l'Excel ; rend (results, chemin_excel)."""
        Config.CLAUDE_MODE_LOT = mode_lot
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / f'cache_{nom}'
        self._raz_client()
        conv = Converter(word_file=images_dir, output_dir=self.tmp / f'out_{nom}',
                         template=self.template, on_log=lambda m: None)
        with patch('anthropic.Anthropic', FauxUnifie):
            results, extractor = conv._extraire_avec_progres(images_dir, 0)
        excel = self.tmp / f'{nom}.xlsx'
        generer_excel(results, extractor, excel, on_log=lambda m: None)
        return results, excel


class TestExcelIdentique(_Base):

    def test_normal_et_lot_memes_reponses_excel_strictement_identique(self):
        images = self._images(3)
        res_normal, excel_normal = self._convertir(images, 'normal', mode_lot=False)
        res_lot, excel_lot = self._convertir(images, 'lot', mode_lot=True)

        # Le lot a bien ete emprunte (3 pages en un envoi, aucun appel normal).
        self.assertEqual(len(FauxUnifie.requests), 3)
        self.assertEqual(FauxUnifie.appels_create, 0)

        # Memes lignes, metadonnees et methode page par page.
        self.assertEqual([r['rows'] for r in res_lot], [r['rows'] for r in res_normal])
        self.assertEqual([r.get('metadata') for r in res_lot],
                         [r.get('metadata') for r in res_normal])
        self.assertEqual([r.get('detection_method') for r in res_lot],
                         [r.get('detection_method') for r in res_normal])

        # Classeur Excel strictement identique (toutes les feuilles, toutes les cellules).
        self.assertEqual(_cellules(excel_lot), _cellules(excel_normal))


class TestCacheRetireDuLot(_Base):

    def test_page_en_cache_retiree_du_lot(self):
        images = self._images(3)
        Config.CLAUDE_MODE_LOT = True
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache'
        # Pre-remplir le cache de la page 1 par une lecture normale.
        ex = co.ClaudeVisionExtractor(self.template)
        self._raz_client()
        with patch('anthropic.Anthropic', FauxUnifie):
            ex.extract(images / 'page_1.png')

        self._raz_client()
        conv = Converter(word_file=images, output_dir=self.tmp / 'out',
                         template=self.template, on_log=lambda m: None)
        with patch('anthropic.Anthropic', FauxUnifie):
            results, _ = conv._extraire_avec_progres(images, 0)

        # Seules les pages 2 et 3 partent en lot ; la page 1 vient du cache.
        self.assertEqual(len(FauxUnifie.requests), 2)
        self.assertTrue(results[0].get('lecture_cache'))
        self.assertTrue(all(r['success'] for r in results))

    def test_toutes_en_cache_aucun_lot(self):
        images = self._images(2)
        Config.CLAUDE_MODE_LOT = True
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache'
        ex = co.ClaudeVisionExtractor(self.template)
        self._raz_client()
        with patch('anthropic.Anthropic', FauxUnifie):
            ex.extract(images / 'page_1.png')
            ex.extract(images / 'page_2.png')

        self._raz_client()
        conv = Converter(word_file=images, output_dir=self.tmp / 'out',
                         template=self.template, on_log=lambda m: None)
        with patch('anthropic.Anthropic', FauxUnifie):
            results, _ = conv._extraire_avec_progres(images, 0)

        # Aucun lot cree (requests reste vide) et aucun fichier lot_*.json ecrit.
        self.assertEqual(FauxUnifie.requests, [])
        self.assertEqual(list((self.tmp / 'out').glob('lot_*.json')), [])
        self.assertTrue(all(r.get('lecture_cache') for r in results))


class TestRepliAppelNormalApresLot(_Base):

    def test_page_erronee_dans_le_lot_relue_en_appel_normal(self):
        images = self._images(3)
        Config.CLAUDE_MODE_LOT = True
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache'
        FauxUnifie.types = {1: 'errored'}      # page 2 en erreur dans le lot
        self._raz_client()
        conv = Converter(word_file=images, output_dir=self.tmp / 'out',
                         template=self.template, on_log=lambda m: None)
        with patch('anthropic.Anthropic', FauxUnifie):
            results, _ = conv._extraire_avec_progres(images, 0)

        # La page 2 a ete relue en UN appel normal apres le lot ; les 3 pages reussissent.
        self.assertEqual(FauxUnifie.appels_create, 1)
        self.assertTrue(all(r['success'] for r in results))
        self.assertFalse(any(r.get('repli_normal') for r in results))


if __name__ == '__main__':
    unittest.main()
