"""
Contraste de l'interface (point 14) : FG_MUTED doit atteindre 4,5:1 (WCAG AA texte normal)
sur CHAQUE fond où il sert de texte. Ce test importe interface.py pour lire les vraies
constantes de couleur ; il rougit si l'une repasse sous le seuil.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_contraste_interface.py -v
"""
import unittest

import interface
from interface_helpers import ratio_contraste

SEUIL_AA = 4.5

# Fonds sur lesquels FG_MUTED est posé comme couleur de texte (fg=FG_MUTED) dans interface.py.
FONDS_DE_FG_MUTED = ("BG_CARD", "BG_PANEL", "BG_MAIN", "BG_LOG")


class TestContrasteFgMuted(unittest.TestCase):

    def test_fg_muted_atteint_4_5_sur_chaque_fond(self):
        fg = interface.FG_MUTED
        for nom_fond in FONDS_DE_FG_MUTED:
            fond = getattr(interface, nom_fond)
            ratio = ratio_contraste(fg, fond)
            self.assertGreaterEqual(
                ratio, SEUIL_AA,
                f"FG_MUTED {fg} sur {nom_fond} {fond} : {ratio:.2f} < {SEUIL_AA}")


if __name__ == '__main__':
    unittest.main()
