"""Étape 2C-4 — astuces qui tournent toutes les 7 s (jeton astuce_rotation).

On teste la rotation (cyclique) et le cycle du minuteur : actif à l'écran, arrêté si caché ou si
les animations sont réduites. Le texte des astuces est de la copie d'interface, pas une donnée.
"""
import pytest

pytest.importorskip("PySide6")

from trios_qt import animations, theme  # noqa: E402
from trios_qt.astuces import Astuces  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402


@pytest.fixture
def astuces(qtbot):
    creer_application([])
    animations.definir_reduction(False)
    a = Astuces(["Astuce A", "Astuce B", "Astuce C"])
    qtbot.addWidget(a)
    yield a
    animations.reinitialiser()


class TestAstucesRotation:

    def test_texte_initial(self, astuces):
        assert astuces.texte_courant() == "Astuce A"

    def test_avancer_cycle(self, astuces):
        assert astuces.avancer() == "Astuce B"
        assert astuces.avancer() == "Astuce C"
        assert astuces.avancer() == "Astuce A"      # boucle

    def test_intervalle_est_le_jeton(self, astuces):
        attendu = int(theme.charger_jetons()["mouvement_ms"]["astuce_rotation"])
        assert astuces.intervalle_ms() == attendu

    def test_label_suit_le_texte(self, astuces):
        astuces.avancer()
        assert astuces.text() == "Astuce B"


class TestAstucesMinuteur:

    def test_actif_apres_affichage(self, astuces):
        astuces.show()
        assert astuces.est_active() is True

    def test_coupe_si_cache(self, astuces):
        astuces.show()
        astuces.hide()
        assert astuces.est_active() is False

    def test_jamais_si_reduit(self, astuces):
        animations.definir_reduction(True)
        astuces.show()
        assert astuces.est_active() is False

    def test_une_seule_astuce_pas_de_rotation(self, qtbot):
        creer_application([])
        animations.definir_reduction(False)
        une = Astuces(["Seule"])
        qtbot.addWidget(une)
        une.show()
        assert une.est_active() is False
        animations.reinitialiser()
