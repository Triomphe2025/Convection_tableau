"""
Reprise automatique du mode lot à la relance (phase 1a, étape 4), sans réseau.

Conditions vérifiées :
  1. même dossier avec les lots de deux documents → seul le bon (empreinte + modèle) est repris ;
  2. relance pendant qu'un lot tourne → aucune page renvoyée (pas de double facturation) ;
  3. lot terminé → marqué « termine » et plus jamais repris ;
  4. lot expiré → pages relues normalement (repli) ;
  5. anti-doublon : heure_debut prise au début de chaque lot (_creer) ;
  6. ancien fichier sans empreinte → non repris automatiquement (journal) ;
  7. événements lot_etat / lot_recupere émis aussi pendant une reprise.

    env\\Scripts\\python.exe -m pytest tests/test_lot_reprise_auto.py -v
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
import evenements as ev
from config import Config
from template import TemplateManager

REPONSE = (
    "TYPE_PAGE: listing\n"
    "A | B | C | D\n"
    'META: {"PAGE": "1", "BORNIER": "", "PET": "", "NO_PLAN": "", "INDICE": ""}\n'
)


def _message(ident='m'):
    return SimpleNamespace(
        id=ident, content=[SimpleNamespace(type='text', text=REPONSE)],
        stop_reason='end_turn', model=Config.CLAUDE_OCR_MODEL,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=50,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0))


def _compteurs(**kw):
    base = dict(succeeded=0, processing=0, errored=0, expired=0, canceled=0)
    base.update(kw)
    return SimpleNamespace(**base)


class _ErreurReseau(Exception):
    status_code = 529


class Faux:
    lots = {}              # batch_id -> {'etats': [...], 'results': {cid: type}}
    create_raise = False
    create_calls = []
    results_calls = []
    retrieve_calls = []
    _i = {}

    class B:
        def create(self, requests):
            Faux.create_calls.append(list(requests))
            if Faux.create_raise:
                raise _ErreurReseau("create KO")
            bid = f'new{len(Faux.create_calls)}'
            Faux.lots[bid] = {'etats': ['ended'],
                              'results': {r['custom_id']: 'succeeded' for r in requests}}
            return SimpleNamespace(id=bid, processing_status='in_progress',
                                   request_counts=_compteurs(processing=len(requests)))

        def retrieve(self, batch_id):
            Faux.retrieve_calls.append(batch_id)
            i = Faux._i.get(batch_id, 0)
            Faux._i[batch_id] = i + 1
            etats = Faux.lots.get(batch_id, {}).get('etats', ['ended'])
            statut = etats[min(i, len(etats) - 1)]
            res = Faux.lots.get(batch_id, {}).get('results', {})
            succ = sum(1 for t in res.values() if t == 'succeeded')
            return SimpleNamespace(id=batch_id, processing_status=statut,
                                   request_counts=_compteurs(succeeded=succ))

        def results(self, batch_id):
            Faux.results_calls.append(batch_id)
            for cid, type_ in Faux.lots.get(batch_id, {}).get('results', {}).items():
                if type_ == 'succeeded':
                    yield SimpleNamespace(custom_id=cid, result=SimpleNamespace(
                        type='succeeded', message=_message(f'm_{cid}')))
                else:
                    yield SimpleNamespace(custom_id=cid, result=SimpleNamespace(type=type_))

        def cancel(self, batch_id):
            pass

        def list(self, limit=20):
            return SimpleNamespace(data=[])

    def __init__(self, api_key=None, **kw):
        self.messages = SimpleNamespace(create=self._create, batches=Faux.B())

    def _create(self, **kw):
        raise AssertionError("pas d'appel normal dans ces tests de lot")


def _image(dossier, nom):
    chemin = Path(dossier) / nom
    Image.new('RGB', (160, 120), 'white').save(chemin)
    return chemin


class _Base(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        noms = ('CLAUDE_CACHE_LECTURES', 'CLAUDE_FORCER_RELECTURE', 'CLAUDE_CACHE_DOSSIER',
                'CLAUDE_OCR_MODEL', 'CLAUDE_EFFORT', 'CLAUDE_THINKING', 'CLAUDE_API_KEY',
                'OCR_MODE', 'CLAUDE_RETRY_DELAIS', 'CLAUDE_LOT_POLL_SECONDES',
                'CLAUDE_LOT_TAILLE_MAX_MO')
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
        Faux.lots = {}
        Faux.create_raise = False
        Faux.create_calls = []
        Faux.results_calls = []
        Faux.retrieve_calls = []
        Faux._i = {}
        self.ex = co.ClaudeVisionExtractor(TemplateManager().get('REPARTITEUR'))
        self.sortie = self.tmp / 'sortie'
        self.sortie.mkdir()

    def tearDown(self):
        for n, v in self._sauve.items():
            setattr(Config, n, v)
        self._tmp.cleanup()

    def _ecrire_lot(self, bid, pages, empreinte, modele=None, termine=False, resultats=None):
        cids = {f'p{idx:05d}': str(p) for idx, p in enumerate(pages)}
        donnees = {'id': bid, 'modele': modele or Config.CLAUDE_OCR_MODEL,
                   'empreinte': empreinte, 'profil': {}, 'date': '2026-11-10T00:00:00',
                   'pages': cids}
        if empreinte is None:
            del donnees['empreinte']
        if termine:
            donnees['termine'] = True
        (self.sortie / f'lot_{bid}.json').write_text(json.dumps(donnees), encoding='utf-8')
        Faux.lots[bid] = {'etats': ['ended'],
                          'results': resultats or {cid: 'succeeded' for cid in cids}}
        return cids

    def _lecteur(self, journal=None, collecteur=None):
        on_log = (lambda m, niveau='info': journal.append(m)) if journal is not None else None
        return claude_lot.LecteurLot(self.ex, on_log=on_log, poll_secondes=0,
                                     on_evenement=collecteur)


class TestDeuxDocuments(_Base):

    def test_seul_le_bon_document_est_repris(self):
        img_a = _image(self.tmp, 'docA_p1.png')
        img_b = _image(self.tmp, 'docB_p1.png')
        self._ecrire_lot('A', [img_a], empreinte='EMP_A')
        self._ecrire_lot('B', [img_b], empreinte='EMP_B')
        journal = []
        lecteur = self._lecteur(journal=journal)
        with patch('anthropic.Anthropic', Faux):
            res = lecteur.lire([img_a], self.sortie, empreinte='EMP_A')
        self.assertTrue(res[str(img_a)]['success'])
        self.assertEqual(Faux.create_calls, [])             # aucune page renvoyée
        self.assertNotIn('B', Faux.results_calls)           # lot B jamais touché
        self.assertTrue(any('autre document' in m for m in journal))


class TestRelancePendantLotEnCours(_Base):

    def test_aucune_page_renvoyee(self):
        img1 = _image(self.tmp, 'p1.png')
        img2 = _image(self.tmp, 'p2.png')
        self._ecrire_lot('A', [img1, img2], empreinte='EMP')
        Faux.lots['A']['etats'] = ['in_progress', 'ended']   # tourne encore à la relance
        lecteur = self._lecteur()
        with patch('anthropic.Anthropic', Faux):
            res = lecteur.lire([img1, img2], self.sortie, empreinte='EMP')
        self.assertTrue(res[str(img1)]['success'])
        self.assertTrue(res[str(img2)]['success'])
        self.assertEqual(Faux.create_calls, [])             # pas de double facturation


class TestLotTermineMarque(_Base):

    def test_marque_termine_puis_plus_repris(self):
        img1 = _image(self.tmp, 'p1.png')
        self._ecrire_lot('A', [img1], empreinte='EMP')
        lecteur = self._lecteur()
        with patch('anthropic.Anthropic', Faux):
            lecteur.lire([img1], self.sortie, empreinte='EMP')
        donnees = json.loads((self.sortie / 'lot_A.json').read_text(encoding='utf-8'))
        self.assertTrue(donnees.get('termine'))
        # 2e relance : le lot marqué « termine » n'est plus repris.
        Faux.retrieve_calls = []
        Faux.results_calls = []
        with patch('anthropic.Anthropic', Faux):
            res2 = lecteur._reprendre_lots_du_dossier(self.sortie, 'EMP',
                                                      Config.CLAUDE_OCR_MODEL)
        self.assertEqual(res2, {})
        self.assertEqual(Faux.retrieve_calls, [])


class TestLotExpire(_Base):

    def test_pages_expirees_relues_normalement(self):
        img1 = _image(self.tmp, 'p1.png')
        cids = self._ecrire_lot('A', [img1], empreinte='EMP',
                                resultats={'p00000': 'expired'})
        self.assertIn('p00000', cids)
        lecteur = self._lecteur()
        with patch('anthropic.Anthropic', Faux):
            res = lecteur.lire([img1], self.sortie, empreinte='EMP')
        self.assertTrue(res[str(img1)]['repli_normal'])
        self.assertEqual(Faux.create_calls, [])             # jamais renvoyée en lot
        donnees = json.loads((self.sortie / 'lot_A.json').read_text(encoding='utf-8'))
        self.assertTrue(donnees.get('termine'))


class TestAntiDoublonParLot(_Base):

    def test_heure_debut_par_lot(self):
        img1 = _image(self.tmp, 'p1.png')
        img2 = _image(self.tmp, 'p2.png')
        Config.CLAUDE_LOT_TAILLE_MAX_MO = 0.0000001     # un lot par page
        Faux.create_raise = True                        # force la recherche de doublon
        heures = []
        lecteur = self._lecteur()
        lecteur._chercher_doublon = lambda client, nb, heure_debut, ids: (
            heures.append(heure_debut) or None)
        with patch('anthropic.Anthropic', Faux):
            lecteur.lire([img1, img2], self.sortie, empreinte='EMP')
        self.assertEqual(len(heures), 2)
        self.assertLess(heures[0], heures[1])           # prise au début de CHAQUE lot


class TestSansEmpreinte(_Base):

    def test_ancien_fichier_non_repris_automatiquement(self):
        img1 = _image(self.tmp, 'p1.png')
        self._ecrire_lot('vieux', [img1], empreinte=None)   # ancien format
        journal = []
        lecteur = self._lecteur(journal=journal)
        with patch('anthropic.Anthropic', Faux):
            res = lecteur.lire([img1], self.sortie, empreinte='EMP')
        self.assertTrue(any('sans empreinte' in m for m in journal))
        self.assertEqual(len(Faux.create_calls), 1)         # repart en nouveau lot
        self.assertTrue(res[str(img1)]['success'])


class TestEvenementsReprise(_Base):

    def test_lot_etat_et_recupere_emis_pendant_reprise(self):
        img1 = _image(self.tmp, 'p1.png')
        self._ecrire_lot('A', [img1], empreinte='EMP')
        # 1er retrieve (reprise) + 1 tour d'attente « en cours » (émet lot_etat) + fin.
        Faux.lots['A']['etats'] = ['in_progress', 'in_progress', 'ended']
        evenements = []
        lecteur = self._lecteur(collecteur=evenements.append)
        with patch('anthropic.Anthropic', Faux):
            lecteur.lire([img1], self.sortie, empreinte='EMP')
        types = [e.type for e in evenements]
        self.assertIn(ev.LOT_ETAT, types)
        self.assertIn(ev.LOT_RECUPERE, types)


if __name__ == '__main__':
    unittest.main()
