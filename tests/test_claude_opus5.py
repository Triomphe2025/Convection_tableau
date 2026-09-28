"""
Tests du passage à Claude Opus 5 (claude_ocr.py) : paramètres envoyés, lecture
d'une réponse commençant par un bloc de réflexion, refus d'un effort incompatible,
préparation des images. Aucun appel réseau : le client anthropic est simulé.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_claude_opus5.py -v
"""
import base64
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import claude_ocr as co
from config import Config
from template import TemplateManager

REPONSE_PIPE = (
    "TYPE_PAGE: listing\n"
    "PJ        29 | 1738N | QA        29 | TS ARTE\n"
    "PJ        30 | 1739N | QA        30 | TS DPE\n"
    'META: {"PAGE": "32", "BORNIER": "", "PET": "GRAND-BUT", "NO_PLAN": "", "INDICE": "TP2"}\n'
)


def _bloc_reflexion():
    # Un bloc de réflexion n'a pas d'attribut .text (thinking vide par défaut).
    return SimpleNamespace(type='thinking', thinking='', signature='sig')


def _bloc_texte(texte):
    return SimpleNamespace(type='text', text=texte)


def _reponse(blocs, stop_reason='end_turn', model='claude-opus-5'):
    return SimpleNamespace(
        content=blocs, stop_reason=stop_reason, model=model,
        usage=SimpleNamespace(input_tokens=1234, output_tokens=56,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class _ConfigClaude(unittest.TestCase):

    def setUp(self):
        noms = ('CLAUDE_OCR_MODEL', 'CLAUDE_THINKING', 'CLAUDE_EFFORT',
                'CLAUDE_API_KEY', 'CLAUDE_MAX_TOKENS', 'CLAUDE_IMAGE_MAX_PX')
        self._sauve = {n: getattr(Config, n) for n in noms}
        Config.CLAUDE_OCR_MODEL = 'claude-opus-5'
        Config.CLAUDE_THINKING = 'disabled'
        Config.CLAUDE_EFFORT = 'high'
        Config.CLAUDE_API_KEY = 'cle-de-test'
        Config.CLAUDE_MAX_TOKENS = 16000
        Config.CLAUDE_IMAGE_MAX_PX = 2576

    def tearDown(self):
        for nom, valeur in self._sauve.items():
            setattr(Config, nom, valeur)


def _image_temp(tmp, taille=(400, 300), mode='RGB', format_='PNG', suffixe='.png'):
    chemin = Path(tmp) / f'page{suffixe}'
    Image.new(mode, taille, 'white').save(chemin, format=format_)
    return chemin


class TestTexteReponse(unittest.TestCase):

    def test_reponse_commencant_par_un_bloc_de_reflexion(self):
        reponse = _reponse([_bloc_reflexion(), _bloc_texte(REPONSE_PIPE)])
        self.assertEqual(co._texte_reponse(reponse), REPONSE_PIPE)

    def test_plusieurs_blocs_texte_concatenes(self):
        reponse = _reponse([_bloc_texte('A'), _bloc_reflexion(), _bloc_texte('B')])
        self.assertEqual(co._texte_reponse(reponse), 'AB')

    def test_aucun_bloc_texte(self):
        self.assertEqual(co._texte_reponse(_reponse([_bloc_reflexion()])), '')


class TestParametresModele(_ConfigClaude):

    def test_opus5_par_defaut(self):
        self.assertEqual(
            co._parametres_modele('claude-opus-5'),
            {'thinking': {'type': 'disabled'}, 'output_config': {'effort': 'high'}},
        )

    def test_effort_max_avec_reflexion_desactivee_refuse(self):
        Config.CLAUDE_EFFORT = 'max'
        with self.assertRaises(ValueError) as ctx:
            co._parametres_modele('claude-opus-5')
        self.assertIn('CLAUDE_THINKING = "disabled"', str(ctx.exception))
        self.assertIn('"max"', str(ctx.exception))

    def test_effort_xhigh_avec_reflexion_desactivee_refuse(self):
        Config.CLAUDE_EFFORT = 'xhigh'
        with self.assertRaises(ValueError):
            co._parametres_modele('claude-opus-5')

    def test_effort_max_avec_reflexion_adaptative_accepte(self):
        Config.CLAUDE_THINKING, Config.CLAUDE_EFFORT = 'adaptive', 'max'
        self.assertEqual(
            co._parametres_modele('claude-opus-5'),
            {'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'max'}},
        )

    def test_haiku_sans_reflexion_ni_effort(self):
        self.assertEqual(co._parametres_modele('claude-haiku-4-5-20251001'), {})

    def test_fable_exige_la_reflexion(self):
        with self.assertRaises(ValueError):
            co._parametres_modele('claude-fable-5-1')

    def test_valeurs_inconnues_refusees(self):
        Config.CLAUDE_EFFORT = 'maximum'
        with self.assertRaises(ValueError):
            co._parametres_modele('claude-opus-5')
        Config.CLAUDE_EFFORT, Config.CLAUDE_THINKING = 'high', 'enabled'
        with self.assertRaises(ValueError):
            co._parametres_modele('claude-opus-5')


class TestPreparerImageClaude(unittest.TestCase):

    def _decoder(self, donnees):
        return Image.open(io.BytesIO(base64.standard_b64decode(donnees)))

    def test_grande_image_reduite_a_2576_en_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = _image_temp(tmp, (4000, 3000), format_='JPEG', suffixe='.jpg')
            donnees, media = co._preparer_image_claude(chemin, 2576)
        img = self._decoder(donnees)
        self.assertEqual(media, 'image/png')
        self.assertEqual(img.format, 'PNG')
        self.assertEqual(img.size, (2576, 1932))

    def test_petite_image_non_agrandie(self):
        with tempfile.TemporaryDirectory() as tmp:
            donnees, _ = co._preparer_image_claude(_image_temp(tmp, (1785, 2526)), 2576)
        self.assertEqual(self._decoder(donnees).size, (1785, 2526))

    def test_image_cmyk_convertie(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = _image_temp(tmp, (100, 50), mode='CMYK', format_='JPEG', suffixe='.jpg')
            donnees, _ = co._preparer_image_claude(chemin, 2576)
        self.assertEqual(self._decoder(donnees).mode, 'RGB')

    def test_fichier_absent(self):
        with self.assertRaises(FileNotFoundError):
            co._preparer_image_claude(Path('absent.png'), 2576)


class FauxClient:
    """Remplace anthropic.Anthropic : enregistre la requête, renvoie une réponse fixée."""

    appels = []
    reponse = None

    def __init__(self, api_key=None):
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        FauxClient.appels.append(kwargs)
        return FauxClient.reponse


class TestExtractOpus5(_ConfigClaude):

    def setUp(self):
        super().setUp()
        FauxClient.appels = []
        FauxClient.reponse = _reponse([_bloc_reflexion(), _bloc_texte(REPONSE_PIPE)])
        self._tmp = tempfile.TemporaryDirectory()
        self.image = _image_temp(self._tmp.name, (4000, 3000))
        self.ex = co.ClaudeVisionExtractor(TemplateManager().get('REPARTITEUR'))

    def tearDown(self):
        self._tmp.cleanup()
        super().tearDown()

    def _extraire(self):
        with patch('anthropic.Anthropic', FauxClient), patch.object(co, '_write_api_log'):
            return self.ex.extract(self.image)

    def test_reponse_avec_reflexion_lue_correctement(self):
        r = self._extraire()
        self.assertTrue(r['success'], r.get('error'))
        attendu = ['PJ        29', '1738N', 'QA        29', 'TS ARTE']
        self.assertEqual(r['rows'][0]['cells'], attendu)

    def test_parametres_envoyes_a_l_api(self):
        self._extraire()
        appel = FauxClient.appels[0]
        self.assertEqual(appel['model'], 'claude-opus-5')
        self.assertEqual(appel['max_tokens'], 16000)
        self.assertEqual(appel['thinking'], {'type': 'disabled'})
        self.assertEqual(appel['output_config'], {'effort': 'high'})
        for interdit in ('temperature', 'top_p', 'top_k'):
            self.assertNotIn(interdit, appel)

    def test_image_envoyee_en_png_reduite(self):
        self._extraire()
        source = FauxClient.appels[0]['messages'][0]['content'][0]['source']
        self.assertEqual(source['media_type'], 'image/png')
        img = Image.open(io.BytesIO(base64.standard_b64decode(source['data'])))
        self.assertEqual(max(img.size), 2576)

    def test_modele_et_tokens_journalises(self):
        with patch('anthropic.Anthropic', FauxClient), \
                patch.object(co, '_write_api_log') as journal:
            r = self.ex.extract(self.image)
        self.assertEqual(r['api_usage']['model'], 'claude-opus-5')
        self.assertEqual(r['api_usage']['input_tokens'], 1234)
        entree = journal.call_args[0][0]
        self.assertEqual(entree['usage']['output_tokens'], 56)

    def test_effort_max_reflexion_desactivee_refuse_sans_appel(self):
        Config.CLAUDE_EFFORT = 'max'
        r = self._extraire()
        self.assertFalse(r['success'])
        self.assertIn('CLAUDE_THINKING', r['error'])
        self.assertEqual(FauxClient.appels, [])

    def test_refus_du_modele(self):
        FauxClient.reponse = _reponse([], stop_reason='refusal')
        r = self._extraire()
        self.assertFalse(r['success'])
        self.assertIn('refusé', r['error'])

    def test_haiku_garde_l_appel_v17(self):
        Config.CLAUDE_OCR_MODEL = 'claude-haiku-4-5-20251001'
        self._extraire()
        appel = FauxClient.appels[0]
        self.assertNotIn('thinking', appel)
        self.assertNotIn('output_config', appel)


if __name__ == '__main__':
    unittest.main()
