"""Construction de l'application Qt et de la fenêtre, sans jamais appeler exec().

Séparer la construction de la boucle d'événements permet de tester la fenêtre sous
QT_QPA_PLATFORM=offscreen sans bloquer la suite.
"""
from __future__ import annotations

import threading

from PySide6.QtWidgets import QApplication

from trios_qt.fenetre import TITRE_FENETRE, FenetrePrincipale  # noqa: F401  (ré-export)

# Modules lourds chargés à la 1re conversion : les importer gelait l'UI ~5 s au clic « Lancer ».
_MODULES_LOURDS = ("converter", "service_conversion", "ocr_processor", "generer_classeur")


def prechauffer() -> threading.Thread:
    """Importe les modules lourds dans un fil à part, pour que « Lancer » ne gèle pas l'UI.

    Rend le fil (déjà démarré) ; une erreur d'import est ignorée (la conversion la relèvera).
    """
    def _importer():
        import importlib
        for nom in _MODULES_LOURDS:
            try:
                importlib.import_module(nom)
            except Exception:
                pass

    fil = threading.Thread(target=_importer, name='prechauffe', daemon=True)
    fil.start()
    return fil


def creer_application(argv=None) -> QApplication:
    # QApplication est un singleton : réutiliser l'instance existante (tests successifs).
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    return app


def creer_fenetre() -> FenetrePrincipale:
    return FenetrePrincipale()
