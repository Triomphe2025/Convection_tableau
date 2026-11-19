"""Zone de dépôt de l'écran Convertir : glisser-déposer fichiers et dossiers, Choisir, Ctrl+O."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from config import Config


def filtrer_sources(chemins):
    """Ne garde que les dossiers et les fichiers dont l'extension est un format source."""
    formats = tuple(f.lower() for f in Config.FORMATS_SOURCE)
    gardes = []
    for chemin in chemins:
        p = Path(chemin)
        if p.is_dir() or p.suffix.lower() in formats:
            gardes.append(str(p))  # forme OS : le dépôt (QUrl) rend des « / »
    return gardes


class ZoneDepot(QFrame):
    """Cible de dépôt : émet `sources_deposees` avec la liste des sources acceptées."""

    sources_deposees = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("zone_depot")
        self.setAcceptDrops(True)
        self._raccourcis = []
        self._construire()

    def _construire(self):
        colonne = QVBoxLayout(self)
        colonne.setAlignment(Qt.AlignCenter)
        self.titre = QLabel("Glissez vos fichiers ou dossiers ici", self)
        self.titre.setObjectName("depot_titre")
        self.titre.setAlignment(Qt.AlignCenter)
        self.aide = QLabel("PDF, images, Word, Excel ou journal", self)
        self.aide.setObjectName("depot_aide")
        self.aide.setAlignment(Qt.AlignCenter)
        rangee = QHBoxLayout()
        rangee.setAlignment(Qt.AlignCenter)
        self.bouton_choisir = QPushButton("Choisir", self)
        self.bouton_choisir.setObjectName("depot_choisir")
        self.bouton_choisir.clicked.connect(self.choisir_fichiers)
        rangee.addWidget(self.bouton_choisir)
        colonne.addWidget(self.titre)
        colonne.addWidget(self.aide)
        colonne.addLayout(rangee)

        raccourci = QShortcut(QKeySequence("Ctrl+O"), self)
        raccourci.activated.connect(self.choisir_fichiers)
        self._raccourcis.append(raccourci)

    def raccourcis(self):
        return list(self._raccourcis)

    # ── Dépôt ─────────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        chemins = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        sources = filtrer_sources(chemins)
        if sources:
            self.sources_deposees.emit(sources)
        event.acceptProposedAction()

    # ── Choix par dialogue ────────────────────────────────────────────
    def choisir_fichiers(self):
        motifs = " ".join("*" + ext for ext in Config.FORMATS_SOURCE)
        chemins, _ = QFileDialog.getOpenFileNames(
            self, "Choisir des fichiers", "", f"Sources ({motifs})")
        sources = filtrer_sources(chemins)
        if sources:
            self.sources_deposees.emit(sources)
