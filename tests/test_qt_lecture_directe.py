"""Étape 2C-6 — « Lecture en direct » : image de la page, bande rose, zones par ligne,
loupe, tableau extrait (9 dernières lignes), puces de valeurs.

On teste la logique pilotée par les événements (image chargée, zones placées et colorées,
tableau rempli depuis cellules, puces) et le cycle de la bande (active en lecture, coupée si
l'écran est caché ou les animations réduites). Le rendu fin est visuel (règle 07 : capture).
"""
import pytest

pytest.importorskip("PySide6")

import evenements as ev  # noqa: E402
from trios_qt import animations, theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.lecture_directe import LectureDirecte  # noqa: E402


@pytest.fixture
def vue(qtbot):
    creer_application([])
    animations.definir_reduction(False)
    v = LectureDirecte()
    qtbot.addWidget(v)
    yield v
    animations.reinitialiser()


@pytest.fixture(scope="module")
def jetons():
    return theme.charger_jetons()


@pytest.fixture(scope="module")
def image_png(tmp_path_factory):
    from PIL import Image
    chemin = tmp_path_factory.mktemp("img") / "page_001.png"
    Image.new("RGB", (400, 560), (250, 250, 250)).save(chemin)
    return str(chemin)


_ZONES = [
    {"ligne": 0, "boite": (0.1, 0.10, 0.9, 0.16)},
    {"ligne": 1, "boite": (0.1, 0.18, 0.9, 0.24)},
    {"ligne": 2, "boite": (0.1, 0.26, 0.9, 0.32)},
]
_CELLULES = [["01", "ROUGE", "TC"], ["02", "BLANC", "TD"], ["03", "BLEU", "TE"]]


class TestImage:

    def test_charger_image_existante(self, vue, image_png):
        assert vue.charger_image(image_png) is True
        assert vue.a_image() is True

    def test_charger_image_absente(self, vue):
        assert vue.charger_image("n_existe_pas.png") is False
        assert vue.a_image() is False


class TestZones:

    def test_couleurs_par_etat(self, vue, jetons):
        c = jetons["couleurs"]
        assert vue.couleur_zone(LectureDirecte.ETAT_VU).name().lower() == c["texte_natif"].lower()
        assert vue.couleur_zone(LectureDirecte.ETAT_LU).name().lower() == c["succes"].lower()
        assert vue.couleur_zone(LectureDirecte.ETAT_COURANTE).name().lower() == \
            c["rose_trios"].lower()
        assert vue.couleur_zone(LectureDirecte.ETAT_DOUTE).name().lower() == c["a_relire"].lower()

    def test_definir_zones_cree_les_rectangles(self, vue, image_png):
        vue.charger_image(image_png)
        vue.definir_zones(_ZONES)
        assert vue.nombre_zones() == 3

    def test_derniere_zone_est_courante(self, vue, image_png):
        vue.charger_image(image_png)
        vue.definir_zones(_ZONES)
        assert vue.etat_zone(2) == LectureDirecte.ETAT_COURANTE
        assert vue.etat_zone(0) == LectureDirecte.ETAT_LU

    def test_zones_vides_sans_erreur(self, vue, image_png):
        vue.charger_image(image_png)
        vue.definir_zones(None)
        assert vue.nombre_zones() == 0


class TestTable:

    def test_remplir_table(self, vue):
        vue.remplir_table(_CELLULES)
        assert vue.lignes_table() == 3

    def test_table_garde_les_neuf_dernieres(self, vue):
        cellules = [[str(i)] for i in range(15)]
        vue.remplir_table(cellules)
        assert vue.lignes_table() == 9
        assert vue.valeur_table(8, 0) == "14"   # la plus récente en bas

    def test_remplir_table_vide(self, vue):
        vue.remplir_table(None)
        assert vue.lignes_table() == 0


class TestPuces:

    def test_puces_de_la_ligne(self, vue):
        vue.definir_puces(["01", "ROUGE", "TC"])
        texte = vue.puces_texte()
        assert "01" in texte and "ROUGE" in texte and "TC" in texte


class TestBande:

    def test_bande_active_en_lecture(self, vue):
        vue.definir_bande_active(True)
        assert vue.bande_active() is True

    def test_bande_arretee(self, vue):
        vue.definir_bande_active(True)
        vue.definir_bande_active(False)
        assert vue.bande_active() is False

    def test_bande_coupee_si_cachee(self, vue):
        vue.show()
        vue.definir_bande_active(True)
        assert vue.bande_active() is True
        vue.hide()
        assert vue.bande_active() is False

    def test_bande_jamais_si_reduit(self, vue):
        animations.definir_reduction(True)
        vue.definir_bande_active(True)
        assert vue.bande_active() is False


