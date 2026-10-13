"""
compte_lignes.py sur des pages fabriquées (cadre, en-tête en pointillés, lignes de texte à pas
fixe, pied) : nombre de lignes, tache dans une case vide, pointillés entre deux câbles, scan
penché, cadre ou trait d'en-tête absents ; fonctions de la grille une par une.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_compte_lignes.py -v
"""
import cv2
import numpy as np

import compte_lignes as cl

PAS = 48


def _page(lignes=30, entete=True, tache=False, pointilles_apres=None, angle=0.0, cadre=True,
          bords_noirs=False, pied_dans_le_cadre=False, ligne_courte=False, bord_haut=False):
    """Page A4 à 300 DPI : 255 = blanc, 0 = encre.

    pied_dans_le_cadre : traits verticaux prolongés jusqu'au bas du pied, sans trait de bas
    de tableau ; le pied (3 lignes) n'est séparé que par le trait plein de son cadre.
    """
    image = np.full((3508, 2480), 255, np.uint8)
    if cadre:
        bas = 3300 if pied_dans_le_cadre else 3000
        for x in (100, 700, 1400, 2380):
            image[100:bas, x:x + 3] = 0
        image[100:103, 100:2383] = 0
        image[3000:3003, 100:2383] = 0
        if pied_dans_le_cadre:
            for y in (3040, 3100, 3160):
                for x in range(150, 900, 22):
                    image[y:y + 25, x:x + 16] = 0
    if bords_noirs:
        image[:, 0:12] = 0
        image[:, 2468:] = 0
    if bord_haut:
        image[0:6, :] = 0
    if ligne_courte:
        # Ligne de la seule colonne COULEUR : « 7 VE », trois caractères séparés par un blanc.
        y = 230 + lignes * PAS
        for x in (750, 810, 832):
            image[y:y + 25, x:x + 16] = 0
    image[130:160, 150:300] = 0
    if entete:
        for x in range(100, 2380, 27):
            image[200:203, x:x + 15] = 0
    for k in range(lignes):
        y = 230 + k * PAS
        for x0, x1 in ((150, 260), (750, 950), (1450, 1700)):
            for x in range(x0, x1, 22):
                image[y:y + 25, x:x + 16] = 0
        if pointilles_apres == k:
            for x in range(100, 2380, 27):
                image[y + 38:y + 40, x:x + 15] = 0
    if tache:
        y = 230 + (lignes + 3) * PAS
        image[y:y + 12, 1500:1515] = 0
    image[3050:3080, 150:600] = 0
    if angle:
        centre = (image.shape[1] / 2, image.shape[0] / 2)
        image = cv2.warpAffine(image, cv2.getRotationMatrix2D(centre, angle, 1.0),
                               (image.shape[1], image.shape[0]), borderValue=255)
    return image


class TestCompterLignes:

    def test_compte_nominal(self):
        resultat = cl.compter_lignes(_page(30), 22.0)
        assert resultat['raison'] is None
        assert resultat['lignes'] == 30
        assert abs(resultat['pas'] - PAS) < 1

    def test_tache_dans_une_case_vide_pas_une_ligne(self):
        assert cl.compter_lignes(_page(30, tache=True), 22.0)['lignes'] == 30

    def test_pointilles_entre_deux_cables_pas_une_ligne(self):
        assert cl.compter_lignes(_page(30, pointilles_apres=10), 22.0)['lignes'] == 30

    def test_scan_penche(self):
        resultat = cl.compter_lignes(_page(40, angle=0.6), 22.0)
        assert resultat['lignes'] == 40
        assert abs(resultat['angle'] + 0.6) < 0.15 or abs(resultat['angle'] - 0.6) < 0.15

    def test_trait_d_entete_absent_comptage_impossible(self):
        resultat = cl.compter_lignes(_page(30, entete=False), 22.0)
        assert resultat['lignes'] is None
        assert resultat['raison']

    def test_cadre_absent_comptage_impossible(self):
        resultat = cl.compter_lignes(_page(30, cadre=False), 22.0)
        assert resultat['raison'] == "traits verticaux du cadre non trouvés"


class TestGrille:

    def test_ajuster_pas_trouve_pas_et_phase(self):
        profil = np.zeros(1500)
        for k in range(30):
            profil[10 + k * PAS:10 + k * PAS + 25] = 100
        pas, phase, regularite = cl.ajuster_pas(profil, 33, 70)
        assert abs(pas - PAS) < 0.5
        assert abs(phase - 22) < 3
        assert regularite > 0.5

    def test_ajuster_pas_profil_vide(self):
        assert cl.ajuster_pas(np.zeros(500), 33, 70) == (0.0, 0.0, 0.0)

    def test_cases_grille_entieres_seulement(self):
        cases = cl.cases_grille(480, 48.0, 24.0)
        assert len(cases) == 10
        assert cases[0] == (0, 48)

    def test_hauteur_caractere_mesuree_sur_la_page(self):
        taches = [(0, 30, 20)] * 40 + [(0, 3, 3)] * 10 + [(0, 6, 40)] * 5
        assert cl.hauteur_caractere(taches, 48.0) == 30

    def test_hauteur_caractere_sans_lettre(self):
        assert cl.hauteur_caractere([(0, 3, 3)], 48.0) is None

    def test_tache_de_caractere(self):
        assert cl.tache_de_caractere(30, 18, 30.0, 48.0)          # lettre
        assert cl.tache_de_caractere(22, 18, 30.0, 48.0)          # « 7 » seul (≥ 70 %)
        assert not cl.tache_de_caractere(8, 8, 30.0, 48.0)        # poussière
        assert not cl.tache_de_caractere(4, 300, 30.0, 48.0)      # reste de trait, plat
        assert not cl.tache_de_caractere(30, 2, 30.0, 48.0)       # rayure, trop fine
        assert not cl.tache_de_caractere(1373, 8, 30.0, 48.0)     # reste de trait vertical


