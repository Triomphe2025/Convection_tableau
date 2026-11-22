"""Astuces qui tournent (étape 2C-4) : une astuce change toutes les 7 s (jeton astuce_rotation).

Minuteur unique ; respecte « animations réduites » et s'arrête quand l'écran est caché. Avec une
seule astuce il n'y a pas de rotation. Le texte est de la copie d'interface (conseils d'usage).
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel

from trios_qt import animations, theme

_ASTUCES_DEFAUT = (
    "Vérifie les cases orange : ce sont les points à relire après la conversion.",
    "Le mode économique (lot) revient 50 % moins cher au-delà de 100 pages.",
    "Tu peux relancer un document : les pages déjà lues ne sont ni relues ni repayées.",
    "Les pages à texte natif sont lues sans appel au modèle, donc gratuitement.",
    "À la fin, « Voir le résumé » ouvre le classeur et les pages à relire.",
)


class Astuces(QLabel):
    """Label qui fait défiler des astuces ; demarrer/arreter liés à l'affichage de l'écran."""

    def __init__(self, astuces=None, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._astuces = list(astuces) if astuces is not None else list(_ASTUCES_DEFAUT)
        self._i = 0
        self._intervalle = int(self._jetons["mouvement_ms"]["astuce_rotation"])
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(self._intervalle)
        self._minuteur.timeout.connect(self.avancer)
        if self._astuces:
            self.setText(self._astuces[0])

    def texte_courant(self) -> str:
        return self._astuces[self._i] if self._astuces else ""

    def avancer(self) -> str:
        if not self._astuces:
            return ""
        self._i = (self._i + 1) % len(self._astuces)
        self.setText(self._astuces[self._i])
        return self._astuces[self._i]

    def intervalle_ms(self) -> int:
        return self._intervalle

    def est_active(self) -> bool:
        return self._minuteur.isActive()

    def demarrer(self) -> bool:
        if animations.animations_reduites() or len(self._astuces) < 2:
            return False
        self._minuteur.start()
        return True

    def arreter(self) -> None:
        self._minuteur.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.demarrer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.arreter()
