"""
Nombre de lignes de texte visibles dans la zone du tableau d'une page, sans lire les mots.

Les listings sont imprimés à pas de ligne fixe : même sur un scan sale, chaque ligne laisse
une bande d'encre. Zone du tableau = entre le trait sous l'en-tête et le bas des traits
verticaux du cadre, entre les traits extrêmes ; les traits du cadre sont retirés ; le pas
et la phase de la grille des lignes sont ajustés ensemble sur le profil d'encre ; une case
de la grille compte comme ligne si son encre s'étend sur au moins LIGNES_LARGEUR_MIN_CARACTERES
caractères (une tache dans une case vide n'est pas une ligne).

Module pur (numpy, OpenCV, config) : image en niveaux de gris en entrée, aucun OCR.
"""
from typing import Dict, List, Optional, Tuple

from config import Config


def _echelle(image) -> float:
    """Pixels de l'image par pixel d'un A4 à 300 DPI (les pages sont rendues à cette taille,
    même une page géante de 223111PE012 rendue à 72 DPI)."""
    return max(image.shape) / (Config.POSITIONS_COTE_A4_PT * 300 / 72)


def _groupes(indices, ecart: int = 3) -> List[Tuple[int, int]]:
    """Suites d'indices consécutifs (à ecart près) : (début, fin)."""
    groupes: List[Tuple[int, int]] = []
    for i in indices:
        if groupes and i - groupes[-1][1] <= ecart:
            groupes[-1] = (groupes[-1][0], int(i))
        else:
            groupes.append((int(i), int(i)))
    return groupes


def traits(noir):
    """Traits longs : verticaux, horizontaux (pointillés compris), horizontaux pleins."""
    import cv2
    hauteur, largeur = noir.shape
    vertical = cv2.morphologyEx(noir, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(20, int(hauteur * Config.LIGNES_PART_TRAIT_VERTICAL)))))
    long = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(20, int(largeur * Config.LIGNES_PART_TRAIT_HORIZONTAL)), 1))
    pleins = cv2.morphologyEx(noir, cv2.MORPH_OPEN, long)
    # Trait sous l'en-tête en pointillés (223111PE011, 6A23111PE133) : les blancs entre tirets
    # sont comblés avant de chercher les traits longs ; ceux entre deux mots, plus larges, non.
    combles = cv2.morphologyEx(noir, cv2.MORPH_CLOSE, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, round(Config.LIGNES_BLANC_POINTILLES * _echelle(noir))), 1)))
    horizontal = cv2.morphologyEx(combles, cv2.MORPH_OPEN, long)
    return vertical, horizontal, pleins


def _traits_horizontaux(masque, x0: int, x1: int) -> List[float]:
    import numpy as np
    return [(a + b) / 2 for a, b in _groupes(np.where(masque[:, x0:x1].sum(axis=1) > 0)[0])]


def zone_tableau(vertical, horizontal, pleins) -> Dict:
    """Zone des lignes de données : (x0, x1, y0, y1) en pixels, ou raison si introuvable.

    Haut = premier trait horizontal (plein ou pointillé) sous le haut des traits verticaux :
    celui qui ferme l'en-tête. Bas = premier trait plein en dessous (bas du tableau ou haut
    du pied), sinon bas des traits verticaux ; les pointillés entre deux câbles (223111PE012)
    ne ferment pas la zone. En-tête et pied sont hors de la zone.
    """
    import numpy as np
    colonnes = _groupes(np.where(vertical.sum(axis=0) > 0)[0])
    if len(colonnes) < 2:
        return {'zone': None, 'raison': "traits verticaux du cadre non trouvés"}
    x0, x1 = colonnes[0][1] + 1, colonnes[-1][0] - 1
    lignes_v = np.where(vertical[:, colonnes[0][0]:colonnes[-1][1] + 1].sum(axis=1) > 0)[0]
    haut, bas = int(lignes_v.min()), int(lignes_v.max())
    marge = 10 * _echelle(vertical)
    regles = _traits_horizontaux(horizontal, x0, x1)
    # Haut du cadre : trait du haut s'il est au-dessus des traits verticaux (6A23111PE133
    # p. 15 : les séparateurs ne commencent que sous les pointillés de l'en-tête).
    haut = min([haut] + [y for y in regles if y < haut])
    sous_entete = [y for y in regles if haut + marge < y < bas - marge]
    if not sous_entete:
        return {'zone': None, 'raison': "trait sous l'en-tête non trouvé"}
    y0 = sous_entete[0]
    suivants = [y for y in _traits_horizontaux(pleins, x0, x1) if y > y0 + marge]
    fin = min(bas, suivants[0]) if suivants else bas
    return {'zone': (x0, x1, int(y0 + marge / 2), int(fin - marge / 2)), 'raison': None}


