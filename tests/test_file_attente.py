"""File d'attente de conversion (module pur, sans Qt) : un fichier à la fois, erreur → suivant."""
from trios_qt.file_attente import FileAttente


class TestFileAttente:

    def test_demarrer_rend_le_premier(self):
        f = FileAttente(["a", "b", "c"])
        assert f.demarrer() == "a"
        assert f.courant == "a"

    def test_terminer_avance_jusqu_au_bout(self):
        f = FileAttente(["a", "b"])
        assert f.demarrer() == "a"
        assert f.terminer() == "b"
        assert f.terminer() is None
        assert f.termine
        assert f.faits == ["a", "b"]

    def test_echec_passe_au_suivant(self):
        f = FileAttente(["a", "b"])
        f.demarrer()
        assert f.terminer(ok=False) == "b"   # erreur sur « a » → on continue
        assert f.echecs == ["a"]
        f.terminer()
        assert f.faits == ["b"] and f.echecs == ["a"]

    def test_arreter_vide_la_file(self):
        f = FileAttente(["a", "b", "c"])
        f.demarrer()
        f.arreter()
        assert f.terminer() is None
        assert f.restants == []
        assert f.courant is None

    def test_file_vide(self):
        f = FileAttente([])
        assert f.demarrer() is None
        assert f.termine
