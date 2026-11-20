"""Étape 5b — dossier de sortie : mémorisé, transmis à estimer, Lancer bloqué sans lui."""
import pytest

pytest.importorskip("PySide6")

from trios_qt import analyse, reglages  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.modele_fichiers import LanceurAnalyse  # noqa: E402
from trios_qt.page_convertir import PageConvertir  # noqa: E402


class _Type:
    def __init__(self):
        self.nom = "Bornier standard"
        self.famille = "tableau"
        self.modele = "Bornier standard"
        self.sorties = ("excel",)


def _res():
    return analyse.ResultatAnalyse(
        etat=analyse.PRET, type=_Type(), preuves=["p"],
        estimation={'cout_usd': 0.12, 'cache_connu': True, 'duree': {'texte': '~ 5 min'},
                    'pages': {'total': 141, 'scan': 141, 'vectoriel': 0}, 'pages_payantes': 141})


@pytest.fixture
def memoire(monkeypatch):
    stock = {}
    monkeypatch.setattr(reglages, "lire_dossier_sortie", lambda: stock.get("d", ""))
    monkeypatch.setattr(reglages, "ecrire_dossier_sortie",
                        lambda c: stock.__setitem__("d", c or ""))
    return stock


def _page(qtbot, estimer_fn=None):
    creer_application([])
    lanceur = LanceurAnalyse(analyser=lambda chemin, **kw: _res())
    p = PageConvertir(lanceur=lanceur, estimer_fn=estimer_fn)
    qtbot.addWidget(p)
    return p


def _ajouter(p, qtbot, chemin):
    with qtbot.waitSignal(p.lanceur.fini, timeout=2000):
        p.ajouter_sources([chemin])


class TestDossierSortie:

    def test_lancer_desactive_sans_dossier(self, qtbot, memoire):
        p = _page(qtbot)
        _ajouter(p, qtbot, r"C:\a.pdf")
        assert not p.bouton_lancer.isEnabled()   # fichier prêt mais pas de dossier

    def test_dossier_commun_active_lancer(self, qtbot, memoire):
        p = _page(qtbot)
        _ajouter(p, qtbot, r"C:\a.pdf")
        p.definir_dossier_sortie(r"C:\sortie")
        assert p.bouton_lancer.isEnabled()

    def test_dossier_memorise_entre_sessions(self, qtbot, memoire):
        p = _page(qtbot)
        p.definir_dossier_sortie(r"C:\sortie\TACHE01")
        assert memoire["d"] == r"C:\sortie\TACHE01"
        p2 = _page(qtbot)   # nouvelle page : lit le réglage mémorisé
        qtbot.addWidget(p2)
        assert p2._dossier_sortie == r"C:\sortie\TACHE01"

    def test_estimer_recoit_le_dossier_commun(self, qtbot, memoire):
        recu = {}

        def estimer_fn(chemin, type=None, profil=None, lot=False, modele=None,
                       dossier_sortie=None):
            recu['dossier'] = dossier_sortie
            return _res().estimation

        p = _page(qtbot, estimer_fn=estimer_fn)
        _ajouter(p, qtbot, r"C:\a.pdf")
        p.definir_dossier_sortie(r"C:\sortie")
        p.selectionner(p.modele.ligne(0).ident)
        assert recu['dossier'] == r"C:\sortie"

    def test_fichiers_a_lancer_liste_les_prets_avec_dossier(self, qtbot, memoire):
        p = _page(qtbot)
        _ajouter(p, qtbot, r"C:\a.pdf")
        p.definir_dossier_sortie(r"C:\sortie")
        couples = p.fichiers_a_lancer()
        assert couples == [(r"C:\a.pdf", r"C:\sortie")]

    def test_ctrl_entree_lance_si_pret(self, qtbot, memoire):
        p = _page(qtbot)
        _ajouter(p, qtbot, r"C:\a.pdf")
        p.definir_dossier_sortie(r"C:\sortie")
        with qtbot.waitSignal(p.lancer_demande, timeout=1000):
            p._tenter_lancer()

    def test_ctrl_entree_sans_effet_si_pas_pret(self, qtbot, memoire):
        p = _page(qtbot)
        _ajouter(p, qtbot, r"C:\a.pdf")   # pas de dossier → bouton désactivé
        recu = []
        p.lancer_demande.connect(lambda: recu.append(1))
        p._tenter_lancer()
        assert recu == []

    def test_surcharge_par_fichier(self, qtbot, memoire):
        recu = {}

        def estimer_fn(chemin, type=None, profil=None, lot=False, modele=None,
                       dossier_sortie=None):
            recu['dossier'] = dossier_sortie
            return _res().estimation

        p = _page(qtbot, estimer_fn=estimer_fn)
        _ajouter(p, qtbot, r"C:\a.pdf")
        p.definir_dossier_sortie(r"C:\commun")
        ident = p.modele.ligne(0).ident
        p.definir_dossier_fichier(ident, r"C:\propre")
        p.selectionner(ident)
        assert recu['dossier'] == r"C:\propre"
