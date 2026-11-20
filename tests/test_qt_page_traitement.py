"""Étape 5c — écran Traitement minimal : progression, 5 dernières lignes, Arrêter, fin."""
import pytest

pytest.importorskip("PySide6")

import evenements as ev  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.page_traitement import PageTraitement  # noqa: E402


@pytest.fixture
def page(qtbot):
    creer_application([])
    p = PageTraitement()
    qtbot.addWidget(p)
    return p


class TestPageTraitement:

    def test_demarrer_fichier_affiche_le_nom(self, page):
        page.demarrer_fichier("223111PE082.pdf")
        assert "223111PE082.pdf" in page.etiquette_fichier.text()

    def test_page_lue_met_a_jour_la_progression(self, page):
        page.demarrer_fichier("a.pdf")
        page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, rang=3, total=20))
        assert "3" in page.etiquette_progression.text()
        assert "20" in page.etiquette_progression.text()

    def test_journal_garde_les_cinq_dernieres(self, page):
        page.demarrer_fichier("a.pdf")
        for i in range(1, 8):
            page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, rang=i, total=20))
        lignes = page.lignes_journal()
        assert len(lignes) == 5
        assert "7" in lignes[-1]        # la plus récente
        assert all("1 / 20" not in ligne for ligne in lignes)  # la 1re a disparu

    def test_arreter_emet_le_signal(self, page, qtbot):
        with qtbot.waitSignal(page.arret_demande, timeout=1000):
            page.bouton_arreter.click()

    def test_fin_montre_les_boutons_d_ouverture(self, page):
        page.demarrer_fichier("a.pdf")
        assert not page.bouton_ouvrir_excel.isVisibleTo(page)
        page.terminer(r"C:\sortie\a.xlsx", r"C:\sortie")
        assert page.bouton_ouvrir_excel.isVisibleTo(page)
        assert page.bouton_ouvrir_dossier.isVisibleTo(page)
