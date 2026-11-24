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
_NATURES_NATIVES = {'vectoriel', 'texte', 'natif'}
_RAIL_CLES = ("preparation", "envoi", "lecture", "recuperation")
_RAIL_LIBELLES = {
    "preparation": "Préparation", "envoi": "Envoi",
    "lecture": "Lecture chez Anthropic", "recuperation": "Récupération et Excel",
}
# Légende de la mosaïque du lot (clé de couleur jetons, libellé).
_LEGENDE_LOT = (
    ("texte_natif", "texte natif (sans Claude)"), ("lot_en_cours", "dans un lot"),
    ("page_scannee", "lue, pas encore rapatriée"), ("tuile_lue", "rapatriée"),
)


class DiagrammeLots(QWidget):
    """Flux « Ce PC → Anthropic » : une piste en pointillés par lot, pastille à l'avancement."""

    def __init__(self, jetons: dict, parent=None):
        super().__init__(parent)
        self._jetons = jetons
        self._lots: list[dict] = []
        self.setMinimumHeight(210)
        from trios_qt import icones
        couleur = jetons["couleurs"]["texte_secondaire"]
        self._pix_poste = icones.charger_icone("poste", couleur, 22).pixmap(22, 22)
        self._pix_nuage = icones.charger_icone("nuage", couleur, 22).pixmap(22, 22)

    def definir_lots(self, lots) -> None:
        self._lots = list(lots)
        self.update()

    def nombre_lots(self) -> int:
        return len(self._lots)

    def fraction_lot(self, i: int) -> float:
        d = self._lots[i]
        return (d.get("lues", 0) / d["total"]) if d.get("total") else 0.0

    def position_fraction(self, i: int) -> float:
        """Position de la pastille sur sa piste selon l'ÉTAPE du lot, pas la part lue :
        rapatrié = revenu à gauche (PC) ; envoi = en route ; chez Anthropic = à droite."""
        phase = self._lots[i].get("phase")
        if phase == PageAttenteLot.RAPATRIE:
            return 0.0
        if phase == PageAttenteLot.ENVOI:
            return 0.4
        return 0.85   # chez Anthropic

    def couleur_lot(self, i: int) -> QColor:
        c = self._jetons["couleurs"]
        rapatrie = self._lots[i].get("phase") == PageAttenteLot.RAPATRIE
        return QColor(c["tuile_lue"] if rapatrie else c["lot_en_cours"])

    ZONE = 124   # largeur fixe d'un bloc (Ce PC / Anthropic) ; au moins 120 px

    def paintEvent(self, _evenement):
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._noeud(peintre, 0, "Ce PC", "prépare, puis récupère", self._pix_poste)
        self._noeud(peintre, self.width() - self.ZONE, "Anthropic", "lit les pages du lot",
                    self._pix_nuage)
        if not self._lots:
            peintre.end()
            return
        x0, x1 = self.ZONE + 6, self.width() - self.ZONE - 6
        larg_pastille = 92.0
        row_h = self.height() / len(self._lots)
        for i, lot in enumerate(self._lots):
            y = (i + 0.5) * row_h
            stylo = QPen(QColor(c["trait"]), 1)
            stylo.setStyle(Qt.PenStyle.DashLine)
            peintre.setPen(stylo)
            peintre.drawLine(int(x0), int(y), int(x1), int(y))
            # Mo, à gauche de la piste, sous le départ.
            peintre.setPen(QColor(c["texte_discret"]))
            peintre.drawText(QRectF(x0, y + 11, 60, 15), Qt.AlignmentFlag.AlignLeft,
                             f"{lot.get('taille_mo', 0):.0f} Mo")
            px = x0 + self.position_fraction(i) * (x1 - x0 - larg_pastille)
            boite = QRectF(px, y - 13, larg_pastille, 26)
            fond = QColor(self.couleur_lot(i))
            fond.setAlphaF(0.30)
            contour = QPen(QColor(self.couleur_lot(i)), 1)   # contour fin visible
            peintre.setPen(contour)
            peintre.setBrush(fond)
            peintre.drawRoundedRect(boite, 13, 13)
            peintre.setPen(QColor(c["texte"]))
            peintre.drawText(boite, Qt.AlignmentFlag.AlignCenter,
                             f"Lot {i + 1} · {lot.get('total', 0)} p.")
            rapatrie = lot.get("phase") == PageAttenteLot.RAPATRIE
            if rapatrie:
                peintre.setPen(QColor(c["succes"]))
                peintre.drawText(QRectF(px + larg_pastille + 8, y - 8, 150, 16),
                                 Qt.AlignmentFlag.AlignLeft, "retour des résultats")
            else:
                # « lu x / y » juste sous la pastille, aligné à droite sur elle.
                peintre.setPen(QColor(c["texte_discret"]))
                peintre.drawText(QRectF(px + larg_pastille - 150, y + 11, 150, 15),
                                 Qt.AlignmentFlag.AlignRight,
                                 f"lu {lot.get('lues', 0)} / {lot.get('total', 0)}")
        peintre.end()

    def _noeud(self, peintre, x, titre, sous, pixmap):
        c = self._jetons["couleurs"]
        cx = x + self.ZONE / 2
        cy = self.height() / 2
        tuile = QRectF(cx - 25, cy - 52, 50, 50)   # carré arrondi encadré, ~50 px
        peintre.setPen(QPen(QColor(c["trait"]), 1))
        peintre.setBrush(QColor(c["sureleve"]))
        peintre.drawRoundedRect(tuile, 12, 12)
        peintre.drawPixmap(int(cx - 11), int(cy - 38), pixmap)
        peintre.setPen(QColor(c["texte"]))
        peintre.drawText(QRectF(x, cy + 4, self.ZONE, 18), Qt.AlignmentFlag.AlignHCenter, titre)
        peintre.setPen(QColor(c["texte_discret"]))
        peintre.drawText(QRectF(x, cy + 22, self.ZONE, 34),
                         Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, sous)


