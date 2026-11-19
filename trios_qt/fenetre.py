"""Fenêtre principale : barre latérale + QStackedWidget (une page vide par écran).

Structure de l'écran 01_convertir.png. Les pages sont vides à l'étape 3 (contenu aux étapes
suivantes) ; le changement d'écran se fait en fondu (jeton passage_ecran, 300 ms), sauf si les
animations sont réduites.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from trios_qt import animations, theme

TITRE_FENETRE = "TriosSeconverter"

# (clé, libellé, marque) ; marque : None, "compteur" (Relecture) ou "beta" (Plans → DXF).
NAV_PRINCIPALE = (
    ("convertir", "Convertir", None),
    ("relecture", "Relecture", "compteur"),
    ("mise_en_forme", "Mise en forme Excel", None),
    ("plans", "Plans → DXF", "beta"),
)
NAV_BAS = (
    ("reglages", "Réglages", None),
    ("aide", "Aide", None),
)


class FenetrePrincipale(QWidget):
    """Fenêtre racine ; expose .pages, .boutons et aller_a(clé) pour la navigation et les tests."""

    def __init__(self, jetons: dict | None = None, points_a_relire: int = 0):
        super().__init__()
        self._jetons = jetons or theme.charger_jetons()
        self._points_a_relire = points_a_relire
        self.setWindowTitle(TITRE_FENETRE)
        self.resize(1360, 900)

        self.pages: dict[str, QWidget] = {}
        self.boutons: dict[str, QPushButton] = {}
        self._pile = QStackedWidget()
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self._duree = int(self._jetons["mouvement_ms"]["passage_ecran"])
        self._courbe = animations.courbe_depuis_jetons(self._jetons["courbe_standard"])

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._construire_barre_laterale())
        racine.addWidget(self._pile, 1)

        premiere = NAV_PRINCIPALE[0][0]
        self.boutons[premiere].setChecked(True)
        self._pile.setCurrentWidget(self.pages[premiere])

    def _construire_barre_laterale(self) -> QWidget:
        barre = QWidget()
        barre.setObjectName("barre_laterale")
        barre.setFixedWidth(224)
        colonne = QVBoxLayout(barre)
        colonne.setContentsMargins(16, 20, 16, 16)
        colonne.setSpacing(6)

        logo = QLabel("TriosSeconverter")
        logo.setObjectName("logo")
        colonne.addWidget(logo)
        colonne.addSpacing(18)

        for cle, libelle, marque in NAV_PRINCIPALE:
            colonne.addWidget(self._creer_entree(cle, libelle, marque))
        colonne.addStretch(1)
        for cle, libelle, marque in NAV_BAS:
            colonne.addWidget(self._creer_entree(cle, libelle, marque))

        colonne.addWidget(self._carte_etat())
        return barre

    def _creer_entree(self, cle: str, libelle: str, marque) -> QPushButton:
        texte = libelle
        if marque == "beta":
            texte = f"{libelle}   bêta"
        elif marque == "compteur":
            texte = f"{libelle}   {self._points_a_relire}"
        bouton = QPushButton(texte)
        bouton.setObjectName(f"nav_{cle}")
        bouton.setProperty("classe", "nav")  # cible du style QSS commun aux entrées de nav
        bouton.setCheckable(True)
        bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton.clicked.connect(lambda _=False, c=cle: self.aller_a(c))
        self._groupe.addButton(bouton)
        self.boutons[cle] = bouton

        page = QWidget()
        page.setObjectName(f"page_{cle}")
        disposition = QVBoxLayout(page)
        disposition.setContentsMargins(40, 36, 40, 36)
        titre = QLabel(libelle)
        titre.setObjectName("titre_ecran")
        disposition.addWidget(titre)
        disposition.addStretch(1)
        self.pages[cle] = page
        self._pile.addWidget(page)
        return bouton

    def _carte_etat(self) -> QWidget:
        carte = QWidget()
        carte.setObjectName("carte_etat")
        disposition = QVBoxLayout(carte)
        disposition.setContentsMargins(12, 10, 12, 10)
        disposition.setSpacing(2)
        self.etiquette_modele = QLabel("Modèle : —")
        self.etiquette_modele.setObjectName("etat_modele")
        self.etiquette_version = QLabel("Version 2.0 · aperçu")
        self.etiquette_version.setObjectName("etat_version")
        disposition.addWidget(self.etiquette_modele)
        disposition.addWidget(self.etiquette_version)
        return carte

    def aller_a(self, cle: str) -> None:
        page = self.pages[cle]
        self._pile.setCurrentWidget(page)
        if not self.boutons[cle].isChecked():
            self.boutons[cle].setChecked(True)
        animations.fondu_entree(page, self._duree, self._courbe)

    def ecran_courant(self) -> str:
        courant = self._pile.currentWidget()
        for cle, page in self.pages.items():
            if page is courant:
                return cle
        return ""
