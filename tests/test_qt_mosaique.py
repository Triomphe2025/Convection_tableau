"""Étape 2C-2 — mosaïque des pages : une case par page, peinte en une passe, pulsation en lecture.

On teste la logique (états par case, géométrie case↔point, infobulle, couleur par état) et le
cycle de la pulsation : active quand une case est en lecture, arrêtée si l'écran est caché ou si
les animations sont réduites. Le rendu lui-même est visuel (règle 07 : capture).
"""
import pytest

pytest.importorskip("PySide6")

from trios_qt import animations, theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.mosaique import Mosaique  # noqa: E402


@pytest.fixture
def mosaique(qtbot):
    creer_application([])
    animations.definir_reduction(False)   # déterministe : les timers peuvent démarrer
    m = Mosaique()
    qtbot.addWidget(m)
    yield m
    animations.reinitialiser()


@pytest.fixture(scope="module")
def jetons():
    return theme.charger_jetons()


class TestMosaiquePages:

    def test_pages_toutes_en_attente(self, mosaique):
        mosaique.definir_pages(6)
        assert mosaique.nombre_pages() == 6
        assert all(mosaique.etat(i) == Mosaique.ATTENTE for i in range(6))

    def test_definir_etat(self, mosaique):
        mosaique.definir_pages(4)
        mosaique.definir_etat(2, Mosaique.LUE)
        assert mosaique.etat(2) == Mosaique.LUE
        assert mosaique.etat(0) == Mosaique.ATTENTE

    def test_index_hors_bornes_ignore(self, mosaique):
        mosaique.definir_pages(3)
        mosaique.definir_etat(9, Mosaique.LUE)   # ne doit pas lever
        assert mosaique.nombre_pages() == 3

    def test_infobulle_memorisee(self, mosaique):
        mosaique.definir_pages(3)
        mosaique.definir_etat(1, Mosaique.A_RELIRE, infobulle="page 12 — 2 à relire")
        assert "à relire" in mosaique.infobulle(1)


class TestMosaiqueGeometrie:

    def test_colonnes_depuis_largeur(self, mosaique):
        mosaique.definir_pages(20)
        pas = Mosaique.TAILLE_TUILE + Mosaique.ECART
        mosaique.resize(5 * pas, 4 * pas)
        assert mosaique.colonnes() == 5

    def test_index_a_point(self, mosaique):
        mosaique.definir_pages(20)
        pas = Mosaique.TAILLE_TUILE + Mosaique.ECART
        mosaique.resize(5 * pas, 4 * pas)
        from PySide6.QtCore import QPoint
        # Centre de la case colonne 2, rangée 1 → index 1*5 + 2 = 7.
        p = QPoint(2 * pas + Mosaique.TAILLE_TUILE // 2, 1 * pas + Mosaique.TAILLE_TUILE // 2)
        assert mosaique.index_a(p) == 7

    def test_index_a_point_hors_cases(self, mosaique):
        mosaique.definir_pages(3)
        from PySide6.QtCore import QPoint
        assert mosaique.index_a(QPoint(99999, 99999)) == -1

    def test_hauteur_une_rangee_pour_15_pages(self, mosaique):
        pas = Mosaique.TAILLE_TUILE + Mosaique.ECART
        mosaique.resize(20 * pas, 200)          # 20 colonnes disponibles
        mosaique.definir_pages(15)
        assert mosaique.rangees() == 1
        assert mosaique.hauteur_rangees(10) == pas

    def test_hauteur_plafonnee_a_10_rangees(self, mosaique):
        pas = Mosaique.TAILLE_TUILE + Mosaique.ECART
        mosaique.resize(20 * pas, 200)
        mosaique.definir_pages(500)             # 25 rangées → plafonné à 10
        assert mosaique.rangees() == 25
        assert mosaique.hauteur_rangees(10) == 10 * pas


class TestMosaiqueCouleur:

    def test_couleur_attente(self, mosaique, jetons):
        attendu = jetons["couleurs"]["tuile_attente"].lower()
        assert mosaique.couleur_etat(Mosaique.ATTENTE).name().lower() == attendu

    def test_couleur_a_relire(self, mosaique, jetons):
        attendu = jetons["couleurs"]["a_relire"].lower()
        assert mosaique.couleur_etat(Mosaique.A_RELIRE).name().lower() == attendu

    def test_couleur_natif(self, mosaique, jetons):
        attendu = jetons["couleurs"]["texte_natif"].lower()
        assert mosaique.couleur_etat(Mosaique.NATIF).name().lower() == attendu


class TestMosaiquePulsation:

    def test_pulsation_active_en_lecture(self, mosaique):
        mosaique.definir_pages(3)
        mosaique.definir_etat(0, Mosaique.LECTURE)
        assert mosaique.est_active() is True

    def test_pulsation_s_arrete_sans_lecture(self, mosaique):
        mosaique.definir_pages(3)
        mosaique.definir_etat(0, Mosaique.LECTURE)
        mosaique.definir_etat(0, Mosaique.LUE)
        assert mosaique.est_active() is False

    def test_pulsation_coupee_si_cachee(self, mosaique):
        mosaique.definir_pages(3)
        mosaique.show()
        mosaique.definir_etat(0, Mosaique.LECTURE)
        assert mosaique.est_active() is True
        mosaique.hide()
        assert mosaique.est_active() is False

    def test_pulsation_jamais_si_animations_reduites(self, mosaique):
        animations.definir_reduction(True)
        mosaique.definir_pages(3)
        mosaique.definir_etat(0, Mosaique.LECTURE)
        assert mosaique.est_active() is False


class TestMosaiqueRendu:

    def test_peint_sans_erreur(self, mosaique):
        mosaique.definir_pages(12)
        mosaique.definir_etat(0, Mosaique.LUE)
        mosaique.definir_etat(1, Mosaique.LECTURE)
        mosaique.definir_etat(2, Mosaique.NATIF)
        mosaique.definir_etat(3, Mosaique.A_RELIRE)
        mosaique.resize(200, 80)
        assert not mosaique.grab().isNull()
