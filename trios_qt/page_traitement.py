"""Écran Traitement (étape 2C-7) : assemble le rail des 4 étapes, la « Lecture en direct »,
l'anneau d'avancement, la mosaïque des pages, les astuces, les messages d'étape, le journal
replié et les boutons Pause / Reprendre / Arrêter. Remplace l'écran provisoire de la 2B.

Tout est piloté par les événements du converter (sur_evenement) ; aucun travail lourd ici.
À la fin : anneau vert + coche, un seul bouton « Voir le résumé », notification Windows si la
fenêtre n'a pas le focus, plus « Ouvrir l'Excel / le dossier ». L'API publique (demarrer_fichier,
sur_evenement, terminer, arret_demande, lignes_journal) reste celle attendue par lancement.py.
"""
import time

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

import evenements as ev
import interface_helpers
from trios_qt import notification, theme
from trios_qt.anneau import Anneau
from trios_qt.astuces import Astuces
from trios_qt.lecture_directe import LectureDirecte
from trios_qt.messages_etape import MessagesEtape
from trios_qt.mosaique import Mosaique
from trios_qt.rail_etapes import RailEtapes

_MAX_LIGNES = 200
_NATURES_NATIVES = {'vectoriel', 'texte', 'natif'}

_LIBELLES_PHASE = {
    'analyse': "Analyse du document", 'lecture': "Lecture des pages",
    'controles': "Contrôles qualité", 'excel': "Génération du classeur",
}


