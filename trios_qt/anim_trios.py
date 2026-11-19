"""Logo « trios » animé (pulsation douce, 3,6 s en boucle) ; respecte réduit / écran caché."""
from PySide6.QtCore import QAbstractAnimation, Qt, QVariantAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from trios_qt import animations

DUREE_MS = 3600


class AnimationTrios(QWidget):
    """Mot-marque « trios » qui respire ; respecte le réglage « animations réduites »."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("anim_trios")
        self._mot = QLabel("trios", self)
        self._mot.setObjectName("anim_trios_glyphe")
        self._mot.setAlignment(Qt.AlignCenter)
        self._opacite = QGraphicsOpacityEffect(self._mot)
        self._mot.setGraphicsEffect(self._opacite)

        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.addWidget(self._mot)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(DUREE_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._peindre)
        self._peindre(0.0)

    def _peindre(self, valeur):
        # Triangle 1 → 0 → 1 : le mot respire sans saut à la reprise de boucle.
        self._opacite.setOpacity(0.5 + 0.5 * abs(1.0 - 2.0 * valeur))

    def duree_ms(self):
        return self._anim.duration()

    def est_active(self):
        return self._anim.state() == QAbstractAnimation.Running

    def demarrer(self):
        """Démarre l'animation, sauf si les animations sont réduites ; rend True si lancée."""
        if animations.animations_reduites():
            return False
        if not self.est_active():
            self._anim.start()
        return True

    def arreter(self):
        self._anim.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.demarrer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.arreter()
