"""Étape 2C-10 — câblage fenêtre : routage lot/tableau par fichier (mode économique, pas
Config.CLAUDE_MODE_LOT), et relais Pause / Reprendre / Arrêter vers le service.

Faux service qui enregistre pause/reprendre/arrêter et ne se termine pas seul (la conversion
reste en cours), pour vérifier le relais depuis l'écran et la mini-fenêtre.
"""
import pytest

pytest.importorskip("PySide6")

import evenements as ev  # noqa: E402
from trios_qt import analyse, animations, theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.fenetre import FenetrePrincipale  # noqa: E402


class _Type:
    nom = "Bornier standard"
    famille = "tableau"
    modele = "Bornier standard"
    sorties = ("excel",)


class _FauxServiceVivant:
    def __init__(self, chemin, dossier, on_ev):
        self.resultat = chemin + ".xlsx"
        self.pauses = 0
        self.reprises = 0
        self.arrets = 0
        self._on_ev = on_ev

    def demarrer(self):
        # Pas de FIN émis : la conversion reste « en cours » pour tester pause/arrêt.
        self._on_ev(ev.Evenement(type=ev.PAGE_LUE, rang=1, total=3))

    def pause(self):
        self.pauses += 1

    def reprendre(self):
        self.reprises += 1

    def arreter(self):
        self.arrets += 1


def _resultat():
    return analyse.ResultatAnalyse(
        etat=analyse.PRET, type=_Type(), preuves=["p"],
        estimation={'cout_usd': 0.1, 'cache_connu': True, 'duree': {'texte': '~ 5 min'},
                    'pages': {'total': 3, 'scan': 3, 'vectoriel': 0}, 'pages_payantes': 3})


@pytest.fixture
def fenetre(qtbot):
    app = creer_application([])
    jetons = theme.appliquer_theme(app)
    animations.definir_reduction(True)
    services = []

    def fabrique(ch, d, cb):
        s = _FauxServiceVivant(ch, d, cb)
        services.append(s)
        return s

    f = FenetrePrincipale(jetons=jetons, fabrique_service=fabrique)
    qtbot.addWidget(f)
    f._services = services
    yield f
    animations.reinitialiser()


def _preparer(f, chemin=r"C:\a.pdf"):
    page = f.page_convertir
    ident = page.modele.ajouter(chemin)
    page.modele.appliquer_resultat(ident, _resultat())
    page.definir_dossier_sortie(r"C:\sortie")


class TestRoutage:

    def test_fichier_tableau_va_a_traitement(self, fenetre):
        _preparer(fenetre)
        fenetre.page_convertir.lancer_demande.emit()
        assert fenetre.ecran_courant() == "traitement"

    def test_fichier_economique_va_a_l_attente_lot(self, fenetre, monkeypatch):
        _preparer(fenetre)
        monkeypatch.setattr(fenetre.page_convertir, "est_differe_chemin", lambda ch: True)
        fenetre.page_convertir.lancer_demande.emit()
        assert fenetre.ecran_courant() == "attente_lot"


class TestRelais:

    def test_pause_reprendre_depuis_l_ecran(self, fenetre):
        _preparer(fenetre)
        fenetre.page_convertir.lancer_demande.emit()
        service = fenetre._services[-1]
        fenetre.page_traitement.pause_demande.emit()
        assert service.pauses == 1
        fenetre.page_traitement.reprendre_demande.emit()
        assert service.reprises == 1

    def test_arret_depuis_l_ecran(self, fenetre):
        _preparer(fenetre)
        fenetre.page_convertir.lancer_demande.emit()
        service = fenetre._services[-1]
        fenetre.page_traitement.arret_demande.emit()
        assert service.arrets == 1

    def test_pause_depuis_la_mini_fenetre(self, fenetre):
        _preparer(fenetre)
        fenetre.page_convertir.lancer_demande.emit()
        service = fenetre._services[-1]
        fenetre.mini.pause_demande.emit()
        assert service.pauses == 1


class TestMini:

    def test_agrandir_cache_la_mini(self, fenetre):
        fenetre.mini.show()
        fenetre.mini.agrandir_demande.emit()
        assert not fenetre.mini.isVisible()
