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

    def test_analyse_met_a_jour_la_progression(self, page):
        # En mode Tesseract, seuls les événements ANALYSE (page/total) arrivent : ils doivent
        # alimenter la progression (sinon l'écran reste figé sur « — »).
        page.demarrer_fichier("a.pdf")
        page.sur_evenement(ev.Evenement(type=ev.ANALYSE, page=12, total=55, nature='scan'))
        assert page.etiquette_progression.text() == "Lecture page 12 / 55"

    def test_phase_affiche_un_libelle_lisible_jamais_phase(self, page):
        page.demarrer_fichier("a.pdf")
        page.sur_evenement(ev.Evenement(type=ev.PHASE, etat='analyse'))
        page.sur_evenement(ev.Evenement(type=ev.PHASE, etat='lecture'))
        lignes = page.lignes_journal()
        assert "Analyse du document" in lignes
        assert "Lecture des pages" in lignes
        assert all(ligne != "phase" for ligne in lignes)

    def test_phase_inconnue_reste_lisible(self, page):
        page.demarrer_fichier("a.pdf")
        page.sur_evenement(ev.Evenement(type=ev.PHASE, etat='mystere'))
        assert page.lignes_journal() == ["Traitement en cours…"]

    def test_arreter_emet_le_signal(self, page, qtbot):
        with qtbot.waitSignal(page.arret_demande, timeout=1000):
            page.bouton_arreter.click()

    def test_arreter_donne_un_retour_immediat(self, page):
        page.demarrer_fichier("a.pdf")
        page.bouton_arreter.click()
        assert "Arrêt demandé" in page.etiquette_progression.text()
        assert not page.bouton_arreter.isEnabled()

    def test_fin_montre_les_boutons_d_ouverture(self, page):
        page.demarrer_fichier("a.pdf")
        assert not page.bouton_ouvrir_excel.isVisibleTo(page)
        page.terminer(r"C:\sortie\a.xlsx", r"C:\sortie")
        assert page.bouton_ouvrir_excel.isVisibleTo(page)
        assert page.bouton_ouvrir_dossier.isVisibleTo(page)