class PageTraitement(QWidget):
    """Suit une conversion : rail, lecture en direct, anneau, mosaïque, journal, Pause/Arrêter."""

    arret_demande = Signal()
    pause_demande = Signal()
    reprendre_demande = Signal()
    voir_resume = Signal()

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("page_traitement")
        self._jetons = jetons or theme.charger_jetons()
        self._journal: list[str] = []
        self._excel = None
        self._dossier = None
        self._total = 0
        self._done = 0
        self._t_premiere_page = None
        self._en_pause = False
        self._natures: dict[int, str] = {}
        self._pdf_vers_index: dict[int, int] = {}
        self._borniers: set[str] = set()
        self._pages_a_relire = 0
        self._tokens_entree = 0
        self._tokens_sortie = 0
        self._plus_que_10_dit = False
        self._construire()
        self._chrono = QTimer(self)
        self._chrono.setInterval(1000)
        self._chrono.timeout.connect(self._tic)

    # ── Construction ─────────────────────────────────────────────────
    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(32, 24, 32, 20)
        colonne.setSpacing(14)

        entete = QHBoxLayout()
        titre = QLabel("Conversion en cours", self)
        titre.setObjectName("titre_ecran")
        self.etiquette_fichier = QLabel("—", self)
        self.etiquette_fichier.setObjectName("traitement_fichier")
        self.etiquette_chrono = QLabel("0:00", self)
        self.etiquette_chrono.setObjectName("traitement_progression")
        entete.addWidget(titre)
        entete.addSpacing(16)
        entete.addWidget(self.etiquette_fichier, 1)
        entete.addWidget(self.etiquette_chrono, 0, Qt.AlignmentFlag.AlignRight)
        colonne.addLayout(entete)

        self.rail = RailEtapes(self._jetons, self)
        colonne.addWidget(self.rail)

        centre = QHBoxLayout()
        centre.setSpacing(16)
        self.lecture = LectureDirecte(self._jetons, self)
        centre.addWidget(self.lecture, 3)
        centre.addWidget(self._colonne_droite(), 0)
        colonne.addLayout(centre, 1)

        self.mosaique = Mosaique(self._jetons, self)
        self.mosaique.setMinimumHeight(40)
        colonne.addWidget(self.mosaique)

        colonne.addLayout(self._barre_boutons())
        colonne.addWidget(self._zone_journal())

        # Messages d'étape : carte flottante en bas à droite, par-dessus le contenu.
        self.messages = MessagesEtape(self._jetons, self)
        self.messages.setGeometry(self.rect())
        self.messages.raise_()

    def _colonne_droite(self) -> QWidget:
        panneau = QWidget(self)
        panneau.setFixedWidth(230)
        col = QVBoxLayout(panneau)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        self.anneau = Anneau(self._jetons, panneau)
        self.anneau.setMinimumHeight(150)
        col.addWidget(self.anneau)
        self.etiquette_stats = QLabel("", panneau)
        self.etiquette_stats.setObjectName("traitement_stats")
        self.etiquette_stats.setTextFormat(Qt.TextFormat.RichText)
        self.etiquette_stats.setWordWrap(True)
        col.addWidget(self.etiquette_stats)
        self.astuces = Astuces(jetons=self._jetons, parent=panneau)
        col.addWidget(self.astuces)
        col.addStretch(1)
        self._maj_stats()
        return panneau

    def _barre_boutons(self) -> QHBoxLayout:
        rangee = QHBoxLayout()
        self.bouton_pause = QPushButton("Pause", self)
        self.bouton_pause.setObjectName("action_secondaire")
        self.bouton_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_pause.clicked.connect(self._basculer_pause)
        self.bouton_arreter = QPushButton("Arrêter", self)
        self.bouton_arreter.setObjectName("bouton_arreter")
        self.bouton_arreter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_arreter.clicked.connect(self._demander_arret)
        self.bouton_resume = QPushButton("Voir le résumé", self)
        self.bouton_resume.setObjectName("bouton_lancer")
        self.bouton_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_resume.clicked.connect(self.voir_resume.emit)
        self.bouton_resume.setVisible(False)
        self.bouton_ouvrir_excel = QPushButton("Ouvrir l'Excel", self)
        self.bouton_ouvrir_excel.setObjectName("action_secondaire")
        self.bouton_ouvrir_excel.clicked.connect(self._ouvrir_excel)
        self.bouton_ouvrir_dossier = QPushButton("Ouvrir le dossier", self)
        self.bouton_ouvrir_dossier.setObjectName("action_secondaire")
        self.bouton_ouvrir_dossier.clicked.connect(self._ouvrir_dossier)
        for b in (self.bouton_ouvrir_excel, self.bouton_ouvrir_dossier):
            b.setVisible(False)
        rangee.addWidget(self.bouton_pause)
        rangee.addWidget(self.bouton_arreter)
        rangee.addStretch(1)
        rangee.addWidget(self.bouton_ouvrir_excel)
        rangee.addWidget(self.bouton_ouvrir_dossier)
        rangee.addWidget(self.bouton_resume)
        return rangee

    def _zone_journal(self) -> QWidget:
        boite = QWidget(self)
        v = QVBoxLayout(boite)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        ligne = QHBoxLayout()
        self.bouton_journal = QPushButton("▸ Journal technique", boite)
        self.bouton_journal.setObjectName("action_secondaire")
        self.bouton_journal.setCheckable(True)
        self.bouton_journal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_journal.toggled.connect(self._basculer_journal)
        self.journal_resume = QLabel("", boite)
        self.journal_resume.setObjectName("traitement_progression")
        ligne.addWidget(self.bouton_journal, 0)
        ligne.addWidget(self.journal_resume, 1)
        v.addLayout(ligne)
        self.journal_complet = QPlainTextEdit(boite)
        self.journal_complet.setObjectName("traitement_journal")
        self.journal_complet.setReadOnly(True)
        self.journal_complet.setFixedHeight(120)
        self.journal_complet.setVisible(False)
        v.addWidget(self.journal_complet)
        return boite

    # ── Cycle de vie ─────────────────────────────────────────────────
    def demarrer_fichier(self, nom) -> None:
        self.etiquette_fichier.setText(str(nom))
        self._journal = []
        self._total = 0
        self._done = 0
        self._t_premiere_page = None
        self._en_pause = False
        self._natures.clear()
        self._pdf_vers_index.clear()
        self._borniers.clear()
        self._pages_a_relire = 0
        self._tokens_entree = 0
        self._tokens_sortie = 0
        self._plus_que_10_dit = False
        self.journal_resume.setText("")
        self.journal_complet.clear()
        self.anneau.reinitialiser()
        self.anneau.definir_sous_libelle("")
        self.etiquette_chrono.setText("0:00")
        self._maj_stats()
        self.bouton_resume.setVisible(False)
        self.bouton_ouvrir_excel.setVisible(False)
        self.bouton_ouvrir_dossier.setVisible(False)
        self.bouton_pause.setVisible(True)
        self.bouton_pause.setText("Pause")
        self.bouton_arreter.setVisible(True)
        self.bouton_arreter.setEnabled(True)
        self._chrono.start()

    def terminer(self, excel=None, dossier=None) -> None:
        self._excel = excel
        self._dossier = dossier
        self._chrono.stop()
        self.anneau.terminer()
        self.mosaique.arreter()
        self.lecture.definir_bande_active(False)
        self.bouton_arreter.setVisible(False)
        self.bouton_pause.setVisible(False)
        self.bouton_resume.setVisible(True)
        self.bouton_ouvrir_excel.setVisible(bool(excel))
        self.bouton_ouvrir_dossier.setVisible(bool(dossier))
        self.messages.afficher("Conversion terminée")
        self._signaler_fin()

    def _signaler_fin(self) -> None:
        fenetre = self.window()
        tray = getattr(fenetre, "tray", None)
        hwnd = int(fenetre.winId()) if fenetre is not None else None
        a_le_focus = bool(fenetre.isActiveWindow()) if fenetre is not None else True
        notification.signaler_fin(hwnd, tray, "TriosSeconverter",
                                  "Conversion terminée — clique « Voir le résumé ».", a_le_focus)

    # ── Événements ───────────────────────────────────────────────────
    def sur_evenement(self, e) -> None:
        if e.type in (ev.PAGE_DEBUT, ev.PAGE_LUE, ev.PAGE_ZONES):
            self.lecture.sur_evenement(e)
        if e.type == ev.ANALYSE:
            if e.page and e.nature:
                self._natures[e.page] = e.nature
            self._maj_progression(e)
        elif e.type == ev.PHASE:
            if e.etat in RailEtapes.CLES:
                self.rail.definir_phase(e.etat)
        elif e.type == ev.PAGE_DEBUT:
            self._page_debut(e)
        elif e.type == ev.PAGE_LUE:
            self._page_lue(e)
        elif e.type == ev.PAGE_ALERTE:
            self._page_alerte(e)
        elif e.type == ev.FIN:
            self.rail.terminer()
        ligne = self._ligne_evenement(e)
        if ligne:
            self._ajouter_journal(ligne)

    def _amorcer_total(self, e) -> None:
        if e.total:
            self._total = e.total
        # Créer les cases dès que le total est connu, même si _total a déjà été posé par ANALYSE.
        if self._total and self.mosaique.nombre_pages() == 0:
            self.mosaique.definir_pages(self._total)

    def _page_debut(self, e) -> None:
        self._amorcer_total(e)
        if self._t_premiere_page is None:
            self._t_premiere_page = time.monotonic()
        idx = (e.rang or e.page or 1) - 1
        self.mosaique.definir_etat(idx, Mosaique.LECTURE, infobulle=f"page {e.page} — en lecture")

    def _page_lue(self, e) -> None:
        self._amorcer_total(e)
        self._done = e.rang or e.page or self._done
        idx = (e.rang or e.page or 1) - 1
        if e.page:
            self._pdf_vers_index[e.page] = idx
        native = self._natures.get(e.page) in _NATURES_NATIVES
        etat = Mosaique.NATIF if native else Mosaique.LUE
        self.mosaique.definir_etat(idx, etat, infobulle=f"page {e.page} — {e.lignes or 0} lignes")
        if e.bornier:
            self._borniers.add(str(e.bornier))
        if e.cout:
            self._tokens_entree += int(e.cout.get('input_tokens', 0) or 0)
            self._tokens_sortie += int(e.cout.get('output_tokens', 0) or 0)
        self._maj_progression(e)
        self._maj_stats()
        self._jalons_messages()

    def _page_alerte(self, e) -> None:
        idx = self._pdf_vers_index.get(e.page)
        if idx is not None:
            infobulle = "page %s — %s" % (e.page_imprimee or e.page,
                                          " ; ".join(e.alertes or []) or "à relire")
            self.mosaique.definir_etat(idx, Mosaique.A_RELIRE, infobulle=infobulle)
        self._pages_a_relire += 1
        self._maj_stats()

    def _maj_progression(self, e) -> None:
        if e.total:
            self._total = e.total
        done = e.rang or e.page or self._done
        if self._total and done:
            self._done = done
            self.anneau.definir_valeur(done / self._total)
            self.anneau.definir_sous_libelle(f"{done} / {self._total} pages")

    def _jalons_messages(self) -> None:
        n = len(self._borniers)
        if n and n % 100 == 0:
            self.messages.afficher(f"{n} tableaux extraits")
        if (not self._plus_que_10_dit and self._total
                and self._done == max(1, self._total - 10) and self._total > 10):
            self._plus_que_10_dit = True
            self.messages.afficher("Plus que 10 pages")

    # ── Affichage dérivé ─────────────────────────────────────────────
    def _maj_stats(self) -> None:
        c = self._jetons["couleurs"]
        cout = self._cout_usd()
        self.etiquette_stats.setText(
            f"<b>{len(self._borniers)}</b> tableaux<br>"
            f"<span style='color:{c['a_relire']}'>{self._pages_a_relire}</span> à relire<br>"
            f"~ {cout:.2f} $")

    def _cout_usd(self) -> float:
        from config import Config
        prix = getattr(Config, 'CLAUDE_PRIX_MODELES', {}) or {}
        modele = getattr(Config, 'CLAUDE_OCR_MODEL', '')
        entree, sortie = prix.get(modele, (0.0, 0.0))
        return self._tokens_entree / 1e6 * entree + self._tokens_sortie / 1e6 * sortie

    def _tic(self) -> None:
        if self._t_premiere_page is None:
            return
        ecoule = time.monotonic() - self._t_premiere_page
        restant = interface_helpers.estimer_temps_restant(ecoule, self._done, self._total)
        texte = interface_helpers.format_duree(ecoule)
        est = interface_helpers.texte_estimation(restant, premiere_page_vue=True)
        self.etiquette_chrono.setText(f"{texte}   {est}" if est else texte)

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

    def _demander_arret(self) -> None:
        # Retour immédiat : l'arrêt est coopératif (vu à la fin de la page en cours), on le dit.
        self.journal_resume.setText("Arrêt demandé — fin de la page en cours…")
        self.bouton_arreter.setEnabled(False)
        self.bouton_pause.setEnabled(False)
        self.arret_demande.emit()

    def _basculer_journal(self, ouvert: bool) -> None:
        self.journal_complet.setVisible(ouvert)
        self.bouton_journal.setText(("▾ " if ouvert else "▸ ") + "Journal technique")

    def _ouvrir_excel(self) -> None:
        if self._excel:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._excel)))

    def _ouvrir_dossier(self) -> None:
        if self._dossier:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._dossier)))

    # ── Journal ──────────────────────────────────────────────────────
    def _ajouter_journal(self, ligne: str) -> None:
        self._journal.append(ligne)
        self._journal = self._journal[-_MAX_LIGNES:]
        self.journal_resume.setText(ligne)
        self.journal_complet.setPlainText("\n".join(self._journal))

    def lignes_journal(self) -> list:
        return list(self._journal)

    @staticmethod
    def _ligne_evenement(e) -> str:
        if e.type in (ev.PAGE_DEBUT, ev.PAGE_LUE) and (e.rang or e.page) and e.total:
            return f"Lecture page {e.rang or e.page} / {e.total}"
        if e.type == ev.PHASE:
            return _LIBELLES_PHASE.get(e.etat, "Traitement en cours…")
        if e.type == ev.PAGE_ALERTE and e.alertes:
            return "⚠ " + " ; ".join(e.alertes)
        if e.type == ev.ERREUR:
            return "✗ " + (e.message or "erreur")
        if e.type == ev.FIN:
            return "✓ terminé"
        return ""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "messages"):
            self.messages.setGeometry(self.rect())
