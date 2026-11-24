"""Phase 2D étape 2 — relecture_modele (module pur) : états des points + écriture dans l'Excel.

Classeur et points.json FABRIQUÉS (aucune donnée client). Vérifie : garder / remplacer / passer
modifient le classeur comme prévu, la mise en forme des autres cellules est intacte, la copie de
sauvegarde existe et n'est créée qu'une fois, l'état est retrouvé après « redémarrage », et un
classeur verrouillé donne un message (VerrouError) sans perdre la relecture.
"""
import json

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

import relecture_modele as rm

_ORANGE = "FFC7CE"


def _classeur(chemin):
    wb = Workbook()
    ws = wb.active
    ws.title = "Borniers"
    ws["A1"], ws["B1"], ws["C1"], ws["D1"] = "BORNE", "COULEUR", "SIGNAL", "JARRETIERES"
    ws["C3"] = "KGCB16"
    ws["C3"].fill = PatternFill("solid", fgColor=_ORANGE)
    ws["B4"] = "ROUGE"
    ws["B4"].fill = PatternFill("solid", fgColor=_ORANGE)
    ws["D5"] = "X"
    ws["D5"].fill = PatternFill("solid", fgColor=_ORANGE)
    # Cellule témoin (pas un point) : mise en forme à préserver.
    ws["F10"] = "garde-moi"
    ws["F10"].font = Font(bold=True)
    ws["F10"].fill = PatternFill("solid", fgColor="112233")
    wb.save(chemin)


def _point(pid, coord, valeur, suggestion=None):
    return {"id": pid, "etat": "a_voir", "sorte": "qualite", "cellule_excel": coord,
            "valeur": valeur, "suggestion": suggestion, "ligne": 2, "colonne": "SIGNAL",
            "page": 24, "page_imprimee": "24", "bornier": "AG16R", "raison": "x",
            "confiance": 96, "zone": None}


@pytest.fixture
def couple(tmp_path):
    xlsx = tmp_path / "doc.xlsx"
    _classeur(xlsx)
    points = {
        "version": 1, "document": "DOC", "excel": str(xlsx), "modele": "Bornier standard",
        "points": [
            _point("C3-qualite", "C3", "KGCB16", "KGBG16"),
            _point("B4-qualite", "B4", "ROUGE", "BLANC"),
            _point("D5-qualite", "D5", "X", None),
        ],
    }
    pjson = tmp_path / "doc_points.json"
    pjson.write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")
    return pjson, xlsx


class TestEtats:

    def test_comptes_initiaux(self, couple):
        r = rm.Relecture(couple[0])
        assert r.total() == 3
        assert r.a_voir() == 3
        assert r.traites() == 0

    def test_garder_corriger_passer_comptes(self, couple):
        r = rm.Relecture(couple[0])
        r.garder("C3-qualite")
        r.corriger("B4-qualite", "BLANC")
        r.passer("D5-qualite")
        assert r.a_voir() == 0
        assert r.traites() == 3

    def test_etat_retrouve_apres_redemarrage(self, couple):
        r = rm.Relecture(couple[0])
        r.corriger("B4-qualite", "BLANC")
        r.passer("D5-qualite")
        r2 = rm.Relecture(couple[0])   # « redémarrage » : relecture rechargée depuis le json
        assert r2.point("B4-qualite")["etat"] == "corrige"
        assert r2.point("D5-qualite")["etat"] == "passe"
        assert r2.a_voir() == 1


class TestLigneComplete:

    def test_ligne_du_point_lit_toute_la_ligne(self, couple):
        r = rm.Relecture(couple[0])
        cols, valeurs = r.ligne_du_point(r.point("C3-qualite"))
        assert cols == ["BORNE", "COULEUR", "SIGNAL", "JARRETIERES"]
        # C3 = SIGNAL (3e colonne) sur la ligne 3 ; seule C3 porte une valeur.
        assert valeurs[2] == "KGCB16"
        assert valeurs[0] == "" and valeurs[1] == ""


class TestEcritureExcel:

    def test_garder_et_corriger_ecrivent_et_enlevent_l_orange(self, couple):
        pjson, xlsx = couple
        r = rm.Relecture(pjson)
        r.garder("C3-qualite")
        r.corriger("B4-qualite", "BLANC")
        r.passer("D5-qualite")
        r.enregistrer_excel()
        ws = load_workbook(xlsx)["Borniers"]
        assert ws["C3"].value == "KGCB16"                 # gardé : valeur inchangée
        assert ws["C3"].fill.fill_type is None            # orange retiré
        assert ws["C3"].comment is not None and "Relu le" in ws["C3"].comment.text
        assert ws["B4"].value == "BLANC"                  # corrigé : nouvelle valeur
        assert ws["B4"].fill.fill_type is None
        assert ws["D5"].value == "X"                      # passé : inchangé
        assert str(ws["D5"].fill.fgColor.rgb).endswith(_ORANGE)   # orange gardé (non traité)

    def test_mise_en_forme_des_autres_cellules_intacte(self, couple):
        pjson, xlsx = couple
        r = rm.Relecture(pjson)
        r.corriger("B4-qualite", "BLANC")
        r.enregistrer_excel()
        ws = load_workbook(xlsx)["Borniers"]
        assert ws["F10"].value == "garde-moi"
        assert ws["F10"].font.bold is True
        assert str(ws["F10"].fill.fgColor.rgb).endswith("112233")

    def test_copie_de_sauvegarde_une_seule_fois(self, couple):
        pjson, xlsx = couple
        backup = xlsx.with_name("doc_avant_relecture.xlsx")
        r = rm.Relecture(pjson)
        r.garder("C3-qualite")
        r.enregistrer_excel()
        assert backup.exists()
        empreinte = backup.stat().st_mtime_ns
        r.corriger("B4-qualite", "BLANC")
        r.enregistrer_excel()
        assert backup.stat().st_mtime_ns == empreinte   # jamais réécrite

    def test_classeur_verrouille_message_sans_perte(self, couple, monkeypatch):
        pjson, xlsx = couple
        r = rm.Relecture(pjson)
        r.corriger("B4-qualite", "BLANC")

        def _save_verrou(self, *a, **k):
            raise PermissionError("verrouillé")
        monkeypatch.setattr("openpyxl.workbook.workbook.Workbook.save", _save_verrou)
        with pytest.raises(rm.VerrouError):
            r.enregistrer_excel()
        # La relecture en cours n'est pas perdue : l'état reste dans le json.
        assert rm.Relecture(pjson).point("B4-qualite")["etat"] == "corrige"
