"""Phase 2D étape 5 — branchements de la fenêtre : Terminé, Relecture, compteur latéral.

Couple Excel + points.json FABRIQUÉ (aucune donnée client). On vérifie le câblage :
« Voir le résumé » ouvre Terminé ; « Relire » (lot) ouvre Relecture chargée ; le compteur de
la barre latérale suit le nombre de points encore « À voir » ; « Relire » de Terminé ouvre
Relecture.
"""
import json

import pytest
from openpyxl import Workbook

pytest.importorskip("PySide6")

from trios_qt.application import creer_application  # noqa: E402
from trios_qt.fenetre import FenetrePrincipale  # noqa: E402


def _couple(tmp_path, n_points=2):
    xlsx = tmp_path / "doc.xlsx"
    wb = Workbook()
    wb.active.title = "Borniers"
    wb.save(xlsx)
    points = {
        "version": 1, "document": "DOC123", "excel": str(xlsx), "modele": "Bornier standard",
        "points": [
            {"id": f"p{i}", "etat": "a_voir", "sorte": "qualite", "cellule_excel": f"C{i + 1}",
             "valeur": "X", "suggestion": "Y", "colonne": "SIGNAL", "page": 24 + i,
             "page_imprimee": str(24 + i), "bornier": "AG16R", "raison": "diffère",
             "confiance": 90, "zone": None}
            for i in range(n_points)]}
    pj = tmp_path / "doc_points.json"
    pj.write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")
    return pj, xlsx


@pytest.fixture
def fen(qtbot, tmp_path):
    creer_application([])
    f = FenetrePrincipale(fabrique_service=lambda *a, **k: None)
    qtbot.addWidget(f)
    f._couple = _couple(tmp_path)
    return f


class TestBranchements:

    def test_voir_resume_ouvre_termine(self, fen):
        fen._chemin_points_courant = str(fen._couple[0])
        fen.page_traitement.voir_resume.emit()
        assert fen.ecran_courant() == "termine"

    def test_relire_lot_ouvre_relecture_chargee(self, fen):
        fen._chemin_points_courant = str(fen._couple[0])
        fen.page_attente_lot.relire_autre.emit()
        assert fen.ecran_courant() == "relecture"
        assert fen.page_relecture.liste.count() == 2

    def test_compteur_lateral_suit_les_points_a_voir(self, fen):
        fen.ouvrir_relecture(str(fen._couple[0]))
        pastille = fen.pastilles["nav_relecture"]
        assert pastille.text() == "2"
        fen.page_relecture.liste.setCurrentRow(0)
        fen.page_relecture.garder()
        assert pastille.text() == "1"

    def test_termine_relire_ouvre_relecture(self, fen):
        fen._chemin_points_courant = str(fen._couple[0])
        fen.page_termine.relire_demande.emit()
        assert fen.ecran_courant() == "relecture"
