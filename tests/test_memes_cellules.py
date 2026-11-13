"""
Filet « mêmes cellules » — non-régression de bout en bout du moteur (phase 1a, étape 1).

Rejoue SANS appel API les journaux .jsonl de conversions validées (mode rejeu existant) et
compare, cellule par cellule, l'Excel produit à un instantané figé pris sur `main`. Le filet
casse si — et seulement si — le code change une cellule, un pied, un commentaire ou la mise en
forme. Il réutilise `dump_classeur` de test_non_regression_xlsx.

Déterminisme (vérifié) : le rejeu .jsonl ne lance ni OCR (pas de Tesseract) ni appel API, et les
TROIS clés du lexique sont neutralisées ici (dossiers vides, y compris QUALITE_LEXIQUE_REFERENCE
= references/excels_valides, hors git) — la sortie ne dépend donc ni de Tesseract ni des
classeurs de référence de la machine, seulement du code.

Dans la suite normale (~5 s) : il protège chaque commit sans qu'on pense à le lancer.
Le lancer seul :
    env\\Scripts\\python.exe -m pytest tests/test_memes_cellules.py -v
Chaque journal est rejoué avec SON vrai modèle de tableau (le journal n'enregistre que le
modèle Claude, pas le modèle de tableau) : PE011 → REPARTITEUR 2, PE012 → Bornier standard,
PE133 → Répartiteur. Un mauvais modèle changerait en-têtes, pied et largeurs de colonnes.

Un 4e cas (223111PE011_lexique) rejoue PE011 avec un mini-lexique figé (tests/fixtures/
mini_lexique, deux formes : OCFSCS, OC FS 14 50) : il garde les alertes de cohérence du lexique
sous le filet (les deux cellules CC FS colorées COULEUR_QUALITE et commentées). Sans ce
mini-lexique, le cas devient rouge.

L'instantané est un vrai « avant » : il est régénéré depuis le code de `main` (3a78399) dans
un worktree jetable (le mini-lexique y est copié), pas depuis la branche. Le filet est donc vert
tant que la branche rend, cellule par cellule, la même chose que `main`.

Régénérer l'instantané (changement voulu du moteur, depuis main) :
    env\\Scripts\\python.exe -m tests.test_memes_cellules --regenerer
"""

import contextlib
import io
import json
import logging
import sys
import tempfile
import unittest
from glob import glob
from pathlib import Path
from unittest.mock import patch

from config import Config
from converter import Converter
from template import TemplateManager
from tests.test_non_regression_xlsx import dump_classeur

FIXTURES = Path(__file__).parent / 'fixtures'
BASELINE = FIXTURES / 'memes_cellules_baseline.json'
JOURNAUX = {
    '223111PE011': 'rejeu_claude/223111PE011_extrait_10pages_claude.jsonl',
    '223111PE012': 'rejeu_claude/223111PE012_extrait_10pages_claude.jsonl',
    '6A23111PE133': 'rejeu_claude/6A23111PE133_extrait_8pages_claude.jsonl',
}
# Vrai modèle de tableau de chaque document (le journal ne l'enregistre pas).
MODELES = {
    '223111PE011': 'REPARTITEUR 2',
    '223111PE012': 'Bornier standard',
    '6A23111PE133': 'Répartiteur',
}
# Mini-lexique figé du 4e cas : deux formes seulement (OCFSCS, OC FS 14 50).
MINI_LEXIQUE = FIXTURES / 'mini_lexique'


def _cas():
    """(nom, journal, modèle, dossier lexique) ; lexique None = neutralisé (dossier vide)."""
    for nom, rel in JOURNAUX.items():
        yield nom, rel, MODELES[nom], None
    # 4e cas : PE011 + mini-lexique → garde les alertes de cohérence sous le filet.
    yield '223111PE011_lexique', JOURNAUX['223111PE011'], MODELES['223111PE011'], MINI_LEXIQUE


CAS = {nom: (rel, modele, lex) for nom, rel, modele, lex in _cas()}


def rejeu_dump(journal_rel, modele, lexique_reference=None):
    """Rejoue un journal avec son modèle (sortie temporaire) et rend l'instantané.

    Les trois clés du lexique sont neutralisées (dossiers vides) ; QUALITE_LEXIQUE_REFERENCE
    pointe sur `lexique_reference` quand il est fourni, sinon sur un dossier vide — la sortie ne
    dépend donc jamais de references/excels_valides (hors git), seulement du code et du lexique
    explicitement passé.
    """
    journal = FIXTURES / journal_rel
    tpl = TemplateManager().get(modele)
    with tempfile.TemporaryDirectory() as sortie, tempfile.TemporaryDirectory() as lex_vide:
        reference = Path(lexique_reference) if lexique_reference else Path(lex_vide)
        with patch.multiple(Config,
                            QUALITE_LEXIQUE_DOSSIER=lex_vide,
                            QUALITE_LEXIQUE_COMPILE=str(Path(lex_vide) / 'absent.json'),
                            QUALITE_LEXIQUE_REFERENCE=reference):
            niveau = logging.root.manager.disable
            logging.disable(logging.CRITICAL)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    Converter(word_file=journal, output_dir=Path(sortie), template=tpl,
                              on_log=lambda *a, **k: None).run()
            finally:
                logging.disable(niveau)
        produits = glob(str(Path(sortie) / '*.xlsx'))
        assert len(produits) == 1, f"{journal_rel} : {len(produits)} .xlsx produits"
        return dump_classeur(produits[0])


def generer_instantane():
    return {nom: rejeu_dump(rel, modele, lex) for nom, rel, modele, lex in _cas()}


class TestMemesCellules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.attendu = json.loads(BASELINE.read_text(encoding='utf-8'))

    def _comparer(self, nom):
        self.assertIn(nom, self.attendu, f"{nom} absent de l'instantané")
        attendu = self.attendu[nom]
        rel, modele, lex = CAS[nom]
        obtenu = rejeu_dump(rel, modele, lex)
        self.assertEqual(sorted(obtenu), sorted(attendu), f"{nom} : feuilles différentes")
        for feuille, ref in attendu.items():
            cur = obtenu[feuille]
            for cle in ('merged', 'row_heights', 'col_widths', 'page_breaks',
                        'print_header', 'print_footer'):
                self.assertEqual(cur.get(cle), ref.get(cle), f"{nom}/{feuille} : {cle}")
            diff = [
                coord for coord in sorted(set(cur['cells']) | set(ref['cells']))
                if cur['cells'].get(coord) != ref['cells'].get(coord)
            ]
            self.assertEqual(diff, [], f"{nom}/{feuille} : cellules différentes {diff[:10]}")

    def test_pe011(self):
        self._comparer('223111PE011')

    def test_pe012(self):
        self._comparer('223111PE012')

    def test_pe133(self):
        self._comparer('6A23111PE133')

    def test_pe011_lexique(self):
        self._comparer('223111PE011_lexique')


if __name__ == '__main__':
    if '--regenerer' in sys.argv:
        BASELINE.write_text(
            json.dumps(generer_instantane(), ensure_ascii=False, indent=1, sort_keys=True),
            encoding='utf-8',
        )
        print(f"Instantané écrit : {BASELINE}")
    else:
        unittest.main()
