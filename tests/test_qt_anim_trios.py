"""Étape 2 — animation « trios » : durée 3,6 s, arrêtée si animations réduites ou écran caché."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QHideEvent, QShowEvent  # noqa: E402

from trios_qt import animations  # noqa: E402
from trios_qt.anim_trios import AnimationTrios  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402


@pytest.fixture
def anim(qtbot):
    creer_application([])
    animations.definir_reduction(False)
    w = AnimationTrios()
    qtbot.addWidget(w)
    yield w
    animations.reinitialiser()


class TestAnimationTrios:

    def test_duree_est_3_6_secondes(self, anim):
        assert anim.duree_ms() == 3600

    def test_demarrer_rend_l_animation_active(self, anim):
        assert anim.demarrer() is True
        assert anim.est_active()

    def test_animations_reduites_empechent_le_demarrage(self, anim):
        animations.definir_reduction(True)
        assert anim.demarrer() is False
        assert not anim.est_active()

    def test_s_arrete_quand_l_ecran_est_cache(self, anim):
        anim.demarrer()
        assert anim.est_active()
        anim.hideEvent(QHideEvent())
        assert not anim.est_active()

    def test_redemarre_quand_l_ecran_est_affiche(self, anim):
        anim.showEvent(QShowEvent())
        assert anim.est_active()

    def test_cachee_reste_eteinte_meme_affichee_si_reduite(self, anim):
        animations.definir_reduction(True)
        anim.showEvent(QShowEvent())
        assert not anim.est_active()
