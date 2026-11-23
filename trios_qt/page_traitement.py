"""Écran Traitement (étape 2C-7, refonte 2C d'après docs/maquettes/02_traitement_tableau_*).

Assemble l'en-tête (fichier + pastille d'état + pills type · modèle · sortie + Mini-fenêtre /
Pause / Arrêter), le rail des 4 étapes à comptes, la carte « Lecture en direct · page n », la
carte de droite (grand anneau, temps restant, écoulé / fin estimée, 3 tuiles, astuce), la carte
« Les N pages » (légende + mosaïque) et le journal replié. Tout est piloté par les événements
du converter ; aucun travail lourd ici. API publique conservée (demarrer_fichier / sur_evenement /
terminer / arret_demande / lignes_journal) pour lancement.py et fenetre.py.
"""
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
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
# Légende de la mosaïque (clé de couleur jetons, libellé).
_LEGENDE = (
    ("tuile_attente", "en attente"), ("rose_trios", "en lecture"), ("tuile_lue", "lue"),
    ("texte_natif", "texte natif"), ("a_relire", "à relire"),
)


class PageTraitement(QWidget):
    """Suit une conversion : en-tête, rail, lecture en direct, anneau, mosaïque, journal."""

    arret_demande = Signal()
    pause_demande = Signal()
    reprendre_demande = Signal()
    voir_resume = Signal()
    mini_demande = Signal()

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
        self._t0 = None
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
        colonne.setContentsMargins(28, 22, 28, 18)
        colonne.setSpacing(14)
        colonne.addWidget(self._entete())
        self.rail = RailEtapes(self._jetons, self)
        colonne.addWidget(self.rail)

        centre = QHBoxLayout()
        centre.setSpacing(16)
        centre.addWidget(self._carte_lecture(), 3)
        centre.addWidget(self._carte_droite(), 0)
        colonne.addLayout(centre, 1)

        colonne.addWidget(self._carte_pages())
        colonne.addWidget(self._barre_journal())

        self.messages = MessagesEtape(self._jetons, self)
        self.messages.setGeometry(self.rect())
        self.messages.raise_()

    def _entete(self) -> QWidget:
        cadre = QWidget(self)
        v = QVBoxLayout(cadre)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        ligne = QHBoxLayout()
        self.etiquette_fichier = QLabel("—", self)
        self.etiquette_fichier.setObjectName("traitement_fichier")
        self.pastille_etat = QLabel("En cours", self)
        self.pastille_etat.setObjectName("pastille_encours")
        ligne.addWidget(self.etiquette_fichier, 0)
        ligne.addWidget(self.pastille_etat, 0)
        ligne.addStretch(1)
        self.bouton_mini = QPushButton("Mini-fenêtre", self)
        self.bouton_mini.setObjectName("action_secondaire")
        self.bouton_mini.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_mini.clicked.connect(self.mini_demande.emit)
        self.bouton_pause = QPushButton("Pause", self)
        self.bouton_pause.setObjectName("action_secondaire")
        self.bouton_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_pause.clicked.connect(self._basculer_pause)
        self.bouton_arreter = QPushButton("Arrêter", self)
        self.bouton_arreter.setObjectName("bouton_arreter")
        self.bouton_arreter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_arreter.clicked.connect(self._demander_arret)
        for b in (self.bouton_mini, self.bouton_pause, self.bouton_arreter):
            ligne.addWidget(b, 0)
        v.addLayout(ligne)

        self._pills = QHBoxLayout()
        self._pills.setSpacing(8)
        self.pill_type = self._pill("⊞ Tableau")
        self.pill_modele = self._pill("—")
        self.pill_sortie = self._pill("→ Excel")
        for p in (self.pill_type, self.pill_modele, self.pill_sortie):
            self._pills.addWidget(p, 0)
        self._pills.addStretch(1)
        v.addLayout(self._pills)
        return cadre

    def _pill(self, texte: str) -> QLabel:
        p = QLabel(texte, self)
        p.setObjectName("pill_info")
        return p

    def _carte(self, objet: str) -> QFrame:
        cadre = QFrame(self)
        cadre.setObjectName(objet)
        return cadre

    def _carte_lecture(self) -> QFrame:
        carte = self._carte("carte_lecture")
        v = QVBoxLayout(carte)
        v.setContentsMargins(16, 14, 16, 14)
        self.lecture = LectureDirecte(self._jetons, carte)
        v.addWidget(self.lecture)
        return carte

    def _carte_droite(self) -> QFrame:
        carte = self._carte("carte_droite")
        carte.setFixedWidth(248)
        v = QVBoxLayout(carte)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)
        self.anneau = Anneau(self._jetons, carte)
        self.anneau.setMinimumHeight(170)
        v.addWidget(self.anneau)
        self.etiquette_restantes = QLabel("", carte)
        self.etiquette_restantes.setObjectName("restantes")
        self.etiquette_restantes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiquette_temps_detail = QLabel("", carte)
        self.etiquette_temps_detail.setObjectName("temps_detail")
        self.etiquette_temps_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.etiquette_restantes)
        v.addWidget(self.etiquette_temps_detail)

        tuiles = QHBoxLayout()
        tuiles.setSpacing(8)
        self.val_tableaux, t1 = self._tuile("0", "tableaux")
        self.val_relire, t2 = self._tuile("0", "pages à relire", "a_relire")
        self.val_cout, t3 = self._tuile("0,00 $", "coût Claude")
        for t in (t1, t2, t3):
            tuiles.addWidget(t, 1)
        v.addLayout(tuiles)

        self.astuces = Astuces(jetons=self._jetons, parent=carte)
        v.addWidget(self.astuces)
        v.addStretch(1)

        self.bouton_resume = QPushButton("Voir le résumé", carte)
        self.bouton_resume.setObjectName("bouton_lancer")
        self.bouton_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_resume.clicked.connect(self.voir_resume.emit)
        self.bouton_resume.setVisible(False)
        self.bouton_ouvrir_excel = QPushButton("Ouvrir l'Excel", carte)
        self.bouton_ouvrir_excel.setObjectName("action_secondaire")
        self.bouton_ouvrir_excel.clicked.connect(self._ouvrir_excel)
        self.bouton_ouvrir_dossier = QPushButton("Ouvrir le dossier", carte)
        self.bouton_ouvrir_dossier.setObjectName("action_secondaire")
        self.bouton_ouvrir_dossier.clicked.connect(self._ouvrir_dossier)
        for b in (self.bouton_resume, self.bouton_ouvrir_excel, self.bouton_ouvrir_dossier):
            b.setVisible(False)
            v.addWidget(b)
        return carte

    def _tuile(self, valeur: str, libelle: str, couleur_valeur: str = "texte"):
        c = self._jetons["couleurs"]
        tuile = QFrame(self)
        tuile.setObjectName("tuile")
        tv = QVBoxLayout(tuile)
        tv.setContentsMargins(6, 8, 6, 8)
        tv.setSpacing(1)
        val = QLabel(valeur, tuile)
        val.setObjectName("tuile_valeur")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(f"color: {c.get(couleur_valeur, c['texte'])}; font-weight: 700;")
        lib = QLabel(libelle, tuile)
        lib.setObjectName("tuile_libelle")
        lib.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lib.setWordWrap(True)
        tv.addWidget(val)
        tv.addWidget(lib)
        return val, tuile

    def _carte_pages(self) -> QFrame:
        carte = self._carte("carte_pages")
        v = QVBoxLayout(carte)
        v.setContentsMargins(16, 12, 16, 14)
        v.setSpacing(8)
        entete = QHBoxLayout()
        self.titre_pages = QLabel("Les pages", carte)
        self.titre_pages.setObjectName("panneau_titre")
        entete.addWidget(self.titre_pages, 0)
        entete.addStretch(1)
        entete.addLayout(self._legende())
        v.addLayout(entete)
        self.mosaique = Mosaique(self._jetons, carte)
        self.mosaique.setMinimumHeight(130)
        v.addWidget(self.mosaique)
        return carte

    def _legende(self) -> QHBoxLayout:
        c = self._jetons["couleurs"]
        rangee = QHBoxLayout()
        rangee.setSpacing(12)
        for cle, libelle in _LEGENDE:
            case = QLabel(self)
            case.setFixedSize(11, 11)
            case.setStyleSheet(f"background-color: {c[cle]}; border-radius: 2px;")
            txt = QLabel(libelle, self)
            txt.setObjectName("legende_texte")
            rangee.addWidget(case, 0)
            rangee.addWidget(txt, 0)
        return rangee

    def _barre_journal(self) -> QWidget:
        boite = QWidget(self)
        v = QVBoxLayout(boite)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        ligne = QHBoxLayout()
        self.bouton_journal = QPushButton("› Journal technique", boite)
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

    # ── Infos d'en-tête (facultatives) ───────────────────────────────
    def definir_infos(self, type_doc=None, modele=None, sortie=None) -> None:
        if type_doc:
            self.pill_type.setText(f"⊞ {type_doc}")
        if modele:
            self.pill_modele.setText(modele)
        if sortie:
            self.pill_sortie.setText(f"→ {sortie}")

    # ── Cycle de vie ─────────────────────────────────────────────────
    def demarrer_fichier(self, nom, type_doc=None, modele=None, sortie=None) -> None:
        self.etiquette_fichier.setText(str(nom))
        self.definir_infos(type_doc, modele, sortie)
        self._journal = []
        self._total = 0
        self._done = 0
        self._t_premiere_page = None
        self._t0 = time.monotonic()
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
        self.etiquette_restantes.setText("")
        self.etiquette_temps_detail.setText("")
        self.pastille_etat.setText("En cours")
        self.pastille_etat.setObjectName("pastille_encours")
        self._rafraichir_style(self.pastille_etat)
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
        self.rail.terminer()
        self.mosaique.arreter()
        self.lecture.definir_bande_active(False)
        self.lecture.definir_resultat("Terminé")
        self.pastille_etat.setText("Terminé")
        self.pastille_etat.setObjectName("pastille_termine")
        self._rafraichir_style(self.pastille_etat)
        self.etiquette_restantes.setText("Terminé")
        self.bouton_arreter.setVisible(False)
        self.bouton_pause.setVisible(False)
        self.bouton_resume.setVisible(True)
        self.bouton_ouvrir_excel.setVisible(bool(excel))
        self.bouton_ouvrir_dossier.setVisible(bool(dossier))
        self.messages.afficher("Conversion terminée")
        self._signaler_fin()

    def _rafraichir_style(self, widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

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
        if self._total and self.mosaique.nombre_pages() == 0:
            self.mosaique.definir_pages(self._total)
            self.titre_pages.setText(f"Les {self._total} pages")

    def _page_debut(self, e) -> None:
        self._amorcer_total(e)
        if self._t_premiere_page is None:
            self._t_premiere_page = time.monotonic()
        self.lecture.definir_titre(e.page)
        idx = (e.rang or e.page or 1) - 1
        self.mosaique.definir_etat(idx, Mosaique.LECTURE, infobulle=f"page {e.page} — en lecture")

    def _page_lue(self, e) -> None:
        self._amorcer_total(e)
        self._done = e.rang or e.page or self._done
        self.lecture.definir_titre(e.page)
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
            self.rail.definir_compte("analyse", f"{self._total} p.")
            self.rail.definir_compte("lecture", f"{done} / {self._total}")

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
        self.val_tableaux.setText(str(len(self._borniers)))
        self.val_relire.setText(str(self._pages_a_relire))
        self.val_cout.setText(self._cout_fr())

    def _cout_usd(self) -> float:
        from config import Config
        prix = getattr(Config, 'CLAUDE_PRIX_MODELES', {}) or {}
        modele = getattr(Config, 'CLAUDE_OCR_MODEL', '')
        entree, sortie = prix.get(modele, (0.0, 0.0))
        return self._tokens_entree / 1e6 * entree + self._tokens_sortie / 1e6 * sortie

    def _cout_fr(self) -> str:
        return f"{self._cout_usd():.2f} $".replace(".", ",")

    def _tic(self) -> None:
        if self._t0 is not None:
            ecoule = time.monotonic() - self._t0
            detail = f"écoulé {interface_helpers.format_duree(ecoule)}"
        else:
            detail = ""
        if self._t_premiere_page is not None and self._total:
            depuis = time.monotonic() - self._t_premiere_page
            restant = interface_helpers.estimer_temps_restant(depuis, self._done, self._total)
            if restant is not None:
                minutes = max(1, int(round(restant / 60)))
                self.etiquette_restantes.setText(f"≈ {minutes} min restantes")
                fin = datetime.now() + timedelta(seconds=restant)
                detail += " · fin estimée vers " + fin.strftime("%H:%M")
        self.etiquette_temps_detail.setText(detail)

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
        self.journal_resume.setText("Arrêt demandé — fin de la page en cours…")
        self.bouton_arreter.setEnabled(False)
        self.bouton_pause.setEnabled(False)
        self.arret_demande.emit()

    def _basculer_journal(self, ouvert: bool) -> None:
        self.journal_complet.setVisible(ouvert)
        self.bouton_journal.setText(("▾ " if ouvert else "› ") + "Journal technique")

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
