"""« Lecture en direct » (étape 2C-6) : image de la page, bande rose qui descend pendant la
lecture, zones par ligne colorées, loupe de la ligne courante, tableau extrait (9 dernières
lignes) et puces des valeurs lues.

Tout est piloté par les événements du converter (PAGE_DEBUT / PAGE_LUE / PAGE_ZONES) : l'image
(`image`) et les cellules (`cellules`) sont des champs additifs de PAGE_LUE (l'Excel ne change
pas). Sans zones (mode Tesseract), seules la bande et le tableau s'animent. La bande respecte
« animations réduites » et s'arrête quand l'écran est caché. Couleurs des jetons.
"""
from pathlib import Path

from PySide6.QtCore import QAbstractAnimation, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPixmap, QStandardItem, QStandardItemModel,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QTableView, QVBoxLayout, QWidget,
)

from trios_qt import animations, theme


class LectureDirecte(QWidget):
    """Vue de lecture en direct ; sur_evenement(e) la pilote au fil de la conversion."""

    ETAT_VU = "vu"
    ETAT_LU = "lu"
    ETAT_COURANTE = "courante"
    ETAT_DOUTE = "doute"
    MAX_LIGNES_TABLE = 9
    REVEAL_MS = 120          # cadence de révélation d'une ligne (bornée, voir cadence_ms)
    REVEAL_BUDGET_MS = 2400  # durée totale maximale d'une révélation (plafond pour finir à temps)

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._taille_image = (1, 1)
        self._zones_items: list[QGraphicsRectItem] = []
        self._etats_zones: list[str] = []
        self._cellules_page: list = []
        self._zones_page: list = []
        self._index_reveal = 0
        self._ligne_loupe = -1
        self._construire()
        self._anim_bande = QVariantAnimation(self)
        self._anim_bande.setDuration(int(self._jetons["mouvement_ms"]["balayage_scan"]))
        self._anim_bande.setStartValue(0.0)
        self._anim_bande.setEndValue(1.0)
        self._anim_bande.setLoopCount(-1)
        self._anim_bande.valueChanged.connect(self._placer_bande)
        self._timer_reveal = QTimer(self)
        self._timer_reveal.timeout.connect(self._pas_reveler)

    def _construire(self) -> None:
        from PySide6.QtWidgets import QAbstractItemView, QHeaderView
        c = self._jetons["couleurs"]
        self._puces_valeurs: list[str] = []
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(10)

        # En-tête de carte : « Lecture en direct · page n » + « Résultat reçu · x / y lignes ».
        entete = QHBoxLayout()
        self.titre = QLabel("Lecture en direct", self)
        self.titre.setObjectName("lecture_titre")
        self.etat_lecture = QLabel("", self)
        self.etat_lecture.setObjectName("lecture_resultat")
        entete.addWidget(self.titre)
        entete.addStretch(1)
        entete.addWidget(self.etat_lecture)
        racine.addLayout(entete)

        # Haut : vignette de la page (bornée) à gauche, tableau extrait à droite.
        haut = QHBoxLayout()
        haut.setSpacing(14)
        self._scene = QGraphicsScene(self)
        self._vue = QGraphicsView(self._scene, self)
        self._vue.setObjectName("lecture_vue")
        self._vue.setFixedSize(360, 250)
        from PySide6.QtGui import QPainter
        self._vue.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self._bande = QGraphicsRectItem()
        self._bande.setBrush(QBrush(QColor(c["rose_trios"])))
        self._bande.setOpacity(0.28)
        self._bande.setPen(QPen(Qt.PenStyle.NoPen))
        self._bande.setVisible(False)
        self._scene.addItem(self._bande)
        haut.addWidget(self._vue, 0)

        self.table = QTableView(self)
        self.table.setObjectName("lecture_table")
        self._modele = QStandardItemModel(self)
        self.table.setModel(self._modele)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        haut.addWidget(self.table, 1)
        racine.addLayout(haut, 1)

        # Loupe pleine largeur (bande agrandie lisible de la ligne courante).
        titre_loupe = QLabel("Loupe sur la ligne lue", self)
        titre_loupe.setObjectName("lecture_loupe_titre")
        racine.addWidget(titre_loupe)
        self.loupe = QLabel(self)
        self.loupe.setObjectName("lecture_loupe")
        self.loupe.setFixedHeight(56)
        self.loupe.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        racine.addWidget(self.loupe)

        # Puces « Lu : » en vraies pastilles.
        rangee_puces = QHBoxLayout()
        rangee_puces.setSpacing(6)
        libelle_lu = QLabel("Lu :", self)
        libelle_lu.setObjectName("lecture_lu")
        rangee_puces.addWidget(libelle_lu, 0)
        self._puces_boite = QHBoxLayout()
        self._puces_boite.setSpacing(6)
        rangee_puces.addLayout(self._puces_boite)
        rangee_puces.addStretch(1)
        racine.addLayout(rangee_puces)

    # ── Image ────────────────────────────────────────────────────────
    def charger_image(self, chemin) -> bool:
        if not chemin or not Path(str(chemin)).exists():
            return False
        pixmap = QPixmap(str(chemin))
        if pixmap.isNull():
            return False
        self._pixmap_item.setPixmap(pixmap)
        self._taille_image = (pixmap.width(), pixmap.height())
        self._scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self._vue.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        return True

    def a_image(self) -> bool:
        return not self._pixmap_item.pixmap().isNull()

    # ── Zones ────────────────────────────────────────────────────────
    def couleur_zone(self, etat: str) -> QColor:
        c = self._jetons["couleurs"]
        table = {self.ETAT_VU: c["texte_natif"], self.ETAT_LU: c["succes"],
                 self.ETAT_COURANTE: c["rose_trios"], self.ETAT_DOUTE: c["a_relire"]}
        return QColor(table.get(etat, c["texte_natif"]))

    def definir_zones(self, zones, index_courant: int | None = None) -> None:
        for item in self._zones_items:
            self._scene.removeItem(item)
        self._zones_items = []
        self._etats_zones = []
        if not zones:
            return
        largeur, hauteur = self._taille_image
        if index_courant is None:
            index_courant = len(zones) - 1
        for i, zone in enumerate(zones):
            x0, y0, x1, y1 = zone["boite"]
            etat = self.ETAT_COURANTE if i == index_courant else self.ETAT_LU
            rect = QGraphicsRectItem(QRectF(x0 * largeur, y0 * hauteur,
                                            (x1 - x0) * largeur, (y1 - y0) * hauteur))
            couleur = self.couleur_zone(etat)
            rect.setPen(QPen(couleur, 2))
            remplissage = QColor(couleur)
            remplissage.setAlphaF(0.22)
            rect.setBrush(QBrush(remplissage))
            self._scene.addItem(rect)
            self._zones_items.append(rect)
            self._etats_zones.append(etat)
        courante = zones[index_courant] if 0 <= index_courant < len(zones) else None
        self._mettre_a_jour_loupe(courante)

    def nombre_zones(self) -> int:
        return len(self._zones_items)

    def etat_zone(self, i: int) -> str:
        return self._etats_zones[i] if 0 <= i < len(self._etats_zones) else ""

    def _mettre_a_jour_loupe(self, zone) -> None:
        if zone is None or self._pixmap_item.pixmap().isNull():
            self.loupe.clear()
            return
        largeur, hauteur = self._taille_image
        x0, y0, x1, y1 = zone["boite"]
        decoupe = self._pixmap_item.pixmap().copy(
            int(x0 * largeur), int(y0 * hauteur),
            max(1, int((x1 - x0) * largeur)), max(1, int((y1 - y0) * hauteur)))
        if not decoupe.isNull():
            cible_l = max(200, self.loupe.width())
            self.loupe.setPixmap(decoupe.scaled(
                cible_l, 44, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    # ── Tableau extrait ──────────────────────────────────────────────
    def remplir_table(self, cellules) -> None:
        self._modele.clear()
        if not cellules:
            return
        dernieres = cellules[-self.MAX_LIGNES_TABLE:]
        for ligne in dernieres:
            self._modele.appendRow([QStandardItem(str(v)) for v in (ligne or [])])

    def cadence_ms(self, nombre_lignes: int) -> int:
        """Cadence de révélation d'une ligne : ~120 ms, bornée pour tenir le budget total."""
        if nombre_lignes <= 0:
            return self.REVEAL_MS
        return max(1, min(self.REVEAL_MS, self.REVEAL_BUDGET_MS // nombre_lignes))

    def ligne_loupe(self) -> int:
        return self._ligne_loupe

    def lignes_table(self) -> int:
        return self._modele.rowCount()

    def valeur_table(self, r: int, c: int) -> str:
        item = self._modele.item(r, c)
        return item.text() if item is not None else ""

    # ── Puces ────────────────────────────────────────────────────────
    def definir_puces(self, cellules_ligne) -> None:
        valeurs = [str(v) for v in (cellules_ligne or []) if str(v).strip()]
        self._puces_valeurs = valeurs
        while self._puces_boite.count():
            el = self._puces_boite.takeAt(0)
            w = el.widget()
            if w is not None:
                w.setParent(None)   # détacher tout de suite (deleteLater est différé)
                w.deleteLater()
        for v in valeurs:
            pastille = QLabel(v, self)
            pastille.setObjectName("lecture_puce")
            self._puces_boite.addWidget(pastille)

    def puces_texte(self) -> str:
        return "  ".join(self._puces_valeurs)

    def definir_titre(self, page) -> None:
        self.titre.setText(f"Lecture en direct · page {page}" if page else "Lecture en direct")

    def definir_resultat(self, texte: str) -> None:
        self.etat_lecture.setText(texte or "")

    def definir_colonnes(self, noms) -> None:
        self._modele.setHorizontalHeaderLabels(list(noms) if noms else [])
        self.table.horizontalHeader().setVisible(bool(noms))

    # ── Bande de lecture ─────────────────────────────────────────────
    def _placer_bande(self, valeur) -> None:
        largeur, hauteur = self._taille_image
        epaisseur = max(6.0, hauteur * 0.05)
        self._bande.setRect(0, float(valeur) * hauteur, largeur, epaisseur)

    def definir_bande_active(self, actif: bool) -> None:
        if actif and not animations.animations_reduites():
            self._bande.setVisible(True)
            if self._anim_bande.state() != QAbstractAnimation.State.Running:
                self._anim_bande.start()
        else:
            self._anim_bande.stop()
            self._bande.setVisible(False)

    def bande_active(self) -> bool:
        return self._anim_bande.state() == QAbstractAnimation.State.Running

    # ── Révélation ligne par ligne (après PAGE_LUE) ──────────────────
    def demarrer_reveler(self, zones, cellules) -> None:
        """Révèle les lignes une à une (zone courante, loupe, tableau, puces) ; instantané si
        les animations sont réduites. Sans cellules, affiche simplement les zones."""
        self._timer_reveal.stop()
        self._zones_page = list(zones or [])
        self._cellules_page = list(cellules or [])
        self._index_reveal = 0
        self._ligne_loupe = -1
        if self._modele.rowCount():
            self._modele.removeRows(0, self._modele.rowCount())
        self.definir_zones([])
        total = len(self._cellules_page) or len(self._zones_page)
        if total == 0:
            return
        if animations.animations_reduites():
            while self._index_reveal < total:
                self._pas_reveler()
        else:
            self._timer_reveal.start(self.cadence_ms(total))

    def terminer_reveler(self) -> None:
        """Termine la révélation en cours d'un coup (appelé à FIN) : plus de « 6 / 9 lignes »."""
        self._timer_reveal.stop()
        total = len(self._cellules_page) or len(self._zones_page)
        while self._index_reveal < total:
            self._pas_reveler()

    def _pas_reveler(self) -> None:
        total = len(self._cellules_page) or len(self._zones_page)
        i = self._index_reveal
        if i >= total:
            self._timer_reveal.stop()
            return
        if self._zones_page:
            self.definir_zones(self._zones_page[:i + 1], index_courant=i)
        if i < len(self._cellules_page):
            ligne = self._cellules_page[i]
            self._modele.appendRow([QStandardItem(str(v)) for v in (ligne or [])])
            while self._modele.rowCount() > self.MAX_LIGNES_TABLE:
                self._modele.removeRow(0)
            self._surligner_derniere()
            self.definir_puces(ligne)
        if i < len(self._zones_page):
            self._mettre_a_jour_loupe(self._zones_page[i])
            self._ligne_loupe = i
        self._index_reveal += 1
        self.definir_resultat(f"Résultat reçu · {self._index_reveal} / {total} lignes")

    def _surligner_derniere(self) -> None:
        from PySide6.QtGui import QBrush, QColor
        fond = QColor(self._jetons["couleurs"]["rose_trios"])
        fond.setAlphaF(0.18)
        for r in range(self._modele.rowCount()):
            couleur = fond if r == self._modele.rowCount() - 1 else QBrush()
            for cc in range(self._modele.columnCount()):
                item = self._modele.item(r, cc)
                if item is not None:
                    item.setBackground(couleur)

    # ── Événements ───────────────────────────────────────────────────
    def sur_evenement(self, e) -> None:
        import evenements as ev
        if e.type == ev.PAGE_DEBUT:
            if e.image:
                self.charger_image(e.image)   # bande rose sur la page en cours de lecture
            self.definir_bande_active(True)
        elif e.type == ev.PAGE_LUE:
            self.definir_bande_active(False)
            if e.image:
                self.charger_image(e.image)
            self.demarrer_reveler(e.zones, e.cellules)
        elif e.type == ev.PAGE_ZONES:
            self.definir_zones(e.zones)

    def _ajuster_vue(self) -> None:
        # fitInView recalculé à la vraie taille de la vue (sinon l'image reste minuscule).
        if not self._pixmap_item.pixmap().isNull():
            self._vue.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajuster_vue()

    def showEvent(self, event):
        super().showEvent(event)
        self._ajuster_vue()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.definir_bande_active(False)
        self._timer_reveal.stop()
