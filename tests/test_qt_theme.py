"""Étape 2 — thème : QSS dérivée des jetons, polices embarquées, aucune couleur en dur.

Sans écran (QT_QPA_PLATFORM=offscreen, posé par conftest).
"""
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from trios_qt import theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def test_jetons_lus_depuis_le_fichier_maquette():
    jetons = theme.charger_jetons()
    assert jetons["couleurs"]["fond"] == "#0E1322"
    assert jetons["polices"]["interface"] == "Inter"


def test_polices_embarquees_donnent_inter_et_jetbrains_mono():
    creer_application([])
    familles = theme.enregistrer_polices()
    assert "Inter" in familles
    assert "JetBrains Mono" in familles


def test_qss_contient_les_couleurs_des_jetons():
    jetons = theme.charger_jetons()
    qss = theme.construire_qss(jetons)
    # Les couleurs de la QSS viennent des jetons, pas de littéraux.
    assert jetons["couleurs"]["fond"] in qss
    assert jetons["couleurs"]["texte"] in qss
    assert jetons["polices"]["interface"] in qss


def test_appliquer_theme_pose_la_feuille_et_la_police():
    app = creer_application([])
    theme.appliquer_theme(app)
    assert app.styleSheet()
    assert app.font().family() == "Inter"


def test_aucune_couleur_en_dur_dans_le_code_qt():
    # Toute couleur doit venir de jetons.json : aucun littéral hexadécimal dans trios_qt/*.py.
    fautifs = []
    for py in (RACINE / "trios_qt").rglob("*.py"):
        for num, ligne in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if HEX.search(ligne):
                fautifs.append(f"{py.name}:{num}: {ligne.strip()}")
    assert not fautifs, "couleurs en dur hors jetons :\n" + "\n".join(fautifs)
