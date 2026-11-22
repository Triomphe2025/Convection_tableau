"""Anneau d'avancement peint (étape 2C-1) : arc proportionnel, pourcentage au centre, coche de fin.

Widget sans minuteur : la valeur (0–1) est posée de l'extérieur par l'écran de traitement. En
cours l'arc est rose (jeton rose_trios) ; à la fin il devient vert (succes) et le centre montre
une coche dessinée au lieu du pourcentage. Toutes les couleurs viennent des jetons.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from trios_qt import theme

_DEPART_HAUT_16 = 90 * 16   # l'arc démarre en haut (midi) et tourne dans le sens horaire


class Anneau(QWidget):
    """Anneau de progression ; definir_valeur / terminer / reinitialiser pilotent le rendu."""

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._valeur = 0.0
        self._termine = False
        self._reussi = True

    def definir_valeur(self, v) -> None:
        self._valeur = max(0.0, min(1.0, float(v)))
        self.update()

    def valeur(self) -> float:
        return self._valeur

    def pourcentage(self) -> int:
        return int(round(self._valeur * 100))

    def pourcentage_texte(self) -> str:
        return f"{self.pourcentage()} %"

    def angle_balayage_16(self) -> int:
        # drawArc attend des 1/16 de degré : 360° = un tour complet pour valeur = 1.
        return int(round(self._valeur * 360 * 16))

    def terminer(self, reussi: bool = True) -> None:
        self._termine = True
        self._reussi = reussi
        self._valeur = 1.0
        self.update()

    def est_termine(self) -> bool:
        return self._termine

    def reinitialiser(self) -> None:
        self._termine = False
        self._reussi = True
        self._valeur = 0.0
        self.update()

    def couleur_progression(self) -> QColor:
        c = self._jetons["couleurs"]
        return QColor(c["succes"] if self._termine else c["rose_trios"])

    def paintEvent(self, _evenement) -> None:
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cote = min(self.width(), self.height())
        epaisseur = max(6.0, cote * 0.09)
        marge = epaisseur / 2 + 1
        boite = QRectF(
            (self.width() - cote) / 2 + marge, (self.height() - cote) / 2 + marge,
            cote - 2 * marge, cote - 2 * marge)

        piste = QPen(QColor(c["trait"]), epaisseur)
        piste.setCapStyle(Qt.PenCapStyle.RoundCap)
        peintre.setPen(piste)
        peintre.drawArc(boite, 0, 360 * 16)

        if self.angle_balayage_16() > 0:
            avance = QPen(self.couleur_progression(), epaisseur)
            avance.setCapStyle(Qt.PenCapStyle.RoundCap)
            peintre.setPen(avance)
            peintre.drawArc(boite, _DEPART_HAUT_16, -self.angle_balayage_16())

        if self._termine and self._reussi:
            self._peindre_coche(peintre, boite)
        else:
            peintre.setPen(QColor(c["texte"]))
            peintre.drawText(boite, Qt.AlignmentFlag.AlignCenter, self.pourcentage_texte())
        peintre.end()

    def _peindre_coche(self, peintre: QPainter, boite: QRectF) -> None:
        from PySide6.QtGui import QPainterPath
        cote = boite.width()
        crayon = QPen(QColor(self._jetons["couleurs"]["succes"]), max(4.0, cote * 0.06))
        crayon.setCapStyle(Qt.PenCapStyle.RoundCap)
        crayon.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        peintre.setPen(crayon)
        cx, cy = boite.center().x(), boite.center().y()
        chemin = QPainterPath()
        chemin.moveTo(cx - cote * 0.18, cy)
        chemin.lineTo(cx - cote * 0.04, cy + cote * 0.14)
        chemin.lineTo(cx + cote * 0.22, cy - cote * 0.16)
        peintre.drawPath(chemin)
