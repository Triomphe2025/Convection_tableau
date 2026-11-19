"""Étape 3 — drapeau « réduire les animations » et fondu de passage d'écran."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget  # noqa: E402

from trios_qt import animations  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402


@pytest.fixture(autouse=True)
def _reinitialiser_drapeau():
    yield
    animations.reinitialiser()


def test_courbe_depuis_jetons_passe_par_0_et_1():
    courbe = animations.courbe_depuis_jetons("cubic-bezier(0.2, 0.8, 0.2, 1)")
    assert courbe.valueForProgress(0.0) == pytest.approx(0.0, abs=1e-6)
    assert courbe.valueForProgress(1.0) == pytest.approx(1.0, abs=1e-6)
    # Courbe accélérée : à mi-parcours elle est déjà au-delà de la moitié (≠ linéaire).
    assert courbe.valueForProgress(0.5) > 0.5


def test_drapeau_force_est_memorise():
    animations.definir_reduction(True)
    assert animations.animations_reduites() is True
    animations.definir_reduction(False)
    assert animations.animations_reduites() is False


def test_fondu_reduit_ne_cree_pas_d_animation(qtbot):
    creer_application([])
    animations.definir_reduction(True)
    widget = QWidget()
    qtbot.addWidget(widget)
    assert animations.fondu_entree(widget, 300) is None
    assert widget.graphicsEffect() is None


def test_fondu_actif_cree_une_animation_de_la_bonne_duree(qtbot):
    creer_application([])
    animations.definir_reduction(False)
    widget = QWidget()
    qtbot.addWidget(widget)
    anim = animations.fondu_entree(widget, 300)
    assert anim is not None
    assert anim.duration() == 300
    assert anim.startValue() == pytest.approx(0.0)
    assert anim.endValue() == pytest.approx(1.0)
