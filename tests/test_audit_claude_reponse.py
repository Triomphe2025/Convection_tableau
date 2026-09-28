"""
Test de lecture de la réponse dans audit_claude._appeler_claude : seuls les blocs
texte sont lus (le premier bloc peut être un bloc de réflexion). Client simulé,
aucun appel réseau.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_audit_claude_reponse.py -v
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import audit_claude


class _FauxClient:
    reponse = None

    def __init__(self, api_key=None):
        self.messages = SimpleNamespace(create=lambda **kwargs: _FauxClient.reponse)


class TestAppelerClaude(unittest.TestCase):

    def _appeler(self, blocs):
        _FauxClient.reponse = SimpleNamespace(content=blocs)
        with patch('anthropic.Anthropic', _FauxClient):
            return audit_claude._appeler_claude('résumé', 'cle', 'claude-opus-5-5')

    def test_bloc_de_reflexion_en_tete_ignore(self):
        blocs = [SimpleNamespace(type='thinking', thinking=''),
                 SimpleNamespace(type='text', text='- [INFO] Bornier X — rien à signaler')]
        self.assertEqual(self._appeler(blocs), '- [INFO] Bornier X — rien à signaler')

    def test_plusieurs_blocs_texte_concatenes(self):
        blocs = [SimpleNamespace(type='text', text='A'), SimpleNamespace(type='text', text='B')]
        self.assertEqual(self._appeler(blocs), 'AB')

    def test_aucun_bloc_texte(self):
        self.assertEqual(self._appeler([SimpleNamespace(type='thinking', thinking='')]), '')


if __name__ == '__main__':
    unittest.main()