class TestEvenements:

    def test_page_debut_lance_la_bande(self, vue):
        vue.sur_evenement(ev.Evenement(type=ev.PAGE_DEBUT, page=1, rang=1, total=3))
        assert vue.bande_active() is True

    def test_page_debut_charge_l_image(self, vue, image_png):
        # Comportement A : l'image est chargée dès PAGE_DEBUT (page en cours de lecture).
        vue.sur_evenement(ev.Evenement(type=ev.PAGE_DEBUT, page=1, rang=1, total=3,
                                       image=image_png))
        assert vue.a_image() is True
        assert vue.bande_active() is True

    def test_page_lue_charge_tout_et_arrete_la_bande(self, vue, image_png):
        animations.definir_reduction(True)   # révélation instantanée pour vérifier l'état final
        vue.sur_evenement(ev.Evenement(type=ev.PAGE_DEBUT, page=1, rang=1, total=3))
        vue.sur_evenement(ev.Evenement(
            type=ev.PAGE_LUE, page=1, rang=1, total=3, lignes=3,
            image=image_png, zones=_ZONES, cellules=_CELLULES))
        assert vue.a_image() is True
        assert vue.nombre_zones() == 3
        assert vue.lignes_table() == 3
        assert vue.bande_active() is False

    def test_page_lue_sans_zones_remplit_la_table(self, vue, image_png):
        # Mode Tesseract : zones None, mais le tableau extrait s'anime quand même.
        animations.definir_reduction(True)
        vue.sur_evenement(ev.Evenement(
            type=ev.PAGE_LUE, page=1, rang=1, total=1, lignes=2,
            image=image_png, zones=None, cellules=[["01", "A"], ["02", "B"]]))
        assert vue.nombre_zones() == 0
        assert vue.lignes_table() == 2


class TestRevelation:

    def test_revelation_pas_a_pas(self, vue, image_png):
        # Comportement B : après N pas, N lignes dans le tableau et la loupe sur la ligne N.
        vue.charger_image(image_png)
        vue.sur_evenement(ev.Evenement(
            type=ev.PAGE_LUE, page=1, rang=1, total=3, lignes=3,
            image=image_png, zones=_ZONES, cellules=_CELLULES))
        assert vue.lignes_table() == 0        # rien révélé tout de suite (animations non réduites)
        vue._pas_reveler()
        assert vue.lignes_table() == 1
        assert vue.ligne_loupe() == 0
        vue._pas_reveler()
        assert vue.lignes_table() == 2
        assert vue.ligne_loupe() == 1
        vue._pas_reveler()
        assert vue.lignes_table() == 3
        assert vue.ligne_loupe() == 2
        assert vue.nombre_zones() == 3        # la dernière zone est courante

    def test_revelation_instantanee_si_reduit(self, vue, image_png):
        animations.definir_reduction(True)
        vue.sur_evenement(ev.Evenement(
            type=ev.PAGE_LUE, page=1, rang=1, total=3, lignes=3,
            image=image_png, zones=_ZONES, cellules=_CELLULES))
        assert vue.lignes_table() == 3        # tout révélé d'un coup

    def test_cadence_bornee(self, vue):
        assert vue.cadence_ms(3) == LectureDirecte.REVEAL_MS      # peu de lignes : ~120 ms
        assert vue.cadence_ms(100) < LectureDirecte.REVEAL_MS     # beaucoup : cadence réduite

    def test_terminer_reveler_finit_d_un_coup(self, vue, image_png):
        # Retouche 2 : à FIN, la révélation en cours se termine d'un coup (plus de « 6 / 9 »).
        vue.charger_image(image_png)
        vue.sur_evenement(ev.Evenement(
            type=ev.PAGE_LUE, page=1, rang=1, total=3, lignes=3,
            image=image_png, zones=_ZONES, cellules=_CELLULES))
        vue._pas_reveler()
        assert vue.lignes_table() == 1          # révélation partielle en cours
        vue.terminer_reveler()
        assert vue.lignes_table() == 3          # tout révélé
        assert "3 / 3" in vue.etat_lecture.text()


class TestRendu:

    def test_peint_sans_erreur(self, vue, image_png):
        vue.resize(400, 500)
        vue.sur_evenement(ev.Evenement(
            type=ev.PAGE_LUE, page=1, rang=1, total=1, lignes=3,
            image=image_png, zones=_ZONES, cellules=_CELLULES))
        assert not vue.grab().isNull()
