"""Écran Convertir : en-tête, bande de dépôt, file des fichiers, panneau des types reconnus."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

import estimation
import types_documents
from trios_qt import analyse, presentation, reglages, theme
from trios_qt.ligne_fichier_widget import MIME_IDENT, LigneFichierWidget
from trios_qt.modele_fichiers import LanceurAnalyse, ModeleFichiers
from trios_qt.zone_depot import ZoneDepot


class _ListeConteneur(QWidget):
    """Conteneur de la liste : accepte le dépôt d'une ligne glissée pour la réordonner."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self._page = page
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_IDENT):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_IDENT):
            event.acceptProposedAction()

    def dropEvent(self, event):
        ident = int(bytes(event.mimeData().data(MIME_IDENT)).decode())
        y = event.position().toPoint().y()
        self._page.deposer_reordonne(ident, y)
        event.acceptProposedAction()


class PageConvertir(QWidget):
    """Assemble le dépôt, la liste des fichiers et le panneau des types ; pilote l'analyse."""

    gerer_types = Signal()
    creer_type = Signal()
    lancer_demande = Signal()

    def __init__(self, registre_fn=None, lanceur=None, estimer_fn=None, parent=None):
        super().__init__(parent)
        self.setObjectName("page_convertir")
        self._registre_fn = registre_fn or types_documents.registre
        self._estimer = estimer_fn or estimation.estimer
        self._jetons = theme.charger_jetons()
        self._widgets = []
        self._ident_selectionne = None
        self._dossier_sortie = reglages.lire_dossier_sortie() or ""   # mémorisé entre sessions

        self.modele = ModeleFichiers()
        self.lanceur = lanceur or LanceurAnalyse()
        self.lanceur.fini.connect(self.modele.appliquer_resultat)
        for signal in (self.modele.rowsInserted, self.modele.rowsRemoved,
                       self.modele.rowsMoved, self.modele.modelReset):
            signal.connect(self._resync)
        self.modele.dataChanged.connect(lambda *_: self._resync())

        self._construire()

    # ── Construction ──────────────────────────────────────────────────
    def _construire(self):
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(40, 30, 40, 24)
        colonne.setSpacing(16)

        titre = QLabel("Nouvelle conversion", self)
        titre.setObjectName("titre_ecran")
        aide = QLabel("Dépose un ou plusieurs fichiers : l'appli reconnaît leur type "
                      "et prépare le bon traitement pour chacun.", self)
        aide.setObjectName("sous_titre_ecran")
        colonne.addWidget(titre)
        colonne.addWidget(aide)

        corps = QHBoxLayout()
        corps.setSpacing(22)
        corps.addLayout(self._construire_colonne_gauche(), 1)
        corps.addWidget(self._construire_panneau_types(), 0, Qt.AlignTop)
        colonne.addLayout(corps, 1)

        for sequence in ("Ctrl+Return", "Ctrl+Enter"):
            raccourci = QShortcut(QKeySequence(sequence), self)
            raccourci.activated.connect(self._tenter_lancer)

    def _construire_colonne_gauche(self):
        gauche = QVBoxLayout()
        gauche.setSpacing(16)

        self.zone = ZoneDepot(self)
        self.zone.sources_deposees.connect(self.ajouter_sources)
        gauche.addWidget(self.zone)

        self._zone_liste = _ListeConteneur(self)
        self._zone_liste.setObjectName("zone_liste")
        self._liste_layout = QVBoxLayout(self._zone_liste)
        self._liste_layout.setContentsMargins(0, 0, 0, 0)
        self._liste_layout.setSpacing(10)
        self._liste_layout.setAlignment(Qt.AlignTop)
        defilement = QScrollArea(self)
        defilement.setObjectName("liste_fichiers")
        defilement.setFrameShape(QFrame.NoFrame)
        defilement.setWidgetResizable(True)
        defilement.viewport().setObjectName("liste_viewport")
        defilement.setWidget(self._zone_liste)
        self.defilement = defilement
        gauche.addWidget(defilement, 1)

        gauche.addLayout(self._construire_bas_de_page())
        return gauche

    def _construire_bas_de_page(self):
        colonne = QVBoxLayout()
        colonne.setSpacing(8)

        rangee_dossier = QHBoxLayout()
        libelle = QLabel("Dossier de sortie :", self)
        libelle.setObjectName("dossier_libelle")
        self.etiquette_dossier = QLabel(self._dossier_sortie or "— à choisir", self)
        self.etiquette_dossier.setObjectName("dossier_chemin")
        bouton_dossier = QPushButton("Choisir…", self)
        bouton_dossier.setObjectName("action_secondaire")
        bouton_dossier.setCursor(Qt.PointingHandCursor)
        bouton_dossier.clicked.connect(self._choisir_dossier)
        rangee_dossier.addWidget(libelle, 0)
        rangee_dossier.addWidget(self.etiquette_dossier, 1)
        rangee_dossier.addWidget(bouton_dossier, 0)
        colonne.addLayout(rangee_dossier)

        rangee = QHBoxLayout()
        self.resume = QLabel("", self)
        self.resume.setObjectName("resume_bas")
        self.resume.setTextFormat(Qt.RichText)
        rangee.addWidget(self.resume, 1, Qt.AlignVCenter)
        self.bouton_lancer = QPushButton("Lancer les 0 fichiers prêts  →", self)
        self.bouton_lancer.setObjectName("bouton_lancer")
        self.bouton_lancer.setCursor(Qt.PointingHandCursor)
        self.bouton_lancer.clicked.connect(self.lancer_demande.emit)
        rangee.addWidget(self.bouton_lancer, 0, Qt.AlignRight)
        colonne.addLayout(rangee)

        self._mettre_a_jour_resume()
        return colonne

    def _tenter_lancer(self):
        if self.bouton_lancer.isEnabled():
            self.lancer_demande.emit()

    def fichiers_a_lancer(self):
        """Couples (chemin, dossier effectif) des fichiers prêts, dans l'ordre de la file."""
        couples = []
        for rang in range(self.modele.rowCount()):
            ligne = self.modele.ligne(rang)
            if ligne.resultat.etat == analyse.PRET:
                couples.append((str(ligne.chemin), self.dossier_effectif(ligne)))
        return couples

    def est_differe_chemin(self, chemin):
        """Le fichier prêt de ce chemin part-il en lot (mode économique) : route l'écran."""
        for rang in range(self.modele.rowCount()):
            ligne = self.modele.ligne(rang)
            if str(ligne.chemin) == str(chemin) and ligne.resultat.etat == analyse.PRET:
                return self._est_differe(ligne)
        return False

    def _choisir_dossier(self):
        from PySide6.QtWidgets import QFileDialog
        chemin = QFileDialog.getExistingDirectory(self, "Dossier de sortie",
                                                  self._dossier_sortie or "")
        if chemin:
            self.definir_dossier_sortie(chemin)

    def _construire_panneau_types(self):
        panneau = QFrame(self)
        panneau.setObjectName("panneau_types")
        panneau.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.panneau_types = panneau
        colonne = QVBoxLayout(panneau)
        colonne.setContentsMargins(16, 14, 16, 16)
        colonne.setSpacing(14)

        ligne_titre = QHBoxLayout()
        titre = QLabel("Types reconnus", panneau)
        titre.setObjectName("panneau_titre")
        ligne_titre.addWidget(titre, 1)
        self.bouton_gerer = QPushButton("Gérer", panneau)
        self.bouton_gerer.setObjectName("panneau_gerer")
        self.bouton_gerer.setCursor(Qt.PointingHandCursor)
        self.bouton_gerer.clicked.connect(self.gerer_types.emit)
        ligne_titre.addWidget(self.bouton_gerer, 0, Qt.AlignRight)
        colonne.addLayout(ligne_titre)

        registre = self._registre_fn()
        self._noms_types = sorted(registre.keys())
        for famille, noms in presentation.groupes_types(registre):
            colonne.addWidget(self._groupe_type(famille, noms, panneau))
        colonne.addSpacing(4)
        colonne.addWidget(self._carte_creer_type(panneau))
        return panneau

    def _groupe_type(self, famille, noms, parent):
        bloc = QWidget(parent)
        v = QVBoxLayout(bloc)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        ligne = QHBoxLayout()
        ligne.setSpacing(8)
        pastille = QLabel(bloc)
        pastille.setObjectName("panneau_pastille")
        pastille.setFixedSize(10, 10)
        couleur = presentation.couleur_famille(famille, self._jetons)
        pastille.setStyleSheet(f"background-color: {couleur}; border-radius: 5px;")
        ligne.addWidget(pastille, 0, Qt.AlignVCenter)
        titre = QLabel(presentation.libelle_groupe(famille), bloc)
        titre.setObjectName("panneau_groupe_titre")
        ligne.addWidget(titre, 1)
        v.addLayout(ligne)
        detail = QLabel(presentation.description_groupe(famille, noms), bloc)
        detail.setObjectName("panneau_groupe_detail")
        detail.setWordWrap(True)
        v.addWidget(detail)
        return bloc

    def _carte_creer_type(self, parent):
        carte = QFrame(parent)
        carte.setObjectName("carte_creer_type")
        v = QVBoxLayout(carte)
        v.setContentsMargins(12, 10, 12, 10)
        texte = QLabel("＋  Un nouveau document arrive ?\nCrée son type à partir d'une "
                       "page exemple.", carte)
        texte.setObjectName("creer_type_texte")
        texte.setWordWrap(True)
        v.addWidget(texte)
        carte.mousePressEvent = lambda _e: self.creer_type.emit()
        carte.setCursor(Qt.PointingHandCursor)
        return carte

    # ── File ──────────────────────────────────────────────────────────
    def ajouter_sources(self, sources):
        for chemin in sources:
            ident = self.modele.ajouter(chemin)
            self.lanceur.lancer(ident, chemin)

    def _resync(self, *_):
        while self._liste_layout.count():
            element = self._liste_layout.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.deleteLater()
        self._widgets = []
        for rang in range(self.modele.rowCount()):
            ligne = self.modele.ligne(rang)
            widget = LigneFichierWidget(ligne, self._jetons, self._zone_liste)
            selectionne = ligne.ident == self._ident_selectionne
            widget.definir_selection(selectionne)
            widget.deplier(selectionne)
            if selectionne:
                self._remplir_deplie(widget, ligne)
            widget.clique.connect(self.selectionner)
            widget.bouton_retirer.clicked.connect(
                lambda _=False, ident=ligne.ident: self._retirer(ident))
            self._liste_layout.addWidget(widget)
            self._widgets.append(widget)
        self._mettre_a_jour_resume()

    def selectionner(self, ident):
        self._ident_selectionne = ident
        for rang, widget in enumerate(self._widgets):
            actif = widget.ident == ident
            widget.definir_selection(actif)
            widget.deplier(actif)
            if actif:
                self._remplir_deplie(widget, self.modele.ligne(rang))

    def _ligne_par_ident(self, ident):
        for rang in range(self.modele.rowCount()):
            if self.modele.ligne(rang).ident == ident:
                return rang, self.modele.ligne(rang)
        return None, None

    def _widget_par_ident(self, ident):
        for widget in self._widgets:
            if widget.ident == ident:
                return widget
        return None

    def dossier_effectif(self, ligne):
        return ligne.dossier_sortie or self._dossier_sortie

    def _estimer_ligne(self, ligne, profil):
        return self._estimer(str(ligne.chemin), type=ligne.resultat.type,
                             profil=profil.profil,
                             lot=presentation.lot_effectif(profil, ligne.lot),
                             modele=profil.modele, dossier_sortie=self.dossier_effectif(ligne))

    def definir_dossier_sortie(self, chemin):
        self._dossier_sortie = chemin or ""
        reglages.ecrire_dossier_sortie(self._dossier_sortie)
        self._rafraichir_dossier()

    def definir_dossier_fichier(self, ident, chemin):
        _, ligne = self._ligne_par_ident(ident)
        if ligne is not None:
            ligne.dossier_sortie = chemin or None
            self._rafraichir_dossier()

    def _rafraichir_dossier(self):
        if hasattr(self, "etiquette_dossier"):
            self.etiquette_dossier.setText(self._dossier_sortie or "— à choisir")
        if self._ident_selectionne is not None:
            _, ligne = self._ligne_par_ident(self._ident_selectionne)
            if ligne is not None and getattr(ligne.resultat.type, 'famille', None) == "tableau":
                self.choisir_profil(self._ident_selectionne, ligne.profil_cle)
        self._mettre_a_jour_resume()

    def _tous_prets_ont_dossier(self):
        for rang in range(self.modele.rowCount()):
            ligne = self.modele.ligne(rang)
            if ligne.resultat.etat == analyse.PRET and not self.dossier_effectif(ligne):
                return False
        return True

    # ── Ligne dépliée ─────────────────────────────────────────────────
    def _remplir_deplie(self, widget, ligne):
        corps = widget.corps_layout()
        while corps.count():
            element = corps.takeAt(0)
            w = element.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        widget.profil_cartes = {}
        widget.case_lot = None
        widget.bouton_creer_type = None

        famille = getattr(ligne.resultat.type, 'famille', None)
        if famille == "tableau":
            self._deplie_tableau(widget, ligne, corps)
        elif famille == "plan":
            self._deplie_plan(corps)
        elif ligne.resultat.etat in (analyse.INCONNU, analyse.A_PRECISER):
            self._deplie_inconnu(widget, corps)
        else:
            corps.addWidget(self._note("Aucun réglage : traitement direct."))

    def _deplie_tableau(self, widget, ligne, corps):
        if ligne.lot is None:
            ligne.lot = presentation.lot_propose(ligne.resultat)
        rangee = QHBoxLayout()
        rangee.setSpacing(10)
        for profil in presentation.PROFILS_TABLEAU:
            devis = self._estimer_ligne(ligne, profil)
            carte = self._carte_profil(widget, ligne, profil, devis)
            widget.profil_cartes[profil.cle] = carte
            rangee.addWidget(carte, 1)
        corps.addLayout(rangee)

        self.case_lot = QCheckBox(
            "Mode économique (lot) — −50 %, résultat différé. "
            "Proposé d'office au-delà de 100 pages.", self)
        self.case_lot.setObjectName("case_lot")
        self.case_lot.setChecked(bool(ligne.lot))
        self.case_lot.toggled.connect(
            lambda actif, i=ligne.ident: self.basculer_lot(i, actif))
        widget.case_lot = self.case_lot
        corps.addWidget(self.case_lot)

        # La ligne (repliée) montre l'estimation du profil actif et du lot courant.
        self.choisir_profil(ligne.ident, ligne.profil_cle)

    def _carte_profil(self, widget, ligne, profil, devis):
        carte = QFrame(self)
        carte.setObjectName("profil_carte")
        carte.setProperty("actif", profil.cle == ligne.profil_cle)
        v = QVBoxLayout(carte)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(2)
        titre = QLabel(profil.titre, carte)
        titre.setObjectName("profil_titre")
        moteur = QLabel(profil.moteur, carte)
        moteur.setObjectName("profil_moteur")
        res_tmp = analyse.ResultatAnalyse(etat=analyse.PRET, estimation=devis)
        estim = QLabel(presentation.texte_estimation(res_tmp) or "0 $", carte)
        estim.setObjectName("profil_estimation")
        v.addWidget(titre)
        v.addWidget(moteur)
        v.addWidget(estim)
        carte.mousePressEvent = lambda _e, i=ligne.ident, c=profil.cle: self.choisir_profil(i, c)
        carte.setCursor(Qt.PointingHandCursor)
        return carte

    def _deplie_plan(self, corps):
        rangee = QHBoxLayout()
        rangee.addWidget(self._note("Finesse :"))
        for i, finesse in enumerate(presentation.FINESSES_PLAN):
            bouton = QPushButton(finesse, self)
            bouton.setObjectName("finesse_bouton")
            bouton.setCheckable(True)
            bouton.setChecked(i == 1)   # Standard par défaut
            rangee.addWidget(bouton)
        rangee.addStretch(1)
        conteneur = QWidget(self)
        conteneur.setLayout(rangee)
        corps.addWidget(conteneur)

    def _deplie_inconnu(self, widget, corps):
        rangee = QHBoxLayout()
        choisir = QPushButton("Choisir un type", self)
        choisir.setObjectName("action_secondaire")
        choisir.clicked.connect(self.gerer_types.emit)
        widget.bouton_creer_type = QPushButton("Créer un type à partir de cette page", self)
        widget.bouton_creer_type.setObjectName("action_secondaire")
        widget.bouton_creer_type.clicked.connect(self.creer_type.emit)
        rangee.addWidget(choisir)
        rangee.addWidget(widget.bouton_creer_type)
        rangee.addStretch(1)
        conteneur = QWidget(self)
        conteneur.setLayout(rangee)
        corps.addWidget(conteneur)

    def _note(self, texte):
        note = QLabel(texte, self)
        note.setObjectName("deplie_note")
        return note

    def choisir_profil(self, ident, cle):
        rang, ligne = self._ligne_par_ident(ident)
        if ligne is None:
            return
        ligne.profil_cle = cle
        profil = next(p for p in presentation.PROFILS_TABLEAU if p.cle == cle)
        ligne.resultat.estimation = self._estimer_ligne(ligne, profil)
        widget = self._widget_par_ident(ident)
        if widget is not None:
            widget.mettre_a_jour(ligne)
            for c, carte in widget.profil_cartes.items():
                carte.setProperty("actif", c == cle)
                carte.style().unpolish(carte)
                carte.style().polish(carte)
        self._mettre_a_jour_resume()

    def basculer_lot(self, ident, actif):
        rang, ligne = self._ligne_par_ident(ident)
        if ligne is None:
            return
        ligne.lot = bool(actif)
        self.choisir_profil(ident, ligne.profil_cle)   # recalcule l'estimation active

    def reordonner(self, ident, nouveau_rang):
        rang, _ = self._ligne_par_ident(ident)
        if rang is not None and rang != nouveau_rang:
            self.modele.deplacer(rang, nouveau_rang)

    def deposer_reordonne(self, ident, y):
        """Réordonne après un glisser : rang cible selon la position y du dépôt."""
        cible = sum(1 for w in self._widgets
                    if w.ident != ident and (w.y() + w.height() / 2) < y)
        cible = max(0, min(cible, self.modele.rowCount() - 1))
        self.reordonner(ident, cible)

    def _retirer(self, ident):
        if ident == self._ident_selectionne:
            self._ident_selectionne = None
        for rang in range(self.modele.rowCount()):
            if self.modele.ligne(rang).ident == ident:
                self.modele.retirer(rang)
                return

    def _est_differe(self, ligne):
        """Le fichier prêt est-il lu en lot (différé) : seulement un tableau en profil Claude."""
        if getattr(ligne.resultat.type, 'famille', None) != "tableau":
            return False
        profil = next((p for p in presentation.PROFILS_TABLEAU
                       if p.cle == ligne.profil_cle), None)
        return bool(profil) and presentation.lot_effectif(profil, ligne.lot)

    def _entree_cout(self, ligne):
        devis = ligne.resultat.estimation or {}
        return {'cout_usd': devis.get('cout_usd', 0.0),
                'cache_connu': devis.get('cache_connu', True),
                'differe': self._est_differe(ligne)}

    def _mettre_a_jour_resume(self):
        total = self.modele.rowCount()
        prets_lignes = [self.modele.ligne(r) for r in range(total)
                        if self.modele.ligne(r).resultat.etat == analyse.PRET]
        prets = len(prets_lignes)
        a_preciser = sum(1 for r in range(total) if self.modele.ligne(r).resultat.etat
                         in (analyse.A_PRECISER, analyse.INCONNU))
        resume = presentation.texte_resume(total, prets, a_preciser, self._jetons)
        cout = presentation.texte_cout_total(
            [self._entree_cout(ligne) for ligne in prets_lignes], self._jetons)
        if cout:
            resume = f"{resume} · {cout}"
        self.resume.setText(resume)
        self.bouton_lancer.setText(f"Lancer les {prets} fichiers prêts  →")
        self.bouton_lancer.setEnabled(prets > 0 and self._tous_prets_ont_dossier())

    # ── Accès pour les tests ──────────────────────────────────────────
    def widget_ligne(self, rang):
        return self._widgets[rang]

    def noms_types(self):
        return list(self._noms_types)
