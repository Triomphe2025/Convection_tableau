"""
Lecture par lot (claude_lot.LecteurLot), sans reseau : la Message Batches API est simulee.
Verifie le custom_id conforme et unique + la table de correspondance enregistree, que chaque
page reussie passe par le chemin unique _traiter_reponse (meme retour, cache ecrit), que les
pages errored / expired / canceled repartent en appel normal (repli_normal), l'arret (lot
annule), l'absence de cle, et la panne reseau a la creation.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_claude_lot.py -v
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import claude_lot
import claude_ocr as co
from config import Config
from template import TemplateManager

REPONSE = (
    "TYPE_PAGE: listing\n"
    "A | B | C | D\n"
    'META: {"PAGE": "1", "BORNIER": "", "PET": "", "NO_PLAN": "", "INDICE": ""}\n'
)


def _message(ident='msg_lot', texte=REPONSE, stop_reason='end_turn'):
    return SimpleNamespace(
        id=ident, content=[SimpleNamespace(type='text', text=texte)],
        stop_reason=stop_reason, model=Config.CLAUDE_OCR_MODEL,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=50,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


def _compteurs(succeeded=0, processing=0, errored=0, expired=0, canceled=0):
    return SimpleNamespace(succeeded=succeeded, processing=processing,
                           errored=errored, expired=expired, canceled=canceled)


class _ErreurReseau(Exception):
    status_code = 529


class FauxBatches:
    """messages.batches simule, piloté par attributs de classe."""

    etats = ['ended']          # statuts rendus par retrieve() successifs
    types = {}                 # index de page -> type non 'succeeded' (errored/expired/canceled)
    create_pannes = 0          # nombre de pannes reseau avant une creation reussie
    requests = []              # requetes passees a create()
    annules = []               # ids passes a cancel()
    _i_etat = 0
    _n_create = 0

    def create(self, requests):
        FauxBatches.requests = list(requests)
        if FauxBatches._n_create < FauxBatches.create_pannes:
            FauxBatches._n_create += 1
            raise _ErreurReseau("panne creation simulee")
        return SimpleNamespace(id='batch_test', processing_status='in_progress',
                               request_counts=_compteurs(processing=len(requests)))

    def retrieve(self, batch_id):
        i = FauxBatches._i_etat
        FauxBatches._i_etat += 1
        statut = FauxBatches.etats[min(i, len(FauxBatches.etats) - 1)]
        return SimpleNamespace(id=batch_id, processing_status=statut,
                               request_counts=_compteurs(succeeded=len(FauxBatches.requests)))

    def results(self, batch_id):
        for idx, req in enumerate(FauxBatches.requests):
            cid = req['custom_id']
            type_ = FauxBatches.types.get(idx, 'succeeded')
            if type_ == 'succeeded':
                res = SimpleNamespace(type='succeeded', message=_message(ident=f'msg_{idx}'))
            else:
                res = SimpleNamespace(type=type_)
            yield SimpleNamespace(custom_id=cid, result=res)

    def cancel(self, batch_id):
        FauxBatches.annules.append(batch_id)


class FauxClientLot:
    def __init__(self, api_key=None, **kw):
        self.messages = SimpleNamespace(batches=FauxBatches())


def _image(dossier, nom):
    chemin = Path(dossier) / nom
    Image.new('RGB', (200, 150), 'white').save(chemin)
    return chemin


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
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache'
        Config.CLAUDE_OCR_MODEL = 'claude-sonnet-5-5'
        Config.CLAUDE_EFFORT = 'medium'
        Config.CLAUDE_API_KEY = 'cle-de-test'
        Config.OCR_MODE = 'claude'
        Config.CLAUDE_RETRY_DELAIS = ()
        Config.CLAUDE_LOT_POLL_SECONDES = 0
        Config.CLAUDE_MODE_LOT = True
        FauxBatches.etats = ['ended']
        FauxBatches.types = {}
        FauxBatches.create_pannes = 0
        FauxBatches.requests = []
        FauxBatches.annules = []
        FauxBatches._i_etat = 0
        FauxBatches._n_create = 0
        self.ex = co.ClaudeVisionExtractor(TemplateManager().get('REPARTITEUR'))
        self.sortie = self.tmp / 'sortie'

    def tearDown(self):
        for n, v in self._sauve.items():
            setattr(Config, n, v)
        self._tmp.cleanup()

    def _lire(self, images, doit_arreter=None):
        lecteur = claude_lot.LecteurLot(self.ex, doit_arreter=doit_arreter, poll_secondes=0)
        with patch('anthropic.Anthropic', FauxClientLot):
            return lecteur.lire(images, self.sortie)


class TestLectureReussie(_Base):

    def test_chaque_page_reussie_via_chemin_unique(self):
        imgs = [_image(self.tmp, 'page_1.png'), _image(self.tmp, 'page_2.png')]
        res = self._lire(imgs)
        for img in imgs:
            r = res[str(img)]
            self.assertTrue(r['success'])
            self.assertEqual(r['detection_method'], 'claude-vision')
            self.assertTrue(r['rows'])
            self.assertFalse(r.get('repli_normal'))

    def test_page_reussie_ecrite_en_cache_relue_sans_appel(self):
        img = _image(self.tmp, 'page_1.png')
        self._lire([img])

        # extract() sur la meme image doit servir le cache : le client ne doit jamais etre appele.
        class _Interdit:
            def __init__(self, *a, **k):
                raise AssertionError("aucun appel attendu : la lecture est en cache")
        with patch('anthropic.Anthropic', _Interdit):
            r = self.ex.extract(img)
        self.assertTrue(r['success'])
        self.assertTrue(r.get('lecture_cache'))


class TestCustomIdEtTable(_Base):

    def test_custom_id_conforme_unique_et_table_enregistree(self):
        import re
        imgs = [_image(self.tmp, 'page.122a.png'), _image(self.tmp, 'page 44B.png'),
                _image(self.tmp, 'page.122a.png'.replace('122a', '123'))]
        self._lire(imgs)
        cids = [r['custom_id'] for r in FauxBatches.requests]
        self.assertEqual(len(cids), len(set(cids)))                 # unicite
        for cid in cids:
            self.assertRegex(cid, r'^[a-zA-Z0-9_-]{1,64}$')         # conforme a l'API

        fichier = self.sortie / 'lot_batch_test.json'
        self.assertTrue(fichier.exists())
        import json
        data = json.loads(fichier.read_text(encoding='utf-8'))
        self.assertEqual(data['id'], 'batch_test')
        self.assertEqual(len(data['pages']), len(imgs))             # une entree par page


class TestRepliAppelNormal(_Base):

    def test_errored_et_expired_repartent_en_appel_normal(self):
        imgs = [_image(self.tmp, f'page_{i}.png') for i in range(3)]
        FauxBatches.types = {1: 'errored', 2: 'expired'}
        res = self._lire(imgs)
        self.assertTrue(res[str(imgs[0])]['success'])
        for i in (1, 2):
            self.assertFalse(res[str(imgs[i])]['success'])
            self.assertTrue(res[str(imgs[i])]['repli_normal'])

    def test_sans_cle_tout_en_repli(self):
        Config.CLAUDE_API_KEY = ''
        imgs = [_image(self.tmp, 'page_1.png')]
        res = self._lire(imgs)
        self.assertTrue(res[str(imgs[0])]['repli_normal'])

    def test_creation_impossible_tout_en_repli(self):
        Config.CLAUDE_RETRY_DELAIS = ()
        FauxBatches.create_pannes = 1          # panne persistante (aucun retry configure)
        imgs = [_image(self.tmp, 'page_1.png')]
        res = self._lire(imgs)
        self.assertTrue(res[str(imgs[0])]['repli_normal'])


class TestArret(_Base):

    def test_arret_annule_le_lot_et_replie(self):
        imgs = [_image(self.tmp, 'page_1.png')]
        res = self._lire(imgs, doit_arreter=lambda: True)
        self.assertEqual(FauxBatches.annules, ['batch_test'])
        self.assertTrue(res[str(imgs[0])]['repli_normal'])


class TestListeVide(_Base):

    def test_aucune_image(self):
        self.assertEqual(self._lire([]), {})


if __name__ == '__main__':
    unittest.main()
