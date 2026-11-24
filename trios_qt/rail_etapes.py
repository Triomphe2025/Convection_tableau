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

    def __init__(self, jetons: dict | None = None, parent=None, cles=None, libelles=None,
                 couleur_courante=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        # Clés et libellés personnalisables (l'écran lot a d'autres étapes que l'écran tableau).
        self._cles = tuple(cles) if cles else self.CLES
        self._libelles = libelles or _LIBELLES
        # Couleur de l'étape en cours (rose par défaut ; violet pour l'écran lot).
        self._couleur_courante = couleur_courante or self._jetons["couleurs"]["rose_trios"]
        self._frac_courante = 1.0   # remplissage de la barre de l'étape en cours (prorata)
        self._courante: str | None = None
        self._termine = False
        self._comptes: dict[str, str] = {}
        self.setMinimumHeight(44)

    @property
    def cles(self):
        return self._cles

    def definir_phase(self, etat: str) -> None:
        if etat not in self._cles:
            return
        self._courante = etat
        self._termine = False
        self.update()

    def definir_compte(self, cle: str, texte: str) -> None:
        if cle in self._cles:
            self._comptes[cle] = texte or ""
            self.update()

    def compte(self, cle: str) -> str:
        return self._comptes.get(cle, "")

    def phase_courante(self) -> str | None:
        return None if self._termine else self._courante

    def _index_courant(self) -> int:
        return self._cles.index(self._courante) if self._courante in self._cles else -1

    def etat_etape(self, cle: str) -> str:
        if self._termine:
            return "fait"
        i = self._cles.index(cle)
        courant = self._index_courant()
        if courant < 0 or i > courant:
            return "a_faire"
        return "en_cours" if i == courant else "fait"

    def fraction(self) -> float:
        faites = sum(1 for c in self._cles if self.etat_etape(c) == "fait")
        return faites / len(self._cles)

    def terminer(self) -> None:
        self._termine = True
        self.update()

    def libelle(self, cle: str) -> str:
        return self._libelles.get(cle, cle)

    def definir_fraction_courante(self, frac: float) -> None:
        self._frac_courante = max(0.0, min(1.0, float(frac)))
        self.update()

    def couleur_segment(self, cle: str) -> QColor:
        """Barre du segment : vert (fait), couleur courante (en cours), gris (à faire)."""
        c = self._jetons["couleurs"]
        etat = self.etat_etape(cle)
        if etat == "fait":
            return QColor(c["succes"])
        if etat == "en_cours":
            return QColor(self._couleur_courante)
        return QColor(c["trait"])

    def rectangles_segments(self):
        """Rectangle de chaque segment (tests de disposition) ; toujours dans le widget."""
        n = len(self._cles)
        largeur_seg = self.width() / n
        return [QRectF(i * largeur_seg, 0, largeur_seg, self.height()) for i in range(n)]

    def paintEvent(self, _evenement):
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        n = len(self._cles)
        largeur_seg = self.width() / n
        y_barre = self.height() - 10
        for i, cle in enumerate(self._cles):
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
            largeur_barre = largeur_seg - 12
            # Étape en cours : fond gris + remplissage partiel (prorata) ; sinon barre pleine.
            if etat == "en_cours" and self._frac_courante < 1.0:
                peintre.setBrush(QColor(c["trait"]))
                peintre.drawRoundedRect(QRectF(x0, y_barre, largeur_barre, 3), 1.5, 1.5)
                peintre.setBrush(self.couleur_segment(cle))
                peintre.drawRoundedRect(
                    QRectF(x0, y_barre, largeur_barre * self._frac_courante, 3), 1.5, 1.5)
            else:
                peintre.setBrush(self.couleur_segment(cle))
                peintre.drawRoundedRect(QRectF(x0, y_barre, largeur_barre, 3), 1.5, 1.5)
        peintre.end()
