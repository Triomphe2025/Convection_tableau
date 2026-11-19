"""Carte d'une ligne de la file (2 niveaux) : famille, nom, type + preuve, sortie + estimation."""
from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from trios_qt import analyse, presentation, theme

MIME_IDENT = "application/x-trios-ident"
_SEUIL_GLISSER = 12   # px au-delà desquels un appui devient un glisser (et non un clic)

_COULEUR_TYPE = {
    analyse.ANALYSE: "texte_discret",
    analyse.INCONNU: "a_relire",
    analyse.A_PRECISER: "a_relire",
    analyse.ERREUR: "erreur",
    analyse.PRET: "texte",
}


class LigneFichierWidget(QFrame):
    """Carte d'un fichier ; se met à jour depuis la ligne du modèle. Cliquable (sélection)."""

    clique = Signal(int)   # ident de la ligne

    def __init__(self, ligne, jetons, parent=None):
        super().__init__(parent)
        self.setObjectName("ligne_fichier")
        self.setProperty("selectionne", False)
        self._jetons = jetons
        self._couleurs = jetons["couleurs"]
        self.ident = ligne.ident
        self.couleur_type = None
        self._press_pos = QPoint()

        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._construire_entete())
        self._corps_deplie = QWidget(self)   # rempli par la page (profils, lot, actions)
        corps = QVBoxLayout(self._corps_deplie)
        corps.setContentsMargins(64, 0, 14, 12)
        corps.setSpacing(10)
        self._corps_deplie.setVisible(False)
        racine.addWidget(self._corps_deplie)

        # Attributs remplis par la page lors du dépli.
        self.profil_cartes = {}
        self.case_lot = None
        self.bouton_creer_type = None

        self.mettre_a_jour(ligne)

    def corps_layout(self):
        return self._corps_deplie.layout()

    def deplier(self, actif):
        self._corps_deplie.setVisible(bool(actif))

    def _construire_entete(self):
        entete = QWidget(self)
        rangee = QHBoxLayout(entete)
        rangee.setContentsMargins(14, 12, 14, 12)
        rangee.setSpacing(14)

        self._carre = QLabel(entete)
        self._carre.setObjectName("ligne_carre")
        self._carre.setAlignment(Qt.AlignCenter)
        self._carre.setFixedSize(36, 36)
        rangee.addWidget(self._carre, 0, Qt.AlignTop)

        gauche = QVBoxLayout()
        gauche.setSpacing(2)
        self._nom = QLabel(entete)
        self._nom.setObjectName("ligne_nom")
        self._sousligne = QLabel(entete)
        self._sousligne.setObjectName("ligne_sousligne")
        gauche.addWidget(self._nom)
        gauche.addWidget(self._sousligne)
        rangee.addLayout(gauche, 5)

        milieu = QVBoxLayout()
        milieu.setSpacing(2)
        self._type = QLabel(entete)
        self._type.setObjectName("ligne_type")
        self._preuve = QLabel(entete)
        self._preuve.setObjectName("ligne_preuve")
        milieu.addWidget(self._type)
        milieu.addWidget(self._preuve)
        rangee.addLayout(milieu, 4)

        droite = QVBoxLayout()
        droite.setSpacing(2)
        self._sortie = QLabel(entete)
        self._sortie.setObjectName("ligne_sortie")
        self._sortie.setAlignment(Qt.AlignRight)
        self._estimation = QLabel(entete)
        self._estimation.setObjectName("ligne_estimation")
        self._estimation.setAlignment(Qt.AlignRight)
        droite.addWidget(self._sortie)
        droite.addWidget(self._estimation)
        rangee.addLayout(droite, 3)

        self.bouton_retirer = QPushButton("✕", entete)
        self.bouton_retirer.setObjectName("ligne_retirer")
        self.bouton_retirer.setCursor(Qt.PointingHandCursor)
        rangee.addWidget(self.bouton_retirer, 0, Qt.AlignTop)
        return entete

    def mettre_a_jour(self, ligne):
        res = ligne.resultat
        famille = getattr(res.type, 'famille', None)
        self._carre.setText(presentation.sigle_famille(famille))
        couleur_fam = presentation.couleur_famille(famille, self._jetons)
        self._carre.setStyleSheet(
            f"background-color: {theme._rgba(couleur_fam, 0.18)};"
            f"color: {couleur_fam}; border-radius: 9px; font-weight: 700;")

        self._nom.setText(ligne.nom)
        self._sousligne.setText(presentation.texte_pages(res))

        famille_type = presentation.nom_famille(famille) + "  ›  " + presentation.texte_type(res)
        self._type.setText(famille_type)
        self.couleur_type = self._couleurs[_COULEUR_TYPE.get(res.etat, "texte")]
        self._type.setStyleSheet(f"color: {self.couleur_type}; font-weight: 600;")
        self._preuve.setText(presentation.preuve_courte(res))
        if res.preuves:
            self._type.setToolTip("\n".join(res.preuves))

        self._sortie.setText(presentation.texte_sortie(res))
        self._estimation.setText(presentation.texte_estimation(res))

    def definir_selection(self, actif):
        self.setProperty("selectionne", bool(actif))
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self._press_pos).manhattanLength() < _SEUIL_GLISSER:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_IDENT, str(self.ident).encode())
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, event):
        # Appui sans glisser = clic (sélection / dépli) ; au-delà du seuil, c'était un glisser.
        if (event.position().toPoint() - self._press_pos).manhattanLength() < _SEUIL_GLISSER:
            self.clique.emit(self.ident)
        super().mouseReleaseEvent(event)

    def nom_affiche(self):
        return self._nom.text()

    def texte_estimation_affiche(self):
        return self._estimation.text()
