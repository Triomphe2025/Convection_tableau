"""Bande de dépôt de l'écran Convertir : glisser-déposer fichiers et dossiers, lien, Ctrl+O."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QVBoxLayout)

from config import Config
from trios_qt import theme
from trios_qt.anim_trios import AnimationTrios

# Formats présentés à l'utilisateur (regroupés, lisibles) — la vraie liste reste FORMATS_SOURCE.
_FORMATS_LISIBLES = ("PDF · TIFF · JPG/PNG · dossier d'images · "
                     "Word .docx · Excel .xlsx · journal .jsonl")


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
    """Bande de dépôt ; émet `sources_deposees` avec la liste des sources acceptées."""

    sources_deposees = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("zone_depot")
        self.setAcceptDrops(True)
        self._raccourcis = []
        # Fonction de dialogue injectable (tests) ; en vrai, le sélecteur de fichiers natif.
        self._dialogue_fichiers = QFileDialog.getOpenFileNames
        self._construire()

    def _construire(self):
        rangee = QHBoxLayout(self)
        rangee.setContentsMargins(18, 10, 18, 10)
        rangee.setSpacing(16)

        self.logo = AnimationTrios(self)
        self.logo.setObjectName("depot_logo")
        self.logo.setFixedSize(52, 52)
        rangee.addWidget(self.logo, 0, Qt.AlignVCenter)

        colonne = QVBoxLayout()
        colonne.setSpacing(2)
        rose = theme.charger_jetons()["couleurs"]["rose_trios"]
        self.invite = QLabel(self)
        self.invite.setObjectName("depot_invite")
        self.invite.setTextFormat(Qt.RichText)
        self.invite.setText(
            "Glisse des fichiers ici, ou "
            f"<a href='#' style='text-decoration:none; color:{rose}'>choisis-les</a>")
        self.invite.linkActivated.connect(lambda _=None: self.choisir_fichiers())
        self.formats = QLabel(_FORMATS_LISIBLES, self)
        self.formats.setObjectName("depot_formats")
        colonne.addWidget(self.invite)
        colonne.addWidget(self.formats)
        rangee.addLayout(colonne, 1)

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
        # Parent = la fenêtre de plus haut niveau (pas la bande) : sinon la boîte native s'ouvre
        # hors écran. On la ramène au premier plan pour que la boîte se place dessus.
        fenetre = self.window()
        if fenetre is not None and fenetre is not self:
            fenetre.raise_()
            fenetre.activateWindow()
        chemins, _ = self._dialogue_fichiers(
            fenetre, "Choisir des fichiers", "", f"Sources ({motifs})")
        sources = filtrer_sources(chemins)
        if sources:
            self.sources_deposees.emit(sources)
