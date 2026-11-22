"""Drapeau global « réduire les animations » et fondu de passage d'écran.

Au démarrage on lit le réglage Windows « réduire les animations » (SPI_GETCLIENTAREAANIMATION) :
toutes les animations de l'appli le respectent (fondu instantané si l'utilisateur l'a demandé,
ou sur une machine sans cette option). La valeur est lue une seule fois puis mémorisée.
"""
from __future__ import annotations

import ctypes
import re
import sys

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPointF, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect

# Constante Win32 : état de l'animation des zones clientes (TRUE = animations actives).
_SPI_GETCLIENTAREAANIMATION = 0x1042

_reduction = None  # None = pas encore lu ; True/False = valeur mémorisée


def _lire_reglage_windows() -> bool:
    """True si l'utilisateur a demandé de réduire les animations. Hors Windows / échec : False."""
    if not sys.platform.startswith("win"):
        return False
    try:
        actives = ctypes.c_int(0)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(actives), 0)
        if not ok:
            return False
        # pvParam reçoit TRUE quand les animations sont actives : réduites = l'inverse.
        return not bool(actives.value)
    except Exception:
        return False


def animations_reduites() -> bool:
    global _reduction
    if _reduction is None:
        _reduction = _lire_reglage_windows()
    return _reduction


def definir_reduction(valeur: bool) -> None:
    """Force le drapeau (tests, ou préférence applicative ultérieure)."""
    global _reduction
    _reduction = bool(valeur)


def reinitialiser() -> None:
    """Oublie la valeur mémorisée : la prochaine lecture repart du réglage Windows."""
    global _reduction
    _reduction = None


def courbe_depuis_jetons(texte: str) -> QEasingCurve:
    """« cubic-bezier(x1, y1, x2, y2) » (jetons.courbe_standard) -> QEasingCurve exacte."""
    nombres = [float(n) for n in re.findall(r"-?\d*\.?\d+", texte)]
    courbe = QEasingCurve(QEasingCurve.Type.BezierSpline)
    if len(nombres) == 4:
        x1, y1, x2, y2 = nombres
        courbe.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1.0, 1.0))
    return courbe


def effet_opacite(widget, duree_ms: int | None = None, jetons: dict | None = None):
    """Pose un QGraphicsOpacityEffect et rend (effet, animation d'opacité réutilisable).

    L'animation (durée = jeton changement_etat par défaut) sert aux fondus répétés (ex. astuces) :
    l'appelant pose startValue / endValue puis start(). Le fondu reste à la charge de l'appelant
    quant au respect de « animations réduites ».
    """
    jetons = jetons or charger_jetons_mouvement()
    if duree_ms is None:
        duree_ms = int(jetons["changement_etat"])
    effet = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effet)
    anim = QPropertyAnimation(effet, b"opacity", widget)
    anim.setDuration(int(duree_ms))
    return effet, anim


def charger_jetons_mouvement() -> dict:
    """Durées de mouvement des jetons (sous-dict mouvement_ms), pour les helpers d'animation."""
    from trios_qt import theme
    return theme.charger_jetons()["mouvement_ms"]


def fondu_entree(widget, duree_ms: int, courbe: QEasingCurve | None = None):
    """Fait apparaître le widget en fondu. Rend None si les animations sont réduites."""
    if animations_reduites():
        return None
    effet = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effet)
    anim = QPropertyAnimation(effet, b"opacity", widget)
    anim.setDuration(int(duree_ms))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    if courbe is not None:
        anim.setEasingCurve(courbe)
    # À la fin, retirer l'effet : il ralentit le rendu et grise les sous-pixels du texte.
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._anim_fondu = anim  # garder une référence, sinon l'animation est collectée
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim
