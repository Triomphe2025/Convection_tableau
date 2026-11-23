"""Mosaïque des pages (étape 2C-2) : une case par page, peinte en UNE passe (pas un widget par
case), état et infobulle par case, pulsation des cases en lecture.

La pulsation est portée par une seule animation en boucle (jeton pulsation_page) ; elle respecte
le réglage « animations réduites » et s'arrête quand l'écran est caché (showEvent / hideEvent),
comme AnimationTrios. Les couleurs viennent des jetons.
"""
from PySide6.QtCore import QAbstractAnimation, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QToolTip, QWidget

from trios_qt import animations, theme


class Mosaique(QWidget):
    """Grille d'états de pages ; definir_pages / definir_etat pilotent le rendu et la pulsation."""

    ATTENTE = "attente"
    LECTURE = "lecture"
    LUE = "lue"
    NATIF = "natif"
    A_RELIRE = "a_relire"
    DANS_LOT = "dans_lot"   # écran lot : page envoyée dans un lot, pas encore lue
    TAILLE_TUILE = 14   # px, côté d'une case
    ECART = 4           # px, blanc entre deux cases

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._etats: list[str] = []
        self._infobulles: list[str] = []
        self._phase = 0.0
        self.setMouseTracking(True)   # pour l'infobulle au survol
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(int(self._jetons["mouvement_ms"]["pulsation_page"]))
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._sur_phase)

    def definir_pages(self, n: int) -> None:
        self._etats = [self.ATTENTE] * int(n)
        self._infobulles = [""] * int(n)
        self._reevaluer_pulsation()
        self.update()

    def nombre_pages(self) -> int:
        return len(self._etats)

    def definir_etat(self, i: int, etat: str, infobulle: str | None = None) -> None:
        if not 0 <= i < len(self._etats):
            return
        self._etats[i] = etat
        if infobulle is not None:
            self._infobulles[i] = infobulle
        self._reevaluer_pulsation()
        self.update()

    def etat(self, i: int) -> str:
        return self._etats[i] if 0 <= i < len(self._etats) else ""

    def infobulle(self, i: int) -> str:
        return self._infobulles[i] if 0 <= i < len(self._infobulles) else ""

    def colonnes(self) -> int:
        pas = self.TAILLE_TUILE + self.ECART
        return max(1, (self.width() + self.ECART) // pas)

    def rangees(self) -> int:
        import math
        return math.ceil(len(self._etats) / self.colonnes()) if self._etats else 0

    def hauteur_rangees(self, max_rangees: int = 10) -> int:
        """Hauteur juste nécessaire pour les pages (1 rangée pour 15 pages), plafonnée."""
        pas = self.TAILLE_TUILE + self.ECART
        r = min(max(1, self.rangees()), max_rangees)
        return int(r * pas)

    def index_a(self, point) -> int:
        pas = self.TAILLE_TUILE + self.ECART
        x, y = point.x(), point.y()
        if x < 0 or y < 0 or x % pas >= self.TAILLE_TUILE or y % pas >= self.TAILLE_TUILE:
            return -1
        colonne = x // pas
        if colonne >= self.colonnes():
            return -1
        index = (y // pas) * self.colonnes() + colonne
        return int(index) if 0 <= index < len(self._etats) else -1

    def couleur_etat(self, etat: str) -> QColor:
        c = self._jetons["couleurs"]
        table = {
            self.ATTENTE: c["tuile_attente"], self.LECTURE: c["rose_trios"],
            self.LUE: c["tuile_lue"], self.NATIF: c["texte_natif"], self.A_RELIRE: c["a_relire"],
            self.DANS_LOT: c["lot_en_cours"],
        }
        return QColor(table.get(etat, c["tuile_attente"]))

    def _a_lecture(self) -> bool:
        return any(e == self.LECTURE for e in self._etats)

    def est_active(self) -> bool:
        return self._anim.state() == QAbstractAnimation.State.Running

    def demarrer(self) -> bool:
        """Lance la pulsation si une case est en lecture et que les animations sont permises."""
        if animations.animations_reduites() or not self._a_lecture():
            return False
        if not self.est_active():
            self._anim.start()
        return True

    def arreter(self) -> None:
        self._anim.stop()

    def _reevaluer_pulsation(self) -> None:
        if self._a_lecture():
            self.demarrer()
        else:
            self.arreter()

    def _sur_phase(self, valeur) -> None:
        # Triangle 1 → 0 → 1 : respiration sans saut à la reprise de boucle.
        self._phase = 0.45 + 0.55 * abs(1.0 - 2.0 * float(valeur))
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._reevaluer_pulsation()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.arreter()

    def event(self, evenement):
        if evenement.type() == evenement.Type.ToolTip:
            index = self.index_a(evenement.pos())
            texte = self.infobulle(index) if index >= 0 else ""
            if texte:
                QToolTip.showText(evenement.globalPos(), texte, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(evenement)

    def paintEvent(self, _evenement):
        pas = self.TAILLE_TUILE + self.ECART
        colonnes = self.colonnes()
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rayon = 3.0
        for i, etat in enumerate(self._etats):
            ligne, colonne = divmod(i, colonnes)
            couleur = QColor(self.couleur_etat(etat))
            if etat == self.LECTURE and self.est_active():
                couleur.setAlphaF(self._phase)   # la case en lecture respire
            boite = QRectF(colonne * pas, ligne * pas, self.TAILLE_TUILE, self.TAILLE_TUILE)
            peintre.setPen(Qt.PenStyle.NoPen)
            peintre.setBrush(couleur)
            peintre.drawRoundedRect(boite, rayon, rayon)
        peintre.end()
