"""Écran Convertir : zone de dépôt, file des fichiers synchronisée, panneau des types reconnus."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

import types_documents
from trios_qt import theme
from trios_qt.ligne_fichier_widget import LigneFichierWidget
from trios_qt.modele_fichiers import LanceurAnalyse, ModeleFichiers
from trios_qt.zone_depot import ZoneDepot


class PageConvertir(QWidget):
    """Assemble le dépôt, la liste des fichiers et le panneau des types ; pilote l'analyse."""

    gerer_types = Signal()

    def __init__(self, registre_fn=None, lanceur=None, parent=None):
        super().__init__(parent)
        self.setObjectName("page_convertir")
        self._registre_fn = registre_fn or types_documents.registre
        self._jetons = theme.charger_jetons()
        self._widgets = []

        self.modele = ModeleFichiers()
        self.lanceur = lanceur or LanceurAnalyse()
        self.lanceur.fini.connect(self.modele.appliquer_resultat)
        for signal in (self.modele.rowsInserted, self.modele.rowsRemoved,
                       self.modele.rowsMoved, self.modele.modelReset):
            signal.connect(self._resync)
        self.modele.dataChanged.connect(lambda *_: self._resync())

        self._construire()

    # ── Construction ──────────────────────────────────────────────────
    def _construire(self):
        colonnes = QHBoxLayout(self)

        gauche = QVBoxLayout()
        self.zone = ZoneDepot(self)
        self.zone.sources_deposees.connect(self.ajouter_sources)
        gauche.addWidget(self.zone)

        self._zone_liste = QWidget(self)
        self._liste_layout = QVBoxLayout(self._zone_liste)
        self._liste_layout.setAlignment(Qt.AlignTop)
        defilement = QScrollArea(self)
        defilement.setObjectName("liste_fichiers")
        defilement.setWidgetResizable(True)
        defilement.setWidget(self._zone_liste)
        gauche.addWidget(defilement, 1)
        colonnes.addLayout(gauche, 1)

        colonnes.addWidget(self._construire_panneau_types())

    def _construire_panneau_types(self):
        panneau = QFrame(self)
        panneau.setObjectName("panneau_types")
        colonne = QVBoxLayout(panneau)
        titre = QLabel("Types reconnus", panneau)
        titre.setObjectName("panneau_titre")
        colonne.addWidget(titre)
        self._noms_types = sorted(self._registre_fn().keys())
        for nom in self._noms_types:
            etiquette = QLabel(nom, panneau)
            etiquette.setObjectName("panneau_type")
            colonne.addWidget(etiquette)
        colonne.addStretch(1)
        self.bouton_gerer = QPushButton("Gérer", panneau)
        self.bouton_gerer.setObjectName("panneau_gerer")
        self.bouton_gerer.clicked.connect(self.gerer_types.emit)
        colonne.addWidget(self.bouton_gerer)
        return panneau

    # ── File ──────────────────────────────────────────────────────────
    def ajouter_sources(self, sources):
        for chemin in sources:
            ident = self.modele.ajouter(chemin)
            self.lanceur.lancer(ident, chemin)

    def _resync(self, *_):
        while self._liste_layout.count():
            element = self._liste_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()
        self._widgets = []
        for rang in range(self.modele.rowCount()):
            ligne = self.modele.ligne(rang)
            widget = LigneFichierWidget(ligne, self._jetons, self._zone_liste)
            widget.bouton_retirer.clicked.connect(
                lambda _=False, ident=ligne.ident: self._retirer(ident))
            self._liste_layout.addWidget(widget)
            self._widgets.append(widget)

    def _retirer(self, ident):
        for rang in range(self.modele.rowCount()):
            if self.modele.ligne(rang).ident == ident:
                self.modele.retirer(rang)
                return

    # ── Accès pour les tests ──────────────────────────────────────────
    def widget_ligne(self, rang):
        return self._widgets[rang]

    def noms_types(self):
        return list(self._noms_types)
