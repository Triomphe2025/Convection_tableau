"""Message 2 — durées par modèle : Difficile (Opus) jamais affiché plus rapide que Précis (Sonnet).

En l'absence de journaux (cas de l'exe neuf), l'estimation retombe sur les constantes de durée
par modèle : leur ordre doit refléter la réalité (Opus plus lent que Sonnet).
"""
import estimation
from config import Config


class TestConstantesDuree:

    def test_opus_plus_lent_que_sonnet(self):
        sp = Config.ESTIMATION_SECONDES_PAR_PAGE
        assert sp['claude-opus-5-5'] >= sp['claude-sonnet-5-5']
        assert sp['claude-opus-5'] >= sp['claude-sonnet-5']

    def test_tesseract_le_plus_rapide(self):
        sp = Config.ESTIMATION_SECONDES_PAR_PAGE
        assert sp['tesseract'] <= sp['claude-haiku-5-5'] <= sp['claude-sonnet-5-5']


class TestEstimationDuree:

    def test_difficile_jamais_plus_rapide_que_precis(self, tmp_path, monkeypatch):
        # Pas de journaux : l'estimation prend les constantes. Même document scanné pour les deux.
        estimation.reinitialiser_cache()
        pdf = "tests/fixtures/scan_6A23111PE102_15p.pdf"
        precis = estimation.estimer(pdf, profil='claude', modele='claude-sonnet-5-5')
        difficile = estimation.estimer(pdf, profil='claude', modele='claude-opus-5-5')
        assert difficile['duree']['secondes'] >= precis['duree']['secondes'] > 0

    def test_mesure_basse_bornee_au_plancher_du_modele(self, monkeypatch):
        # Un journal bruité donnant Opus très rapide (2 s) ne doit pas passer sous sa constante :
        # la durée mesurée est bornée au plancher du modèle (garde Opus >= Sonnet).
        monkeypatch.setitem(estimation._moyennes_cache, 'claude-opus-5-5',
                            {'tokens': (1, 1), 'secondes': 2.0, 'source': 'test', 'n': 1})
        duree = estimation._duree_par_page('claude', 'claude-opus-5-5')
        assert duree == Config.ESTIMATION_SECONDES_PAR_PAGE['claude-opus-5-5']
