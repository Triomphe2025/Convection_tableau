"""types_documents.py : registre des types de documents (champs optionnels, familles, doublons)."""
import json
import tempfile
from pathlib import Path

import types_documents as td
from template import TableTemplate, TemplateManager

RACINE = Path(__file__).resolve().parent.parent


def _modele(nom, colonnes, mots_pied, cartouche):
    return TableTemplate(
        name=nom,
        columns=list(colonnes),
        footer_detect_keywords=list(mots_pied),
        footer_left_label=cartouche,
    )


class TestRegistre:

    def test_contient_les_modeles_livres(self):
        types = td.registre()
        for nom in ("Bornier standard", "Répartiteur", "REPARTITEUR", "REPARTITEUR 2"):
            assert nom in types, nom
            assert types[nom].famille == "tableau"

    def test_familles_integrees_plan_excel_journal(self):
        types = td.registre()
        assert types["Plan"].famille == "plan"
        assert "dxf" in types["Plan"].sorties
        assert ".tif" in types["Plan"].extensions and ".pdf" in types["Plan"].extensions
        assert types["Excel"].famille == "excel"
        assert ".xlsx" in types["Excel"].extensions
        assert types["Journal"].famille == "journal"
        assert ".jsonl" in types["Journal"].extensions

    def test_defauts_deduits_du_modele(self):
        modele = _modele("Essai", ["A", "B"], ["NO PLAN", "P.E.T"], "SIEMENS")
        types = td.registre(modeles={"Essai": modele})
        assert "Essai" in types
        reco = types["Essai"].reconnaissance
        assert reco.entete_colonnes == ("A", "B")
        assert reco.mots_pied == ("NO PLAN", "P.E.T")
        assert reco.marque_cartouche == "SIEMENS"


class TestDoublons:

    def test_repartiteur_signale_comme_doublon(self):
        paires = {frozenset(p) for p in td.doublons(td.registre())}
        assert frozenset({"Répartiteur", "REPARTITEUR"}) in paires

    def test_modeles_distincts_non_signales(self):
        paires = {frozenset(p) for p in td.doublons(td.registre())}
        assert frozenset({"Bornier standard", "REPARTITEUR 2"}) not in paires

    def test_doublon_present_dans_les_deux_sens(self):
        a = _modele("Un", ["A", "B"], ["X"], "M")
        b = _modele("Deux", ["A", "B"], ["X"], "M")
        paires = td.doublons(td.registre(modeles={"Un": a, "Deux": b}))
        assert {frozenset(p) for p in paires} == {frozenset({"Un", "Deux"})}


class TestRelectureTemplatesJson:

    def test_champs_optionnels_ignores_par_template_manager(self):
        # La phase 2E écrira ces champs dans templates.json ; TemplateManager doit les ignorer
        # sans erreur et rendre exactement les mêmes modèles qu'avant.
        brut = json.loads((RACINE / "templates.json").read_text(encoding="utf-8"))
        avant = TemplateManager._lire(RACINE / "templates.json")
        enrichi = {}
        for nom, td_dict in brut.items():
            copie = dict(td_dict)
            copie["famille"] = "tableau"
            copie["reconnaissance"] = {"mots_pied": ["NO PLAN"], "format_page": "A4"}
            copie["sorties"] = ["excel"]
            copie["profil_lecture"] = "claude"
            copie["ecran_attente"] = "tableau"
            copie["relecture"] = True
            enrichi[nom] = copie
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(enrichi, f, ensure_ascii=False)
            chemin = Path(f.name)
        try:
            apres = TemplateManager._lire(chemin)
        finally:
            chemin.unlink(missing_ok=True)
        assert set(apres) == set(avant)
        for nom in avant:
            assert apres[nom].to_dict() == avant[nom].to_dict(), nom
