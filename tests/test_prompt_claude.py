"""
Consigne Claude (_build_prompt) après externalisation dans ressources/prompt_claude.txt et
encodage (textes_proteges) : la sortie reste IDENTIQUE À L'OCTET au golden capturé avant le
changement, le gabarit ne laisse aucun jeton non rempli, et le .dat encodé ne contient pas le
texte en clair tout en se redécodant à l'identique.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_prompt_claude.py -v
"""
import json
import unittest
from pathlib import Path

from claude_ocr import _build_prompt, _charger_gabarit
from template import TemplateManager
from textes_proteges import decoder, encoder

RACINE = Path(__file__).parent.parent
GOLDEN = json.loads((Path(__file__).parent / 'fixtures' / 'prompt_claude_golden.json')
                    .read_text('utf-8'))
TXT = RACINE / 'ressources' / 'prompt_claude.txt'


class TestPromptGolden(unittest.TestCase):

    def test_sortie_identique_au_golden(self):
        for nom, attendu in GOLDEN.items():
            self.assertEqual(_build_prompt(TemplateManager().get(nom)), attendu, nom)

    def test_aucun_jeton_restant(self):
        for nom in GOLDEN:
            self.assertNotIn('⟦', _build_prompt(TemplateManager().get(nom)), nom)


class TestGabaritLisible(unittest.TestCase):

    def test_txt_source_lisible_et_jetons_presents(self):
        texte = TXT.read_text('utf-8')
        self.assertIn('Tu analyses une image', texte)
        for jeton in ('⟦COL_ZONES⟧', '⟦RULES⟧', '⟦META_JSON⟧', '⟦MARQUEUR⟧'):
            self.assertIn(jeton, texte)

    def test_dev_lit_le_txt(self):
        self.assertEqual(_charger_gabarit(), TXT.read_text('utf-8'))


class TestEncodage(unittest.TestCase):

    def test_aller_retour(self):
        texte = TXT.read_text('utf-8')
        self.assertEqual(decoder(encoder(texte)), texte)

    def test_texte_absent_en_clair_du_blob(self):
        blob = encoder(TXT.read_text('utf-8'))
        self.assertNotIn(b'Tu analyses', blob)
        self.assertNotIn(b'TYPE_PAGE', blob)


if __name__ == '__main__':
    unittest.main()
