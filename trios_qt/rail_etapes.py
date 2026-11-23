"""Rail des 4 étapes de la conversion (étape 2C-3, refonte 2C) : analyse, lecture, contrôles,
Excel — en 4 segments, chacun avec son libellé, son compte (« 720 p. », « 700 / 720 ») et sa
barre.

L'étape courante vient de l'événement PHASE : les étapes précédentes passent « fait », la
courante « en_cours », les suivantes « a_faire ». Peint en une passe ; couleurs des jetons.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from trios_qt import theme

_LIBELLES = {
    "analyse": "Analyse du PDF", "lecture": "Lecture des pages",
    "controles": "Contrôles", "excel": "Excel",
}


class RailEtapes(QWidget):
    """Rail des 4 étapes en segments ; definir_phase / definir_compte / terminer le pilotent."""

    CLES = ("analyse", "lecture", "controles", "excel")

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._courante: str | None = None
        self._termine = False
        self._comptes: dict[str, str] = {}
        self.setMinimumHeight(44)

    def definir_phase(self, etat: str) -> None:
        if etat not in self.CLES:
            return
        self._courante = etat
        self._termine = False
        self.update()

    def definir_compte(self, cle: str, texte: str) -> None:
        if cle in self.CLES:
            self._comptes[cle] = texte or ""
            self.update()

    def compte(self, cle: str) -> str:
        return self._comptes.get(cle, "")

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

    def couleur_segment(self, cle: str) -> QColor:
        """Barre du segment : vert (fait), rose (en cours), gris (à faire)."""
        c = self._jetons["couleurs"]
        etat = self.etat_etape(cle)
        return QColor({"fait": c["succes"], "en_cours": c["rose_trios"]}.get(etat, c["trait"]))

    def rectangles_segments(self):
        """Rectangle de chaque segment (tests de disposition) ; toujours dans le widget."""
        n = len(self.CLES)
        largeur_seg = self.width() / n
        return [QRectF(i * largeur_seg, 0, largeur_seg, self.height()) for i in range(n)]

    def paintEvent(self, _evenement):
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        n = len(self.CLES)
        largeur_seg = self.width() / n
        y_barre = self.height() - 10
        for i, cle in enumerate(self.CLES):
            x0 = i * largeur_seg
            etat = self.etat_etape(cle)
            actif = etat in ("fait", "en_cours")
            peintre.setPen(QColor(c["texte"] if actif else c["texte_discret"]))
            peintre.drawText(QRectF(x0, 0, largeur_seg - 70, 22),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             self.libelle(cle))
            peintre.setPen(QColor(c["texte_secondaire"] if actif else c["texte_discret"]))
            peintre.drawText(QRectF(x0, 0, largeur_seg - 10, 22),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             self.compte(cle))
            peintre.setPen(Qt.PenStyle.NoPen)
            peintre.setBrush(self.couleur_segment(cle))
            peintre.drawRoundedRect(QRectF(x0, y_barre, largeur_seg - 12, 3), 1.5, 1.5)
        peintre.end()
