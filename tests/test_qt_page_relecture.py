"""Phase 2D étape 4 — écran Relecture : chargement, décisions, raccourcis, enregistrement.

Couple Excel + points.json FABRIQUÉ (aucune donnée client). Le modèle (relecture_modele) est
déjà testé ; ici on vérifie le câblage de l'écran.
"""
import json

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill

pytest.importorskip("PySide6")

import relecture_modele as rm  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.page_relecture import PageRelecture  # noqa: E402


def _couple(tmp_path):
    xlsx = tmp_path / "doc.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Borniers"
    ws["C3"] = "KGCB16"
    ws["C3"].fill = PatternFill("solid", fgColor="FFC7CE")
    ws["D5"] = "X"
    ws["D5"].fill = PatternFill("solid", fgColor="FFC7CE")
    wb.save(xlsx)
    points = {"version": 1, "document": "DOC", "excel": str(xlsx), "points": [
        {"id": "C3", "etat": "a_voir", "sorte": "qualite", "cellule_excel": "C3",
         "valeur": "KGCB16", "suggestion": "KGBG16", "colonne": "SIGNAL", "page": 24,
         "page_imprimee": "24", "bornier": "AG16R", "raison": "diffère", "confiance": 96,
         "zone": None},
        {"id": "D5", "etat": "a_voir", "sorte": "qualite", "cellule_excel": "D5",
         "valeur": "X", "suggestion": None, "colonne": "JARRETIERES", "page": 25,
         "page_imprimee": "25", "bornier": "C13T", "raison": "illisible", "confiance": 50,
         "zone": None}]}
    pjson = tmp_path / "doc_points.json"
    pjson.write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")
    return pjson, xlsx


@pytest.fixture
def page(qtbot, tmp_path):
    creer_application([])
    p = PageRelecture()
    qtbot.addWidget(p)
    p._couple = _couple(tmp_path)
    p.definir_relecture(rm.Relecture(p._couple[0]))
    return p


class TestChargement:

    def test_liste_des_points(self, page):
        assert page.liste.count() == 2
        assert "Page 24" in page.liste.item(0).text()

    def test_selection_remplit_les_champs(self, page):
        page.liste.setCurrentRow(0)
        assert "SIGNAL" in page._champs
        assert page._champs["SIGNAL"].text() == "KGCB16"
        assert "96 %" in page.explication.text()


class TestDecisions:

    def test_garder(self, page):
        page.liste.setCurrentRow(0)
        page.garder()
        assert page._relecture.point("C3")["etat"] == "garde"
        assert "1 sur 2 traités" in page.etiquette_progres.text()

    def test_remplacer_prend_la_suggestion(self, page):
        page.liste.setCurrentRow(0)
        page.remplacer()
        assert page._relecture.point("C3")["etat"] == "corrige"
        assert page._relecture.point("C3")["valeur_corrigee"] == "KGBG16"

    def test_passer(self, page):
        page.liste.setCurrentRow(1)
        page.passer()
        assert page._relecture.point("D5")["etat"] == "passe"

    def test_decision_avance_au_point_suivant(self, page):
        page.liste.setCurrentRow(0)
        page.garder()
        assert page.liste.currentRow() == 1


class TestEnregistrement:

    def test_enregistrer_ecrit_le_classeur(self, page, qtbot):
        page.liste.setCurrentRow(0)
        page.remplacer()
        with qtbot.waitSignal(page.enregistre, timeout=1000) as bloc:
            page.enregistrer()
        assert bloc.args == [True]
        ws = load_workbook(page._couple[1])["Borniers"]
        assert ws["C3"].value == "KGBG16"

    def test_classeur_verrouille_message(self, page, qtbot, monkeypatch):
        page.liste.setCurrentRow(0)
        page.garder()
        monkeypatch.setattr(page._relecture, "enregistrer_excel",
                            lambda *a, **k: (_ for _ in ()).throw(rm.VerrouError("x")))
        with qtbot.waitSignal(page.enregistre, timeout=1000) as bloc:
            page.enregistrer()
        assert bloc.args == [False]
        assert page.message_image.isVisibleTo(page)


class TestImage:

    def test_image_absente_affiche_un_message(self, page):
        page.definir_relecture(page._relecture, image_de_page=lambda pg: None)
        page.liste.setCurrentRow(0)
        assert page.message_image.isVisibleTo(page)
