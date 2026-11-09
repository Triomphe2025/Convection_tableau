"""
Contraste de l'interface (point 14) : tout texte posé doit atteindre 4,5:1 (WCAG AA texte
normal) sur son fond. Ce test importe interface.py pour lire les vraies constantes de couleur ;
il rougit si l'une repasse sous le seuil, ou si l'ancienne valeur FG_MUTED revient en dur.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_contraste_interface.py -v
"""
import unittest
from pathlib import Path

import interface
from interface_helpers import ratio_contraste

SEUIL_AA = 4.5

# Fonds sur lesquels FG_MUTED est posé comme couleur de texte (fg=FG_MUTED) dans interface.py.
FONDS_DE_FG_MUTED = ("BG_CARD", "BG_PANEL", "BG_MAIN", "BG_LOG")

# Éléments où FG_MUTED sert de FOND (ou de texte sur fond sombre) : éclaircir FG_MUTED avait
# dégradé ces cas. Chaque paire (nom_texte, nom_fond) renvoie à des constantes d'interface.py.
PAIRES_FOND_MUTED = (
    ("FG_MUTED", "BG_BTN_OFF"),              # bouton désactivé : texte/contour sur fond sombre
    ("FG_PASTILLE_FOND_MUTED", "FG_MUTED"),  # pastille d'étape à venir : texte sur fond FG_MUTED
)


class TestContrasteFgMuted(unittest.TestCase):

    def test_fg_muted_atteint_4_5_sur_chaque_fond(self):
        fg = interface.FG_MUTED
        for nom_fond in FONDS_DE_FG_MUTED:
            fond = getattr(interface, nom_fond)
            ratio = ratio_contraste(fg, fond)
            self.assertGreaterEqual(
                ratio, SEUIL_AA,
                f"FG_MUTED {fg} sur {nom_fond} {fond} : {ratio:.2f} < {SEUIL_AA}")

    def test_paires_sur_fond_muted_atteignent_4_5(self):
        for nom_fg, nom_fond in PAIRES_FOND_MUTED:
            fg = getattr(interface, nom_fg)
            fond = getattr(interface, nom_fond)
            ratio = ratio_contraste(fg, fond)
            self.assertGreaterEqual(
                ratio, SEUIL_AA,
                f"{nom_fg} {fg} sur {nom_fond} {fond} : {ratio:.2f} < {SEUIL_AA}")

    def test_aucune_couleur_muted_en_dur(self):
        source = Path(interface.__file__).read_text(encoding='utf-8')
        occurrences = source.count("#7878a0")
        self.assertEqual(
            occurrences, 0,
            f"Ancienne valeur FG_MUTED codée en dur {occurrences} fois ; utiliser FG_MUTED")


if __name__ == '__main__':
    unittest.main()
