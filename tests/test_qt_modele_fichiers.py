"""Étape 1 — file de fichiers (QAbstractListModel) + lanceur d'analyse dans un fil à part."""
import threading

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from trios_qt import analyse  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.modele_fichiers import LanceurAnalyse, ModeleFichiers  # noqa: E402


@pytest.fixture
def modele(qtbot):
    creer_application([])
    return ModeleFichiers()


def _resultat(etat):
    return analyse.ResultatAnalyse(etat=etat)


class TestModeleFichiers:

    def test_ajouter_affiche_le_fichier_tout_de_suite_en_analyse(self, modele):
        ident = modele.ajouter(r"C:\doc_a_traiter\PE203.pdf")
        assert modele.rowCount() == 1
        ligne = modele.ligne(0)
        assert ligne.ident == ident
        assert ligne.nom == "PE203.pdf"
        assert ligne.resultat.etat == analyse.ANALYSE
        assert modele.data(modele.index(0), Qt.DisplayRole) == "PE203.pdf"

    def test_appliquer_resultat_complete_la_ligne(self, modele, qtbot):
        ident = modele.ajouter(r"C:\doc_a_traiter\PE203.pdf")
        with qtbot.waitSignal(modele.dataChanged, timeout=1000):
            modele.appliquer_resultat(ident, _resultat(analyse.PRET))
        assert modele.ligne(0).resultat.etat == analyse.PRET

    def test_retirer_enleve_la_ligne(self, modele):
        modele.ajouter(r"C:\a.pdf")
        ident_b = modele.ajouter(r"C:\b.pdf")
        modele.retirer(0)
        assert modele.rowCount() == 1
        assert modele.ligne(0).ident == ident_b

    def test_deplacer_reordonne(self, modele):
        a = modele.ajouter(r"C:\a.pdf")
        b = modele.ajouter(r"C:\b.pdf")
        c = modele.ajouter(r"C:\c.pdf")
        modele.deplacer(0, 2)
        assert [modele.ligne(i).ident for i in range(3)] == [b, c, a]

    def test_appliquer_resultat_suit_le_fichier_meme_apres_reordre(self, modele):
        # Le fil d'analyse rend un ident ; la ligne peut avoir bougé (glisser) entre-temps.
        a = modele.ajouter(r"C:\a.pdf")
        modele.ajouter(r"C:\b.pdf")
        modele.deplacer(0, 1)   # a passe en deuxième position
        modele.appliquer_resultat(a, _resultat(analyse.PRET))
        rang_a = next(i for i in range(modele.rowCount()) if modele.ligne(i).ident == a)
        assert modele.ligne(rang_a).resultat.etat == analyse.PRET
        assert modele.ligne(0).resultat.etat == analyse.ANALYSE


class TestLanceurAnalyse:

    def test_analyse_tourne_hors_du_fil_de_l_interface(self, qtbot):
        creer_application([])
        fil_ui = threading.get_ident()
        vu = {}

        def _analyser(chemin, **kw):
            vu['fil'] = threading.get_ident()
            return _resultat(analyse.PRET)

        lanceur = LanceurAnalyse(analyser=_analyser)
        with qtbot.waitSignal(lanceur.fini, timeout=2000) as bloc:
            lanceur.lancer(7, r"C:\doc.pdf")
        assert bloc.args[0] == 7
        assert bloc.args[1].etat == analyse.PRET
        assert vu['fil'] != fil_ui

    def test_lanceur_remplit_le_modele(self, qtbot):
        creer_application([])
        modele = ModeleFichiers()
        lanceur = LanceurAnalyse(analyser=lambda chemin, **kw: _resultat(analyse.PRET))
        lanceur.fini.connect(modele.appliquer_resultat)
        ident = modele.ajouter(r"C:\doc.pdf")
        with qtbot.waitSignal(lanceur.fini, timeout=2000):
            lanceur.lancer(ident, r"C:\doc.pdf")
        assert modele.ligne(0).resultat.etat == analyse.PRET
