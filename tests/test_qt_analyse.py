"""Cœur d'analyse d'un fichier déposé (trios_qt/analyse.py) : pur, sans Qt, injectable."""
import json
import tempfile
from pathlib import Path

from trios_qt import analyse


class _Type:
    """Faux TypeDocument minimal (nom, famille, modele) pour les tests d'analyse."""

    def __init__(self, nom="Bornier standard", famille="tableau", modele="Bornier standard"):
        self.nom = nom
        self.famille = famille
        self.modele = modele


class TestAnalyser:

    def test_type_connu_sur_est_pret_avec_estimation(self):
        devis = {'cout_usd': 1.23, 'approche': True}
        res = analyse.analyser(
            "doc.pdf",
            detecter=lambda c: (_Type(), 0.95, ["preuve"]),
            preciser=lambda conf, preuves: False,
            estimer=lambda chemin, **kw: devis,
        )
        assert res.etat == analyse.PRET
        assert res.type.nom == "Bornier standard"
        assert res.estimation is devis

    def test_a_preciser_est_oriente_mais_garde_une_estimation(self):
        # « à préciser » : non prêt tant que le type n'est pas confirmé, mais on montre un coût.
        res = analyse.analyser(
            "doc.pdf",
            detecter=lambda c: (_Type(), 0.4, ["à préciser : Répartiteur ?"]),
            preciser=lambda conf, preuves: True,
            estimer=lambda chemin, **kw: {'cout_usd': 2.0},
        )
        assert res.etat == analyse.A_PRECISER
        assert res.estimation == {'cout_usd': 2.0}
        assert res.type is not None

    def test_type_inconnu_n_appelle_pas_estimer(self):
        def _estimer_interdit(chemin, **kw):
            raise AssertionError("estimer ne doit pas être appelé sur un type inconnu")

        res = analyse.analyser(
            "mystere.odt",
            detecter=lambda c: (None, 0.0, ["extension .odt inconnue"]),
            estimer=_estimer_interdit,
        )
        assert res.etat == analyse.INCONNU
        assert res.estimation is None

    def test_erreur_est_recuperable(self):
        def _detecter_casse(chemin):
            raise ValueError("fichier corrompu")

        res = analyse.analyser("doc.pdf", detecter=_detecter_casse)
        assert res.etat == analyse.ERREUR
        assert "corrompu" in res.erreur

    def test_dossier_sortie_est_transmis_a_estimer(self):
        recu = {}

        def _estimer(chemin, **kw):
            recu.update(kw)
            return {'cout_usd': 0.0}

        analyse.analyser(
            "doc.pdf",
            dossier_sortie=r"C:\sortie\TACHE01",
            lot=True,
            detecter=lambda c: (_Type(), 0.95, []),
            preciser=lambda conf, preuves: False,
            estimer=_estimer,
        )
        assert recu['dossier_sortie'] == r"C:\sortie\TACHE01"
        assert recu['lot'] is True

    def test_fichier_reel_jsonl_est_un_journal_pret(self):
        # Fichier réel décidé par l'extension (sans Tesseract) : chaîne detecter + estimer vraie.
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "lecture_claude.jsonl"
            with open(chemin, 'w', encoding='utf-8') as f:
                f.write(json.dumps({'page': 1}) + "\n")
                f.write(json.dumps({'page': 2}) + "\n")
            res = analyse.analyser(chemin)
        assert res.etat == analyse.PRET
        assert res.type.famille == "journal"
        assert res.estimation['cout_usd'] == 0.0
