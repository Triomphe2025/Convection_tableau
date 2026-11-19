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

HAUTEUR_PASTILLE = 20  # px, pilule à hauteur fixe (rayon = moitié) ; partagé avec fenetre.py

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


def _rgba(hexa: str, alpha: float) -> str:
    """« #RRGGBB » + opacité -> « rgba(r, g, b, a) » (atténuation d'une couleur des jetons)."""
    h = hexa.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def construire_qss(jetons: dict) -> str:
    """Feuille QSS dérivée des jetons — aucune couleur n'est écrite en dur dans ce fichier."""
    c = jetons["couleurs"]
    t = jetons["tailles_texte_px"]
    r = jetons["rayons_px"]
    famille = jetons["polices"]["interface"]
    repli = jetons["polices"]["repli_windows"]
    return f"""
QWidget {{
    color: {c['texte']};
    font-family: "{famille}", "{repli}";
    font-size: {int(t['courant'])}px;
}}
#fenetre, QWidget[classe="page"] {{
    background-color: {c['fond']};
}}
QLabel {{
    background-color: transparent;
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
    font-size: 20px;
    font-weight: 800;
}}
QPushButton[classe="nav"] {{
    background-color: transparent;
    color: {c['texte_secondaire']};
    border: none;
    border-radius: {int(r['bouton'])}px;
    padding: 9px 10px;
    min-height: 26px;
    text-align: left;
    font-size: {int(t['courant'])}px;
    font-weight: 400;
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
#pastille_compteur {{
    background-color: {_rgba(c['a_relire'], 0.18)};
    color: {c['a_relire']};
    border-radius: {int(HAUTEUR_PASTILLE / 2)}px;
    padding: 0px 7px;
    font-size: {int(t['aide'])}px;
    font-weight: 600;
}}
#pastille_beta {{
    background-color: transparent;
    color: {c['texte_discret']};
    border: 1px solid {c['trait']};
    border-radius: {int(HAUTEUR_PASTILLE / 2)}px;
    padding: 0px 7px;
    font-size: {int(t['aide'])}px;
    font-weight: 500;
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
#sous_titre_ecran {{
    color: {c['texte_secondaire']};
    font-size: {int(t['courant'])}px;
}}
#zone_depot {{
    background-color: {c['surface']};
    border: 1px solid {c['trait']};
    border-radius: {int(r['carte'])}px;
}}
#depot_logo {{
    border: 2px solid {c['rose_trios']};
    border-radius: {int(r['bouton'])}px;
    background-color: {_rgba(c['rose_trios'], 0.10)};
}}
#depot_invite {{
    color: {c['texte']};
    font-size: {int(t['titre_bloc'])}px;
    font-weight: 600;
}}
#depot_formats {{
    color: {c['texte_discret']};
    font-size: {int(t['aide'])}px;
}}
#liste_fichiers, #liste_viewport, #zone_liste {{
    background-color: {c['fond']};
    border: none;
}}
#ligne_fichier {{
    background-color: {c['surface']};
    border: 1px solid {c['trait']};
    border-radius: {int(r['carte'])}px;
}}
#ligne_fichier[selectionne="true"] {{
    border: 2px solid {c['action_principale']};
}}
#ligne_carre {{
    font-size: {int(t['aide'])}px;
}}
#ligne_nom {{
    color: {c['texte']};
    font-family: "{jetons['polices']['codes']}", monospace;
    font-size: {int(t['courant'])}px;
}}
#ligne_sousligne {{
    color: {c['texte_discret']};
    font-size: {int(t['aide'])}px;
}}
#ligne_type {{
    font-size: {int(t['courant'])}px;
}}
#ligne_preuve {{
    color: {c['texte_secondaire']};
    font-size: {int(t['aide'])}px;
}}
#ligne_sortie {{
    color: {c['texte_secondaire']};
}}
#ligne_estimation {{
    color: {c['texte_discret']};
    font-size: {int(t['aide'])}px;
}}
#ligne_retirer {{
    background-color: transparent;
    color: {c['texte_discret']};
    border: none;
    font-size: {int(t['titre_bloc'])}px;
    max-width: 22px;
}}
#ligne_retirer:hover {{
    color: {c['erreur']};
}}
#panneau_types {{
    background-color: {c['surface']};
    border: 1px solid {c['trait']};
    border-radius: {int(r['carte'])}px;
    min-width: 236px;
    max-width: 276px;
}}
#panneau_titre {{
    color: {c['texte']};
    font-size: {int(t['titre_bloc'])}px;
    font-weight: 600;
}}
#panneau_gerer {{
    background-color: transparent;
    color: {c['rose_trios']};
    border: none;
    font-size: {int(t['aide'])}px;
    font-weight: 600;
}}
#panneau_groupe_titre {{
    color: {c['texte']};
    font-weight: 600;
}}
#panneau_groupe_detail {{
    color: {c['texte_discret']};
    font-size: {int(t['aide'])}px;
}}
#carte_creer_type {{
    background-color: transparent;
    border: 1px dashed {c['trait']};
    border-radius: {int(r['bouton'])}px;
}}
#creer_type_texte {{
    color: {c['texte_discret']};
    font-size: {int(t['aide'])}px;
}}
#resume_bas {{
    color: {c['texte_secondaire']};
}}
#bouton_lancer {{
    background-color: {c['action_principale']};
    color: {c['texte']};
    border: none;
    border-radius: {int(r['bouton'])}px;
    padding: 11px 22px;
    font-weight: 700;
}}
#bouton_lancer:hover {{
    background-color: {c['action_principale_survol']};
}}
#bouton_lancer:disabled {{
    background-color: {c['tuile_attente']};
    color: {c['texte_discret']};
}}
#profil_carte {{
    background-color: {c['fond']};
    border: 1px solid {c['trait']};
    border-radius: {int(r['bouton'])}px;
}}
#profil_carte[actif="true"] {{
    border: 2px solid {c['action_principale']};
}}
#profil_titre {{
    color: {c['texte']};
    font-weight: 600;
}}
#profil_moteur {{
    color: {c['texte_secondaire']};
    font-size: {int(t['aide'])}px;
}}
#profil_estimation {{
    color: {c['texte_discret']};
    font-size: {int(t['aide'])}px;
}}
#case_lot, #deplie_note {{
    color: {c['texte_secondaire']};
    font-size: {int(t['aide'])}px;
}}
#finesse_bouton, #action_secondaire {{
    background-color: {c['sureleve']};
    color: {c['texte']};
    border: 1px solid {c['trait']};
    border-radius: {int(r['bouton'])}px;
    padding: 6px 14px;
}}
#finesse_bouton:checked {{
    border: 1px solid {c['action_principale']};
    color: {c['texte']};
}}
#anim_trios_glyphe {{
    color: {c['rose_trios']};
    font-size: {int(t['titre_bloc'])}px;
    font-weight: 800;
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