class BarreDecompte(QWidget):
    """Fine barre horizontale qui se vide jusqu'à la prochaine vérification du lot."""

    def __init__(self, jetons: dict, parent=None):
        super().__init__(parent)
        self._jetons = jetons
        self._fraction = 1.0
        self.setFixedHeight(3)

    def definir_fraction(self, f: float) -> None:
        self._fraction = max(0.0, min(1.0, float(f)))
        self.update()

    def paintEvent(self, _evenement):
        c = self._jetons["couleurs"]
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(QColor(c["trait"]))
        peintre.drawRoundedRect(QRectF(0, 0, self.width(), 3), 1.5, 1.5)
        peintre.setBrush(QColor(c["lot_en_cours"]))
        peintre.drawRoundedRect(QRectF(0, 0, self.width() * self._fraction, 3), 1.5, 1.5)
        peintre.end()


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
        self._natures: dict[int, str] = {}
        self._total = 0
        self._pages_rapatriees: set[int] = set()
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
        self.rail = RailEtapes(self._jetons, self, cles=_RAIL_CLES, libelles=_RAIL_LIBELLES,
                               couleur_courante=self._jetons["couleurs"]["lot_en_cours"])
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
        self.anneau.setFixedSize(96, 96)
        self.anneau.definir_taille_pourcentage(22)   # « 52 » tient dans l'anneau
        self.anneau.definir_couleur(self._jetons["couleurs"]["lot_en_cours"])   # arc violet
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
        self.etiquette_verification.setObjectName("temps_detail")   # gris normal (pas orange gras)
        v.addWidget(self.etiquette_verification)
        self.barre_decompte = BarreDecompte(self._jetons, carte)
        v.addWidget(self.barre_decompte)
        return carte

    def _carte_fermer(self) -> QFrame:
        self.carte_fermer = self._carte("carte_droite")
        v = QVBoxLayout(self.carte_fermer)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        from trios_qt import icones
        rangee_titre = QHBoxLayout()
        rangee_titre.setSpacing(7)
        icone = QLabel(self.carte_fermer)
        icone.setPixmap(icones.charger_icone(
            "bouclier", self._jetons["couleurs"]["succes"], 18).pixmap(18, 18))
        titre = QLabel("Tu peux fermer l'appli", self.carte_fermer)
        titre.setObjectName("panneau_titre")
        rangee_titre.addWidget(icone, 0)
        rangee_titre.addWidget(titre, 0)
        rangee_titre.addStretch(1)
        texte = QLabel("Les lots continuent chez Anthropic. À la prochaine ouverture, l'appli "
                       "récupère les résultats toute seule et finit l'Excel.", self.carte_fermer)
        texte.setObjectName("temps_detail")
        texte.setWordWrap(True)
        self.interrupteur_prevenir = QCheckBox("Me prévenir à la fin (notification Windows)",
                                               self.carte_fermer)
        self.interrupteur_prevenir.setObjectName("case_lot")
        v.addLayout(rangee_titre)
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
        self.ligne_relire, self.etiq_relire, self.bouton_relire = self._ligne_action(
            "Relire", self.relire_autre.emit)
        self.ligne_suivant, self.etiq_suivant, self.bouton_suivant = self._ligne_action(
            "Lancer", self.fichier_suivant.emit)
        v.addWidget(self.ligne_relire)
        v.addWidget(self.ligne_suivant)
        v.addStretch(1)
        self.ligne_relire.setVisible(False)    # masquées tant qu'il n'y a rien
        self.ligne_suivant.setVisible(False)
        return self.carte_pendant

    def _ligne_action(self, lien, rappel):
        cadre = QWidget(self.carte_pendant)
        h = QHBoxLayout(cadre)
        h.setContentsMargins(0, 0, 0, 0)
        etiquette = QLabel("", cadre)
        etiquette.setObjectName("temps_detail")
        bouton = QPushButton(lien, cadre)
        bouton.setObjectName("lien_action")
        bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton.clicked.connect(rappel)
        h.addWidget(etiquette, 1)
        h.addWidget(bouton, 0)
        return cadre, etiquette, bouton

    def definir_points_a_relire(self, n: int, document: str = "") -> None:
        if n and n > 0:
            nom = document or self.etiquette_fichier.text()
            self.etiq_relire.setText(f"Relire les {n} points de {nom}")
            self.ligne_relire.setVisible(True)
        else:
            self.ligne_relire.setVisible(False)

    def definir_fichier_suivant(self, nom: str = "") -> None:
        if nom:
            self.etiq_suivant.setText("Lancer le fichier suivant de la file")
            self.ligne_suivant.setVisible(True)
        else:
            self.ligne_suivant.setVisible(False)

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
        if e.type == ev.ANALYSE:
            self._analyse(e)
        elif e.type == ev.LOT_CREE:
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

    def _amorcer_pages(self, total) -> None:
        if total and self.mosaique.nombre_pages() == 0:
            self._total = total
            self.mosaique.definir_pages(total)
            self.titre_pages.setText(f"Les {total} pages")
            self.mosaique.setFixedHeight(self.mosaique.hauteur_rangees(10))

    def _analyse(self, e) -> None:
        if e.page and e.nature:
            self._natures[e.page] = e.nature
        self._amorcer_pages(e.total)
        self._repeindre_mosaique()

    def _repeindre_mosaique(self) -> None:
        # Cases par PLAGE de pages de chaque lot (pas par rang agrégé) : natif, « dans un lot »,
        # « lue pas rapatriée » (lavande), « rapatriée » (vert). Les natives gardent leur rang.
        if self.mosaique.nombre_pages() == 0 or not self._total:
            return
        bornes = []   # (lot, début, fin) sur la suite des pages scannées, dans l'ordre de création
        cumul = 0
        for d in self._lots.values():
            bornes.append((d, cumul, cumul + d.get("total", 0)))
            cumul += d.get("total", 0)
        rang = 0
        for p in range(1, self._total + 1):
            if self._natures.get(p) in _NATURES_NATIVES:
                self.mosaique.definir_etat(p - 1, Mosaique.NATIF)
                continue
            self.mosaique.definir_etat(p - 1, self._etat_scan(p, rang, bornes))
            rang += 1

    def _etat_scan(self, page: int, rang: int, bornes) -> str:
        if page in self._pages_rapatriees:
            return Mosaique.LUE
        for d, debut, fin in bornes:
            if debut <= rang < fin:
                if d.get("phase") == self.RAPATRIE:
                    return Mosaique.LUE
                if rang - debut < d.get("lues", 0):
                    return Mosaique.LUE_NON_RAPATRIEE
                return Mosaique.DANS_LOT
        return Mosaique.DANS_LOT

    def _lot(self, lot: str, taille_mo: float = 0.0) -> dict:
        if lot not in self._lots:
            self._lots[lot] = {"lot": lot, "taille_mo": taille_mo, "lues": 0, "total": 0,
                               "phase": self.ENVOI}
        return self._lots[lot]

    def _rafraichir_diagramme(self) -> None:
        self.rail.definir_phase("lecture")
        self.diagramme.definir_lots(list(self._lots.values()))
        self._maj_anneau()
        self._maj_rail_comptes()
        self._repeindre_mosaique()

    def _maj_rail_comptes(self) -> None:
        lots = list(self._lots.values())
        n = len(lots)
        pages = sum(d.get("total", 0) for d in lots)
        mo = sum(d.get("taille_mo", 0.0) for d in lots)
        lues = sum(d.get("lues", 0) for d in lots)
        total = sum(d.get("total", 0) for d in lots)
        rapatries = sum(1 for d in lots if d.get("phase") == self.RAPATRIE)
        self.rail.definir_compte("preparation", f"{pages} p. · {mo:.0f} Mo · {n} lots")
        self.rail.definir_compte("envoi", f"{n} / {n} lots")
        self.rail.definir_compte("lecture", f"{lues} / {total}")
        self.rail.definir_compte("recuperation", f"{rapatries} / {n} lots")
        self.rail.definir_fraction_courante(lues / total if total else 0.0)

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
        self._amorcer_pages(e.total)
        if e.page:
            self._pages_rapatriees.add(e.page)
        self._repeindre_mosaique()

    # ── Affichage dérivé ─────────────────────────────────────────────
    def _maj_anneau(self) -> None:
        lues = sum(d.get("lues", 0) for d in self._lots.values())
        total = sum(d.get("total", 0) for d in self._lots.values())
        if total:
            self.anneau.definir_valeur(lues / total)
            self.anneau.definir_centre(str(lues), f"sur {total}")   # « 52 » + « sur 116 »

    def _maj_verification(self) -> None:
        if self._derniere_verif is None:
            return
        ecoule = int(time.monotonic() - self._derniere_verif)
        prochaine = max(0, self._delai - ecoule)
        self.etiquette_verification.setText(
            f"Dernière vérification il y a {ecoule} s · prochaine dans {prochaine} s")
        self.barre_decompte.definir_fraction(prochaine / self._delai if self._delai else 0.0)

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
