"""Phase 2D étape 3 — resume_termine (module pur) : chiffres et « ce qui demande ton attention »
de l'écran Terminé, dérivés du résumé de conversion + des points. Données fabriquées."""
import resume_termine as rt


def _resume():
    return {"fichier": "doc.xlsx", "pages_total": 720, "duree_s": 4680, "cout_usd": 0.90,
            "tableaux": 711, "natures": {"scan": 709, "vectoriel": 10, "texte_cache": 1},
            "pages_servies_cache": 312}


def _pt(sorte, page, cellule="C3", raison="x", bornier="E65T"):
    return {"id": f"{cellule}-{sorte}-{page}", "etat": "a_voir", "sorte": sorte, "page": page,
            "page_imprimee": str(page), "bornier": bornier, "cellule_excel": cellule,
            "raison": raison}


class TestChiffres:

    def test_ligne_entete(self):
        assert rt.ligne_entete(_resume()) == "doc.xlsx · 720 pages · 1 h 18 min · 0,90 $"

    def test_cout_format_francais(self):
        assert rt.cout_fr(0.9) == "0,90 $"

    def test_carte_pages(self):
        grand, detail = rt.carte_pages(_resume())
        assert grand == "720"
        assert detail == "709 scans · 10 vectorielles · 1 texte caché"

    def test_carte_points(self):
        points = [_pt("qualite", 24, "C1"), _pt("qualite", 24, "C2"), _pt("illisible", 50, "D1")]
        n, detail = rt.carte_points(points)
        assert n == 3
        assert "sur 2 pages" in detail

    def test_carte_cout(self):
        grand, detail = rt.carte_cout(_resume())
        assert grand == "0,90 $"
        assert "1 h 18 min" in detail and "312 pages servies par le cache" in detail


class TestAttention:

    def test_page_degradee_et_ecarts(self):
        points = [_pt("page_degradee", 373, cellule=None, raison="scan dégradé"),
                  _pt("qualite", 24, "C1"), _pt("qualite", 25, "C2")]
        items = rt.attention(points)
        titres = [it["titre"] for it in items]
        assert any("Page 373" in t and "scan défectueux" in t for t in titres)
        assert any("2 cellules qui s'écartent" in t for t in titres)
        assert any("page(s) dégradée(s)" in t for t in titres)

    def test_aucune_page_degradee_ok(self):
        points = [_pt("qualite", 24, "C1")]
        items = rt.attention(points)
        ok = [it for it in items if it["niveau"] == "ok"]
        assert ok and "aucune page dégradée" in ok[0]["titre"]
