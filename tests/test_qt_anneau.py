"""Étape 2C-1 — anneau d'avancement peint : valeur bornée, %, angle de balayage, état de fin.

Le rendu (arc, coche dessinée) est visuel (règle 07 : capture) ; ici on teste la logique qui
pilote le rendu : bornage de la valeur, texte du pourcentage, angle de l'arc, bascule de fin et
couleur d'anneau (rose en cours, succès à la fin). Les couleurs attendues sont lues dans les
mêmes jetons que le widget — jamais recopiées dans le test.
"""
import pytest

pytest.importorskip("PySide6")

from trios_qt import theme  # noqa: E402
from trios_qt.anneau import Anneau  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402


@pytest.fixture
def anneau(qtbot):
    creer_application([])
    a = Anneau()
    qtbot.addWidget(a)
    return a


@pytest.fixture(scope="module")
def jetons():
    return theme.charger_jetons()


class TestAnneauValeur:

    def test_valeur_initiale_nulle(self, anneau):
        assert anneau.valeur() == 0.0

    def test_definir_valeur_simple(self, anneau):
        anneau.definir_valeur(0.47)
        assert anneau.valeur() == pytest.approx(0.47)

    def test_valeur_bornee_en_bas(self, anneau):
        anneau.definir_valeur(-0.5)
        assert anneau.valeur() == 0.0

    def test_valeur_bornee_en_haut(self, anneau):
        anneau.definir_valeur(1.4)
        assert anneau.valeur() == 1.0


class TestAnneauPourcentage:

    def test_texte_zero(self, anneau):
        assert anneau.pourcentage_texte() == "0 %"

    def test_texte_arrondi(self, anneau):
        anneau.definir_valeur(0.473)
        assert anneau.pourcentage_texte() == "47 %"

    def test_texte_plein(self, anneau):
        anneau.definir_valeur(1.0)
        assert anneau.pourcentage_texte() == "100 %"


class TestAnneauAngle:

    def test_angle_nul(self, anneau):
        assert anneau.angle_balayage_16() == 0

    def test_angle_quart(self, anneau):
        anneau.definir_valeur(0.25)
        assert anneau.angle_balayage_16() == 90 * 16

    def test_angle_plein(self, anneau):
        anneau.definir_valeur(1.0)
        assert anneau.angle_balayage_16() == 360 * 16


class TestAnneauFin:

    def test_en_cours_non_termine(self, anneau):
        assert anneau.est_termine() is False

    def test_terminer_passe_a_cent(self, anneau):
        anneau.definir_valeur(0.3)
        anneau.terminer()
        assert anneau.est_termine() is True
        assert anneau.valeur() == 1.0
        assert anneau.pourcentage_texte() == "100 %"

    def test_reinitialiser_efface_la_fin(self, anneau):
        anneau.terminer()
        anneau.reinitialiser()
        assert anneau.est_termine() is False
        assert anneau.valeur() == 0.0


class TestAnneauCouleur:

    def test_couleur_en_cours_rose(self, anneau, jetons):
        attendu = jetons["couleurs"]["rose_trios"].lower()
        assert anneau.couleur_progression().name().lower() == attendu

    def test_couleur_fin_succes(self, anneau, jetons):
        anneau.terminer()
        attendu = jetons["couleurs"]["succes"].lower()
        assert anneau.couleur_progression().name().lower() == attendu


class TestAnneauRendu:

    def test_peint_sans_erreur_en_cours(self, anneau):
        anneau.resize(120, 120)
        anneau.definir_valeur(0.6)
        assert not anneau.grab().isNull()

    def test_peint_sans_erreur_termine(self, anneau):
        anneau.resize(120, 120)
        anneau.terminer()
        assert not anneau.grab().isNull()
