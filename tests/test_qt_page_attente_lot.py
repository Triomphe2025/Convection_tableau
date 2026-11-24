"""Étape 2C-8 — écran d'attente du mode lot : une piste par lot, anneau des pages lues, cartes
« Tu peux fermer » / « Pendant ce temps », mosaïque par état de lot. Pas de Pause.

Piloté par les événements LOT_CREE / LOT_ETAT / LOT_RECUPERE et PAGE_LUE. On vérifie l'état des
widgets à plusieurs instants. Un faux service rejoue une suite d'événements (JSON dans tests/).
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

import evenements as ev  # noqa: E402
from trios_qt import animations, theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.mosaique import Mosaique  # noqa: E402
from trios_qt.page_attente_lot import PageAttenteLot  # noqa: E402

SUITE = Path(__file__).parent / "fixtures" / "evenements_lot.json"


@pytest.fixture
def page(qtbot):
    creer_application([])
    animations.definir_reduction(False)
    p = PageAttenteLot()
    qtbot.addWidget(p)
    p.demarrer_fichier("223111PE203.pdf")
    yield p
    animations.reinitialiser()


@pytest.fixture(scope="module")
def jetons():
    return theme.charger_jetons()


def _ev(d):
    return ev.Evenement(**d)


class TestPistes:

    def test_lot_cree_une_piste(self, page):
        page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot="batch_1",
                                        compteurs={"requetes": 30, "taille_mo": 12.5}))
        assert page.nombre_pistes() == 1
        assert "12.5" in page.lot_texte("batch_1")

    def test_lot_etat_avance(self, page):
        page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot="batch_1",
                                        compteurs={"requetes": 30, "taille_mo": 12.5}))
        page.sur_evenement(ev.Evenement(type=ev.LOT_ETAT, lot="batch_1", compteurs={
            "lues": 12, "en_attente": 18, "a_reprendre": 0, "total": 30, "delai": 30}))
        assert page.anneau.valeur() == pytest.approx(12 / 30)
        assert "12" in page.lot_texte("batch_1")

    def test_lot_recupere_marque_rapatrie(self, page):
        page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot="batch_1",
                                        compteurs={"requetes": 30, "taille_mo": 12.5}))
        page.sur_evenement(ev.Evenement(type=ev.LOT_RECUPERE, lot="batch_1",
                                        compteurs={"lues": 30, "total": 30}))
        assert page.phase_piste("batch_1") == PageAttenteLot.RAPATRIE


class TestDiagramme:

    def test_diagramme_reflete_les_lots(self, page):
        page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot="b1",
                                        compteurs={"requetes": 24, "taille_mo": 46.0}))
        page.sur_evenement(ev.Evenement(type=ev.LOT_ETAT, lot="b1", compteurs={
            "lues": 12, "en_attente": 12, "a_reprendre": 0, "total": 24, "delai": 30}))
        assert page.diagramme.nombre_lots() == 1
        assert page.diagramme.fraction_lot(0) == pytest.approx(0.5)

    def test_couleur_rapatrie_vs_en_cours(self, page, jetons):
        c = jetons["couleurs"]
        page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot="b1",
                                        compteurs={"requetes": 24, "taille_mo": 46.0}))
        assert page.diagramme.couleur_lot(0).name().lower() == c["lot_en_cours"].lower()
        page.sur_evenement(ev.Evenement(type=ev.LOT_RECUPERE, lot="b1",
                                        compteurs={"lues": 24, "total": 24}))
        assert page.diagramme.couleur_lot(0).name().lower() == c["tuile_lue"].lower()


class TestMosaique:

    def test_page_lue_rapatriee_en_vert(self, page):
        page.sur_evenement(ev.Evenement(type=ev.LOT_ETAT, lot="b", compteurs={
            "lues": 0, "en_attente": 2, "a_reprendre": 0, "total": 2, "delai": 30}))
        page.sur_evenement(ev.Evenement(type=ev.PAGE_LUE, page=1, rang=1, total=2, lignes=3))
        assert page.mosaique.etat(0) == Mosaique.LUE

    def test_mosaique_remplie_des_analyse(self, page):
        # Retouche 1 : cases dès ANALYSE / LOT_CREE (plus de mosaïque vide pendant l'attente).
        natures = [(1, 'vectoriel'), (2, 'scan'), (3, 'scan'), (4, 'scan'), (5, 'vectoriel')]
        for p, nat in natures:
            page.sur_evenement(ev.Evenement(type=ev.ANALYSE, page=p, total=5, nature=nat))
        page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot="b1",
                                        compteurs={"requetes": 3, "taille_mo": 5.0}))
        assert page.mosaique.nombre_pages() == 5
        assert page.mosaique.etat(0) == Mosaique.NATIF       # page 1 native → texte natif
        assert page.mosaique.etat(1) == Mosaique.DANS_LOT    # page 2 scan → dans un lot
        page.sur_evenement(ev.Evenement(type=ev.LOT_ETAT, lot="b1",
                                        compteurs={"lues": 1, "total": 3, "delai": 30}))
        assert Mosaique.LUE_NON_RAPATRIEE in [page.mosaique.etat(i) for i in range(5)]
        page.sur_evenement(ev.Evenement(type=ev.LOT_RECUPERE, lot="b1",
                                        compteurs={"lues": 3, "total": 3}))
        assert Mosaique.LUE in [page.mosaique.etat(i) for i in range(5)]


class TestMosaiqueScenario:
    """Scénario de la maquette : 141 pages, 25 vectorielles, 5 lots, lot 0 récupéré."""

    def _scenario(self, page):
        total = 141
        vect = set(range(1, 26))   # 25 pages vectorielles (texte natif)
        for p in range(1, total + 1):
            nat = 'vectoriel' if p in vect else 'scan'
            page.sur_evenement(ev.Evenement(type=ev.ANALYSE, page=p, total=total, nature=nat))
        reqs = [24, 24, 23, 23, 22]   # 116 pages scannées en 5 lots
        for i, r in enumerate(reqs):
            page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot=f"b{i}",
                                            compteurs={"requetes": r, "taille_mo": 40.0}))
        return reqs

    def test_pages_vectorielles_bleues(self, page):
        # Point 1 : exactement 25 cases « natif » après ANALYSE (bleu, texte natif).
        self._scenario(page)
        natif = sum(1 for i in range(141) if page.mosaique.etat(i) == Mosaique.NATIF)
        assert natif == 25

    def test_etats_par_plage_de_lot(self, page, jetons):
        # Point 2 : états par plage de pages de chaque lot ; lavande (page_scannee) pour les lues.
        reqs = self._scenario(page)
        page.sur_evenement(ev.Evenement(type=ev.LOT_RECUPERE, lot="b0",
                                        compteurs={"lues": 24, "total": 24}))
        for i, lus in ((1, 14), (2, 8), (3, 4), (4, 2)):
            page.sur_evenement(ev.Evenement(type=ev.LOT_ETAT, lot=f"b{i}", compteurs={
                "lues": lus, "total": reqs[i], "delai": 30}))
        etats = [page.mosaique.etat(i) for i in range(141)]
        assert etats.count(Mosaique.NATIF) == 25            # restent bleues
        assert etats.count(Mosaique.LUE) == 24              # lot 0 rapatrié → vert
        assert etats.count(Mosaique.LUE_NON_RAPATRIEE) == 14 + 8 + 4 + 2   # lavande
        attendu = jetons["couleurs"]["page_scannee"].lower()
        assert page.mosaique.couleur_etat(Mosaique.LUE_NON_RAPATRIEE).name().lower() == attendu


class TestPastilles:

    def test_position_par_phase_pas_par_fraction(self, page):
        # Retouche 2 : un lot chez Anthropic à 2/22 lues est côté Anthropic (droite), pas à gauche.
        page.sur_evenement(ev.Evenement(type=ev.LOT_CREE, lot="b1",
                                        compteurs={"requetes": 22, "taille_mo": 5.0}))
        page.sur_evenement(ev.Evenement(type=ev.LOT_ETAT, lot="b1",
                                        compteurs={"lues": 2, "total": 22, "delai": 30}))
        assert page.diagramme.position_fraction(0) >= 0.5
        page.sur_evenement(ev.Evenement(type=ev.LOT_RECUPERE, lot="b1",
                                        compteurs={"lues": 22, "total": 22}))
        assert page.diagramme.position_fraction(0) <= 0.1   # rapatrié : revenu à gauche


class TestSansPause:

    def test_aucun_bouton_pause(self, page):
        assert not hasattr(page, "bouton_pause")


class TestCartes:

    def test_carte_fermer_et_prevenir(self, page):
        assert page.carte_fermer is not None
        assert page.interrupteur_prevenir is not None

    def test_carte_pendant_ce_temps(self, page):
        assert page.carte_pendant is not None


class TestVerification:

    def test_prochaine_verification_affichee(self, page):
        page.sur_evenement(ev.Evenement(type=ev.LOT_ETAT, lot="b", compteurs={
            "lues": 1, "en_attente": 1, "a_reprendre": 0, "total": 2, "delai": 30}))
        assert "s" in page.etiquette_verification.text().lower()


class TestRejeuFixture:

    def test_rejeu_suite_enregistree(self, page):
        suite = json.loads(SUITE.read_text(encoding="utf-8"))
        for d in suite:
            page.sur_evenement(_ev(d))
        # À la fin de la suite : les deux lots rapatriés, anneau plein.
        assert page.nombre_pistes() == 2
        assert page.anneau.valeur() == pytest.approx(1.0)


class TestFin:

    def test_terminer_montre_les_ouvertures(self, page):
        page.terminer(r"C:\s\a.xlsx", r"C:\s")
        assert page.bouton_ouvrir_excel.isVisibleTo(page)
