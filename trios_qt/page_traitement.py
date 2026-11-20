"""Écran Traitement minimal (provisoire, remplacé en 2C) : fichier, progression, journal, arrêt."""
from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import evenements as ev

_MAX_LIGNES = 5


class PageTraitement(QWidget):
    """Suit une conversion en cours : fichier, « page n / total », 5 dernières lignes, Arrêter."""

    arret_demande = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page_traitement")
        self._journal = []
        self._excel = None
        self._dossier = None
        self._construire()

    def _construire(self):
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(40, 30, 40, 24)
        colonne.setSpacing(14)

        titre = QLabel("Conversion en cours", self)
        titre.setObjectName("titre_ecran")
        colonne.addWidget(titre)

        self.etiquette_fichier = QLabel("—", self)
        self.etiquette_fichier.setObjectName("traitement_fichier")
        self.etiquette_progression = QLabel("—", self)
        self.etiquette_progression.setObjectName("traitement_progression")
        colonne.addWidget(self.etiquette_fichier)
        colonne.addWidget(self.etiquette_progression)

        self.journal = QLabel("", self)
        self.journal.setObjectName("traitement_journal")
        self.journal.setTextFormat(Qt.PlainText)
        self.journal.setAlignment(Qt.AlignTop)
        colonne.addWidget(self.journal, 1)

        rangee = QHBoxLayout()
        self.bouton_arreter = QPushButton("Arrêter", self)
        self.bouton_arreter.setObjectName("bouton_arreter")
        self.bouton_arreter.setCursor(Qt.PointingHandCursor)
        self.bouton_arreter.clicked.connect(self.arret_demande.emit)
        self.bouton_ouvrir_excel = QPushButton("Ouvrir l'Excel", self)
        self.bouton_ouvrir_excel.setObjectName("action_secondaire")
        self.bouton_ouvrir_excel.clicked.connect(self._ouvrir_excel)
        self.bouton_ouvrir_dossier = QPushButton("Ouvrir le dossier", self)
        self.bouton_ouvrir_dossier.setObjectName("action_secondaire")
        self.bouton_ouvrir_dossier.clicked.connect(self._ouvrir_dossier)
        self.bouton_ouvrir_excel.setVisible(False)
        self.bouton_ouvrir_dossier.setVisible(False)
        rangee.addWidget(self.bouton_arreter, 0, Qt.AlignLeft)
        rangee.addStretch(1)
        rangee.addWidget(self.bouton_ouvrir_excel, 0)
        rangee.addWidget(self.bouton_ouvrir_dossier, 0)
        colonne.addLayout(rangee)

    def demarrer_fichier(self, nom):
        self.etiquette_fichier.setText(nom)
        self.etiquette_progression.setText("—")
        self._journal = []
        self.journal.setText("")
        self.bouton_ouvrir_excel.setVisible(False)
        self.bouton_ouvrir_dossier.setVisible(False)
        self.bouton_arreter.setVisible(True)

    def sur_evenement(self, e):
        if e.type in (ev.PAGE_DEBUT, ev.PAGE_LUE) and e.rang and e.total:
            self.etiquette_progression.setText(f"page {e.rang} / {e.total}")
        ligne = self._ligne_evenement(e)
        if ligne:
            self._journal.append(ligne)
            self._journal = self._journal[-_MAX_LIGNES:]
            self.journal.setText("\n".join(self._journal))

    @staticmethod
    def _ligne_evenement(e):
        if e.type in (ev.PAGE_DEBUT, ev.PAGE_LUE) and e.rang and e.total:
            return f"page {e.rang} / {e.total}"
        if e.type == ev.PHASE:
            return e.message or "phase"
        if e.type == ev.PAGE_ALERTE and e.alertes:
            return "⚠ " + " ; ".join(e.alertes)
        if e.type == ev.ERREUR:
            return "✗ " + (e.message or "erreur")
        if e.type == ev.FIN:
            return "✓ terminé"
        return ""

    def terminer(self, excel=None, dossier=None):
        self._excel = excel
        self._dossier = dossier
        self.bouton_arreter.setVisible(False)
        self.bouton_ouvrir_excel.setVisible(bool(excel))
        self.bouton_ouvrir_dossier.setVisible(bool(dossier))

    def _ouvrir_excel(self):
        if self._excel:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._excel))

    def _ouvrir_dossier(self):
        if self._dossier:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._dossier))

    def lignes_journal(self):
        return list(self._journal)
