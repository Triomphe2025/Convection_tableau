"""Icônes de la barre latérale : SVG Lucide (licence ISC) teintés depuis les jetons.

Les SVG utilisent stroke="currentColor" ; on les rend puis on les recolore par composition
(SourceIn) avec la couleur passée par l'appelant — jamais de couleur écrite en dur ici.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def _dossier_icones() -> Path:
    if hasattr(sys, "_MEIPASS"):
        candidat = Path(sys._MEIPASS) / "trios_qt" / "icones"
        if candidat.is_dir():
            return candidat
    return Path(__file__).resolve().parent / "icones"


def charger_icone(cle: str, couleur: str, taille: int = 18) -> QIcon:
    chemin = _dossier_icones() / f"{cle}.svg"
    rendu = QSvgRenderer(str(chemin))
    pixmap = QPixmap(taille, taille)
    pixmap.fill(Qt.GlobalColor.transparent)
    peintre = QPainter(pixmap)
    rendu.render(peintre)
    # Recolorer les traits du glyphe avec la couleur des jetons.
    peintre.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    peintre.fillRect(pixmap.rect(), QColor(couleur))
    peintre.end()
    return QIcon(pixmap)
