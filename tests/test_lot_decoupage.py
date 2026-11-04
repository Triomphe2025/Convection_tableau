"""
Correctif du mode lot (claude_lot) : decoupage par taille, creation de tous les lots avant la
recuperation, arret pendant les relances, pas de doublon apres un delai depasse (sans reprendre
un autre lot du meme document). Sans reseau (Message Batches API simulee).

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_lot_decoupage.py -v
"""
import datetime
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


def _message(ident='msg'):
    return SimpleNamespace(
        id=ident, content=[SimpleNamespace(type='text', text=REPONSE)],
        stop_reason='end_turn', model=Config.CLAUDE_OCR_MODEL,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=50,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


def _compteurs(succeeded=0, processing=0, errored=0, expired=0, canceled=0):
    return SimpleNamespace(succeeded=succeeded, processing=processing,
                           errored=errored, expired=expired, canceled=canceled)


class _ErreurReseau(Exception):
    status_code = 529


class APITimeoutError(Exception):
    """Nom reconnu par claude_ocr._erreur_reseau : delai d'envoi depasse."""


class FauxBatchesTaille:
    """messages.batches simule : create peut lever, list rend d'eventuels lots recents.

    Les resultats sont rendus PAR LOT (requetes_par_lot) : le correctif cree tous les lots
    avant de recuperer, donc results() ne peut pas se fier au dernier create. `ordre` trace la
    suite des appels pour verifier que tous les create precedent le premier results.
    """

    exceptions_create: list = []   # exception (ou None) levee au i-eme create
    lots_recents: list = []        # lots supplementaires rendus par list() (doublon cote serveur)
    requetes_par_lot: dict = {}    # batch_id -> requetes (resultats propres a chaque lot)
    derniere_requete: list = []    # requetes du dernier create meme s'il a leve (doublon serveur)
    cids_reprise: list = []        # custom_id rendus par results() en reprise (sans create)
    n_create = 0
    ordre: list = []               # 'create' / 'results' dans l'ordre d'appel

    def create(self, requests):
        FauxBatchesTaille.ordre.append('create')
        FauxBatchesTaille.derniere_requete = list(requests)
        i = FauxBatchesTaille.n_create
        FauxBatchesTaille.n_create += 1
        exc = (FauxBatchesTaille.exceptions_create[i]
               if i < len(FauxBatchesTaille.exceptions_create) else None)
        if exc is not None:
            raise exc
        bid = f'batch_{i}'
        FauxBatchesTaille.requetes_par_lot[bid] = list(requests)
        return SimpleNamespace(
            id=bid, processing_status='ended',
            created_at=datetime.datetime.now(datetime.timezone.utc),
            request_counts=_compteurs(succeeded=len(requests)))

    def retrieve(self, batch_id):
        n = len(FauxBatchesTaille.requetes_par_lot.get(batch_id, []))
        return SimpleNamespace(id=batch_id, processing_status='ended',
                               request_counts=_compteurs(succeeded=n))

    def results(self, batch_id):
        FauxBatchesTaille.ordre.append('results')
        reqs = FauxBatchesTaille.requetes_par_lot.get(batch_id)
        if reqs is None:
            # Doublon repris (create a leve) : requetes du dernier envoi ; sinon reprise disque.
            reqs = (FauxBatchesTaille.derniere_requete
                    or [{'custom_id': c} for c in FauxBatchesTaille.cids_reprise])
        for req in reqs:
            yield SimpleNamespace(
                custom_id=req['custom_id'],
                result=SimpleNamespace(type='succeeded', message=_message(req['custom_id'])))

    def list(self, limit=20):
        crees = [SimpleNamespace(
            id=bid, processing_status='ended',
            created_at=datetime.datetime.now(datetime.timezone.utc),
            request_counts=_compteurs(succeeded=len(reqs)))
            for bid, reqs in FauxBatchesTaille.requetes_par_lot.items()]
        return SimpleNamespace(data=crees + list(FauxBatchesTaille.lots_recents))

    def cancel(self, batch_id):
        pass


class FauxClientTaille:
    def __init__(self, api_key=None, **kw):
        self.messages = SimpleNamespace(batches=FauxBatchesTaille())


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
                'OCR_MODE', 'CLAUDE_RETRY_DELAIS', 'CLAUDE_LOT_POLL_SECONDES', 'CLAUDE_MODE_LOT',
                'CLAUDE_LOT_TAILLE_MAX_MO', 'CLAUDE_LOT_FENETRE_DOUBLON_MIN')
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
        FauxBatchesTaille.exceptions_create = []
        FauxBatchesTaille.lots_recents = []
        FauxBatchesTaille.requetes_par_lot = {}
        FauxBatchesTaille.derniere_requete = []
        FauxBatchesTaille.cids_reprise = []
        FauxBatchesTaille.n_create = 0
        FauxBatchesTaille.ordre = []
        self.ex = co.ClaudeVisionExtractor(TemplateManager().get('REPARTITEUR'))
        self.sortie = self.tmp / 'sortie'

    def tearDown(self):
        for n, v in self._sauve.items():
            setattr(Config, n, v)
        self._tmp.cleanup()

    def _lire(self, images, doit_arreter=None):
        lecteur = claude_lot.LecteurLot(self.ex, doit_arreter=doit_arreter, poll_secondes=0)
        with patch('anthropic.Anthropic', FauxClientTaille):
            return lecteur.lire(images, self.sortie)


