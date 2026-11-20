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
    # Les 6 écrans de la barre latérale (4 principaux + Réglages + Aide)…
    assert {"convertir", "relecture", "mise_en_forme", "plans",
            "reglages", "aide"} <= set(fenetre.pages)
    # … plus l'écran Traitement, hors barre latérale (atteint depuis « Lancer »).
    assert "traitement" in fenetre.pages
