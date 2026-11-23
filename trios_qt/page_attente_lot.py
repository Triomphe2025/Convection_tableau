"""Écran d'attente du mode lot (étape 2C-8, refonte 2C d'après docs/maquettes/09_attente_lot).

En-tête (fichier + pastille « Chez Anthropic » + pills + Mini-fenêtre / Annuler les lots), rail à
4 segments (Préparation / Envoi / Lecture chez Anthropic / Récupération et Excel), diagramme de
flux « Ce PC → Anthropic » (une piste en pointillés par lot, pastille qui avance), 3 cartes en bas
(anneau des pages lues + vérifications, « Tu peux fermer l'appli », « Pendant ce temps ») et
mosaïque « Les N pages » à légende. Pas de Pause. Piloté par LOT_CREE / LOT_ETAT / LOT_RECUPERE et
PAGE_LUE ; aucun travail lourd ici.
"""
import time

from PySide6.QtCore import QRectF, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import evenements as ev
from trios_qt import theme
from trios_qt.anneau import Anneau
from trios_qt.mosaique import Mosaique
from trios_qt.rail_etapes import RailEtapes

_MAX_LIGNES = 200
_RAIL_CLES = ("preparation", "envoi", "lecture", "recuperation")
_RAIL_LIBELLES = {
    "preparation": "Préparation", "envoi": "Envoi",
    "lecture": "Lecture chez Anthropic", "recuperation": "Récupération et Excel",
}
# Légende de la mosaïque du lot (clé de couleur jetons, libellé).
_LEGENDE_LOT = (
    ("texte_natif", "texte natif (sans Claude)"), ("lot_en_cours", "dans un lot"),
    ("rose_trios", "lue, pas encore rapatriée"), ("tuile_lue", "rapatriée"),
)


class DiagrammeLots(QWidget):
    """Flux « Ce PC → Anthropic » : une piste en pointillés par lot, pastille à l'avancement."""

    def __init__(self, jetons: dict, parent=None):
        super().__init__(parent)
        self._jetons = jetons
        self._lots: list[dict] = []
        self.setMinimumHeight(170)

    def definir_lots(self, lots) -> None:
        self._lots = list(lots)
        self.update()

    def nombre_lots(self) -> int:
        return len(self._lots)

    def fraction_lot(self, i: int) -> float:
        d = self._lots[i]
        return (d.get("lues", 0) / d["total"]) if d.get("total") else 0.0

    def couleur_lot(self, i: int) -> QColor:
        c = self._jetons["couleurs"]
        rapatrie = self._lots[i].get("phase") == PageAttenteLot.RAPATRIE
        return QColor(c["tuile_lue"] if rapatrie else c["lot_en_cours"])

    def paintEvent(self, _evenement):
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._noeud(peintre, 0, "Ce PC", "prépare, puis récupère")
        self._noeud(peintre, self.width() - 86, "Anthropic", "lit les pages du lot")
        if not self._lots:
            peintre.end()
            return
        x0, x1 = 92, self.width() - 92
        larg_pastille = 92.0
        row_h = self.height() / len(self._lots)
        for i, lot in enumerate(self._lots):
            y = (i + 0.5) * row_h
            stylo = QPen(QColor(c["trait"]), 1)
            stylo.setStyle(Qt.PenStyle.DashLine)
            peintre.setPen(stylo)
            peintre.drawLine(int(x0), int(y), int(x1), int(y))
            frac = self.fraction_lot(i)
            px = x0 + frac * (x1 - x0 - larg_pastille)
            boite = QRectF(px, y - 13, larg_pastille, 26)
            peintre.setPen(Qt.PenStyle.NoPen)
            fond = QColor(self.couleur_lot(i))
            fond.setAlphaF(0.30)
            peintre.setBrush(fond)
            peintre.drawRoundedRect(boite, 13, 13)
            peintre.setPen(QColor(c["texte"]))
            peintre.drawText(boite, Qt.AlignmentFlag.AlignCenter,
                             f"Lot {i + 1} · {lot.get('total', 0)} p.")
            peintre.setPen(QColor(c["texte_discret"]))
            peintre.drawText(QRectF(x0, y + 10, 70, 16), Qt.AlignmentFlag.AlignLeft,
                             f"{lot.get('taille_mo', 0):.0f} Mo")
            rapatrie = lot.get("phase") == PageAttenteLot.RAPATRIE
            droite = ("retour des résultats" if rapatrie
                      else f"lu {lot.get('lues', 0)} / {lot.get('total', 0)}")
            peintre.setPen(QColor(c["succes"] if rapatrie else c["texte_discret"]))
            boite_d = QRectF(x1 - 150, y + 10, 150, 16)
            peintre.drawText(boite_d, Qt.AlignmentFlag.AlignRight, droite)
        peintre.end()

    def _noeud(self, peintre, x, titre, sous):
        c = self._jetons["couleurs"]
        boite = QRectF(x, self.height() / 2 - 26, 86, 52)
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(QColor(c["sureleve"]))
        peintre.drawRoundedRect(boite, 10, 10)
        peintre.setPen(QColor(c["texte"]))
        peintre.drawText(QRectF(x, self.height() / 2 - 22, 86, 20),
                         Qt.AlignmentFlag.AlignCenter, titre)
        peintre.setPen(QColor(c["texte_discret"]))
        peintre.drawText(QRectF(x - 10, self.height() / 2 + 28, 106, 28),
                         Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, sous)


