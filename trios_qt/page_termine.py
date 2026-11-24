"""Écran Terminé (phase 2D, d'après docs/maquettes/03_termine).

En-tête (coche verte + « Conversion terminée » + ligne de résumé + Relire / Ouvrir l'Excel /
Dossier), 4 cartes de chiffres clés, carte « Ce qui demande ton attention » et colonne « Ensuite »
(outils qui appellent le code existant). Alimenté par definir_resume(resume, points) ; les chiffres
et les éléments d'attention viennent de resume_termine (module pur). Aucun travail lourd ici.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import resume_termine as rt
from trios_qt import icones, theme
from trios_qt.anneau import Anneau

# (clé outil, icône, titre, description)
_OUTILS = (
    ("auditer", "aide", "Auditer le classeur", "Doublons, pieds incomplets, couleurs manquantes."),
    ("comparer", "relecture", "Comparer au scan", "Toutes les divergences, page par page."),
    ("lexique", "info", "Enrichir le lexique",
     "Une fois l'Excel corrigé, pour mieux lire les prochains."),
    ("formater", "mise_en_forme", "Mettre en forme pour l'impression",
     "Lignes par page, colonnes et marges."),
)
_ICONE_NIVEAU = {"alerte": ("erreur", "⚠"), "attention": ("a_relire", "!"), "ok": ("succes", "✓")}


class PageTermine(QWidget):
    """Écran de fin ; definir_resume(resume, points) le remplit."""

    relire_demande = Signal()
    voir_page = Signal(object)
    ouvrir_excel = Signal()
    ouvrir_dossier = Signal()
    outil_demande = Signal(str)

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("page_termine")
        self._jetons = jetons or theme.charger_jetons()
        self._construire()

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(28, 24, 28, 20)
        colonne.setSpacing(16)
        colonne.addWidget(self._entete())
        colonne.addLayout(self._cartes_chiffres())
        centre = QHBoxLayout()
        centre.setSpacing(16)
        centre.addWidget(self._carte_attention(), 2)
        centre.addWidget(self._carte_outils(), 1)
        colonne.addLayout(centre, 1)
        colonne.addStretch(1)

    def _entete(self) -> QWidget:
        cadre = QWidget(self)
        ligne = QHBoxLayout(cadre)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(14)
        self._coche = Anneau(self._jetons, cadre)
        self._coche.setFixedSize(60, 60)
        self._coche.terminer()
        ligne.addWidget(self._coche, 0)
        bloc = QVBoxLayout()
        bloc.setSpacing(2)
        titre = QLabel("Conversion terminée", cadre)
        titre.setObjectName("titre_ecran")
        self.etiquette_resume = QLabel("", cadre)
        self.etiquette_resume.setObjectName("traitement_fichier")
        bloc.addWidget(titre)
        bloc.addWidget(self.etiquette_resume)
        ligne.addLayout(bloc, 0)
        ligne.addStretch(1)
        self.bouton_relire = QPushButton("Relire les points", cadre)
        self.bouton_relire.setObjectName("bouton_lancer")
        self.bouton_relire.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_relire.clicked.connect(self.relire_demande.emit)
        self.bouton_excel = QPushButton("Ouvrir l'Excel", cadre)
        self.bouton_excel.setObjectName("action_secondaire")
        self.bouton_excel.clicked.connect(self.ouvrir_excel.emit)
        self.bouton_dossier = QPushButton("Dossier", cadre)
        self.bouton_dossier.setObjectName("action_secondaire")
        self.bouton_dossier.clicked.connect(self.ouvrir_dossier.emit)
        for b in (self.bouton_relire, self.bouton_excel, self.bouton_dossier):
            ligne.addWidget(b, 0)
        return cadre

    def _cartes_chiffres(self) -> QHBoxLayout:
        rangee = QHBoxLayout()
        rangee.setSpacing(16)
        self.val_tableaux, c1 = self._carte_stat("Tableaux extraits", "texte")
        self.val_pages, c2 = self._carte_stat("Pages lues", "texte")
        self.val_points, c3 = self._carte_stat("Points à relire", "a_relire")
        self.val_cout, c4 = self._carte_stat("Coût · durée", "texte")
        self.det_tableaux = c1.findChild(QLabel, "stat_detail")
        self.det_pages = c2.findChild(QLabel, "stat_detail")
        self.det_points = c3.findChild(QLabel, "stat_detail")
        self.det_cout = c4.findChild(QLabel, "stat_detail")
        for c in (c1, c2, c3, c4):
            rangee.addWidget(c, 1)
        return rangee

    def _carte_stat(self, titre: str, couleur_grand: str):
        c = self._jetons["couleurs"]
        carte = QFrame(self)
        carte.setObjectName("carte_droite")
        v = QVBoxLayout(carte)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(4)
        lib = QLabel(titre, carte)
        lib.setObjectName("temps_detail")
        grand = QLabel("—", carte)
        grand.setObjectName("stat_grand")
        grand.setStyleSheet(f"color: {c.get(couleur_grand, c['texte'])}; font-weight: 800;")
        detail = QLabel("", carte)
        detail.setObjectName("stat_detail")
        detail.setWordWrap(True)
        v.addWidget(lib)
        v.addWidget(grand)
        v.addWidget(detail)
        return grand, carte

    def _carte_attention(self) -> QFrame:
        carte = QFrame(self)
        carte.setObjectName("carte_droite")
        v = QVBoxLayout(carte)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)
        titre = QLabel("Ce qui demande ton attention", carte)
        titre.setObjectName("panneau_titre")
        v.addWidget(titre)
        self._attention_boite = QVBoxLayout()
        self._attention_boite.setSpacing(10)
        v.addLayout(self._attention_boite)
        v.addStretch(1)
        return carte

    def _carte_outils(self) -> QFrame:
        c = self._jetons["couleurs"]
        carte = QFrame(self)
        carte.setObjectName("carte_droite")
        v = QVBoxLayout(carte)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(12)
        titre = QLabel("Ensuite", carte)
        titre.setObjectName("panneau_titre")
        v.addWidget(titre)
        for cle, ic, nom, desc in _OUTILS:
            ligne = QHBoxLayout()
            ligne.setSpacing(10)
            icone = QLabel(carte)
            icone.setPixmap(icones.charger_icone(ic, c["texte_secondaire"], 18).pixmap(18, 18))
            icone.setAlignment(Qt.AlignmentFlag.AlignTop)
            bloc = QVBoxLayout()
            bloc.setSpacing(1)
            lien = QPushButton(nom, carte)
            lien.setObjectName("outil_titre")
            lien.setCursor(Qt.CursorShape.PointingHandCursor)
            lien.clicked.connect(lambda _=False, k=cle: self.outil_demande.emit(k))
            d = QLabel(desc, carte)
            d.setObjectName("temps_detail")
            d.setWordWrap(True)
            bloc.addWidget(lien)
            bloc.addWidget(d)
            ligne.addWidget(icone, 0)
            ligne.addLayout(bloc, 1)
            v.addLayout(ligne)
        v.addStretch(1)
        return carte

    # ── Remplissage ──────────────────────────────────────────────────
    def definir_resume(self, resume: dict, points: list) -> None:
        self.etiquette_resume.setText(rt.ligne_entete(resume))
        self.val_tableaux.setText(rt.carte_tableaux(resume)[0])
        self.det_tableaux.setText(rt.carte_tableaux(resume)[1])
        gp, dp = rt.carte_pages(resume)
        self.val_pages.setText(gp)
        self.det_pages.setText(dp)
        np_, det = rt.carte_points(points)
        self.val_points.setText(str(np_))
        self.det_points.setText(det)
        self.bouton_relire.setText(f"Relire les {np_} points")
        gc, dc = rt.carte_cout(resume)
        self.val_cout.setText(gc)
        self.det_cout.setText(dc)
        self._remplir_attention(rt.attention(points))

    def _remplir_attention(self, items: list) -> None:
        while self._attention_boite.count():
            el = self._attention_boite.takeAt(0)
            w = el.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        c = self._jetons["couleurs"]
        for it in items:
            ligne = QWidget(self)
            h = QHBoxLayout(ligne)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(10)
            cle_couleur, glyphe = _ICONE_NIVEAU.get(it["niveau"], ("texte_discret", "·"))
            puce = QLabel(glyphe, ligne)
            puce.setStyleSheet(f"color: {c[cle_couleur]}; font-weight: 700;")
            puce.setAlignment(Qt.AlignmentFlag.AlignTop)
            bloc = QVBoxLayout()
            bloc.setSpacing(1)
            titre = QLabel(it["titre"], ligne)
            titre.setObjectName("attention_titre")
            titre.setWordWrap(True)
            bloc.addWidget(titre)
            if it.get("detail"):
                d = QLabel(it["detail"], ligne)
                d.setObjectName("temps_detail")
                d.setWordWrap(True)
                bloc.addWidget(d)
            h.addWidget(puce, 0)
            h.addLayout(bloc, 1)
            if it.get("action"):
                lien = QPushButton("Voir" if it["action"] == "voir" else "Relire", ligne)
                lien.setObjectName("lien_action")
                lien.setCursor(Qt.CursorShape.PointingHandCursor)
                if it["action"] == "voir":
                    lien.clicked.connect(lambda _=False: self.voir_page.emit(None))
                else:
                    lien.clicked.connect(self.relire_demande.emit)
                h.addWidget(lien, 0, Qt.AlignmentFlag.AlignTop)
            self._attention_boite.addWidget(ligne)
