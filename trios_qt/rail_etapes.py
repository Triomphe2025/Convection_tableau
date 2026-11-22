"""Rail des 4 étapes de la conversion (étape 2C-3) : analyse, lecture, contrôles, classeur.

L'étape courante vient de l'événement PHASE : les étapes précédentes passent « fait », la
courante « en_cours », les suivantes « a_faire ». La barre se remplit à la part d'étapes faites.
Peint en une passe ; couleurs des jetons.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from trios_qt import theme

_LIBELLES = {
    "analyse": "Analyse", "lecture": "Lecture", "controles": "Contrôles", "excel": "Classeur",
}


class RailEtapes(QWidget):
    """Rail des 4 étapes + barre ; definir_phase(etat) / terminer() pilotent l'avancement."""

    CLES = ("analyse", "lecture", "controles", "excel")

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._courante: str | None = None
        self._termine = False
        self.setMinimumHeight(52)

    def definir_phase(self, etat: str) -> None:
        if etat not in self.CLES:
            return
        self._courante = etat
        self._termine = False
        self.update()

    def phase_courante(self) -> str | None:
        return None if self._termine else self._courante

    def _index_courant(self) -> int:
        return self.CLES.index(self._courante) if self._courante in self.CLES else -1

    def etat_etape(self, cle: str) -> str:
        if self._termine:
            return "fait"
        i = self.CLES.index(cle)
        courant = self._index_courant()
        if courant < 0 or i > courant:
            return "a_faire"
        return "en_cours" if i == courant else "fait"

    def fraction(self) -> float:
        faites = sum(1 for c in self.CLES if self.etat_etape(c) == "fait")
        return faites / len(self.CLES)

    def terminer(self) -> None:
        self._termine = True
        self.update()

    def libelle(self, cle: str) -> str:
        return _LIBELLES.get(cle, cle)

    def _couleur(self, etat: str) -> QColor:
        c = self._jetons["couleurs"]
        return QColor({"fait": c["succes"], "en_cours": c["rose_trios"]}.get(etat, c["trait"]))

    _MARGE = 24

    def _geometrie(self):
        n = len(self.CLES)
        largeur = max(1, self.width() - 2 * self._MARGE)
        return self._MARGE, self.height() * 0.42, largeur, largeur / (n - 1)

    def rectangles_libelles(self):
        """Pour chaque étape : (rectangle du libellé, alignement). Les extrémités sont alignées
        sur le bord (gauche pour la 1re, droite pour la dernière) pour ne jamais dépasser."""
        marge, y, _largeur, pas = self._geometrie()
        yb, h = y + 10, 18.0
        bord = 2.0
        rectangles = []
        dernier = len(self.CLES) - 1
        for i in range(len(self.CLES)):
            x = marge + i * pas
            if i == 0:
                rectangles.append((QRectF(bord, yb, pas, h), Qt.AlignmentFlag.AlignLeft))
            elif i == dernier:
                rectangles.append((QRectF(self.width() - bord - pas, yb, pas, h),
                                   Qt.AlignmentFlag.AlignRight))
            else:
                rectangles.append((QRectF(x - pas / 2, yb, pas, h), Qt.AlignmentFlag.AlignHCenter))
        return rectangles

    def paintEvent(self, _evenement):
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        marge, y, largeur, pas = self._geometrie()

        peintre.setPen(QPen(QColor(c["trait"]), 3))
        peintre.drawLine(int(marge), int(y), int(marge + largeur), int(y))
        if self.fraction() > 0:
            peintre.setPen(QPen(QColor(c["succes"]), 3))
            peintre.drawLine(int(marge), int(y), int(marge + largeur * self.fraction()), int(y))

        rectangles = self.rectangles_libelles()
        for i, cle in enumerate(self.CLES):
            x = marge + i * pas
            etat = self.etat_etape(cle)
            rayon = 7 if etat == "en_cours" else 5
            peintre.setPen(Qt.PenStyle.NoPen)
            peintre.setBrush(self._couleur(etat))
            peintre.drawEllipse(QRectF(x - rayon, y - rayon, 2 * rayon, 2 * rayon))
            couleur_texte = c["texte"] if etat != "a_faire" else c["texte_discret"]
            peintre.setPen(QColor(couleur_texte))
            boite, alignement = rectangles[i]
            peintre.drawText(boite, alignement | Qt.AlignmentFlag.AlignVCenter, self.libelle(cle))
        peintre.end()
