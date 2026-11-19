"""Widget d'une ligne de la file : sigle de famille, nom, type (coloré), estimation, retirer."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from trios_qt import presentation


class LigneFichierWidget(QFrame):
    """Vue d'une entrée de la file ; se met à jour depuis la ligne du modèle."""

    def __init__(self, ligne, jetons, parent=None):
        super().__init__(parent)
        self.setObjectName("ligne_fichier")
        self._jetons = jetons
        self.ident = ligne.ident
        self.couleur_type = None

        rangee = QHBoxLayout(self)
        self._sigle = QLabel(self)
        self._sigle.setObjectName("ligne_sigle")
        self._nom = QLabel(self)
        self._nom.setObjectName("ligne_nom")
        self._type = QLabel(self)
        self._type.setObjectName("ligne_type")
        self._estimation = QLabel(self)
        self._estimation.setObjectName("ligne_estimation")
        self.bouton_retirer = QPushButton("✕", self)
        self.bouton_retirer.setObjectName("ligne_retirer")

        rangee.addWidget(self._sigle)
        rangee.addWidget(self._nom, 1)
        rangee.addWidget(self._type)
        rangee.addWidget(self._estimation)
        rangee.addWidget(self.bouton_retirer, 0, Qt.AlignRight)

        self.mettre_a_jour(ligne)

    def mettre_a_jour(self, ligne):
        res = ligne.resultat
        famille = getattr(res.type, 'famille', None)
        self._sigle.setText(presentation.sigle_famille(famille))
        self._nom.setText(ligne.nom)
        self._type.setText(presentation.texte_type(res))
        self.couleur_type = presentation.couleur_etat(res.etat, self._jetons)
        self._type.setStyleSheet(f"color: {self.couleur_type};")
        self._estimation.setText(presentation.texte_estimation(res))
        if res.preuves:
            self._type.setToolTip("\n".join(res.preuves))

    def nom_affiche(self):
        return self._nom.text()

    def texte_estimation_affiche(self):
        return self._estimation.text()
