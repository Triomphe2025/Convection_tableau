"""Animation « trios » du dépôt : feuille qui entre, tableau qui sort (3,6 s, en boucle)."""
from PySide6.QtCore import QAbstractAnimation, Qt, QVariantAnimation
from PySide6.QtWidgets import (QGraphicsOpacityEffect, QLabel, QStackedLayout,
                               QWidget)

from trios_qt import animations

DUREE_MS = 3600


class AnimationTrios(QWidget):
    """Fond animé décoratif ; respecte le réglage « animations réduites » et l'écran caché."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("anim_trios")
        self._feuille = QLabel("\U0001F4C4", self)   # la feuille qui entre
        self._tableau = QLabel("▦", self)        # le tableau qui sort
        for etiquette in (self._feuille, self._tableau):
            etiquette.setAlignment(Qt.AlignCenter)
            etiquette.setObjectName("anim_trios_glyphe")
        self._opacite_feuille = QGraphicsOpacityEffect(self._feuille)
        self._opacite_tableau = QGraphicsOpacityEffect(self._tableau)
        self._feuille.setGraphicsEffect(self._opacite_feuille)
        self._tableau.setGraphicsEffect(self._opacite_tableau)

        pile = QStackedLayout(self)
        pile.setStackingMode(QStackedLayout.StackAll)
        pile.addWidget(self._tableau)
        pile.addWidget(self._feuille)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(DUREE_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._peindre)
        self._peindre(0.0)

    def _peindre(self, valeur):
        # La feuille s'efface pendant que le tableau apparaît (fondu croisé en boucle).
        self._opacite_feuille.setOpacity(1.0 - valeur)
        self._opacite_tableau.setOpacity(valeur)

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