class TestDecoupageUnitaire(_Base):

    def test_decouper_groupe_par_taille(self):
        # Plafond = 70 octets : [30,30] tiennent ensemble, 30 puis 80 (page seule trop grosse).
        Config.CLAUDE_LOT_TAILLE_MAX_MO = 70 / (1024 * 1024)
        infos = [{'nom': 'a', 'taille': 30}, {'nom': 'b', 'taille': 30},
                 {'nom': 'c', 'taille': 30}, {'nom': 'd', 'taille': 80}]
        lecteur = claude_lot.LecteurLot(self.ex)
        lots = lecteur._decouper(infos)
        noms = [[i['nom'] for i in lot] for lot in lots]
        self.assertEqual(noms, [['a', 'b'], ['c'], ['d']])

    def test_decouper_un_seul_lot_sous_le_plafond(self):
        Config.CLAUDE_LOT_TAILLE_MAX_MO = 50
        infos = [{'nom': 'a', 'taille': 30}, {'nom': 'b', 'taille': 30}]
        lots = claude_lot.LecteurLot(self.ex)._decouper(infos)
        self.assertEqual(len(lots), 1)
        self.assertEqual([i['nom'] for i in lots[0]], ['a', 'b'])


class TestDecoupageIntegration(_Base):

    def test_un_lot_par_page_quand_plafond_minuscule(self):
        Config.CLAUDE_LOT_TAILLE_MAX_MO = 0          # chaque page part dans son propre lot
        imgs = [_image(self.tmp, f'page_{i}.png') for i in range(3)]
        res = self._lire(imgs)
        self.assertEqual(FauxBatchesTaille.n_create, 3)          # trois envois distincts
        self.assertEqual(len(list(self.sortie.glob('lot_*.json'))), 3)
        for img in imgs:
            self.assertTrue(res[str(img)]['success'])

    def test_tous_les_lots_crees_avant_la_premiere_recuperation(self):
        # Correction 2 : les 3 lots partent d'abord, on ne recupere qu'ensuite.
        Config.CLAUDE_LOT_TAILLE_MAX_MO = 0
        imgs = [_image(self.tmp, f'page_{i}.png') for i in range(3)]
        self._lire(imgs)
        premier_results = FauxBatchesTaille.ordre.index('results')
        avant = FauxBatchesTaille.ordre[:premier_results]
        self.assertEqual(avant.count('create'), 3)               # 3 create avant tout results

    def test_toutes_les_pages_dans_un_lot_par_defaut(self):
        Config.CLAUDE_LOT_TAILLE_MAX_MO = 50
        imgs = [_image(self.tmp, f'page_{i}.png') for i in range(3)]
        res = self._lire(imgs)
        self.assertEqual(FauxBatchesTaille.n_create, 1)          # un seul envoi
        self.assertEqual(len(FauxBatchesTaille.requetes_par_lot['batch_0']), 3)
        self.assertTrue(all(res[str(img)]['success'] for img in imgs))


class TestArretPendantRelances(_Base):

    def test_arret_coupe_les_relances_et_replie(self):
        # create echoue (reseau) et l'utilisateur demande l'arret : les pauses s'arretent net.
        Config.CLAUDE_RETRY_DELAIS = (1, 1, 1)
        FauxBatchesTaille.exceptions_create = [_ErreurReseau() for _ in range(5)]
        imgs = [_image(self.tmp, 'page_0.png')]
        res = self._lire(imgs, doit_arreter=lambda: True)
        self.assertTrue(res[str(imgs[0])]['repli_normal'])
        self.assertEqual(FauxBatchesTaille.n_create, 1)          # une tentative, pas de boucle


