"""Étape 5 — garde-fou du .spec Qt : entrée, mode dossier, PySide6, données et licences jointes.

Contrôles statiques (sans lancer PyInstaller) : le .spec vise run_qt.py en onedir et les
ressources qu'il embarque existent réellement (polices, icônes, jetons, LGPL).
"""
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SPEC = (RACINE / "TriosSeconverter_Qt.spec").read_text(encoding="utf-8")


def test_spec_vise_run_qt_en_mode_dossier():
    assert "'run_qt.py'" in SPEC
    # onedir : binaires hors de l'exe + COLLECT (jamais onefile pour la LGPL de PySide6).
    assert "exclude_binaries=True" in SPEC
    assert "COLLECT(" in SPEC
    assert "name='TriosSeconverter_Qt'" in SPEC


def test_spec_separe_de_l_exe_actuel():
    # L'ancienne interface Tkinter n'est pas embarquée par ce spec.
    assert "interface.py" not in SPEC
    assert "'tkinter'" in SPEC  # exclue


def test_spec_embarque_pyside6():
    for module in ("PySide6.QtWidgets", "PySide6.QtSvg"):
        assert module in SPEC


def test_ressources_embarquees_existent():
    polices = list((RACINE / "trios_qt" / "polices").glob("*.ttf"))
    dossier_icones = RACINE / "trios_qt" / "icones"
    icones = {p.stem for p in dossier_icones.glob("*.svg")}
    assert len(polices) == 6
    # 6 nav + ampoule/info + poste/nuage (blocs lot) + bouclier (carte fermer) + pause (mini).
    assert len(icones) == 12
    assert {"ampoule", "info", "poste", "nuage", "bouclier", "pause"} <= icones
    assert (RACINE / "docs" / "maquettes" / "jetons.json").is_file()


def test_licences_jointes():
    for nom in ("LGPL-3.0.txt", "Inter-OFL.txt", "JetBrainsMono-OFL.txt", "Lucide-ISC.txt"):
        assert (RACINE / "licences" / nom).is_file(), nom
    assert "licences" in SPEC
