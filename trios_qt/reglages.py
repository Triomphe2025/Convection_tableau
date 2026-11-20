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


def charger_cle_api_demarrage():
    """Charge la clé API depuis la même source que l'appli actuelle (env ANTHROPIC_API_KEY) dans
    Config.CLAUDE_API_KEY si elle n'y est pas déjà. Rend la clé effective (chaîne, vide si aucune).
    """
    from config import Config
    cle = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if cle and not getattr(Config, 'CLAUDE_API_KEY', '').strip():
        Config.CLAUDE_API_KEY = cle
    return getattr(Config, 'CLAUDE_API_KEY', '') or ''
