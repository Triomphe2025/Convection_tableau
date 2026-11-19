"""Étape 3 — page Convertir : dépôt → file synchronisée, panneau des types, lien « Gérer »."""
import pytest

pytest.importorskip("PySide6")

from trios_qt import analyse  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.modele_fichiers import LanceurAnalyse  # noqa: E402
from trios_qt.page_convertir import PageConvertir  # noqa: E402
from trios_qt.theme import charger_jetons  # noqa: E402

COULEURS = charger_jetons()['couleurs']


class _Type:
    def __init__(self, nom="Bornier standard", famille="tableau", modele="Bornier standard"):
        self.nom = nom
        self.famille = famille
        self.modele = modele


def _registre_bidon():
    from types_documents import TYPE_EXCEL, TYPE_JOURNAL, TYPE_PLAN
    return {
        "Bornier standard": _Type(),
        "Plan": TYPE_PLAN,
        "Excel": TYPE_EXCEL,
        "Journal": TYPE_JOURNAL,
    }


@pytest.fixture
def page(qtbot):
    creer_application([])
    lanceur = LanceurAnalyse(analyser=lambda chemin, **kw: analyse.ResultatAnalyse(
        etat=analyse.PRET, type=_Type(),
        estimation={'cout_usd': 1.5, 'cache_connu': True, 'duree': {'texte': '~ 2 min'}}))
    p = PageConvertir(registre_fn=_registre_bidon, lanceur=lanceur)
    qtbot.addWidget(p)
    return p


class TestPageConvertir:

    def test_depot_ajoute_une_ligne_en_analyse_puis_la_complete(self, page, qtbot):
        with qtbot.waitSignal(page.lanceur.fini, timeout=2000):
            page.ajouter_sources([r"C:\doc_a_traiter\PE203.pdf"])
        assert page.modele.rowCount() == 1
        assert page.modele.ligne(0).resultat.etat == analyse.PRET
        widget = page.widget_ligne(0)
        assert "PE203.pdf" in widget.nom_affiche()

    def test_ligne_affiche_l_estimation(self, page, qtbot):
        with qtbot.waitSignal(page.lanceur.fini, timeout=2000):
            page.ajouter_sources([r"C:\doc.pdf"])
        assert "$" in page.widget_ligne(0).texte_estimation_affiche()

    def test_panneau_liste_les_types_du_registre(self, page):
        noms = page.noms_types()
        for attendu in ("Bornier standard", "Plan", "Excel", "Journal"):
            assert attendu in noms

    def test_gerer_emet_le_signal_de_navigation(self, page, qtbot):
        with qtbot.waitSignal(page.gerer_types, timeout=1000):
            page.bouton_gerer.click()

    def test_retirer_enleve_la_ligne(self, page, qtbot):
        with qtbot.waitSignal(page.lanceur.fini, timeout=2000):
            page.ajouter_sources([r"C:\doc.pdf"])
        page.widget_ligne(0).bouton_retirer.click()
        assert page.modele.rowCount() == 0

    def test_fenetre_monte_la_page_convertir(self, qtbot):
        from trios_qt import animations, theme
        from trios_qt.fenetre import FenetrePrincipale
        creer_application([])
        theme.appliquer_theme(creer_application([]))
        animations.definir_reduction(True)
        f = FenetrePrincipale()
        qtbot.addWidget(f)
        try:
            assert isinstance(f.page_convertir, PageConvertir)
            assert f.pages["convertir"].findChildren(PageConvertir)
        finally:
            animations.reinitialiser()

    def test_a_preciser_est_colore_en_orange(self, qtbot):
        creer_application([])
        lanceur = LanceurAnalyse(analyser=lambda chemin, **kw: analyse.ResultatAnalyse(
            etat=analyse.A_PRECISER, type=_Type("Répartiteur"),
            estimation={'cout_usd': 1.0, 'cache_connu': False, 'duree': {'texte': '~ 1 min'}}))
        p = PageConvertir(registre_fn=_registre_bidon, lanceur=lanceur)
        qtbot.addWidget(p)
        with qtbot.waitSignal(p.lanceur.fini, timeout=2000):
            p.ajouter_sources([r"C:\mystere.pdf"])
        assert p.widget_ligne(0).couleur_type == COULEURS['a_relire']
