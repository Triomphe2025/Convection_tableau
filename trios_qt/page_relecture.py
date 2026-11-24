"""Écran Relecture (phase 2D, d'après docs/maquettes/04_relecture).

Parcourt les points de `<nom>_points.json` (via relecture_modele.Relecture) : liste à gauche avec
leur état, au centre l'extrait du scan zoomé sur la cellule (cadre orange) et la ligne de
comparaison (cadre bleu pointillé), la ligne en champs modifiables, l'explication et la confiance,
puis Garder / Remplacer / Passer et « Enregistrer dans l'Excel ». L'image de page est fournie par
un rappel `image_de_page(page)` (la fenêtre la cherche dans le dossier de travail ou la régénère) :
si elle manque, un message clair, jamais un écran vide. L'état est persisté par le modèle.
"""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from trios_qt import theme

_LIBELLE_ETAT = {"a_voir": "À voir", "garde": "Gardé", "corrige": "Corrigé", "passe": "Passé"}


class PageRelecture(QWidget):
    """Relecture des points d'un document ; definir_relecture(...) la charge."""

    enregistre = Signal(bool)        # True = enregistré, False = classeur verrouillé
    points_changes = Signal()        # pour le compteur de la barre latérale

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("page_relecture")
        self._jetons = jetons or theme.charger_jetons()
        self._relecture = None
        self._image_de_page = lambda page: None
        self._retenir_lexique = lambda valeur: None
        self._points = []
        self._courant = -1
        self._taille_image = (1, 1)
        self._zoom = 1.5
        self._construire()

    def _construire(self) -> None:
        colonne = QVBoxLayout(self)
        colonne.setContentsMargins(28, 22, 28, 18)
        colonne.setSpacing(12)
        colonne.addWidget(self._entete())
        centre = QHBoxLayout()
        centre.setSpacing(16)
        centre.addWidget(self._liste(), 0)
        centre.addWidget(self._carte_centre(), 1)
        colonne.addLayout(centre, 1)

    def _entete(self) -> QWidget:
        cadre = QWidget(self)
        v = QVBoxLayout(cadre)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        ligne = QHBoxLayout()
        self.titre = QLabel("Relecture", cadre)
        self.titre.setObjectName("titre_ecran")
        ligne.addWidget(self.titre, 1)
        self.bouton_enregistrer = QPushButton("Enregistrer dans l'Excel", cadre)
        self.bouton_enregistrer.setObjectName("action_secondaire")
        self.bouton_enregistrer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton_enregistrer.clicked.connect(self.enregistrer)
        ligne.addWidget(self.bouton_enregistrer, 0)
        v.addLayout(ligne)
        bas = QHBoxLayout()
        self.barre = QProgressBar(cadre)
        self.barre.setObjectName("relecture_barre")
        self.barre.setTextVisible(False)
        self.barre.setFixedHeight(4)
        self.etiquette_progres = QLabel("0 sur 0 traités", cadre)
        self.etiquette_progres.setObjectName("temps_detail")
        bas.addWidget(self.barre, 1)
        bas.addWidget(self.etiquette_progres, 0)
        v.addLayout(bas)
        return cadre

    def _liste(self) -> QWidget:
        self.liste = QListWidget(self)
        self.liste.setObjectName("relecture_liste")
        self.liste.setFixedWidth(260)
        self.liste.currentRowChanged.connect(self._sur_selection)
        return self.liste

    def _carte_centre(self) -> QFrame:
        carte = QFrame(self)
        carte.setObjectName("carte_lecture")
        v = QVBoxLayout(carte)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        entete = QHBoxLayout()
        self.titre_point = QLabel("", carte)
        self.titre_point.setObjectName("lecture_titre")
        self.sous_point = QLabel("", carte)
        self.sous_point.setObjectName("temps_detail")
        bloc = QVBoxLayout()
        bloc.setSpacing(1)
        bloc.addWidget(self.titre_point)
        bloc.addWidget(self.sous_point)
        entete.addLayout(bloc, 1)
        self.bouton_moins = QPushButton("−", carte)
        self.bouton_moins.setObjectName("mini_icone")
        self.bouton_moins.setFixedSize(28, 24)
        self.bouton_moins.clicked.connect(lambda: self._zoomer(-0.25))
        self.etiquette_zoom = QLabel("150 %", carte)
        self.bouton_plus = QPushButton("+", carte)
        self.bouton_plus.setObjectName("mini_icone")
        self.bouton_plus.setFixedSize(28, 24)
        self.bouton_plus.clicked.connect(lambda: self._zoomer(0.25))
        entete.addWidget(self.bouton_moins, 0)
        entete.addWidget(self.etiquette_zoom, 0)
        entete.addWidget(self.bouton_plus, 0)
        v.addLayout(entete)

        self._scene = QGraphicsScene(self)
        self.vue = QGraphicsView(self._scene, carte)
        self.vue.setObjectName("lecture_vue")
        self.vue.setFixedHeight(180)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.message_image = QLabel("", carte)
        self.message_image.setObjectName("temps_detail")
        self.message_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_image.setVisible(False)
        v.addWidget(self.vue)
        v.addWidget(self.message_image)

        self._champs_boite = QHBoxLayout()
        self._champs_boite.setSpacing(10)
        v.addLayout(self._champs_boite)
        self._champs = {}

        self.explication = QLabel("", carte)
        self.explication.setObjectName("relecture_explication")
        self.explication.setWordWrap(True)
        v.addWidget(self.explication)

        actions = QHBoxLayout()
        self.bouton_garder = QPushButton("Garder", carte)
        self.bouton_garder.setObjectName("bouton_lancer")
        self.bouton_garder.clicked.connect(self.garder)
        self.bouton_remplacer = QPushButton("Remplacer par la suggestion", carte)
        self.bouton_remplacer.setObjectName("action_secondaire")
        self.bouton_remplacer.clicked.connect(self.remplacer)
        self.bouton_passer = QPushButton("Passer", carte)
        self.bouton_passer.setObjectName("action_secondaire")
        self.bouton_passer.clicked.connect(self.passer)
        actions.addWidget(self.bouton_garder, 0)
        actions.addWidget(self.bouton_remplacer, 0)
        actions.addWidget(self.bouton_passer, 0)
        actions.addStretch(1)
        from PySide6.QtWidgets import QCheckBox
        self.case_lexique = QCheckBox("Retenir dans le lexique", carte)
        self.case_lexique.setObjectName("case_lot")
        actions.addWidget(self.case_lexique, 0)
        v.addLayout(actions)

        aide = QLabel("Entrée garder · R remplacer · Tab cellule suivante · "
                      "Ctrl+↓ point suivant · Échap passer", carte)
        aide.setObjectName("temps_detail")
        v.addWidget(aide)
        v.addStretch(1)
        return carte

    # ── Chargement ───────────────────────────────────────────────────
    def definir_relecture(self, relecture, image_de_page=None, retenir_lexique=None) -> None:
        self._relecture = relecture
        if image_de_page is not None:
            self._image_de_page = image_de_page
        if retenir_lexique is not None:
            self._retenir_lexique = retenir_lexique
        self.titre.setText(f"Relecture · {relecture.enveloppe.get('document', '')}")
        # Seuls les points de cellule sont relus ici (les points de page n'ont pas de cellule).
        self._points = [p for p in relecture.points() if p.get("cellule_excel")]
        self.liste.clear()
        for p in self._points:
            self.liste.addItem(QListWidgetItem(self._libelle_point(p)))
        self._maj_progres()
        if self._points:
            self.liste.setCurrentRow(0)

    def _libelle_point(self, p) -> str:
        page = p.get("page_imprimee") or p.get("page")
        return (f"Page {page} · {p.get('bornier') or ''}\n"
                f"{p.get('cellule_excel')} · {p.get('colonne') or ''}\n"
                f"{_LIBELLE_ETAT.get(p.get('etat'), p.get('etat'))}")

    # ── Sélection d'un point ─────────────────────────────────────────
    def _sur_selection(self, rang: int) -> None:
        if not 0 <= rang < len(self._points):
            return
        self._courant = rang
        p = self._points[rang]
        page = p.get("page_imprimee") or p.get("page")
        self.titre_point.setText(f"Page {page} · bornier {p.get('bornier') or ''}")
        self.sous_point.setText(p.get("raison") or "")
        conf = p.get("confiance")
        expl = p.get("raison") or ""
        if conf is not None:
            expl = f"{expl}  ·  Confiance de lecture : {conf} %"
        self.explication.setText(expl)
        self._remplir_champs(p)
        self._charger_extrait(p)

    def _remplir_champs(self, p) -> None:
        while self._champs_boite.count():
            el = self._champs_boite.takeAt(0)
            w = el.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._champs = {}
        # Ligne entière lue dans l'Excel (contexte) ; repli sur la seule cellule douteuse.
        colonnes, valeurs = self._relecture.ligne_du_point(p) if self._relecture else ([], [])
        if not colonnes:
            colonnes = [p.get("colonne") or ""]
            valeurs = [str(p.get("valeur") or "")]
        douteuse = p.get("colonne")
        for i, col in enumerate(colonnes):
            bloc = QVBoxLayout()
            lib = QLabel(str(col or ""), self)
            lib.setObjectName("champ_libelle")
            champ = QLineEdit(valeurs[i] if i < len(valeurs) else "", self)
            champ.setObjectName("champ_douteux" if col == douteuse else "champ_relecture")
            bloc.addWidget(lib)
            bloc.addWidget(champ)
            self._champs[col] = champ
            cadre = QWidget(self)
            cadre.setLayout(bloc)
            self._champs_boite.addWidget(cadre)

    def _charger_extrait(self, p) -> None:
        self._scene.setForegroundBrush(QBrush(Qt.BrushStyle.NoBrush))
        for it in list(self._scene.items()):
            if isinstance(it, QGraphicsRectItem):
                self._scene.removeItem(it)
        chemin = self._image_de_page(p.get("page"))
        if not chemin:
            self._pixmap_item.setPixmap(QPixmap())
            self.vue.setVisible(False)
            self.message_image.setText("Image de la page indisponible — relance la conversion "
                                       "ou ouvre l'Excel pour vérifier.")
            self.message_image.setVisible(True)
            return
        self.vue.setVisible(True)
        self.message_image.setVisible(False)
        pixmap = QPixmap(str(chemin))
        self._pixmap_item.setPixmap(pixmap)
        self._taille_image = (pixmap.width() or 1, pixmap.height() or 1)
        zone = p.get("zone")
        if zone and zone.get("boite"):
            self._cadre(zone["boite"], self._jetons["couleurs"]["a_relire"], pointille=False)
        self._ajuster_vue()

    def _cadre(self, boite01, couleur, pointille):
        largeur, hauteur = self._taille_image
        x0, y0, x1, y1 = boite01
        rect = QGraphicsRectItem(QRectF(x0 * largeur, y0 * hauteur,
                                        (x1 - x0) * largeur, (y1 - y0) * hauteur))
        stylo = QPen(QColor(couleur), 3)
        if pointille:
            stylo.setStyle(Qt.PenStyle.DashLine)
        rect.setPen(stylo)
        self._scene.addItem(rect)

    def _ajuster_vue(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.vue.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _zoomer(self, delta: float) -> None:
        self._zoom = max(0.5, min(4.0, self._zoom + delta))
        self.etiquette_zoom.setText(f"{int(self._zoom * 100)} %")
        self.vue.resetTransform()
        self.vue.scale(self._zoom, self._zoom)

    # ── Décisions ────────────────────────────────────────────────────
    def _point_courant(self):
        if 0 <= self._courant < len(self._points):
            return self._points[self._courant]
        return None

    def garder(self) -> None:
        p = self._point_courant()
        if p and self._relecture:
            self._relecture.garder(p["id"])
            self._apres_decision()

    def remplacer(self) -> None:
        p = self._point_courant()
        if p and self._relecture:
            valeur = p.get("suggestion") or p.get("valeur")
            self._relecture.corriger(p["id"], valeur)
            if self.case_lexique.isChecked() and p.get("colonne"):
                self._retenir_lexique(valeur)
            self._apres_decision()

    def passer(self) -> None:
        p = self._point_courant()
        if p and self._relecture:
            self._relecture.passer(p["id"])
            self._apres_decision()

    def _apres_decision(self) -> None:
        p = self._points[self._courant]
        item = self.liste.item(self._courant)
        if item is not None:
            item.setText(self._libelle_point(p))
        self._maj_progres()
        self.points_changes.emit()
        if self._courant + 1 < len(self._points):
            self.liste.setCurrentRow(self._courant + 1)

    def _maj_progres(self) -> None:
        if not self._relecture:
            return
        total = len(self._points)
        traites = sum(1 for p in self._points if p.get("etat") != "a_voir")
        self.barre.setMaximum(max(1, total))
        self.barre.setValue(traites)
        self.etiquette_progres.setText(f"{traites} sur {total} traités")

    def enregistrer(self) -> None:
        if not self._relecture:
            return
        import relecture_modele
        try:
            self._relecture.enregistrer_excel()
            self.enregistre.emit(True)
        except relecture_modele.VerrouError:
            self.message_image.setText("Le classeur est ouvert dans Excel : ferme-le puis "
                                       "réessaie. Ta relecture est conservée.")
            self.message_image.setVisible(True)
            self.enregistre.emit(False)

    # ── Raccourcis clavier ───────────────────────────────────────────
    def keyPressEvent(self, e):
        from PySide6.QtCore import Qt as _Qt
        touche = e.key()
        if touche in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
            self.garder()
        elif touche == _Qt.Key.Key_R:
            self.remplacer()
        elif touche == _Qt.Key.Key_Escape:
            self.passer()
        elif touche == _Qt.Key.Key_Down and e.modifiers() & _Qt.KeyboardModifier.ControlModifier:
            if self._courant + 1 < len(self._points):
                self.liste.setCurrentRow(self._courant + 1)
        else:
            super().keyPressEvent(e)
