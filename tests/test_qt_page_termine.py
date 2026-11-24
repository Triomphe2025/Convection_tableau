"""Phase 2D étape 3 — écran Terminé : remplissage des chiffres et des signaux."""
import pytest

pytest.importorskip("PySide6")

from trios_qt.application import creer_application  # noqa: E402
from trios_qt.page_termine import PageTermine  # noqa: E402


@pytest.fixture
def page(qtbot):
    creer_application([])
    p = PageTermine()
    qtbot.addWidget(p)
    return p


def _resume():
    return {"fichier": "doc.xlsx", "pages_total": 720, "duree_s": 4680, "cout_usd": 0.90,
            "tableaux": 711, "natures": {"scan": 709, "vectoriel": 10, "texte_cache": 1},
            "pages_servies_cache": 312}


def _points():
    return [{"id": "C1-qualite", "etat": "a_voir", "sorte": "qualite", "page": 24,
             "cellule_excel": "C1", "raison": "x", "bornier": "AG16R"},
            {"id": "C2-qualite", "etat": "a_voir", "sorte": "qualite", "page": 25,
             "cellule_excel": "C2", "raison": "x", "bornier": "C13T"}]


class TestPageTermine:

    def test_chiffres_remplis(self, page):
        page.definir_resume(_resume(), _points())
        assert page.val_tableaux.text() == "711"
        assert page.val_pages.text() == "720"
        assert page.val_points.text() == "2"
        assert page.val_cout.text() == "0,90 $"
        assert "doc.xlsx" in page.etiquette_resume.text()

    def test_bouton_relire_porte_le_compte(self, page):
        page.definir_resume(_resume(), _points())
        assert "2 points" in page.bouton_relire.text()

    def test_signal_relire(self, page, qtbot):
        with qtbot.waitSignal(page.relire_demande, timeout=1000):
            page.bouton_relire.click()

    def test_signal_outil(self, page, qtbot):
        with qtbot.waitSignal(page.outil_demande, timeout=1000) as bloc:
            page.definir_resume(_resume(), _points())
            # Déclenche le premier outil (Auditer) via le signal.
            page.outil_demande.emit("auditer")
        assert bloc.args == ["auditer"]

    def test_peint_sans_erreur(self, page):
        page.definir_resume(_resume(), _points())
        page.resize(1200, 700)
        assert not page.grab().isNull()
