"""
DPI de la fenêtre (point 13) : le guard _activer_dpi d'interface.py ne demande la netteté
à Windows que si le réglage Config.DPI_NET est actif. La décision elle-même (Windows + réglage)
est testée dans test_interface_helpers (dpi_a_activer) ; ici on vérifie que le guard respecte
le réglage par défaut (False) et ne provoque aucun effet de bord.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_dpi_interface.py -v
"""
import unittest

import interface
from config import Config


class TestActiverDpi(unittest.TestCase):

    def test_desactive_par_defaut_ne_fait_rien(self):
        avant = Config.DPI_NET
        Config.DPI_NET = False
        try:
            self.assertFalse(interface._activer_dpi())
        finally:
            Config.DPI_NET = avant


if __name__ == '__main__':
    unittest.main()
