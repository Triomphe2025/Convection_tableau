"""Étape 3 — présentation d'une ligne (pur, sans Qt) : sigle, type, estimation, couleur d'état."""
from trios_qt import analyse, presentation
from trios_qt.theme import charger_jetons

JETONS = charger_jetons()
COULEURS = JETONS['couleurs']


class _Type:
    def __init__(self, nom, famille):
        self.nom = nom
        self.famille = famille


def _res(etat, type_=None, estimation=None):
    return analyse.ResultatAnalyse(etat=etat, type=type_, estimation=estimation)


class TestSigleFamille:

    def test_tableau_et_plan(self):
        assert presentation.sigle_famille("tableau") == "TAB"
        assert presentation.sigle_famille("plan") == "PLN"

    def test_famille_absente(self):
        assert presentation.sigle_famille(None) == "?"


class TestTexteType:

    def test_pret_montre_le_nom(self):
        res = _res(analyse.PRET, _Type("Bornier standard", "tableau"))
        assert presentation.texte_type(res) == "Bornier standard"

    def test_a_preciser_est_signale(self):
        res = _res(analyse.A_PRECISER, _Type("Répartiteur", "tableau"))
        assert "à préciser" in presentation.texte_type(res)
        assert "Répartiteur" in presentation.texte_type(res)

    def test_inconnu_demande_un_type(self):
        assert presentation.texte_type(_res(analyse.INCONNU)) == "à préciser"

    def test_analyse_en_cours(self):
        assert presentation.texte_type(_res(analyse.ANALYSE)) == "analyse…"


class TestTexteEstimation:

    def test_cout_prefixe_tilde(self):
        res = _res(analyse.PRET, estimation={
            'cout_usd': 1.234, 'cache_connu': True, 'duree': {'texte': '~ 3 min'}})
        texte = presentation.texte_estimation(res)
        assert texte.startswith("~")
        assert "1,23" in texte and "$" in texte

    def test_cache_inconnu_affiche_au_plus(self):
        res = _res(analyse.PRET, estimation={
            'cout_usd': 2.0, 'cache_connu': False, 'duree': {'texte': '~ 1 min'}})
        assert "au plus" in presentation.texte_estimation(res)

    def test_cout_nul_sans_dollar(self):
        res = _res(analyse.PRET, estimation={
            'cout_usd': 0.0, 'cache_connu': True, 'duree': {'texte': '~ 12 s'}})
        texte = presentation.texte_estimation(res)
        assert "$" not in texte
        assert "12 s" in texte

    def test_sans_estimation_vide(self):
        assert presentation.texte_estimation(_res(analyse.ANALYSE)) == ""


class TestCouleurEtat:

    def test_a_preciser_et_inconnu_sont_orange(self):
        assert presentation.couleur_etat(analyse.A_PRECISER, JETONS) == COULEURS['a_relire']
        assert presentation.couleur_etat(analyse.INCONNU, JETONS) == COULEURS['a_relire']

    def test_pret_est_vert(self):
        assert presentation.couleur_etat(analyse.PRET, JETONS) == COULEURS['succes']

    def test_erreur_est_rouge(self):
        assert presentation.couleur_etat(analyse.ERREUR, JETONS) == COULEURS['erreur']