class PageAttenteLot(QWidget):
    """Suit l'attente d'un document lu en mode lot ; une piste par lot, pas de Pause."""

    ENVOI = "envoi"
    CHEZ = "chez_anthropic"
    RETOUR = "retour"
    RAPATRIE = "rapatrie"

    arret_demande = Signal()
    relire_autre = Signal()
    fichier_suivant = Signal()
    voir_resume = Signal()
    mini_demande = Signal()

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("page_attente_lot")
        self._jetons = jetons or theme.charger_jetons()
        self._journal: list[str] = []
        self._excel = None
        self._dossier = None
        self._lots: dict[str, dict] = {}
        self._derniere_verif = None
        self._delai = 0
        self._construire()
        self._chrono = QTimer(self)
        self._chrono.setInterval(1000)
        self._chrono.timeout.connect(self._maj_verification)
        self._chrono.start()

    # ── Construction ─────────────────────────────────────────────────
    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(28, 22, 28, 18)
        colonne.setSpacing(14)
        colonne.addWidget(self._entete())
        self.rail = RailEtapes(self._jetons, self, cles=_RAIL_CLES, libelles=_RAIL_LIBELLES)
        colonne.addWidget(self.rail)

        carte_flux = self._carte("carte_lecture")
        vf = QVBoxLayout(carte_flux)
        vf.setContentsMargins(16, 14, 16, 14)
        self.diagramme = DiagrammeLots(self._jetons, carte_flux)
        vf.addWidget(self.diagramme)
        colonne.addWidget(carte_flux, 1)

        bas = QHBoxLayout()
        bas.setSpacing(12)
        bas.addWidget(self._carte_anneau(), 1)
        bas.addWidget(self._carte_fermer(), 1)
        bas.addWidget(self._carte_pendant(), 1)
        colonne.addLayout(bas)

        colonne.addWidget(self._carte_pages())

    def _entete(self) -> QWidget:
        cadre = QWidget(self)
        v = QVBoxLayout(cadre)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        ligne = QHBoxLayout()
        self.etiquette_fichier = QLabel("—", self)
        self.etiquette_fichier.setObjectName("traitement_fichier")
        self.pastille_etat = QLabel("Chez Anthropic", self)
        self.pastille_etat.setObjectName("pastille_lot")
        ligne.addWidget(self.etiquette_fichier, 0)
        ligne.addWidget(self.pastille_etat, 0)
        ligne.addStretch(1)
        self.bouton_mini = QPushButton("Mini-fenêtre", self)
        self.bouton_mini.setObjectName("action_secondaire")
        self.bouton_mini.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_mini.clicked.connect(self.mini_demande.emit)
        self.bouton_arreter = QPushButton("Annuler les lots", self)
        self.bouton_arreter.setObjectName("bouton_arreter")
        self.bouton_arreter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_arreter.clicked.connect(self._demander_arret)
        self.bouton_ouvrir_excel = QPushButton("Ouvrir l'Excel", self)
        self.bouton_ouvrir_excel.setObjectName("action_secondaire")
        self.bouton_ouvrir_excel.clicked.connect(self._ouvrir_excel)
        self.bouton_ouvrir_dossier = QPushButton("Ouvrir le dossier", self)
        self.bouton_ouvrir_dossier.setObjectName("action_secondaire")
        self.bouton_ouvrir_dossier.clicked.connect(self._ouvrir_dossier)
        self.bouton_resume = QPushButton("Voir le résumé", self)
        self.bouton_resume.setObjectName("bouton_lancer")
        self.bouton_resume.clicked.connect(self.voir_resume.emit)
        for b in (self.bouton_ouvrir_excel, self.bouton_ouvrir_dossier, self.bouton_resume):
            b.setVisible(False)
        ligne.addWidget(self.bouton_mini, 0)
        ligne.addWidget(self.bouton_arreter, 0)
        ligne.addWidget(self.bouton_ouvrir_excel, 0)
        ligne.addWidget(self.bouton_ouvrir_dossier, 0)
        ligne.addWidget(self.bouton_resume, 0)
        v.addLayout(ligne)

        pills = QHBoxLayout()
        pills.setSpacing(8)
        for p in (self._pill("⊞ Tableau · Bornier standard"),
                  self._pill("Mode économique (lot) · −50 %"),
                  self._pill("Claude Sonnet 5.5 · → Excel")):
            pills.addWidget(p, 0)
        pills.addStretch(1)
        v.addLayout(pills)
        return cadre

    def _pill(self, texte: str) -> QLabel:
        p = QLabel(texte, self)
        p.setObjectName("pill_info")
        return p

    def _carte(self, objet: str) -> QFrame:
        cadre = QFrame(self)
        cadre.setObjectName(objet)
        return cadre

    def _carte_anneau(self) -> QFrame:
        carte = self._carte("carte_droite")
        v = QVBoxLayout(carte)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(6)
        rangee = QHBoxLayout()
        self.anneau = Anneau(self._jetons, carte)
        self.anneau.setFixedSize(92, 92)
        rangee.addWidget(self.anneau, 0)
        droite = QVBoxLayout()
        titre = QLabel("pages lues par Anthropic", carte)
        titre.setObjectName("panneau_titre")
        titre.setWordWrap(True)
        texte = QLabel("La plupart des lots reviennent en moins d'une heure ; "
                       "le délai maximum est de 24 h.", carte)
        texte.setObjectName("temps_detail")
        texte.setWordWrap(True)
        droite.addWidget(titre)
        droite.addWidget(texte)
        rangee.addLayout(droite, 1)
        v.addLayout(rangee)
        self.etiquette_verification = QLabel("", carte)
        self.etiquette_verification.setObjectName("mini_relire")
        v.addWidget(self.etiquette_verification)
        return carte

    def _carte_fermer(self) -> QFrame:
        self.carte_fermer = self._carte("carte_droite")
        v = QVBoxLayout(self.carte_fermer)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        titre = QLabel("Tu peux fermer l'appli", self.carte_fermer)
        titre.setObjectName("panneau_titre")
        texte = QLabel("Les lots continuent chez Anthropic. À la prochaine ouverture, l'appli "
                       "récupère les résultats toute seule et finit l'Excel.", self.carte_fermer)
        texte.setObjectName("temps_detail")
        texte.setWordWrap(True)
        self.interrupteur_prevenir = QCheckBox("Me prévenir à la fin (notification Windows)",
                                               self.carte_fermer)
        self.interrupteur_prevenir.setObjectName("case_lot")
        v.addWidget(titre)
        v.addWidget(texte)
        v.addWidget(self.interrupteur_prevenir)
        return self.carte_fermer

    def _carte_pendant(self) -> QFrame:
        self.carte_pendant = self._carte("carte_droite")
        v = QVBoxLayout(self.carte_pendant)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        titre = QLabel("Pendant ce temps", self.carte_pendant)
        titre.setObjectName("panneau_titre")
        v.addWidget(titre)
        self.bouton_relire = QPushButton("Relire un autre document", self.carte_pendant)
        self.bouton_relire.setObjectName("action_secondaire")
        self.bouton_relire.clicked.connect(self.relire_autre.emit)
        self.bouton_suivant = QPushButton("Lancer le fichier suivant", self.carte_pendant)
        self.bouton_suivant.setObjectName("action_secondaire")
        self.bouton_suivant.clicked.connect(self.fichier_suivant.emit)
        v.addWidget(self.bouton_relire)
        v.addWidget(self.bouton_suivant)
        return self.carte_pendant

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
        c = self._jetons["couleurs"]
        for cle, libelle in _LEGENDE_LOT:
            case = QLabel(self)
            case.setFixedSize(11, 11)
            case.setStyleSheet(f"background-color: {c[cle]}; border-radius: 2px;")
            txt = QLabel(libelle, self)
            txt.setObjectName("legende_texte")
            entete.addWidget(case, 0)
            entete.addWidget(txt, 0)
            entete.addSpacing(8)
        v.addLayout(entete)
        self.mosaique = Mosaique(self._jetons, carte)
        self.mosaique.setFixedHeight(Mosaique.TAILLE_TUILE + Mosaique.ECART)
        v.addWidget(self.mosaique)
        return carte

    # ── Cycle de vie ─────────────────────────────────────────────────
    def demarrer_fichier(self, nom, type_doc=None, modele=None, sortie=None) -> None:
        self.etiquette_fichier.setText(str(nom))
        self._journal = []
        self._lots = {}
        self._derniere_verif = None
        self.diagramme.definir_lots([])
        self.anneau.reinitialiser()
        self.bouton_arreter.setVisible(True)
        self.bouton_arreter.setEnabled(True)

    def terminer(self, excel=None, dossier=None) -> None:
        self._excel = excel
        self._dossier = dossier
        self._chrono.stop()
        self.anneau.terminer()
        self.rail.terminer()
        self.pastille_etat.setText("Terminé")
        self.pastille_etat.setObjectName("pastille_termine")
        self.pastille_etat.style().unpolish(self.pastille_etat)
        self.pastille_etat.style().polish(self.pastille_etat)
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
        ligne = self._ligne_evenement(e)
        if ligne:
            self._ajouter_journal(ligne)

    def _lot(self, lot: str, taille_mo: float = 0.0) -> dict:
        if lot not in self._lots:
            self._lots[lot] = {"lot": lot, "taille_mo": taille_mo, "lues": 0, "total": 0,
                               "phase": self.ENVOI}
        return self._lots[lot]

    def _rafraichir_diagramme(self) -> None:
        self.rail.definir_phase("lecture")
        self.diagramme.definir_lots(list(self._lots.values()))
        self._maj_anneau()

    def _lot_cree(self, e) -> None:
        comp = e.compteurs or {}
        d = self._lot(e.lot, float(comp.get("taille_mo", 0.0)))
        d["phase"] = self.CHEZ
        d["total"] = int(comp.get("requetes", d["total"]))
        self._rafraichir_diagramme()

    def _lot_etat(self, e) -> None:
        comp = e.compteurs or {}
        d = self._lot(e.lot, float(comp.get("taille_mo", 0.0)))
        d["phase"] = self.CHEZ
        d["lues"] = int(comp.get("lues", 0))
        d["total"] = int(comp.get("total", 0)) or d["total"]
        self._delai = int(comp.get("delai", self._delai))
        self._derniere_verif = time.monotonic()
        self._rafraichir_diagramme()
        self._maj_verification()

    def _lot_recupere(self, e) -> None:
        comp = e.compteurs or {}
        d = self._lot(e.lot, float(comp.get("taille_mo", 0.0)))
        d["total"] = int(comp.get("total", d["total"]))
        d["lues"] = int(comp.get("lues", d["total"]))
        d["phase"] = self.RAPATRIE
        self._rafraichir_diagramme()

    def _page_lue(self, e) -> None:
        if e.total and self.mosaique.nombre_pages() == 0:
            self.mosaique.definir_pages(e.total)
            self.titre_pages.setText(f"Les {e.total} pages")
            self.mosaique.setFixedHeight(self.mosaique.hauteur_rangees(10))
        idx = (e.rang or e.page or 1) - 1
        self.mosaique.definir_etat(idx, Mosaique.LUE, infobulle=f"page {e.page} — rapatriée")

    # ── Affichage dérivé ─────────────────────────────────────────────
    def _maj_anneau(self) -> None:
        lues = sum(d.get("lues", 0) for d in self._lots.values())
        total = sum(d.get("total", 0) for d in self._lots.values())
        if total:
            self.anneau.definir_valeur(lues / total)
            self.anneau.definir_sous_libelle(f"{lues} sur {total}")

    def _maj_verification(self) -> None:
        if self._derniere_verif is None:
            return
        ecoule = int(time.monotonic() - self._derniere_verif)
        prochaine = max(0, self._delai - ecoule)
        self.etiquette_verification.setText(
            f"Dernière vérification il y a {ecoule} s · prochaine dans {prochaine} s")

    def nombre_pistes(self) -> int:
        return len(self._lots)

    def phase_piste(self, lot: str) -> str:
        return self._lots[lot]["phase"]

    def lot_texte(self, lot: str) -> str:
        d = self._lots[lot]
        return f"Lot {lot} · {d['taille_mo']:.1f} Mo · {d['lues']}/{d['total']} pages"

    # ── Boutons ──────────────────────────────────────────────────────
    def _demander_arret(self) -> None:
        self.etiquette_verification.setText("Annulation demandée — lots en cours annulés…")
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
