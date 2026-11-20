"""Réglages persistés de l'aperçu Qt (QSettings) : dossier de sortie mémorisé entre sessions."""
from PySide6.QtCore import QSettings

_ORG = "TriosSeconverter"
_APP = "apercu"
_CLE_DOSSIER = "convertir/dossier_sortie"


def _settings():
    return QSettings(_ORG, _APP)


def lire_dossier_sortie():
    return _settings().value(_CLE_DOSSIER, "", type=str)


def ecrire_dossier_sortie(chemin):
    _settings().setValue(_CLE_DOSSIER, chemin or "")
