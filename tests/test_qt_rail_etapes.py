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
        assert any("Classeur" in t or "classeur" in t for t in textes)

    def test_peint_sans_erreur(self, rail):
        rail.definir_phase("controles")
        rail.resize(400, 60)
        assert not rail.grab().isNull()

    def test_libelles_ne_depassent_pas_le_widget(self, rail):
        # Retouche 1 : les libellés d'extrémité (Analyse, Classeur) ne doivent pas être coupés.
        from PySide6.QtGui import QFontMetricsF
        rail.resize(460, 64)
        fm = QFontMetricsF(rail.font())
        rectangles = rail.rectangles_libelles()
        assert len(rectangles) == len(RailEtapes.CLES)
        for cle, (rect, _align) in zip(RailEtapes.CLES, rectangles):
            assert rect.left() >= 0
            assert rect.right() <= rail.width()
            assert fm.horizontalAdvance(rail.libelle(cle)) <= rect.width() + 0.5
