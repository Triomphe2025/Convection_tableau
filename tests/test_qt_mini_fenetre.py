"""Étape 2C-9 — mini-fenêtre : fenêtre outil toujours au premier plan (~440×150) avec anneau,
pages, temps restant, barre à repères des pages à relire, Pause, Agrandir.

On teste l'état des widgets pilotés par les événements, la bascule Pause, le signal Agrandir et
que la progression de la barre des tâches (optionnelle) ne plante jamais.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

import evenements as ev  # noqa: E402
from trios_qt import animations  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.mini_fenetre import MiniFenetre  # noqa: E402


@pytest.fixture
def mini(qtbot):
    creer_application([])
    animations.definir_reduction(False)
    m = MiniFenetre()
    qtbot.addWidget(m)
    yield m
    animations.reinitialiser()


class TestFenetre:

    def test_toujours_au_premier_plan(self, mini):
        flags = mini.windowFlags()
        assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)

    def test_taille_compacte(self, mini):
        assert mini.width() <= 520 and mini.height() <= 220


class TestAvancement:

    def test_page_lue_met_a_jour(self, mini):
        mini.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=5, rang=5, total=20, lignes=4))
        assert mini.anneau.valeur() == pytest.approx(0.25)
        assert "5" in mini.etiquette_pages.text() and "20" in mini.etiquette_pages.text()

    def test_temps_formate(self, mini):
        mini.definir_temps(125)
        assert "2 min" in mini.etiquette_temps.text()   # format maquette « ≈ 2 min »

    def test_fichier_et_etat(self, mini):
        mini.definir_fichier("6A23111PE203_TP2.pdf")
        assert "6A23111PE203_TP2.pdf" in mini.etiquette_fichier.text()
        mini.sur_evenement(ev.Evenement(type=ev.PAGE_DEBUT, page=703, rang=703, total=720))
        assert "703" in mini.etiquette_etat.text()


class TestReperes:

    def test_alerte_ajoute_un_repere(self, mini):
        mini.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=7, rang=7, total=20, lignes=4))
        mini.sur_evenement(ev.Evenement(type=ev.PAGE_ALERTE, page=7, page_imprimee='7',
                                        alertes=['scan dégradé']))
        assert mini.barre.nombre_reperes() == 1

    def test_alerte_compte_a_relire(self, mini):
        mini.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=7, rang=7, total=20, lignes=4))
        mini.sur_evenement(ev.Evenement(type=ev.PAGE_ALERTE, page=7, page_imprimee='7',
                                        alertes=['scan dégradé']))
        assert "1" in mini.etiquette_relire.text()


class TestBoutons:

    def test_pause_puis_reprendre(self, mini, qtbot):
        with qtbot.waitSignal(mini.pause_demande, timeout=1000):
            mini.bouton_pause.click()
        assert mini.en_pause() is True
        with qtbot.waitSignal(mini.reprendre_demande, timeout=1000):
            mini.bouton_pause.click()
        assert mini.en_pause() is False

    def test_agrandir_emet_le_signal(self, mini, qtbot):
        with qtbot.waitSignal(mini.agrandir_demande, timeout=1000):
            mini.bouton_agrandir.click()


class TestBarreTaches:

    def test_progression_barre_taches_ne_plante_pas(self, mini):
        # Appel optionnel (ITaskbarList3) : ne doit jamais lever, même sans COM.
        mini.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=1, rang=1, total=4, lignes=2))
        assert True
