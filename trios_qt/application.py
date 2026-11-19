"""Construction de l'application Qt et de la fenêtre, sans jamais appeler exec().

Séparer la construction de la boucle d'événements permet de tester la fenêtre sous
QT_QPA_PLATFORM=offscreen sans bloquer la suite.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from trios_qt.fenetre import TITRE_FENETRE, FenetrePrincipale  # noqa: F401  (ré-export)


def creer_application(argv=None) -> QApplication:
    # QApplication est un singleton : réutiliser l'instance existante (tests successifs).
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    return app


def creer_fenetre() -> FenetrePrincipale:
    return FenetrePrincipale()
