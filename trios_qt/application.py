"""Construction de l'application Qt et de la fenêtre, sans jamais appeler exec().

Séparer la construction de la boucle d'événements permet de tester la fenêtre sous
QT_QPA_PLATFORM=offscreen sans bloquer la suite.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

TITRE_FENETRE = "TriosSeconverter"


def creer_application(argv=None) -> QApplication:
    # QApplication est un singleton : réutiliser l'instance existante (tests successifs).
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    return app


def creer_fenetre() -> QMainWindow:
    fenetre = QMainWindow()
    fenetre.setWindowTitle(TITRE_FENETRE)
    fenetre.resize(1360, 900)
    # Fenêtre vide à l'étape 1 ; la barre latérale et les écrans arrivent à l'étape 3.
    fenetre.setCentralWidget(QWidget())
    return fenetre
