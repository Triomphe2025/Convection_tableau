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
        self.setFixedSize(460, 164)
        self._total = 0
        self._done = 0
        self._t_premiere_page = None
        self._en_pause = False
        self._a_relire = 0
        self._construire()
        self._chrono = QTimer(self)
        self._chrono.setInterval(1000)
        self._chrono.timeout.connect(self._tic)
        self._chrono.start()

    def _construire(self) -> None:
        c = self._jetons["couleurs"]
        racine = QVBoxLayout(self)
        racine.setContentsMargins(14, 11, 14, 11)
        racine.setSpacing(8)

        entete = QHBoxLayout()
        logo = QLabel(self)
        logo.setObjectName("mini_logo")
        logo.setTextFormat(Qt.TextFormat.RichText)
        logo.setText(f'<b><span style="color:{c["rose_trios"]}">Trios</span>'
                     f'<span style="color:{c["texte"]}">Seconverter</span></b>')
        premier_plan = QLabel("⬚ au premier plan", self)
        premier_plan.setObjectName("mini_discret")
        self.bouton_agrandir = QPushButton("⤢", self)
        self.bouton_agrandir.setObjectName("mini_icone")
        self.bouton_agrandir.setFixedSize(26, 22)
        self.bouton_agrandir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_agrandir.clicked.connect(self.agrandir_demande.emit)
        entete.addWidget(logo, 0)
        entete.addWidget(premier_plan, 0)
        entete.addStretch(1)
        entete.addWidget(self.bouton_agrandir, 0)
        racine.addLayout(entete)

        corps = QHBoxLayout()
        corps.setSpacing(12)
        self.anneau = Anneau(self._jetons, self)
        self.anneau.setFixedSize(92, 92)
        corps.addWidget(self.anneau, 0)

        colonne = QVBoxLayout()
        colonne.setSpacing(4)
        self.etiquette_fichier = QLabel("—", self)
        self.etiquette_fichier.setObjectName("traitement_fichier")
        colonne.addWidget(self.etiquette_fichier)

        info = QHBoxLayout()
        info.setSpacing(6)
        self.etiquette_pages = QLabel("0 / 0 pages", self)
        self.etiquette_pages.setObjectName("mini_info")
        self.etiquette_temps = QLabel("", self)
        self.etiquette_temps.setObjectName("mini_info")
        self.etiquette_relire = QLabel("", self)
        self.etiquette_relire.setObjectName("mini_relire")
        info.addWidget(self.etiquette_pages, 0)
        info.addWidget(QLabel("·", self), 0)
        info.addWidget(self.etiquette_temps, 0)
        info.addWidget(QLabel("·", self), 0)
        info.addWidget(self.etiquette_relire, 0)
        info.addStretch(1)
        colonne.addLayout(info)

        rangee_barre = QHBoxLayout()
        rangee_barre.setSpacing(8)
        self.barre = BarreReperes(self._jetons, self)
        self.bouton_pause = QPushButton("⏸", self)
        self.bouton_pause.setObjectName("mini_icone")
        self.bouton_pause.setFixedSize(30, 22)
        self.bouton_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_pause.clicked.connect(self._basculer_pause)
        rangee_barre.addWidget(self.barre, 1)
        rangee_barre.addWidget(self.bouton_pause, 0)
        colonne.addLayout(rangee_barre)

        self.etiquette_etat = QLabel("", self)
        self.etiquette_etat.setObjectName("mini_discret")
        colonne.addWidget(self.etiquette_etat)
        corps.addLayout(colonne, 1)
        racine.addLayout(corps)

    # ── Événements ───────────────────────────────────────────────────
    def definir_fichier(self, nom) -> None:
        self.etiquette_fichier.setText(str(nom))

    def sur_evenement(self, e) -> None:
        if e.type in (ev.PAGE_DEBUT, ev.PAGE_LUE, ev.ANALYSE):
            self._maj_avancement(e)
        if e.type == ev.PAGE_DEBUT and e.page:
            self.etiquette_etat.setText(f"Page {e.page} · lecture de la page…")
        elif e.type == ev.PAGE_ALERTE:
            self._ajouter_repere(e)
        elif e.type == ev.FIN:
            self.anneau.terminer()
            self.barre.definir_avancement(1.0, self._total)
            self.etiquette_etat.setText("Conversion terminée")

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
        self._a_relire += 1
        self.etiquette_relire.setText(f"{self._a_relire} à relire")

    def definir_temps(self, restant_s) -> None:
        # Format maquette : « ≈ N min » (au moins 1 min dès qu'il reste du temps).
        minutes = max(1, int(round((restant_s or 0) / 60)))
        self.etiquette_temps.setText(f"≈ {minutes} min")

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
