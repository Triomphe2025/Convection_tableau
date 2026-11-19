"""Thème de l'interface Qt : jetons de design -> polices embarquées + feuille QSS.

Toutes les couleurs, tailles, rayons et durées viennent de docs/maquettes/jetons.json ; aucune
valeur de couleur n'est écrite en dur ici (le test test_qt_theme le vérifie). La QSS complète des
composants s'étoffe à l'étape 3 ; cette base pose le fond, le texte et la police par défaut.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

# Graisses utilisées par jetons.json (polices.interface / polices.codes), en TTF statiques.
_FICHIERS_POLICES = (
    "Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf",
    "JetBrainsMono-Regular.ttf", "JetBrainsMono-Medium.ttf",
)

_polices_chargees = False


def _racine_ressources() -> Path:
    # En exe PyInstaller les ressources sont sous _MEIPASS ; en dev, à la racine du projet.
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _dossier_polices() -> Path:
    base = _racine_ressources()
    # En dev les polices sont dans le paquet ; en exe le .spec les place sous trios_qt/polices.
    candidat = base / "trios_qt" / "polices"
    if candidat.is_dir():
        return candidat
    return Path(__file__).resolve().parent / "polices"


def chemin_jetons() -> Path:
    return _racine_ressources() / "docs" / "maquettes" / "jetons.json"


def charger_jetons(chemin: Path | None = None) -> dict:
    chemin = chemin or chemin_jetons()
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def enregistrer_polices(dossier: Path | None = None) -> list[str]:
    """Embarque les TTF via QFontDatabase ; rend les familles chargées. Idempotent par session."""
    global _polices_chargees
    dossier = dossier or _dossier_polices()
    familles: set[str] = set()
    for nom in _FICHIERS_POLICES:
        fid = QFontDatabase.addApplicationFont(str(dossier / nom))
        for famille in QFontDatabase.applicationFontFamilies(fid):
            familles.add(famille)
    _polices_chargees = True
    return sorted(familles)


def construire_qss(jetons: dict) -> str:
    """Feuille QSS dérivée des jetons — aucune couleur n'est écrite en dur dans ce fichier."""
    c = jetons["couleurs"]
    t = jetons["tailles_texte_px"]
    r = jetons["rayons_px"]
    famille = jetons["polices"]["interface"]
    repli = jetons["polices"]["repli_windows"]
    return f"""
QWidget {{
    background-color: {c['fond']};
    color: {c['texte']};
    font-family: "{famille}", "{repli}";
    font-size: {int(t['courant'])}px;
}}
QToolTip {{
    background-color: {c['sureleve']};
    color: {c['texte']};
    border: 1px solid {c['trait']};
    border-radius: {int(r['bouton'])}px;
    padding: 4px 8px;
}}
#barre_laterale {{
    background-color: {c['barre_laterale']};
    border-right: 1px solid {c['trait']};
}}
#logo {{
    color: {c['texte']};
    font-size: {int(t['titre_bloc'])}px;
    font-weight: 700;
}}
QPushButton[classe="nav"] {{
    background-color: transparent;
    color: {c['texte_secondaire']};
    border: none;
    border-radius: {int(r['bouton'])}px;
    padding: 9px 12px;
    text-align: left;
    font-size: {int(t['courant'])}px;
    font-weight: 500;
}}
QPushButton[classe="nav"]:hover {{
    background-color: {c['surface']};
    color: {c['texte']};
}}
QPushButton[classe="nav"]:checked {{
    background-color: {c['sureleve']};
    color: {c['texte']};
    font-weight: 600;
}}
#titre_ecran {{
    color: {c['texte']};
    font-size: {int(t['titre_ecran'])}px;
    font-weight: 700;
}}
#carte_etat {{
    background-color: {c['surface']};
    border: 1px solid {c['trait']};
    border-radius: {int(r['carte'])}px;
}}
#etat_modele {{
    color: {c['texte_secondaire']};
}}
#etat_version {{
    color: {c['texte_discret']};
    font-size: {int(t['aide'])}px;
}}
""".strip()


def appliquer_theme(app, jetons: dict | None = None) -> dict:
    """Charge les polices, pose la police par défaut et la QSS ; rend les jetons."""
    jetons = jetons or charger_jetons()
    enregistrer_polices()
    famille = jetons["polices"]["interface"]
    taille = int(jetons["tailles_texte_px"]["courant"])
    app.setFont(QFont(famille, taille))
    app.setStyleSheet(construire_qss(jetons))
    return jetons
