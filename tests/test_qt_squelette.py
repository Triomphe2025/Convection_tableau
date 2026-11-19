"""Étape 1 — test de fumée de la nouvelle interface Qt : la fenêtre vide s'instancie.

Sans écran (QT_QPA_PLATFORM=offscreen, posé par conftest), sans appeler exec().
"""
import pytest

pytest.importorskip("PySide6")

from trios_qt.application import TITRE_FENETRE, creer_application, creer_fenetre  # noqa: E402


def test_creer_application_rend_un_singleton():
    app1 = creer_application([])
    app2 = creer_application([])
    assert app1 is app2


def test_creer_fenetre_titre_et_pages(qtbot):
    creer_application([])
    fenetre = creer_fenetre()
    qtbot.addWidget(fenetre)
    assert fenetre.windowTitle() == TITRE_FENETRE
    # La fenêtre porte les 6 écrans (4 principaux + Réglages + Aide).
    assert set(fenetre.pages) == {
        "convertir", "relecture", "mise_en_forme", "plans", "reglages", "aide"}
