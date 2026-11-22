"""« Lecture en direct » (étape 2C-6) : image de la page, bande rose qui descend pendant la
lecture, zones par ligne colorées, loupe de la ligne courante, tableau extrait (9 dernières
lignes) et puces des valeurs lues.

Tout est piloté par les événements du converter (PAGE_DEBUT / PAGE_LUE / PAGE_ZONES) : l'image
(`image`) et les cellules (`cellules`) sont des champs additifs de PAGE_LUE (l'Excel ne change
pas). Sans zones (mode Tesseract), seules la bande et le tableau s'animent. La bande respecte
« animations réduites » et s'arrête quand l'écran est caché. Couleurs des jetons.
"""
from pathlib import Path

from PySide6.QtCore import QAbstractAnimation, QRectF, Qt, QVariantAnimation
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

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._taille_image = (1, 1)
        self._zones_items: list[QGraphicsRectItem] = []
        self._etats_zones: list[str] = []
        self._construire()
        self._anim_bande = QVariantAnimation(self)
        self._anim_bande.setDuration(int(self._jetons["mouvement_ms"]["balayage_scan"]))
        self._anim_bande.setStartValue(0.0)
        self._anim_bande.setEndValue(1.0)
        self._anim_bande.setLoopCount(-1)
        self._anim_bande.valueChanged.connect(self._placer_bande)

    def _construire(self) -> None:
        c = self._jetons["couleurs"]
        rangee = QHBoxLayout(self)
        rangee.setContentsMargins(0, 0, 0, 0)
        rangee.setSpacing(12)

        self._scene = QGraphicsScene(self)
        self._vue = QGraphicsView(self._scene, self)
        self._vue.setObjectName("lecture_vue")
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
        rangee.addWidget(self._vue, 1)

        # Panneau de droite à largeur bornée : la loupe (ligne agrandie) ne doit pas étirer
        # la colonne et écraser la vue de la page.
        panneau = QWidget(self)
        panneau.setObjectName("lecture_panneau")
        panneau.setMinimumWidth(240)
        panneau.setMaximumWidth(360)
        colonne = QVBoxLayout(panneau)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(8)
        self.loupe = QLabel(panneau)
        self.loupe.setObjectName("lecture_loupe")
        self.loupe.setFixedHeight(54)
        self.loupe.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.puces = QLabel(panneau)
        self.puces.setObjectName("lecture_puces")
        self.puces.setWordWrap(True)
        self.table = QTableView(panneau)
        self.table.setObjectName("lecture_table")
        self._modele = QStandardItemModel(self)
        self.table.setModel(self._modele)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        colonne.addWidget(self.loupe)
        colonne.addWidget(self.puces)
        colonne.addWidget(self.table, 1)
        rangee.addWidget(panneau, 0)

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

    def lignes_table(self) -> int:
        return self._modele.rowCount()

    def valeur_table(self, r: int, c: int) -> str:
        item = self._modele.item(r, c)
        return item.text() if item is not None else ""

    # ── Puces ────────────────────────────────────────────────────────
    def definir_puces(self, cellules_ligne) -> None:
        valeurs = [str(v) for v in (cellules_ligne or []) if str(v).strip()]
        self.puces.setText("  •  ".join(valeurs))

    def puces_texte(self) -> str:
        return self.puces.text()

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

    # ── Événements ───────────────────────────────────────────────────
    def sur_evenement(self, e) -> None:
        import evenements as ev
        if e.type == ev.PAGE_DEBUT:
            self.definir_bande_active(True)
        elif e.type == ev.PAGE_LUE:
            self.definir_bande_active(False)
            if e.image:
                self.charger_image(e.image)
            self.definir_zones(e.zones)
            self.remplir_table(e.cellules)
            if e.cellules:
                self.definir_puces(e.cellules[-1])
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
