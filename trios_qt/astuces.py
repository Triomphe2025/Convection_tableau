"""Astuces qui tournent (étape 2C-4, retouche 4) : carte avec icône ampoule et petit titre
« Astuce » ; une astuce change toutes les 7 s (jeton astuce_rotation), en fondu.

Minuteur unique de rotation ; le fondu et la rotation respectent « animations réduites » et
s'arrêtent quand l'écran est caché. Avec une seule astuce il n'y a pas de rotation. Le texte est
de la copie d'interface (conseils d'usage).
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from trios_qt import animations, icones, theme

_ASTUCES_DEFAUT = (
    "Vérifie les cases orange : ce sont les points à relire après la conversion.",
    "Le mode économique (lot) revient 50 % moins cher au-delà de 100 pages.",
    "Tu peux relancer un document : les pages déjà lues ne sont ni relues ni repayées.",
    "Les pages à texte natif sont lues sans appel au modèle, donc gratuitement.",
    "À la fin, « Voir le résumé » ouvre le classeur et les pages à relire.",
)


class Astuces(QWidget):
    """Carte d'astuces qui défilent en fondu ; demarrer/arreter liés à l'affichage de l'écran."""

    def __init__(self, astuces=None, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._astuces = list(astuces) if astuces is not None else list(_ASTUCES_DEFAUT)
        self._i = 0
        self._intervalle = int(self._jetons["mouvement_ms"]["astuce_rotation"])

        self.carte = _carte(self)
        colonne = QVBoxLayout(self.carte)
        colonne.setContentsMargins(14, 11, 14, 12)
        colonne.setSpacing(5)
        entete = QHBoxLayout()
        entete.setSpacing(7)
        taille = int(self._jetons["tailles_texte_px"]["aide"]) + 2
        self._pixmap = icones.charger_icone(
            "ampoule", self._jetons["couleurs"]["a_relire"], taille).pixmap(taille, taille)
        self._icone = QLabel(self.carte)
        self._icone.setPixmap(self._pixmap)
        self._titre = QLabel("Astuce", self.carte)
        self._titre.setObjectName("astuce_titre")
        entete.addWidget(self._icone, 0, Qt.AlignmentFlag.AlignVCenter)
        entete.addWidget(self._titre, 0, Qt.AlignmentFlag.AlignVCenter)
        entete.addStretch(1)
        self._texte = QLabel(self.carte)
        self._texte.setObjectName("astuce_texte")
        self._texte.setWordWrap(True)
        colonne.addLayout(entete)
        colonne.addWidget(self._texte)

        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.addWidget(self.carte)

        self._effet, self._fondu = animations.effet_opacite(self._texte)
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(self._intervalle)
        self._minuteur.timeout.connect(self.avancer)
        if self._astuces:
            self._texte.setText(self._astuces[0])

    def texte_courant(self) -> str:
        return self._astuces[self._i] if self._astuces else ""

    def texte_affiche(self) -> str:
        return self._texte.text()

    def titre_texte(self) -> str:
        return self._titre.text()

    def icone_pixmap(self):
        return self._pixmap

    def avancer(self) -> str:
        if not self._astuces:
            return ""
        self._i = (self._i + 1) % len(self._astuces)
        self._texte.setText(self._astuces[self._i])
        if not animations.animations_reduites():
            self._fondu.stop()
            self._fondu.setStartValue(0.0)
            self._fondu.setEndValue(1.0)
            self._fondu.start()
        return self._astuces[self._i]

    def en_fondu(self) -> bool:
        from PySide6.QtCore import QAbstractAnimation
        return self._fondu.state() == QAbstractAnimation.State.Running

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
        self._fondu.stop()


def _carte(parent):
    from PySide6.QtWidgets import QFrame
    cadre = QFrame(parent)
    cadre.setObjectName("carte_astuce")
    return cadre
