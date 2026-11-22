"""Écran d'attente du mode lot (étape 2C-8) : une piste par lot (envoi → chez Anthropic → retour
→ rapatrié), anneau des pages lues, « dernière vérification il y a n s, prochaine dans n s »,
cartes « Tu peux fermer l'appli » (+ « Me prévenir à la fin ») et « Pendant ce temps », mosaïque
par état de lot. Pas de Pause (la pause n'agit pas pendant l'attente d'un lot).

Piloté par LOT_CREE / LOT_ETAT / LOT_RECUPERE et PAGE_LUE. À la réouverture de l'appli, un lot en
cours rouvre cet écran et reprend (géré en amont, phase 1A). Aucun travail lourd ici.
"""
import time

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import evenements as ev
from trios_qt import theme
from trios_qt.anneau import Anneau
from trios_qt.mosaique import Mosaique

_MAX_LIGNES = 200


class PageAttenteLot(QWidget):
    """Suit l'attente d'un document lu en mode lot ; une piste par lot, pas de Pause."""

    ENVOI = "envoi"
    CHEZ = "chez_anthropic"
    RETOUR = "retour"
    RAPATRIE = "rapatrie"

    _LIBELLES = {ENVOI: "envoi", CHEZ: "chez Anthropic", RETOUR: "retour", RAPATRIE: "rapatrié"}

    arret_demande = Signal()
    relire_autre = Signal()
    fichier_suivant = Signal()
    voir_resume = Signal()

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("page_attente_lot")
        self._jetons = jetons or theme.charger_jetons()
        self._journal: list[str] = []
        self._excel = None
        self._dossier = None
        self._pistes: dict[str, dict] = {}
        self._compteurs: dict[str, tuple] = {}   # lot -> (lues, total)
        self._derniere_verif = None
        self._delai = 0
        self._construire()
        self._chrono = QTimer(self)
        self._chrono.setInterval(1000)
        self._chrono.timeout.connect(self._tic)
        self._chrono.start()

    # ── Construction ─────────────────────────────────────────────────
    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(32, 24, 32, 20)
        colonne.setSpacing(14)

        titre = QLabel("Mode économique — lecture par lots", self)
        titre.setObjectName("titre_ecran")
        self.etiquette_fichier = QLabel("—", self)
        self.etiquette_fichier.setObjectName("traitement_fichier")
        colonne.addWidget(titre)
        colonne.addWidget(self.etiquette_fichier)

        haut = QHBoxLayout()
        haut.setSpacing(16)
        self.anneau = Anneau(self._jetons, self)
        self.anneau.setMinimumSize(180, 150)   # sinon l'anneau collapse (stretch 0, hors panneau)
        self.anneau.setMaximumWidth(220)
        haut.addWidget(self.anneau, 0)
        self._pistes_boite = QVBoxLayout()
        self._pistes_boite.setSpacing(8)
        cadre_pistes = QWidget(self)
        cadre_pistes.setLayout(self._pistes_boite)
        haut.addWidget(cadre_pistes, 1)
        colonne.addLayout(haut)

        self.etiquette_verification = QLabel("", self)
        self.etiquette_verification.setObjectName("traitement_progression")
        colonne.addWidget(self.etiquette_verification)

        self.mosaique = Mosaique(self._jetons, self)
        self.mosaique.setMinimumHeight(40)
        colonne.addWidget(self.mosaique)

        colonne.addWidget(self._cartes())
        colonne.addLayout(self._barre_boutons())
        colonne.addStretch(1)

    def _cartes(self) -> QWidget:
        boite = QWidget(self)
        rangee = QHBoxLayout(boite)
        rangee.setContentsMargins(0, 0, 0, 0)
        rangee.setSpacing(12)

        self.carte_fermer = QFrame(self)
        self.carte_fermer.setObjectName("carte_message")
        cf = QVBoxLayout(self.carte_fermer)
        cf.addWidget(QLabel("Tu peux fermer l'appli : le lot continue chez Anthropic. "
                            "À la réouverture, cet écran reprend tout seul."))
        self.interrupteur_prevenir = QCheckBox("Me prévenir à la fin", self.carte_fermer)
        self.interrupteur_prevenir.setObjectName("case_lot")
        cf.addWidget(self.interrupteur_prevenir)
        rangee.addWidget(self.carte_fermer, 1)

        self.carte_pendant = QFrame(self)
        self.carte_pendant.setObjectName("carte_astuce")
        cp = QVBoxLayout(self.carte_pendant)
        cp.addWidget(QLabel("Pendant ce temps"))
        self.bouton_relire = QPushButton("Relire un autre document", self.carte_pendant)
        self.bouton_relire.setObjectName("action_secondaire")
        self.bouton_relire.clicked.connect(self.relire_autre.emit)
        self.bouton_suivant = QPushButton("Lancer le fichier suivant", self.carte_pendant)
        self.bouton_suivant.setObjectName("action_secondaire")
        self.bouton_suivant.clicked.connect(self.fichier_suivant.emit)
        cp.addWidget(self.bouton_relire)
        cp.addWidget(self.bouton_suivant)
        rangee.addWidget(self.carte_pendant, 1)
        return boite

    def _barre_boutons(self):
        rangee = QHBoxLayout()
        self.bouton_arreter = QPushButton("Arrêter", self)
        self.bouton_arreter.setObjectName("bouton_arreter")
        self.bouton_arreter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_arreter.clicked.connect(self._demander_arret)
        self.bouton_resume = QPushButton("Voir le résumé", self)
        self.bouton_resume.setObjectName("bouton_lancer")
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
        rangee.addWidget(self.bouton_arreter)
        rangee.addStretch(1)
        rangee.addWidget(self.bouton_ouvrir_excel)
        rangee.addWidget(self.bouton_ouvrir_dossier)
        rangee.addWidget(self.bouton_resume)
        return rangee

    # ── Cycle de vie ─────────────────────────────────────────────────
    def demarrer_fichier(self, nom) -> None:
        self.etiquette_fichier.setText(str(nom))
        self._journal = []
        self._pistes = {}
        self._compteurs = {}
        self._derniere_verif = None
        while self._pistes_boite.count():
            el = self._pistes_boite.takeAt(0)
            if el.widget() is not None:
                el.widget().deleteLater()
        self.anneau.reinitialiser()
        self.bouton_resume.setVisible(False)
        self.bouton_ouvrir_excel.setVisible(False)
        self.bouton_ouvrir_dossier.setVisible(False)
        self.bouton_arreter.setVisible(True)
        self.bouton_arreter.setEnabled(True)

    def terminer(self, excel=None, dossier=None) -> None:
        self._excel = excel
        self._dossier = dossier
        self._chrono.stop()
        self.anneau.terminer()
        self.bouton_arreter.setVisible(False)
        self.bouton_resume.setVisible(True)
        self.bouton_ouvrir_excel.setVisible(bool(excel))
        self.bouton_ouvrir_dossier.setVisible(bool(dossier))

    # ── Événements ───────────────────────────────────────────────────
    def sur_evenement(self, e) -> None:
        if e.type == ev.LOT_CREE:
            self._lot_cree(e)
        elif e.type == ev.LOT_ETAT:
            self._lot_etat(e)
        elif e.type == ev.LOT_RECUPERE:
            self._lot_recupere(e)
        elif e.type == ev.PAGE_LUE:
            self._page_lue(e)
        elif e.type == ev.FIN:
            pass
        ligne = self._ligne_evenement(e)
        if ligne:
            self._ajouter_journal(ligne)

    def _piste_neuve(self, lot: str, taille_mo: float) -> None:
        label = QLabel(self)
        label.setObjectName("piste_lot")
        label.setWordWrap(True)
        self._pistes[lot] = {"label": label, "phase": self.ENVOI, "taille_mo": taille_mo,
                             "lues": 0, "total": 0}
        self._pistes_boite.addWidget(label)

    def _lot_cree(self, e) -> None:
        comp = e.compteurs or {}
        if e.lot not in self._pistes:
            self._piste_neuve(e.lot, float(comp.get("taille_mo", 0.0)))
        self._pistes[e.lot]["phase"] = self.CHEZ
        self._pistes[e.lot]["total"] = int(comp.get("requetes", 0))
        self._maj_piste(e.lot)

    def _lot_etat(self, e) -> None:
        comp = e.compteurs or {}
        if e.lot not in self._pistes:
            self._piste_neuve(e.lot, float(comp.get("taille_mo", 0.0)))
        self._pistes[e.lot]["phase"] = self.CHEZ
        lues, total = int(comp.get("lues", 0)), int(comp.get("total", 0))
        self._pistes[e.lot]["lues"] = lues
        self._pistes[e.lot]["total"] = total or self._pistes[e.lot]["total"]
        self._compteurs[e.lot] = (lues, total)
        self._delai = int(comp.get("delai", self._delai))
        self._derniere_verif = time.monotonic()
        self._maj_piste(e.lot)
        self._maj_anneau()
        self._maj_verification()

    def _lot_recupere(self, e) -> None:
        comp = e.compteurs or {}
        if e.lot not in self._pistes:
            self._piste_neuve(e.lot, float(comp.get("taille_mo", 0.0)))
        total = int(comp.get("total", self._pistes[e.lot]["total"]))
        lues = int(comp.get("lues", total))
        self._pistes[e.lot].update(phase=self.RAPATRIE, lues=lues, total=total)
        self._compteurs[e.lot] = (lues, total)
        self._maj_piste(e.lot)
        self._maj_anneau()

    def _page_lue(self, e) -> None:
        if e.total and self.mosaique.nombre_pages() == 0:
            self.mosaique.definir_pages(e.total)
        idx = (e.rang or e.page or 1) - 1
        self.mosaique.definir_etat(idx, Mosaique.LUE,
                                   infobulle=f"page {e.page} — rapatriée")

    # ── Affichage dérivé ─────────────────────────────────────────────
    def _maj_piste(self, lot: str) -> None:
        p = self._pistes[lot]
        phase = self._LIBELLES.get(p["phase"], p["phase"])
        self._pistes[lot]["label"].setText(
            f"Lot {lot} — {p['taille_mo']:.1f} Mo — {phase} — {p['lues']}/{p['total']} pages")

    def _maj_anneau(self) -> None:
        lues = sum(lu for lu, _ in self._compteurs.values())
        total = sum(to for _, to in self._compteurs.values())
        if total:
            self.anneau.definir_valeur(lues / total)
            self.anneau.definir_sous_libelle(f"{lues} / {total} pages lues")

    def _maj_verification(self) -> None:
        if self._derniere_verif is None:
            return
        ecoule = int(time.monotonic() - self._derniere_verif)
        prochaine = max(0, self._delai - ecoule)
        self.etiquette_verification.setText(
            f"Dernière vérification il y a {ecoule} s, prochaine dans {prochaine} s")

    def _tic(self) -> None:
        self._maj_verification()

    def nombre_pistes(self) -> int:
        return len(self._pistes)

    def piste(self, lot: str) -> QLabel:
        return self._pistes[lot]["label"]

    def phase_piste(self, lot: str) -> str:
        return self._pistes[lot]["phase"]

    # ── Boutons ──────────────────────────────────────────────────────
    def _demander_arret(self) -> None:
        self.etiquette_verification.setText("Arrêt demandé — le lot en cours est annulé…")
        self.bouton_arreter.setEnabled(False)
        self.arret_demande.emit()

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

    def lignes_journal(self) -> list:
        return list(self._journal)

    @staticmethod
    def _ligne_evenement(e) -> str:
        if e.type == ev.LOT_CREE:
            return f"Lot {e.lot} envoyé"
        if e.type == ev.LOT_RECUPERE:
            return f"Lot {e.lot} rapatrié"
        if e.type == ev.ERREUR:
            return "✗ " + (e.message or "erreur")
        if e.type == ev.FIN:
            return "✓ terminé"
        return ""
