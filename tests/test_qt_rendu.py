"""Étape 3b #1 — les QLabel sont transparents : le fond général ne va que sur la fenêtre et
les pages, pas sur chaque widget. Rendu réel (grab) et lecture du pixel derrière les étiquettes.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint  # noqa: E402

from trios_qt import animations, theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.fenetre import FenetrePrincipale  # noqa: E402


def _couleur_derriere(fenetre, label) -> str:
    image = fenetre.grab().toImage()
    point = label.mapTo(fenetre, QPoint(label.width() - 4, label.height() // 2))
    return image.pixelColor(point).name().upper()


def test_labels_transparents_sur_leurs_fonds(qtbot):
    app = creer_application([])
    jetons = theme.appliquer_theme(app)
    animations.definir_reduction(True)
    try:
        fenetre = FenetrePrincipale(jetons=jetons, points_a_relire=12)
        fenetre.resize(1360, 872)
        qtbot.addWidget(fenetre)
        fenetre.show()
        app.processEvents()
        app.processEvents()
        couleurs = jetons["couleurs"]
        # Derrière le logo on doit voir la barre latérale, pas un rectangle « fond ».
        assert _couleur_derriere(fenetre, fenetre._logo) == couleurs["barre_laterale"].upper()
        # Derrière « Modèle » on doit voir la carte (surface), pas « fond ».
        assert _couleur_derriere(fenetre, fenetre.etiquette_modele) == couleurs["surface"].upper()
    finally:
        animations.reinitialiser()