class TestTraitsEtZone:

    def test_zone_sous_les_pointilles_jusqu_au_trait_plein(self):
        noir = 255 - _page(30)
        vertical = cl.traits_verticaux(noir)
        zone = cl.zone_tableau(vertical, cl.regles(noir, 103, 2380))
        assert zone['raison'] is None
        x0, x1, y0, y1 = zone['zone']
        assert 200 < y0 < 230 and 2980 < y1 < 3000
        assert 100 < x0 < 110 and 2370 < x1 < 2381

    def test_inclinaison_retrouvee(self):
        noir = 255 - _page(40, angle=0.5)
        assert abs(abs(cl.inclinaison(noir)) - 0.5) < 0.1


class TestCoucheTexte:

    def test_mots_groupes_par_ligne_dans_la_zone(self):
        mots = [(10, 100, 30, 108, '01'), (60, 100.5, 90, 108.5, 'PH'),
                (10, 112, 30, 120, '02'), (10, 300, 30, 308, 'PIED'),
                (10, 124, 30, 132, '|')]
        assert cl.lignes_couche_texte(mots, (0, 200, 90, 250)) == 2

    def test_zone_vide(self):
        assert cl.lignes_couche_texte([], (0, 200, 90, 250)) == 0


class TestBornesDeLaZone:

    def test_bords_noirs_du_scan_ignores(self):
        assert cl.compter_lignes(_page(30, bords_noirs=True), 22.0)['lignes'] == 30

    def test_pied_dans_le_cadre_non_compte(self):
        resultat = cl.compter_lignes(_page(20, pied_dans_le_cadre=True), 22.0)
        assert resultat['lignes'] == 20
        assert resultat['zone'][3] < 3000

    def test_trait_trouve_seulement_dans_le_pied_comptage_impossible(self):
        resultat = cl.compter_lignes(_page(30, entete=False), 22.0)
        assert resultat['lignes'] is None
        assert "haut du cadre" in resultat['raison']

    def test_regles_pointilles_et_plein(self):
        noir = 255 - _page(30)
        trouves = cl.regles(noir, 103, 2380)
        # Position à la fenêtre de mesure près (quelques pixels).
        assert [plein for _, _, plein in trouves] == [True, False, True]
        for (a, b, _), attendu in zip(trouves, (101, 201, 3001)):
            assert abs((a + b) / 2 - attendu) <= 5

    def test_regles_ligne_de_texte_pas_un_trait(self):
        noir = np.zeros((400, 1000), np.uint8)
        noir[100:125, 0:1000:2] = 255          # texte dense : trop haut pour un trait
        assert cl.regles(noir, 0, 1000) == []

    def test_traits_verticaux_bord_ecarte(self):
        noir = 255 - _page(5, bords_noirs=True)
        colonnes = np.where(cl.traits_verticaux(noir).sum(axis=0) > 0)[0]
        assert colonnes.min() >= 100 and colonnes.max() <= 2383


class TestDecisions:

    def test_alerte_pour_un_ou_deux_ecarts(self):
        d = cl.decisions([{'visibles': 47, 'lues': 46}, {'visibles': 30, 'lues': 30},
                          {'visibles': 10, 'lues': 12}] + [{'visibles': 5, 'lues': 5}] * 7)
        assert d['synthese'] is None
        assert [p['type'] for p in d['pages'][:3]] == ['alerte', None, 'alerte']
        assert d['pages'][0]['message'] == '47 lignes visibles, 46 lues'

    def test_au_dela_comptage_incertain(self):
        d = cl.decisions([{'visibles': 59, 'lues': 56}] + [{'visibles': 5, 'lues': 5}] * 9)
        assert d['pages'][0] == {'type': 'incertain', 'message': (
            'comptage incertain (écart de 3 lignes : 59 visibles, 56 lues)')}

    def test_plus_de_20_pour_cent_une_synthese(self):
        d = cl.decisions([{'visibles': 33, 'lues': 32}] * 3 + [{'visibles': 5, 'lues': 5}] * 7)
        assert 'écart sur 3 pages sur 10' in d['synthese']
        assert all(p['type'] is None for p in d['pages'])

    def test_comptage_impossible_hors_du_compte(self):
        d = cl.decisions([{'visibles': None, 'lues': 4}, {'visibles': 4, 'lues': 4}])
        assert d['synthese'] is None
        assert d['pages'][0]['type'] is None

    def test_document_vide(self):
        assert cl.decisions([]) == {'synthese': None, 'pages': []}


class TestDecisionPage:

    def test_egal_ou_non_compte(self):
        assert cl.decision_page(30, 30) == {'type': None, 'message': None}
        assert cl.decision_page(None, 30) == {'type': None, 'message': None}

    def test_deux_lignes_alerte_trois_incertain(self):
        assert cl.decision_page(32, 30)['type'] == 'alerte'
        assert cl.decision_page(33, 30)['type'] == 'incertain'
        assert cl.decision_page(27, 30)['type'] == 'incertain'


class TestCorrectionsEtape9:

    def test_ligne_courte_comptee(self):
        assert cl.compter_lignes(_page(20, ligne_courte=True))['lignes'] == 21

    def test_bord_haut_du_scan_pas_le_haut_du_cadre(self):
        resultat = cl.compter_lignes(_page(20, bord_haut=True))
        assert resultat['lignes'] == 20
        assert resultat['zone'][2] > 200          # sous l'en-tête, pas sous le bord

    def test_pas_caractere_facultatif(self):
        assert cl.compter_lignes(_page(10))['lignes'] == cl.compter_lignes(_page(10), 22.0)[
            'lignes']
