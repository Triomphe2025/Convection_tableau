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


def _page(lignes=30, entete=True, tache=False, pointilles_apres=None, angle=0.0, cadre=True):
    """Page A4 à 300 DPI : 255 = blanc, 0 = encre."""
    image = np.full((3508, 2480), 255, np.uint8)
    if cadre:
        for x in (100, 700, 1400, 2380):
            image[100:3000, x:x + 3] = 0
        image[100:103, 100:2383] = 0
        image[3000:3003, 100:2383] = 0
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

    def test_case_est_ligne_largeur_minimale(self):
        case = np.zeros((48, 600), bool)
        case[10:35, 100:115] = True
        assert not cl.case_est_ligne(case, 44.0, 22.0, 12.0)
        case[10:35, 100:200] = True
        assert cl.case_est_ligne(case, 44.0, 22.0, 12.0)

    def test_case_est_ligne_trait_plat(self):
        case = np.zeros((48, 600), bool)
        case[20:23, 0:600] = True
        assert not cl.case_est_ligne(case, 44.0, 22.0, 12.0)

    def test_case_vide(self):
        assert not cl.case_est_ligne(np.zeros((48, 600), bool), 44.0, 22.0, 12.0)


class TestTraitsEtZone:

    def test_zone_sous_les_pointilles_jusqu_au_trait_plein(self):
        noir = 255 - _page(30)
        zone = cl.zone_tableau(*cl.traits(noir))
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
