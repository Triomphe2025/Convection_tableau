"""Étape 5c — câblage fenêtre : « Lancer » ouvre l'écran Traitement et démarre le contrôleur."""
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


class _FauxService:
    def __init__(self, chemin, dossier, on_ev):
        self.resultat = chemin + ".xlsx"
        self.arrete = False
        self._on_ev = on_ev

    def demarrer(self):
        self._on_ev(ev.Evenement(type=ev.PAGE_LUE, rang=1, total=1))
        self._on_ev(ev.Evenement(type=ev.FIN))

    def arreter(self):
        self.arrete = True


def _resultat():
    return analyse.ResultatAnalyse(
        etat=analyse.PRET, type=_Type(), preuves=["p"],
        estimation={'cout_usd': 0.1, 'cache_connu': True, 'duree': {'texte': '~ 5 min'},
                    'pages': {'total': 2, 'scan': 2, 'vectoriel': 0}, 'pages_payantes': 2})


def test_lancer_ouvre_traitement_et_demarre(qtbot):
    app = creer_application([])
    jetons = theme.appliquer_theme(app)
    animations.definir_reduction(True)
    try:
        f = FenetrePrincipale(jetons=jetons,
                              fabrique_service=lambda ch, d, cb: _FauxService(ch, d, cb))
        qtbot.addWidget(f)
        page = f.page_convertir
        ident = page.modele.ajouter(r"C:\a.pdf")
        page.modele.appliquer_resultat(ident, _resultat())
        page.definir_dossier_sortie(r"C:\sortie")
        page.lancer_demande.emit()
        assert f.ecran_courant() == "traitement"
        assert "a.pdf" in f.page_traitement.etiquette_fichier.text()
        # Le faux service a émis FIN : les boutons d'ouverture sont montrés.
        assert f.page_traitement.bouton_ouvrir_excel.isVisibleTo(f.page_traitement)
    finally:
        animations.reinitialiser()
