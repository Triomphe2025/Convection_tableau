"""Message 1 — l'exe Qt doit embarquer templates.json (sinon REPARTITEUR/REPARTITEUR 2 absents).

Le registre lit templates.json via chemin_ressource (→ _MEIPASS dans l'exe). Sans l'embarquer,
seuls les modèles codés (Bornier standard, Répartiteur) apparaissent dans l'appli compilée.
"""
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def test_spec_qt_embarque_templates_json():
    spec = (RACINE / "TriosSeconverter_Qt.spec").read_text(encoding="utf-8")
    assert "templates.json" in spec, "TriosSeconverter_Qt.spec doit inclure templates.json"


def test_templates_json_porte_les_repartiteurs():
    # Les modèles attendus dans l'appli compilée et absents du code (DEFAULT_TEMPLATE seul).
    data = json.loads((RACINE / "templates.json").read_text(encoding="utf-8"))
    noms = set(data) if isinstance(data, dict) else {t.get("name") for t in data}
    assert {"REPARTITEUR", "REPARTITEUR 2"} <= noms
