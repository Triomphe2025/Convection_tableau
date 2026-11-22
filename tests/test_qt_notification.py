"""Étape 2C-5 — notification de fin : bulle Windows + clignotement de la barre des tâches.

La décision (signaler seulement hors focus, sous Windows) réutilise interface_helpers ; les appels
système (FlashWindowEx, ITaskbarList3) ne doivent jamais planter quand ils sont indisponibles.
"""
import pytest

pytest.importorskip("PySide6")

from trios_qt import notification  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402


class _FauxTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, titre, message, *a, **k):
        self.messages.append((titre, message))


@pytest.fixture(autouse=True)
def _app():
    creer_application([])


class TestAppelsSysteme:

    def test_flash_sans_fenetre_ne_plante_pas(self):
        assert notification.flash_barre_taches(None) is False

    def test_progression_sans_fenetre_ne_plante_pas(self):
        assert notification.definir_progression_barre(None, 0.5) is False

    def test_notifier_tray_absent(self):
        assert notification.notifier(None, "t", "m") is False

    def test_notifier_tray_present(self):
        tray = _FauxTray()
        assert notification.notifier(tray, "Terminé", "Classeur prêt") is True
        assert tray.messages == [("Terminé", "Classeur prêt")]


class TestSignalerFin:

    def test_pas_de_signal_si_focus(self):
        tray = _FauxTray()
        resultat = notification.signaler_fin(
            None, tray, "Terminé", "ok", a_le_focus=True, plateforme="win32")
        assert resultat is False
        assert tray.messages == []

    def test_signal_si_hors_focus_windows(self):
        tray = _FauxTray()
        resultat = notification.signaler_fin(
            None, tray, "Terminé", "ok", a_le_focus=False, plateforme="win32")
        assert resultat is True
        assert tray.messages == [("Terminé", "ok")]

    def test_pas_de_signal_hors_windows(self):
        tray = _FauxTray()
        resultat = notification.signaler_fin(
            None, tray, "Terminé", "ok", a_le_focus=False, plateforme="linux")
        assert resultat is False
        assert tray.messages == []
