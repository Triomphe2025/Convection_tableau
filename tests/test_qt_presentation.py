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
        assert presentation.sigle_famille("plan") == "DXF"

    def test_famille_absente(self):
        assert presentation.sigle_famille(None) == "?"


class TestTexteType:

    def test_pret_montre_le_nom(self):
        res = _res(analyse.PRET, _Type("Bornier standard", "tableau"))
        assert presentation.texte_type(res) == "Bornier standard"

    def test_plan_scanne_pas_redondant(self):
        from types_documents import TYPE_PLAN
        res = _res(analyse.PRET, TYPE_PLAN, estimation={'pages': {
            'total': 1, 'scan': 1, 'vectoriel': 0, 'ocr_invisible': 0, 'vide': 0}})
        assert presentation.texte_type(res) == "Plan scanné"

    def test_plan_vectoriel_selon_natures(self):
        from types_documents import TYPE_PLAN
        res = _res(analyse.PRET, TYPE_PLAN, estimation={'pages': {
            'total': 2, 'scan': 0, 'vectoriel': 2, 'ocr_invisible': 0, 'vide': 0}})
        assert presentation.texte_type(res) == "Plan vectoriel"

    def test_excel_est_mise_en_forme(self):
        from types_documents import TYPE_EXCEL
        assert presentation.texte_type(_res(analyse.PRET, TYPE_EXCEL)) == "Mise en forme"

    def test_journal_est_rejeu(self):
        from types_documents import TYPE_JOURNAL
        assert presentation.texte_type(_res(analyse.PRET, TYPE_JOURNAL)) == "Rejeu sans appel"

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


class TestNomFamille:

    def test_familles_connues(self):
        assert presentation.nom_famille("tableau") == "Tableau"
        assert presentation.nom_famille("plan") == "Plan"
        assert presentation.nom_famille("excel") == "Excel"

    def test_famille_absente_est_inconnu(self):
        assert presentation.nom_famille(None) == "Inconnu"


class TestCouleurFamille:

    def test_chaque_famille_a_sa_couleur(self):
        assert presentation.couleur_famille("tableau", JETONS) == COULEURS['rose_trios']
        assert presentation.couleur_famille("plan", JETONS) == COULEURS['texte_natif']
        assert presentation.couleur_famille("excel", JETONS) == COULEURS['succes']
        assert presentation.couleur_famille("journal", JETONS) == COULEURS['texte_discret']

    def test_inconnu_est_orange(self):
        assert presentation.couleur_famille(None, JETONS) == COULEURS['a_relire']


class TestTextePages:

    def test_detaille_scannees_et_natif(self):
        res = _res(analyse.PRET, estimation={'pages': {
            'total': 141, 'scan': 116, 'vectoriel': 25, 'ocr_invisible': 0, 'vide': 0}})
        assert presentation.texte_pages(res) == "141 pages · 116 scannées · 25 en texte natif"

    def test_une_seule_page_au_singulier(self):
        res = _res(analyse.PRET, estimation={'pages': {
            'total': 1, 'scan': 1, 'vectoriel': 0, 'ocr_invisible': 0, 'vide': 0}})
        assert presentation.texte_pages(res) == "1 page · 1 scannée"

    def test_sans_estimation_vide(self):
        assert presentation.texte_pages(_res(analyse.ANALYSE)) == ""


class TestTexteSortie:

    def test_excel_et_dxf(self):
        from types_documents import TYPE_PLAN
        assert presentation.texte_sortie(_res(analyse.PRET, TYPE_PLAN)) == "→ DXF"
        tab = _Type("Bornier standard", "tableau")
        tab.sorties = ("excel",)
        assert presentation.texte_sortie(_res(analyse.PRET, tab)) == "→ Excel"

    def test_sans_type_vide(self):
        assert presentation.texte_sortie(_res(analyse.INCONNU)) == ""


class TestPreuveCourte:

    def test_inconnu_dit_aucun_type(self):
        assert presentation.preuve_courte(_res(analyse.INCONNU)) == "aucun type ne correspond"

    def test_prend_la_derniere_preuve(self):
        res = _res(analyse.PRET, _Type("X", "tableau"))
        res.preuves = ["format 842 pt", "pied BORNIER reconnu"]
        assert presentation.preuve_courte(res) == "pied BORNIER reconnu"


class TestGroupesTypes:

    def test_groupe_par_famille_dans_l_ordre(self):
        from types_documents import TYPE_EXCEL, TYPE_JOURNAL, TYPE_PLAN
        registre = {
            "Bornier standard": _Type("Bornier standard", "tableau"),
            "Répartiteur": _Type("Répartiteur", "tableau"),
            "Plan": TYPE_PLAN,
            "Excel": TYPE_EXCEL,
            "Journal": TYPE_JOURNAL,
        }
        groupes = presentation.groupes_types(registre)
        familles = [f for f, _ in groupes]
        assert familles == ["tableau", "plan", "excel", "journal"]
        noms_tableau = dict(groupes)["tableau"]
        assert "Bornier standard" in noms_tableau and "Répartiteur" in noms_tableau

    def test_libelle_de_groupe(self):
        assert presentation.libelle_groupe("tableau") == "Tableaux → Excel"
        assert presentation.libelle_groupe("plan") == "Plans → DXF"

    def test_description_tableau_liste_les_modeles(self):
        desc = presentation.description_groupe("tableau", ["Bornier standard", "Répartiteur"])
        assert "Bornier standard" in desc and "Répartiteur" in desc

    def test_description_plan_est_une_phrase(self):
        desc = presentation.description_groupe("plan", ["Plan"])
        assert "Plan" not in desc.split(" · ")  # pas juste le nom du type
        assert desc  # une vraie description


class TestLotPropose:

    def test_propose_au_dela_de_100_pages_payantes(self):
        res = _res(analyse.PRET, estimation={'pages_payantes': 141})
        assert presentation.lot_propose(res) is True

    def test_pas_propose_en_dessous(self):
        res = _res(analyse.PRET, estimation={'pages_payantes': 76})
        assert presentation.lot_propose(res) is False

    def test_sans_estimation_non_propose(self):
        assert presentation.lot_propose(_res(analyse.ANALYSE)) is False


class TestProfils:

    def test_trois_profils_tableau(self):
        cles = [p.cle for p in presentation.PROFILS_TABLEAU]
        assert cles == ["rapide", "precis", "difficile"]

    def test_rapide_est_tesseract_sans_cout(self):
        rapide = presentation.PROFILS_TABLEAU[0]
        assert rapide.profil == "tesseract"
        assert rapide.modele is None


class TestLotEffectif:

    def test_lot_sur_un_profil_claude(self):
        precis = presentation.PROFILS_TABLEAU[1]
        assert presentation.lot_effectif(precis, True) is True

    def test_lot_ignore_sur_tesseract(self):
        rapide = presentation.PROFILS_TABLEAU[0]   # Tesseract : le lot ne s'applique pas
        assert presentation.lot_effectif(rapide, True) is False


class TestTexteResume:

    def test_colore_les_compteurs(self):
        jetons = JETONS
        texte = presentation.texte_resume(5, 4, 1, jetons)
        assert COULEURS['succes'] in texte and "4 prêts" in texte
        assert COULEURS['a_relire'] in texte and "1 à préciser" in texte

    def test_sans_a_preciser_omis(self):
        texte = presentation.texte_resume(3, 3, 0, JETONS)
        assert "à préciser" not in texte