def ajuster_pas(profil, pas_min: float, pas_max: float) -> Tuple[float, float, float]:
    """(pas, phase, régularité) de la grille de lignes, ajustés ensemble sur le profil.

    Pas de départ = premier pic d'autocorrélation dans [pas_min, pas_max], puis pas et
    phase affinés par la somme circulaire du profil (centre des bandes d'encre) ;
    régularité = |somme| / encre totale (1 = bandes parfaitement périodiques).
    """
    import numpy as np
    w = np.asarray(profil, dtype=float)
    total = w.sum()
    if total <= 0 or len(w) < 2 * pas_max:
        return 0.0, 0.0, 0.0
    centre = w - w.mean()
    auto = np.correlate(centre, centre, mode='full')[len(w) - 1:]
    a, b = int(pas_min), min(int(pas_max) + 1, len(auto) - 1)
    pas0 = a + int(np.argmax(auto[a:b]))
    y = np.arange(len(w))
    meilleur = (-1.0, float(pas0), 0.0)
    for pas in np.arange(pas0 * 0.9, pas0 * 1.1, 0.05):
        somme = (w * np.exp(2j * np.pi * y / pas)).sum()
        if abs(somme) > meilleur[0]:
            meilleur = (abs(somme), float(pas), float(np.angle(somme) / (2 * np.pi) * pas % pas))
    return meilleur[1], meilleur[2], meilleur[0] / total


def cases_grille(hauteur: int, pas: float, phase: float) -> List[Tuple[int, int]]:
    """Cases [début, fin) de la grille de lignes, centrées sur phase + k × pas."""
    cases: List[Tuple[int, int]] = []
    centre = phase % pas
    while centre - pas / 2 < hauteur:
        debut = max(0, int(round(centre - pas / 2)))
        fin = min(hauteur, int(round(centre + pas / 2)))
        # Une case coupée de plus de moitié par le bord de la zone n'est pas une ligne entière.
        if fin - debut >= pas / 2:
            cases.append((debut, fin))
        centre += pas
    return cases


