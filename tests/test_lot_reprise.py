"""
Reprise d'un lot (claude_lot.LecteurLot.reprendre) depuis lot_<id>.json, sans reseau.

Trois cas demandes :
  - lot termine        -> resultats recuperes (pages reussies par le chemin unique) ;
  - lot encore en cours -> l'attente reprend puis les resultats sont recuperes ;
  - lot expire / annule -> les pages manquantes repartent en appel normal (repli_normal).
Plus un cas de robustesse : lot introuvable cote serveur (retrieve en echec) -> repli.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_lot_reprise.py -v
"""
import json
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


def _message(ident='msg_reprise'):
    return SimpleNamespace(
        id=ident, content=[SimpleNamespace(type='text', text=REPONSE)],
        stop_reason='end_turn', model=Config.CLAUDE_OCR_MODEL,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=50,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


def _compteurs(**kw):
    base = dict(succeeded=0, processing=0, errored=0, expired=0, canceled=0)
    base.update(kw)
    return SimpleNamespace(**base)


class _ErreurReseau(Exception):
    status_code = 529


class FauxBatchesReprise:
    """messages.batches simule pour la reprise : results() pilote par les custom_id du fichier."""

    etats = ['ended']          # statuts rendus par retrieve() successifs
    retrieve_pannes = 0        # pannes reseau persistantes sur retrieve (lot introuvable)
    resultats = {}             # custom_id -> type (succeeded / expired / canceled / errored)
    annules = []               # ids passes a cancel()
    creees = []                # requetes passees a create() : doit rester vide en reprise
    _i_etat = 0

    def create(self, requests):
        FauxBatchesReprise.creees = list(requests)
        raise AssertionError("la reprise ne doit jamais creer de nouveau lot")

    def retrieve(self, batch_id):
        if FauxBatchesReprise.retrieve_pannes:
            raise _ErreurReseau("lot introuvable")
        i = FauxBatchesReprise._i_etat
        FauxBatchesReprise._i_etat += 1
        statut = FauxBatchesReprise.etats[min(i, len(FauxBatchesReprise.etats) - 1)]
        return SimpleNamespace(id=batch_id, processing_status=statut,
                               request_counts=_compteurs(processing=1))

    def results(self, batch_id):
        for cid, type_ in FauxBatchesReprise.resultats.items():
            if type_ == 'succeeded':
                yield SimpleNamespace(custom_id=cid,
                                      result=SimpleNamespace(type='succeeded',
                                                             message=_message(ident=f'msg_{cid}')))
            else:
                yield SimpleNamespace(custom_id=cid, result=SimpleNamespace(type=type_))

    def cancel(self, batch_id):
        FauxBatchesReprise.annules.append(batch_id)


class FauxClientReprise:
    def __init__(self, api_key=None, **kw):
        self.messages = SimpleNamespace(batches=FauxBatchesReprise())


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
        FauxBatchesReprise.etats = ['ended']
        FauxBatchesReprise.retrieve_pannes = 0
        FauxBatchesReprise.resultats = {}
        FauxBatchesReprise.annules = []
        FauxBatchesReprise.creees = []
        FauxBatchesReprise._i_etat = 0
        self.ex = co.ClaudeVisionExtractor(TemplateManager().get('REPARTITEUR'))
        self.sortie = self.tmp / 'sortie'
        self.sortie.mkdir()

    def tearDown(self):
        for n, v in self._sauve.items():
            setattr(Config, n, v)
        self._tmp.cleanup()

    def _ecrire_lot(self, images, batch_id='batch_repris'):
        """Ecrit un lot_<id>.json comme le ferait un envoi, custom_id = rang de page."""
        pages = {f'p{idx:05d}': str(img) for idx, img in enumerate(images)}
        fichier = self.sortie / f'lot_{batch_id}.json'
        fichier.write_text(json.dumps(
            {'id': batch_id, 'modele': Config.CLAUDE_OCR_MODEL,
             'date': '2026-11-04T00:00:00', 'pages': pages},
            ensure_ascii=False, indent=2), encoding='utf-8')
        return fichier, pages

    def _reprendre(self, fichier, journal=None):
        on_log = (lambda m, niveau='info': journal.append(m)) if journal is not None else None
        lecteur = claude_lot.LecteurLot(self.ex, on_log=on_log, poll_secondes=0)
        with patch('anthropic.Anthropic', FauxClientReprise):
            return lecteur.reprendre(fichier)


class TestLotTermine(_Base):

    def test_resultats_recuperes_sans_nouveau_lot(self):
        imgs = [_image(self.tmp, 'page_1.png'), _image(self.tmp, 'page_2.png')]
        fichier, pages = self._ecrire_lot(imgs)
        FauxBatchesReprise.etats = ['ended']
        FauxBatchesReprise.resultats = {cid: 'succeeded' for cid in pages}
        res = self._reprendre(fichier)
        for img in imgs:
            r = res[str(img)]
            self.assertTrue(r['success'])
            self.assertEqual(r['detection_method'], 'claude-vision')
            self.assertFalse(r.get('repli_normal'))
        self.assertEqual(FauxBatchesReprise.creees, [])            # jamais de nouveau lot


class TestLotEnCours(_Base):

    def test_attente_reprise_puis_resultats(self):
        imgs = [_image(self.tmp, 'page_1.png')]
        fichier, pages = self._ecrire_lot(imgs)
        # retrieve : en cours a la reprise, puis termine au sondage suivant.
        FauxBatchesReprise.etats = ['in_progress', 'ended']
        FauxBatchesReprise.resultats = {cid: 'succeeded' for cid in pages}
        journal = []
        res = self._reprendre(fichier, journal=journal)
        self.assertTrue(res[str(imgs[0])]['success'])
        self.assertTrue(any('encore en cours' in m for m in journal))


class TestLotExpireOuAnnule(_Base):

    def test_pages_expirees_repartent_en_appel_normal(self):
        imgs = [_image(self.tmp, 'page_1.png'), _image(self.tmp, 'page_2.png')]
        fichier, pages = self._ecrire_lot(imgs)
        cids = list(pages)
        FauxBatchesReprise.etats = ['ended']
        # Une page lue, une page expiree : l'expiree repart en appel normal.
        FauxBatchesReprise.resultats = {cids[0]: 'succeeded', cids[1]: 'expired'}
        res = self._reprendre(fichier)
        self.assertTrue(res[str(imgs[0])]['success'])
        self.assertFalse(res[str(imgs[1])]['success'])
        self.assertTrue(res[str(imgs[1])]['repli_normal'])

    def test_pages_annulees_repartent_en_appel_normal(self):
        imgs = [_image(self.tmp, 'page_1.png')]
        fichier, pages = self._ecrire_lot(imgs)
        FauxBatchesReprise.etats = ['ended']
        FauxBatchesReprise.resultats = {cid: 'canceled' for cid in pages}
        res = self._reprendre(fichier)
        self.assertTrue(res[str(imgs[0])]['repli_normal'])


class TestLotIntrouvable(_Base):

    def test_retrieve_en_echec_tout_en_repli(self):
        imgs = [_image(self.tmp, 'page_1.png')]
        fichier, _ = self._ecrire_lot(imgs)
        FauxBatchesReprise.retrieve_pannes = 1          # lot purge / supprime cote serveur
        res = self._reprendre(fichier)
        self.assertTrue(res[str(imgs[0])]['repli_normal'])


class TestFichierLot(_Base):

    def test_fichier_absent_rien_a_reprendre(self):
        res = self._reprendre(self.sortie / 'lot_inexistant.json')
        self.assertEqual(res, {})

    def test_fichier_sans_pages_rien_a_reprendre(self):
        fichier = self.sortie / 'lot_vide.json'
        fichier.write_text(json.dumps({'id': 'x', 'pages': {}}), encoding='utf-8')
        self.assertEqual(self._reprendre(fichier), {})

    def test_sans_cle_tout_en_repli(self):
        Config.CLAUDE_API_KEY = ''
        imgs = [_image(self.tmp, 'page_1.png')]
        fichier, _ = self._ecrire_lot(imgs)
        res = self._reprendre(fichier)
        self.assertTrue(res[str(imgs[0])]['repli_normal'])


if __name__ == '__main__':
    unittest.main()
