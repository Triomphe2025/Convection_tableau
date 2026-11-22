"""Messages d'étape (étape 2C-4, retouche 3) : petite carte en bas à droite qui glisse en 300 ms,
reste 3 s, puis s'efface. File d'un message à la fois.

La carte (fond sureleve, trait, rayon carte, icône) est ancrée en bas à droite — jamais par-dessus
l'en-tête. Le glissement respecte « animations réduites » (apparition immédiate, sans glisser).
L'écran caché vide la file. Durées : jeton message_etape_affiche (3 s) et passage_ecran (300 ms).
"""
from PySide6.QtCore import QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from trios_qt import animations, icones, theme


class MessagesEtape(QWidget):
    """Messages d'étape en file, un à la fois, dans une carte glissante en bas à droite."""

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._duree = int(self._jetons["mouvement_ms"]["message_etape_affiche"])
        self._duree_glissement = int(self._jetons["mouvement_ms"]["passage_ecran"])
        self._marge = 16
        self._file: list[str] = []
        self._courant = ""

        self.carte = QFrame(self)
        self.carte.setObjectName("carte_message")
        rangee = QHBoxLayout(self.carte)
        rangee.setContentsMargins(12, 9, 14, 9)
        rangee.setSpacing(9)
        self._icone = QLabel(self.carte)
        taille = int(self._jetons["tailles_texte_px"]["titre_bloc"])
        self._pixmap = icones.charger_icone(
            "info", self._jetons["couleurs"]["texte_secondaire"], taille).pixmap(taille, taille)
        self._icone.setPixmap(self._pixmap)
        self._texte = QLabel(self.carte)
        self._texte.setObjectName("message_texte")
        rangee.addWidget(self._icone, 0, Qt.AlignmentFlag.AlignVCenter)
        rangee.addWidget(self._texte, 0, Qt.AlignmentFlag.AlignVCenter)
        self.carte.setVisible(False)

        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.setInterval(self._duree)
        self._minuteur.timeout.connect(self._afficher_suivant)
        self._anim = QPropertyAnimation(self.carte, b"pos", self)
        self._anim.setDuration(self._duree_glissement)
        self._anim.setEasingCurve(animations.courbe_depuis_jetons(self._jetons["courbe_standard"]))

    def afficher(self, message: str) -> None:
        self._file.append(message)
        if not self._courant:
            self._prochain()

    def _prochain(self) -> None:
        if self._file:
            self._courant = self._file.pop(0)
            self._texte.setText(self._courant)
            self.carte.adjustSize()
            self.carte.setVisible(True)
            self._glisser()
            self._minuteur.start()
        else:
            self._courant = ""
            self.carte.setVisible(False)
            self._minuteur.stop()
            self._anim.stop()

    def _position_finale(self) -> QPoint:
        x = max(self._marge, self.width() - self.carte.width() - self._marge)
        y = max(self._marge, self.height() - self.carte.height() - self._marge)
        return QPoint(x, y)

    def _glisser(self) -> None:
        finale = self._position_finale()
        if animations.animations_reduites():
            self.carte.move(finale)
            return
        depart = QPoint(finale.x(), finale.y() + self.carte.height() + self._marge)
        self.carte.move(depart)
        self._anim.stop()
        self._anim.setStartValue(depart)
        self._anim.setEndValue(finale)
        self._anim.start()

    def _afficher_suivant(self) -> None:
        self._prochain()

    def message_courant(self) -> str:
        return self._courant

    def est_visible(self) -> bool:
        return bool(self._courant)

    def en_glissement(self) -> bool:
        from PySide6.QtCore import QAbstractAnimation
        return self._anim.state() == QAbstractAnimation.State.Running

    def duree_ms(self) -> int:
        return self._duree

    def duree_glissement_ms(self) -> int:
        return self._duree_glissement

    def minuteur_actif(self) -> bool:
        return self._minuteur.isActive()

    def icone_pixmap(self):
        return self._pixmap

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._courant:
            self.carte.move(self._position_finale())

    def hideEvent(self, event):
        super().hideEvent(event)
        self._file.clear()
        self._courant = ""
        self.carte.setVisible(False)
        self._minuteur.stop()
        self._anim.stop()