def inclinaison(noir) -> float:
    """Angle (degrés) qui rend les lignes du scan horizontales : profil d'encre le plus marqué.

    Un scan penché de quelques dixièmes de degré décale un trait d'en-tête de plusieurs
    pixels sur la largeur du tableau (6A23111PE133 p. 6) : ni trait long ni bandes nettes.
    """
    import cv2
    import numpy as np
    petit = cv2.resize(noir, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    centre = (petit.shape[1] / 2, petit.shape[0] / 2)
    meilleur = (-1.0, 0.0)
    pas = Config.LIGNES_INCLINAISON_PAS
    for angle in np.arange(-Config.LIGNES_INCLINAISON_MAX, Config.LIGNES_INCLINAISON_MAX + pas,
                           pas):
        tourne = cv2.warpAffine(petit, cv2.getRotationMatrix2D(centre, float(angle), 1.0),
                                (petit.shape[1], petit.shape[0]))
        score = float((tourne.sum(axis=1).astype(float) ** 2).sum())
        if score > meilleur[0]:
            meilleur = (score, float(angle))
    return meilleur[1]


def case_est_ligne(encre_case, largeur_min: float, pas_caractere: float,
                   hauteur_min: float = 0.0) -> bool:
    """Encre de la case étalée sur au moins largeur_min pixels (lettres d'un mot réunies) et
    haute d'au moins hauteur_min (un trait ou un reste de trait n'est pas une ligne)."""
    import cv2
    import numpy as np
    rangees = encre_case.sum(axis=1)
    if not rangees.any() or (rangees >= 0.1 * rangees.max()).sum() < hauteur_min:
        return False
    colonnes = (encre_case.sum(axis=0) > 0).astype(np.uint8).reshape(1, -1)
    if not colonnes.any():
        return False
    # Les blancs entre les lettres d'un mot sont comblés ; ceux entre les cellules, non.
    noyau = cv2.getStructuringElement(cv2.MORPH_RECT, (max(1, int(pas_caractere)), 1))
    pleines = cv2.morphologyEx(colonnes, cv2.MORPH_CLOSE, noyau)
    return any(b - a + 1 >= largeur_min for a, b in _groupes(np.where(pleines[0] > 0)[0], 1))


def compter_lignes(gris, pas_caractere: float) -> Dict:
    """Lignes visibles dans la zone du tableau : nombre, pas, phase, régularité, raison.

    raison non vide = comptage impossible (cadre introuvable, pas non trouvé).
    """
    import cv2
    import numpy as np
    sortie = {'lignes': None, 'pas': None, 'phase': None, 'regularite': None, 'zone': None,
              'cases': [], 'angle': 0.0, 'raison': None}
    noir = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    angle = inclinaison(noir)
    if angle:
        centre = (noir.shape[1] / 2, noir.shape[0] / 2)
        noir = cv2.warpAffine(noir, cv2.getRotationMatrix2D(centre, angle, 1.0),
                              (noir.shape[1], noir.shape[0]))
    sortie['angle'] = angle
    vertical, horizontal, pleins = traits(noir)
    zone = zone_tableau(vertical, horizontal, pleins)
    if zone['raison']:
        return dict(sortie, raison=zone['raison'])
    x0, x1, y0, y1 = zone['zone']
    sortie['zone'] = zone['zone']
    traces = cv2.dilate(vertical | horizontal | pleins, np.ones((7, 7), np.uint8))
    encre = (noir & ~traces)[y0:y1, x0:x1] > 0
    echelle = _echelle(gris)
    pas, phase, regularite = ajuster_pas(encre.sum(axis=1), Config.LIGNES_PAS_MIN * echelle,
                                         Config.LIGNES_PAS_MAX * echelle)
    sortie.update(pas=pas, phase=phase + y0, regularite=regularite)
    if regularite < Config.LIGNES_REGULARITE_MIN:
        return dict(sortie, raison=f"lignes non régulières (régularité {regularite:.2f})")
    largeur_min = Config.LIGNES_LARGEUR_MIN_CARACTERES * pas_caractere
    hauteur_min = Config.LIGNES_HAUTEUR_MIN_PART * pas
    cases = [(a, b) for a, b in cases_grille(encre.shape[0], pas, phase)
             if case_est_ligne(encre[a:b], largeur_min, pas_caractere, hauteur_min)]
    sortie['cases'] = [(a + y0, b + y0) for a, b in cases]
    sortie['lignes'] = len(cases)
    return sortie


def lignes_couche_texte(mots, zone_pt: Tuple[float, float, float, float],
                        tolerance: Optional[float] = None) -> int:
    """Lignes de texte d'une page vectorielle dans la zone (points PDF) : mots groupés par y.

    mots = (x0, y0, x1, y1, texte, …) de PyMuPDF get_text('words').
    """
    x0, x1, y0, y1 = zone_pt
    tolerance = Config.PDF_GRILLE_TOLERANCE_Y if tolerance is None else tolerance
    centres = sorted((m[1] + m[3]) / 2 for m in mots
                     if x0 <= (m[0] + m[2]) / 2 <= x1 and y0 <= (m[1] + m[3]) / 2 <= y1
                     and any(c.isalnum() for c in m[4]))
    lignes, dernier = 0, None
    for y in centres:
        if dernier is None or y - dernier > tolerance:
            lignes += 1
        dernier = y
    return lignes
