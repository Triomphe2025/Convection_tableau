"""Étape 2C-3 — rail des 4 étapes (analyse, lecture, contrôles, classeur) + barre d'avancement.

On teste la logique : l'étape courante et sa barre d'après l'événement PHASE, les étapes passées
marquées « fait », la fin. Les libellés restent lisibles (jamais l'état technique brut).
"""
import pytest

pytest.importorskip("PySide6")

from trios_qt.application import creer_application  # noqa: E402
from trios_qt.rail_etapes import RailEtapes  # noqa: E402


@pytest.fixture
def rail(qtbot):
    creer_application([])
    r = RailEtapes()
    qtbot.addWidget(r)
    return r


class TestRailPhase:

    def test_depart_tout_a_faire(self, rail):
        assert all(rail.etat_etape(c) == "a_faire" for c in RailEtapes.CLES)
        assert rail.fraction() == 0.0

    def test_phase_lecture_marque_analyse_faite(self, rail):
        rail.definir_phase("lecture")
        assert rail.etat_etape("analyse") == "fait"
        assert rail.etat_etape("lecture") == "en_cours"
        assert rail.etat_etape("controles") == "a_faire"
        assert rail.phase_courante() == "lecture"

    def test_fraction_progresse(self, rail):
        rail.definir_phase("analyse")
        assert rail.fraction() == 0.0
        rail.definir_phase("excel")
        assert rail.fraction() == pytest.approx(0.75)

    def test_phase_inconnue_ignoree(self, rail):
        rail.definir_phase("lecture")
        rail.definir_phase("mystere")
        assert rail.phase_courante() == "lecture"

    def test_terminer_tout_fait(self, rail):
        rail.definir_phase("lecture")
        rail.terminer()
        assert all(rail.etat_etape(c) == "fait" for c in RailEtapes.CLES)
        assert rail.fraction() == 1.0
        assert rail.phase_courante() is None


class TestRailLibelles:

    def test_libelles_lisibles(self, rail):
        textes = [rail.libelle(c) for c in RailEtapes.CLES]
        assert "analyse" not in textes          # jamais la clé technique brute
        assert any("Analyse" in t for t in textes)
        assert any("Lecture" in t for t in textes)
        assert "Excel" in textes

    def test_peint_sans_erreur(self, rail):
        rail.definir_phase("controles")
        rail.resize(400, 60)
        assert not rail.grab().isNull()

    def test_segments_dans_le_widget(self, rail):
        # Refonte : 4 segments côte à côte, chacun dans les bornes du widget.
        rail.resize(1120, 60)
        segments = rail.rectangles_segments()
        assert len(segments) == len(RailEtapes.CLES)
        for rect in segments:
            assert rect.left() >= -0.01
            assert rect.right() <= rail.width() + 0.01


class TestRailCouleurs:

    @pytest.fixture(scope="class")
    def jetons(self):
        from trios_qt import theme
        return theme.charger_jetons()

    def test_fait_vert_courant_rose(self, rail, jetons):
        rail.definir_phase("lecture")
        c = jetons["couleurs"]
        assert rail.couleur_segment("analyse").name().lower() == c["succes"].lower()
        assert rail.couleur_segment("lecture").name().lower() == c["rose_trios"].lower()
        assert rail.couleur_segment("controles").name().lower() == c["trait"].lower()

    def test_fin_tout_vert(self, rail, jetons):
        rail.definir_phase("lecture")
        rail.terminer()
        succes = jetons["couleurs"]["succes"].lower()
        assert all(rail.couleur_segment(c).name().lower() == succes for c in RailEtapes.CLES)


class TestRailComptes:

    def test_compte_par_segment(self, rail):
        rail.definir_compte("analyse", "720 p.")
        rail.definir_compte("lecture", "700 / 720")
        assert rail.compte("analyse") == "720 p."
        assert rail.compte("lecture") == "700 / 720"

    def test_compte_cle_inconnue_ignoree(self, rail):
        rail.definir_compte("mystere", "x")
        assert rail.compte("mystere") == ""
