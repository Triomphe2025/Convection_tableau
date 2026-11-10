"""Événements structurés de la conversion (phase 1a, étape 2).

Module pur, sans dépendance au moteur ni à Tkinter : une dataclass figée émise EN PLUS
de on_progress / on_log, pour une interface qui veut suivre le détail (future interface
PySide6). L'absence de rappel on_evenement ne change rien au reste du pipeline.
"""
from dataclasses import dataclass, field
from time import time
from typing import List, Optional

# Types d'événements (au minimum).
ANALYSE = 'analyse'            # nature d'une page (vectoriel / scan / …)
PHASE = 'phase'               # analyse, lecture, contrôles, excel
PAGE_DEBUT = 'page_debut'
PAGE_LUE = 'page_lue'         # lignes extraites + zones (par ligne) si déjà disponibles
PAGE_ZONES = 'page_zones'     # zones par ligne arrivées après coup (lecture Tesseract prête)
PAGE_ALERTE = 'page_alerte'
LOT_CREE = 'lot_cree'
LOT_ETAT = 'lot_etat'
LOT_RECUPERE = 'lot_recupere'
FIN = 'fin'
ERREUR = 'erreur'


@dataclass(frozen=True)
class Evenement:
    """Un événement du pipeline ; seuls les champs utiles au type sont renseignés.

    `page` = numéro de page du PDF (1 = première page) ; `rang`/`total` = progression parmi
    les pages lues ; `page_imprimee` = numéro imprimé dans le pied (affichage des alertes).
    `zones` = [{'ligne': indice de ligne lue, 'boite': (x0, y0, x1, y1) en 0–1}].
    `compteurs` = détail chiffré d'un lot (requêtes, taille, lues, en attente, délai…).
    """
    type: str
    horodatage: float = field(default_factory=time)
    page: Optional[int] = None
    rang: Optional[int] = None
    total: Optional[int] = None
    page_imprimee: Optional[str] = None
    nature: Optional[str] = None
    etat: Optional[str] = None
    bornier: Optional[str] = None
    lignes: Optional[int] = None
    zones: Optional[List[dict]] = None
    alertes: Optional[List[str]] = None
    cout: Optional[dict] = None
    lot: Optional[str] = None
    compteurs: Optional[dict] = None
    message: Optional[str] = None
