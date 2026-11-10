"""Événements structurés de la conversion (phase 1a, étape 2).

Module pur, sans dépendance au moteur ni à Tkinter : une dataclass figée émise EN PLUS
de on_progress / on_log, pour une interface qui veut suivre le détail (future interface
PySide6). L'absence de rappel on_evenement ne change rien au reste du pipeline.
"""
from dataclasses import dataclass, field
from time import time
from typing import List, Optional, Tuple

# Types d'événements (au minimum).
ANALYSE = 'analyse'            # nature d'une page (vectoriel / scan / …)
PHASE = 'phase'               # analyse, lecture, contrôles, excel
PAGE_DEBUT = 'page_debut'
PAGE_LUE = 'page_lue'         # lignes extraites + zones
PAGE_ALERTE = 'page_alerte'
LOT_CREE = 'lot_cree'
LOT_ETAT = 'lot_etat'
LOT_RECUPERE = 'lot_recupere'
FIN = 'fin'
ERREUR = 'erreur'


@dataclass(frozen=True)
class Evenement:
    """Un événement du pipeline ; seuls les champs utiles au type sont renseignés."""
    type: str
    horodatage: float = field(default_factory=time)
    page: Optional[int] = None
    total: Optional[int] = None
    nature: Optional[str] = None
    etat: Optional[str] = None
    bornier: Optional[str] = None
    lignes: Optional[int] = None
    zones: Optional[List[Tuple[float, float, float, float]]] = None
    alertes: Optional[List[str]] = None
    cout: Optional[dict] = None
    lot: Optional[str] = None
    message: Optional[str] = None


def zones_relatives(lecture) -> Optional[List[Tuple[float, float, float, float]]]:
    """Boîtes des mots Tesseract d'une page en coordonnées 0–1, ou None si absentes.

    `lecture` : objet à `.mots` (tuples x0, y0, x1, y1, texte, conf) et `.taille`
    (largeur, hauteur en pixels). Les traits du cadre (« | ») et les mots vides sont
    écartés. None si pas de lecture, pas de mot visible, ou taille nulle.
    """
    if lecture is None:
        return None
    largeur, hauteur = lecture.taille
    if largeur <= 0 or hauteur <= 0:
        return None
    zones = [
        (x0 / largeur, y0 / hauteur, x1 / largeur, y1 / hauteur)
        for x0, y0, x1, y1, texte, _conf in lecture.mots
        if texte.strip('|').strip()
    ]
    return zones or None
