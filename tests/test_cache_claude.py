"""
Cache des lectures Claude (cache_claude.py + ClaudeVisionExtractor + Converter), sans reseau :
le client anthropic est simule. Verifie qu'une meme demande n'appelle qu'une fois, qu'une
difference force un nouvel appel, qu'une erreur / un refus / une reponse coupee n'est jamais
gardee, que la campagne desactive le cache, la reprise apres une coupure reseau, et le retry.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_cache_claude.py -v
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import claude_ocr as co
from config import Config
from converter import ConnexionPerdue, Converter
from template import TemplateManager

REPONSE = (
    "TYPE_PAGE: listing\n"
    "A | B | C | D\n"
    'META: {"PAGE": "1", "BORNIER": "", "PET": "", "NO_PLAN": "", "INDICE": ""}\n'
)


def _rep(stop_reason='end_turn', texte=REPONSE, ident='msg_1'):
    return SimpleNamespace(
        id=ident, content=[SimpleNamespace(type='text', text=texte)],
        stop_reason=stop_reason, model=Config.CLAUDE_OCR_MODEL,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=50,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class _Erreur529(Exception):
    status_code = 529


class FauxClient:
    """anthropic.Anthropic simulé : scénario par appel (ok, refus, tronqué, panne réseau)."""

    scenario = []     # liste d'actions : 'ok' | 'refus' | 'tronque' | '529'
    appels = 0
    requetes = []     # kwargs de chaque appel (pour inspecter system / cache_control)

    def __init__(self, api_key=None, **kw):
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    @classmethod
    def _action(cls):
        i = cls.appels
        cls.appels += 1
        return cls.scenario[i] if i < len(cls.scenario) else 'ok'

    def _create(self, **kw):
        FauxClient.requetes.append(kw)
        action = self._action()
        if action == '529':
            raise _Erreur529("surcharge simulée")
        if action == 'refus':
            return _rep(stop_reason='refusal')
        if action == 'tronque':
            return _rep(stop_reason='max_tokens')
        return _rep()

    def _stream(self, **kw):
        raise AssertionError("streaming non attendu dans ces tests")


def _image(dossier, nom='page_1.png', couleur='white'):
    chemin = Path(dossier) / nom
    Image.new('RGB', (200, 150), couleur).save(chemin)
    return chemin


class _Base(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        noms = ('CLAUDE_CACHE_LECTURES', 'CLAUDE_FORCER_RELECTURE', 'CLAUDE_CACHE_DOSSIER',
                'CLAUDE_OCR_MODEL', 'CLAUDE_EFFORT', 'CLAUDE_THINKING', 'CLAUDE_API_KEY',
                'OCR_MODE', 'CLAUDE_RETRY_DELAIS')
        self._sauve = {n: getattr(Config, n) for n in noms}
        Config.CLAUDE_CACHE_LECTURES = True
        Config.CLAUDE_FORCER_RELECTURE = False
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache'
        Config.CLAUDE_OCR_MODEL = 'claude-sonnet-5-5'
        Config.CLAUDE_EFFORT = 'medium'
        Config.CLAUDE_API_KEY = 'cle-de-test'
        Config.OCR_MODE = 'claude'
        Config.CLAUDE_RETRY_DELAIS = ()
        FauxClient.scenario = []
        FauxClient.appels = 0
        FauxClient.requetes = []
        self.ex = co.ClaudeVisionExtractor(TemplateManager().get('REPARTITEUR'))

    def tearDown(self):
        for n, v in self._sauve.items():
            setattr(Config, n, v)
        self._tmp.cleanup()

    def _extraire(self, image):
        with patch('anthropic.Anthropic', FauxClient):
            return self.ex.extract(image)


class TestCacheReutilisation(_Base):

    def test_deux_lectures_meme_image_un_seul_appel(self):
        img = _image(self.tmp)
        r1 = self._extraire(img)
        r2 = self._extraire(img)
        self.assertTrue(r1['success'] and r2['success'])
        self.assertEqual(FauxClient.appels, 1)
        self.assertFalse(r1.get('lecture_cache'))
        self.assertTrue(r2.get('lecture_cache'))
        self.assertEqual(r1['rows'], r2['rows'])
        self.assertEqual(r2['api_usage']['input_tokens'], 0)

    def test_image_differente_nouvel_appel(self):
        self._extraire(_image(self.tmp, 'page_1.png', 'white'))
        self._extraire(_image(self.tmp, 'page_2.png', 'black'))
        self.assertEqual(FauxClient.appels, 2)

    def test_modele_different_nouvel_appel(self):
        img = _image(self.tmp)
        self._extraire(img)
        Config.CLAUDE_OCR_MODEL = 'claude-opus-5-5'
        self._extraire(img)
        self.assertEqual(FauxClient.appels, 2)

    def test_effort_different_nouvel_appel(self):
        img = _image(self.tmp)
        self._extraire(img)
        Config.CLAUDE_EFFORT = 'low'
        self._extraire(img)
        self.assertEqual(FauxClient.appels, 2)

    def test_forcer_relecture_ignore_le_cache(self):
        img = _image(self.tmp)
        self._extraire(img)
        Config.CLAUDE_FORCER_RELECTURE = True
        r2 = self._extraire(img)
        self.assertEqual(FauxClient.appels, 2)
        self.assertFalse(r2.get('lecture_cache'))


class TestErreursNonGardees(_Base):

    def test_refus_non_garde(self):
        FauxClient.scenario = ['refus', 'refus']
        img = _image(self.tmp)
        self.assertFalse(self._extraire(img)['success'])
        self.assertFalse(self._extraire(img)['success'])
        self.assertEqual(FauxClient.appels, 2)     # pas de réutilisation

    def test_reponse_tronquee_non_gardee(self):
        FauxClient.scenario = ['tronque', 'tronque']
        img = _image(self.tmp)
        self._extraire(img)
        self._extraire(img)
        self.assertEqual(FauxClient.appels, 2)

    def test_cle_api_absente_du_cache(self):
        img = _image(self.tmp)
        self._extraire(img)
        contenu = ''.join(p.read_text('utf-8') for p in
                          Path(Config.CLAUDE_CACHE_DOSSIER).glob('*.json'))
        self.assertNotIn('cle-de-test', contenu)
        self.assertIn('"raw"', contenu)


class TestCampagneDesactiveCache(_Base):

    def test_reglage_en_memoire_coupe_le_cache(self):
        import campagne_mesure
        img = _image(self.tmp)
        with campagne_mesure.reglage_en_memoire('claude-sonnet-5-5', 'medium', 'cle-de-test'):
            self.assertFalse(Config.CLAUDE_CACHE_LECTURES)
            with patch('anthropic.Anthropic', FauxClient):
                self.ex.extract(img)
                self.ex.extract(img)
        self.assertEqual(FauxClient.appels, 2)     # jamais servi par le cache
        self.assertTrue(Config.CLAUDE_CACHE_LECTURES)   # restauré


class TestRetry(_Base):

    def test_retry_puis_succes(self):
        Config.CLAUDE_RETRY_DELAIS = (0,)
        FauxClient.scenario = ['529', 'ok']
        img = _image(self.tmp)
        with patch('claude_ocr.time.sleep'):
            r = self._extraire(img)
        self.assertTrue(r['success'])
        self.assertEqual(FauxClient.appels, 2)

    def test_panne_persistante_connexion_perdue(self):
        FauxClient.scenario = ['529']
        r = self._extraire(_image(self.tmp))
        self.assertFalse(r['success'])
        self.assertTrue(r.get('connexion_perdue'))


class TestRepriseApresCoupure(_Base):

    def _cinq_images(self):
        for k in range(1, 6):
            Image.new('RGB', (200, 150), (k * 40, k * 10, 0)).save(self.tmp / f'page_{k}.png')
        return self.tmp

    def _extraire_toutes(self, images_dir):
        conv = Converter(word_file=images_dir, output_dir=self.tmp / 'out',
                         template=TemplateManager().get('REPARTITEUR'), on_log=lambda m: None)
        with patch('anthropic.Anthropic', FauxClient):
            return conv._extraire_avec_progres(images_dir, 0)

    def test_coupure_page3_puis_reprise(self):
        images_dir = self._cinq_images()
        # 1er passage : pages 1-2 OK, page 3 coupure réseau → arrêt propre
        FauxClient.scenario = ['ok', 'ok', '529']
        with self.assertRaises(ConnexionPerdue) as cm:
            self._extraire_toutes(images_dir)
        self.assertIn('page 3', str(cm.exception))
        self.assertEqual(FauxClient.appels, 3)

        # Relance : pages 1-2 depuis le cache, seules 3-5 rappellent l'API
        FauxClient.scenario = []
        FauxClient.appels = 0
        resultats, _ = self._extraire_toutes(images_dir)
        self.assertEqual(len(resultats), 5)
        self.assertTrue(all(r['success'] for r in resultats))
        self.assertEqual(FauxClient.appels, 3)     # pages 3, 4, 5 seulement
        self.assertEqual([r.get('lecture_cache') for r in resultats],
                         [True, True, False, False, False])

    def test_resultat_identique_a_une_conversion_sans_panne(self):
        images_dir = self._cinq_images()
        FauxClient.scenario = ['ok', 'ok', '529']
        with self.assertRaises(ConnexionPerdue):
            self._extraire_toutes(images_dir)
        FauxClient.scenario = []
        FauxClient.appels = 0
        repris, _ = self._extraire_toutes(images_dir)
        # Conversion neuve (autre cache) : tout par l'API, aucune panne
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache2'
        FauxClient.appels = 0
        neuf, _ = self._extraire_toutes(images_dir)
        self.assertEqual([r['rows'] for r in repris], [r['rows'] for r in neuf])


class TestConsigneEnCache(_Base):
    """Étape 1 : consigne commune mise en cache (bloc system + cache_control), clé inchangée."""

    def test_cle_cache_identique_a_la_formule_d_origine(self):
        # Exigence : même hash qu'avant pour une même page → les lectures déjà payées
        # restent réutilisables. La clé hache toujours la consigne complète (_build_prompt),
        # indépendamment de la place (system) dans la requête.
        import cache_claude
        img = _image(self.tmp)
        model = Config.CLAUDE_OCR_MODEL
        parametres = co._parametres_modele(model)
        image_data, media_type = co._preparer_image_claude(img, Config.CLAUDE_IMAGE_MAX_PX)
        prompt = co._build_prompt(self.ex._tpl)
        attendue = cache_claude.cle(image_data, media_type, prompt, model,
                                    parametres, co._limite_tokens(parametres))
        self.assertEqual(self.ex.cle_cache(img), attendue)
        self.assertEqual(self.ex.cle_cache(img), self.ex.cle_cache(img))   # stable

    def test_consigne_en_bloc_system_avec_cache_control(self):
        self._extraire(_image(self.tmp))
        req = FauxClient.requetes[0]
        self.assertIn('system', req)
        self.assertEqual(req['system'][0]['cache_control'], {'type': 'ephemeral'})
        self.assertIn('Tu analyses', req['system'][0]['text'])          # la consigne
        # L'image est seule dans le message user (la consigne la précède, en system).
        contenu = req['messages'][0]['content']
        self.assertEqual([b['type'] for b in contenu], ['image'])

    def test_feedback_garde_la_structure_d_avant(self):
        with patch('anthropic.Anthropic', FauxClient):
            self.ex.extract(_image(self.tmp), feedback='corrige la colonne 2')
        req = FauxClient.requetes[0]
        self.assertNotIn('system', req)
        self.assertEqual([b['type'] for b in req['messages'][0]['content']],
                         ['image', 'text'])


class TestCoutCache(unittest.TestCase):
    """campagne_mesure : tokens de cache lus/écrits comptés à leur vrai prix."""

    def test_cout_usd_cache_lu_moins_cher(self):
        import campagne_mesure as cm
        # Sonnet 5.5 (2/10) : lecture cache 0,05× → 1 000 tokens lus = 1 000×2×0.05/1e6
        plein = cm.cout_usd('claude-sonnet-5-5', 1000, 0)
        cache = cm.cout_usd('claude-sonnet-5-5', 0, 0, cache_read=1000)
        self.assertAlmostEqual(plein, 1000 * 2 / 1e6)
        self.assertAlmostEqual(cache, 1000 * 2 * 0.05 / 1e6)
        self.assertLess(cache, plein)

    def test_cout_usd_cache_ecrit_et_lot(self):
        import campagne_mesure as cm
        ecrit = cm.cout_usd('claude-sonnet-5-5', 0, 0, cache_creation=1000)
        self.assertAlmostEqual(ecrit, 1000 * 2 * 1.25 / 1e6)
        self.assertAlmostEqual(cm.cout_usd('claude-sonnet-5-5', 1000, 1000, lot=True),
                               cm.cout_usd('claude-sonnet-5-5', 1000, 1000) * 0.5)

    def test_lire_journal_separe_les_tokens_de_cache(self):
        import json
        import tempfile as tf
        import campagne_mesure as cm
        lignes = [json.dumps({'image': 'p1.png', 'success': True, 'usage': {
            'input_tokens': 10, 'output_tokens': 3,
            'cache_read_input_tokens': 7, 'cache_creation_input_tokens': 5}})]
        f = Path(tf.mkdtemp()) / 'j.jsonl'
        f.write_text('\n'.join(lignes), encoding='utf-8')
        bilan = cm.lire_journal(f)
        self.assertEqual(bilan['cache_read'], 7)
        self.assertEqual(bilan['cache_creation'], 5)
        self.assertEqual(bilan['tokens_entree'], 22)   # total inchangé (10+7+5)


if __name__ == '__main__':
    unittest.main()
