"""Mini-fenêtre (étape 2C-9) : fenêtre outil toujours au premier plan (~440×150) avec anneau,
pages lues, temps restant, barre d'avancement à repères (pages à relire), Pause et Agrandir.

La progression est aussi poussée dans le bouton de la barre des tâches (ITaskbarList3 via
notification.definir_progression_barre) : optionnelle, elle ne plante jamais si indisponible.
Piloté par les événements (sur_evenement) ; aucun travail lourd ici.
"""
import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import evenements as ev
import interface_helpers
from trios_qt import notification, theme
from trios_qt.anneau import Anneau


class BarreReperes(QWidget):
    """Barre d'avancement horizontale avec des repères (pages à relire) peints par-dessus."""

    def __init__(self, jetons: dict, parent=None):
        super().__init__(parent)
        self._jetons = jetons
        self._fraction = 0.0
        self._total = 0
        self._reperes: set[int] = set()
        self.setMinimumHeight(10)

    def definir_avancement(self, fraction: float, total: int) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._total = total
        self.update()

    def ajouter_repere(self, index: int) -> None:
        self._reperes.add(int(index))
        self.update()

    def nombre_reperes(self) -> int:
        return len(self._reperes)

    def reinitialiser(self) -> None:
        self._fraction = 0.0
        self._reperes = set()
        self.update()

    def paintEvent(self, _evenement):
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h, w = self.height(), self.width()
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(QColor(c["trait"]))
        peintre.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        peintre.setBrush(QColor(c["succes"]))
        peintre.drawRoundedRect(QRectF(0, 0, w * self._fraction, h), h / 2, h / 2)
        if self._total:
            peintre.setBrush(QColor(c["a_relire"]))
            for index in self._reperes:
                x = w * (index + 0.5) / self._total
                peintre.drawEllipse(QRectF(x - h / 2, 0, h, h))
        peintre.end()


class MiniFenetre(QWidget):
    """Fenêtre outil au premier plan ; miroir compact de l'écran Traitement."""

    pause_demande = Signal()
    reprendre_demande = Signal()
    agrandir_demande = Signal()

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self.setObjectName("mini_fenetre")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(440, 150)
        self._total = 0
        self._done = 0
        self._t_premiere_page = None
        self._en_pause = False
        self._construire()
        self._chrono = QTimer(self)
        self._chrono.setInterval(1000)
        self._chrono.timeout.connect(self._tic)
        self._chrono.start()

    def _construire(self) -> None:
        rangee = QHBoxLayout(self)
        rangee.setContentsMargins(14, 12, 14, 12)
        rangee.setSpacing(14)
        self.anneau = Anneau(self._jetons, self)
        self.anneau.setFixedSize(118, 118)
        rangee.addWidget(self.anneau, 0)

        colonne = QVBoxLayout()
        colonne.setSpacing(6)
        self.etiquette_pages = QLabel("0 / 0 pages", self)
        self.etiquette_pages.setObjectName("traitement_fichier")
        self.etiquette_temps = QLabel("restant —", self)
        self.etiquette_temps.setObjectName("traitement_progression")
        self.barre = BarreReperes(self._jetons, self)
        colonne.addWidget(self.etiquette_pages)
        colonne.addWidget(self.etiquette_temps)
        colonne.addWidget(self.barre)
        boutons = QHBoxLayout()
        self.bouton_pause = QPushButton("Pause", self)
        self.bouton_pause.setObjectName("action_secondaire")
        self.bouton_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_pause.clicked.connect(self._basculer_pause)
        self.bouton_agrandir = QPushButton("Agrandir", self)
        self.bouton_agrandir.setObjectName("action_secondaire")
        self.bouton_agrandir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_agrandir.clicked.connect(self.agrandir_demande.emit)
        boutons.addWidget(self.bouton_pause)
        boutons.addWidget(self.bouton_agrandir)
        boutons.addStretch(1)
        colonne.addLayout(boutons)
        rangee.addLayout(colonne, 1)

    # ── Événements ───────────────────────────────────────────────────
    def sur_evenement(self, e) -> None:
        if e.type in (ev.PAGE_DEBUT, ev.PAGE_LUE, ev.ANALYSE):
            self._maj_avancement(e)
        elif e.type == ev.PAGE_ALERTE:
            self._ajouter_repere(e)
        elif e.type == ev.FIN:
            self.anneau.terminer()
            self.barre.definir_avancement(1.0, self._total)

    def _maj_avancement(self, e) -> None:
        if e.total:
            self._total = e.total
        done = e.rang or e.page or self._done
        if e.type == ev.PAGE_LUE and self._t_premiere_page is None:
            self._t_premiere_page = time.monotonic()
        if self._total and done:
            self._done = done
            fraction = done / self._total
            self.anneau.definir_valeur(fraction)
            self.anneau.definir_sous_libelle(f"{done} / {self._total}")
            self.etiquette_pages.setText(f"{done} / {self._total} pages")
            self.barre.definir_avancement(fraction, self._total)
            notification.definir_progression_barre(self._hwnd(), fraction)

    def _ajouter_repere(self, e) -> None:
        if e.page:
            self.barre.ajouter_repere(e.page - 1)

    def definir_temps(self, restant_s) -> None:
        self.etiquette_temps.setText(
            f"restant ~ {interface_helpers.format_duree(restant_s)}")

    def _tic(self) -> None:
        if self._t_premiere_page is None:
            return
        ecoule = time.monotonic() - self._t_premiere_page
        restant = interface_helpers.estimer_temps_restant(ecoule, self._done, self._total)
        if restant is not None:
            self.definir_temps(restant)

    def _hwnd(self):
        try:
            return int(self.window().winId())
        except Exception:
            return None

    # ── Boutons ──────────────────────────────────────────────────────
    def _basculer_pause(self) -> None:
        self._en_pause = not self._en_pause
        if self._en_pause:
            self.bouton_pause.setText("Reprendre")
            self.pause_demande.emit()
        else:
            self.bouton_pause.setText("Pause")
            self.reprendre_demande.emit()

    def en_pause(self) -> bool:
        return self._en_pause