class TestPasDeDoublon(_Base):

    def test_delai_depasse_reprend_le_lot_existant(self):
        # L'envoi leve APITimeoutError mais a abouti cote serveur : un lot recent du meme
        # nombre de requetes existe -> il est repris, aucun second create n'est emis.
        Config.CLAUDE_RETRY_DELAIS = (1,)
        FauxBatchesTaille.exceptions_create = [APITimeoutError("delai depasse")]
        FauxBatchesTaille.lots_recents = [SimpleNamespace(
            id='batch_serveur', processing_status='ended',
            created_at=datetime.datetime.now(datetime.timezone.utc),
            request_counts=_compteurs(succeeded=1))]
        imgs = [_image(self.tmp, 'page_0.png')]
        res = self._lire(imgs)
        self.assertEqual(FauxBatchesTaille.n_create, 1)          # pas de doublon cree
        self.assertTrue(res[str(imgs[0])]['success'])
        self.assertTrue((self.sortie / 'lot_batch_serveur.json').exists())

    def test_aucun_lot_recent_du_bon_nombre_reste_en_echec(self):
        # Delai depasse sans retry et aucun lot correspondant : la page part en repli.
        Config.CLAUDE_RETRY_DELAIS = ()
        FauxBatchesTaille.exceptions_create = [APITimeoutError("delai depasse")]
        FauxBatchesTaille.lots_recents = [SimpleNamespace(
            id='autre', processing_status='ended',
            created_at=datetime.datetime.now(datetime.timezone.utc),
            request_counts=_compteurs(succeeded=9))]       # nombre different -> pas un doublon
        imgs = [_image(self.tmp, 'page_0.png')]
        res = self._lire(imgs)
        self.assertTrue(res[str(imgs[0])]['repli_normal'])

    def test_un_autre_lot_du_meme_nombre_nest_pas_repris(self):
        # Deux lots d'une page (meme nombre). Le 2e create leve APITimeoutError : le lot 1,
        # pourtant du meme nombre de pages, NE doit PAS etre repris comme lot 2 (son id est
        # deja connu). Le lot 2 part en repli, le lot 1 reste intact et reussit.
        Config.CLAUDE_LOT_TAILLE_MAX_MO = 0                      # une page par lot
        Config.CLAUDE_RETRY_DELAIS = ()
        FauxBatchesTaille.exceptions_create = [None, APITimeoutError("delai depasse")]
        imgs = [_image(self.tmp, f'page_{i}.png') for i in range(2)]
        res = self._lire(imgs)
        self.assertEqual(FauxBatchesTaille.n_create, 2)          # 1 cree + 1 tentative echouee
        self.assertTrue(res[str(imgs[0])]['success'])            # lot 1 lu normalement
        self.assertTrue(res[str(imgs[1])]['repli_normal'])       # lot 2 en repli, pas un doublon
        fichiers = sorted(f.name for f in self.sortie.glob('lot_*.json'))
        self.assertEqual(fichiers, ['lot_batch_0.json'])         # le lot 1 n'est pas ecrase


class TestRepriseDossierMultiLot(_Base):

    def test_reprise_dun_dossier_reprend_chaque_lot(self):
        import json
        self.sortie.mkdir(parents=True, exist_ok=True)
        imgs = [_image(self.tmp, f'page_{i}.png') for i in range(2)]
        # Deux fichiers de lot, une page chacun (document decoupe en deux lots).
        for n, img in enumerate(imgs):
            (self.sortie / f'lot_b{n}.json').write_text(json.dumps(
                {'id': f'b{n}', 'modele': Config.CLAUDE_OCR_MODEL, 'date': '2026-11-04',
                 'pages': {f'p{n:05d}': str(img)}}, ensure_ascii=False), encoding='utf-8')
        FauxBatchesTaille.cids_reprise = ['p00000', 'p00001']
        lecteur = claude_lot.LecteurLot(self.ex, poll_secondes=0)
        with patch('anthropic.Anthropic', FauxClientTaille):
            res = lecteur.reprendre(self.sortie)      # un dossier, pas un fichier
        for img in imgs:
            self.assertTrue(res[str(img)]['success'])


if __name__ == '__main__':
    unittest.main()
