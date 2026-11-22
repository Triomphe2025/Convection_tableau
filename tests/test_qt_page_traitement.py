"""Étape 2C-7 — écran Traitement assemblé : rail, lecture en direct, anneau, mosaïque, journal,
Pause / Reprendre / Arrêter, fin. Remplace l'écran provisoire de la 2B.

Pilote l'écran par des événements et vérifie l'état des composants à plusieurs instants et à la
fin. Réutilise l'API publique attendue par lancement.py (demarrer_fichier, sur_evenement,
terminer, arret_demande, lignes_journal).
"""
import pytest

pytest.importorskip("PySide6")

import evenements as ev  # noqa: E402
from trios_qt import animations  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.mosaique import Mosaique  # noqa: E402
from trios_qt.page_traitement import PageTraitement  # noqa: E402
from trios_qt.rail_etapes import RailEtapes  # noqa: E402


@pytest.fixture
def page(qtbot):
    creer_application([])
    animations.definir_reduction(False)
    p = PageTraitement()
    qtbot.addWidget(p)
    p.demarrer_fichier("223111PE082.pdf")
    yield p
    animations.reinitialiser()


class TestBase:

    def test_demarrer_fichier_affiche_le_nom(self, page):
        assert "223111PE082.pdf" in page.etiquette_fichier.text()

    def test_phase_met_a_jour_le_rail(self, page):
        page.sur_evenement(ev.Evenement(type=ev.PHASE, etat='lecture'))
        assert page.rail.phase_courante() == 'lecture'
        assert page.rail.etat_etape('analyse') == 'fait'

    def test_journal_une_ligne_visible_et_historique(self, page):
        page.sur_evenement(ev.Evenement(type=ev.PHASE, etat='analyse'))
        page.sur_evenement(ev.Evenement(type=ev.PHASE, etat='lecture'))
        assert page.journal_resume.text() == "Lecture des pages"   # la dernière
        assert "Analyse du document" in page.lignes_journal()


class TestProgression:

    def test_anneau_suit_rang_sur_total(self, page):
        page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=3, rang=3, total=10, lignes=5))
        assert page.anneau.valeur() == pytest.approx(0.3)
        assert "3 / 10" in page.anneau.sous_libelle()

    def test_mosaique_lecture_puis_lue(self, page):
        page.sur_evenement(ev.Evenement(type=ev.PAGE_DEBUT, page=1, rang=1, total=4))
        assert page.mosaique.etat(0) == Mosaique.LECTURE
        page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=1, rang=1, total=4,
                                        lignes=5, cout={'input_tokens': 10, 'output_tokens': 2}))
        assert page.mosaique.etat(0) == Mosaique.LUE

    def test_page_native_en_bleu(self, page):
        page.sur_evenement(ev.Evenement(type=ev.ANALYSE, page=1, total=3, nature='vectoriel'))
        page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=1, rang=1, total=3, lignes=4))
        assert page.mosaique.etat(0) == Mosaique.NATIF

    def test_alerte_marque_a_relire(self, page):
        page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=7, rang=1, total=3, lignes=4))
        page.sur_evenement(ev.Evenement(type=ev.PAGE_ALERTE, page=7, page_imprimee='7',
                                        alertes=['scan dégradé']))
        assert page.mosaique.etat(0) == Mosaique.A_RELIRE
        assert "1" in page.etiquette_stats.text()


class TestLectureDirecte:

    def test_page_lue_charge_l_image(self, page, tmp_path):
        from PIL import Image
        chemin = tmp_path / "page_001.png"
        Image.new("RGB", (300, 400), (240, 240, 240)).save(chemin)
        page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=1, rang=1, total=1, lignes=2,
                                        image=str(chemin), cellules=[["01", "A"]]))
        assert page.lecture.a_image() is True
        assert page.lecture.lignes_table() == 1


class TestPauseArret:

    def test_pause_puis_reprendre(self, page, qtbot):
        with qtbot.waitSignal(page.pause_demande, timeout=1000):
            page.bouton_pause.click()
        assert page.en_pause() is True
        assert page.bouton_pause.text() == "Reprendre"
        with qtbot.waitSignal(page.reprendre_demande, timeout=1000):
            page.bouton_pause.click()
        assert page.en_pause() is False
        assert page.bouton_pause.text() == "Pause"

    def test_arreter_retour_immediat(self, page, qtbot):
        with qtbot.waitSignal(page.arret_demande, timeout=1000):
            page.bouton_arreter.click()
        assert "Arrêt demandé" in page.journal_resume.text()
        assert not page.bouton_arreter.isEnabled()


class TestFin:

    def test_terminer_anneau_vert_et_resume(self, page):
        page.sur_evenement(ev.Evenement(type=ev.FIN, total=3, etat='terminee'))
        page.terminer(r"C:\sortie\a.xlsx", r"C:\sortie")
        assert page.anneau.est_termine() is True
        assert page.rail.etat_etape('excel') == 'fait'
        assert page.bouton_resume.isVisibleTo(page)
        assert page.bouton_ouvrir_excel.isVisibleTo(page)
        assert not page.bouton_arreter.isVisibleTo(page)

    def test_voir_resume_emet_le_signal(self, page, qtbot):
        page.terminer(r"C:\s\a.xlsx", r"C:\s")
        with qtbot.waitSignal(page.voir_resume, timeout=1000):
            page.bouton_resume.click()

    def test_phases_restent_lisibles(self, page):
        page.sur_evenement(ev.Evenement(type=ev.PHASE, etat='excel'))
        assert "excel" not in page.lignes_journal()
        assert "Génération du classeur" in page.lignes_journal()


class TestCompat:

    def test_fin_tout_le_rail_fait(self, page):
        page.sur_evenement(ev.Evenement(type=ev.FIN, total=3, etat='terminee'))
        assert all(page.rail.etat_etape(c) == 'fait' for c in RailEtapes.CLES)
