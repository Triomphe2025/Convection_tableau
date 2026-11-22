"""Réglages persistés de l'aperçu Qt (QSettings) : dossier de sortie, chargement de la clé API.

La clé API et les réglages se chargent au démarrage depuis la MÊME source que l'appli actuelle
(variable d'environnement ANTHROPIC_API_KEY → Config.CLAUDE_API_KEY, comme ligne_de_commande.py),
pour que la carte d'état reflète une clé déjà configurée. Les tests isolent QSettings dans un
fichier .ini temporaire (`configurer_pour_tests`) : jamais les réglages réels de l'appli.
"""
import os
from pathlib import Path

from PySide6.QtCore import QSettings

_ORG = "TriosSeconverter"
_APP = "apercu"
_CLE_DOSSIER = "convertir/dossier_sortie"
_CLE_API = "ocr/cle_api"

# Défini par les tests (configurer_pour_tests) → réglages dans un .ini isolé, jamais le vrai store.
_fichier_test = None


def configurer_pour_tests(dossier):
    """Redirige QSettings vers un .ini isolé (dossier des tests) ; None = réglages réels."""
    global _fichier_test
    _fichier_test = str(Path(dossier) / "apercu_tests.ini") if dossier is not None else None


def _settings():
    if _fichier_test is not None:
        return QSettings(_fichier_test, QSettings.Format.IniFormat)
    return QSettings(_ORG, _APP)


def lire_dossier_sortie():
    return _settings().value(_CLE_DOSSIER, "", type=str)


def ecrire_dossier_sortie(chemin):
    _settings().setValue(_CLE_DOSSIER, chemin or "")


def lire_cle_api():
    """Clé API enregistrée par l'aperçu Qt (QSettings), ou '' si aucune."""
    return _settings().value(_CLE_API, "", type=str)


def ecrire_cle_api(cle):
    """Enregistre la clé API dans les réglages de l'aperçu Qt (persistée entre sessions)."""
    _settings().setValue(_CLE_API, (cle or "").strip())


def charger_cle_api_demarrage():
    """Pose Config.CLAUDE_API_KEY au démarrage si elle est vide, dans l'ordre : clé enregistrée
    par l'aperçu (QSettings) → variable d'environnement ANTHROPIC_API_KEY (comme l'appli actuelle).
    Rend la clé effective (chaîne, vide si aucune). L'ancienne appli ne persiste pas la clé : elle
    est saisie à chaque session ; l'aperçu la mémorise une fois pour toutes.
    """
    from config import Config
    if not getattr(Config, 'CLAUDE_API_KEY', '').strip():
        cle = lire_cle_api().strip() or os.environ.get('ANTHROPIC_API_KEY', '').strip()
        if cle:
            Config.CLAUDE_API_KEY = cle
    return getattr(Config, 'CLAUDE_API_KEY', '') or ''
