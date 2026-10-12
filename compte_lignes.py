"""
Nombre de lignes de texte visibles dans la zone du tableau d'une page, sans lire les mots.

Les listings sont imprimés à pas de ligne fixe : même sur un scan sale, chaque ligne laisse
une bande d'encre. Zone du tableau = entre le trait sous l'en-tête (dans le haut du cadre) et
le premier trait plein en dessous, entre les traits verticaux extrêmes (bords du scan
écartés) ; les traits du cadre sont retirés ; le pas
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


def traits_verticaux(noir):
    """Traits verticaux longs du cadre ; ceux collés au bord de l'image sont écartés (bords
    noirs d'un scan, 223111PE012 p. 4 et 5 : pris pour le cadre, la page entière était comptée)."""
    import cv2
    hauteur, largeur = noir.shape
    vertical = cv2.morphologyEx(noir, cv2.MORPH_OPEN, cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(20, int(hauteur * Config.LIGNES_PART_TRAIT_VERTICAL)))))
    bord = int(Config.LIGNES_MARGE_BORD * largeur)
    vertical[:, :bord] = 0
    vertical[:, largeur - bord:] = 0
    return vertical


def regles(noir, x0: int, x1: int) -> List[Tuple[int, int, bool]]:
    """Traits horizontaux entre x0 et x1 : (début, fin, plein), par couverture de la largeur.

    Un trait est une bande mince dont l'encre, blancs entre tirets comblés et réunie sur
    LIGNES_FENETRE_TRAIT rangées (un trait scanné ondule sur 8 à 10 rangées, aucune ne le
    contient en entier), couvre au moins LIGNES_COUVERTURE_TRAIT de la largeur, avec du blanc
    d'un côté au moins ; une ligne de texte est trop haute pour passer. Mesurer la couverture
    et non un segment continu : les pointillés d'en-tête de 6A23111PE133 sont coupés par les
    traits verticaux (plus long segment 890 px sur 2 267). Plein = l'encre brute couvre au
    moins LIGNES_COUVERTURE_PLEIN de la largeur.
    """
    import cv2
    import numpy as np
    ech = _echelle(noir)
    bande = noir[:, x0:x1]
    fenetre = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(1, round(Config.LIGNES_FENETRE_TRAIT * ech))))
    combles = cv2.morphologyEx(bande, cv2.MORPH_CLOSE, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, round(Config.LIGNES_BLANC_POINTILLES * ech)), 1)))
    couverture = (cv2.dilate(combles, fenetre) > 0).mean(axis=1)
    brute = (cv2.dilate(bande, fenetre) > 0).mean(axis=1)
    epaisseur = max(2, round((Config.LIGNES_EPAISSEUR_TRAIT + Config.LIGNES_FENETRE_TRAIT)
                             * ech))
    autour = epaisseur + max(2, round(4 * ech))
    sortie = []
    for a, b in _groupes(np.where(couverture >= Config.LIGNES_COUVERTURE_TRAIT)[0], 1):
        if b - a + 1 > epaisseur:
            continue
        voisins = [couverture[y] for y in (a - autour, b + autour) if 0 <= y < len(couverture)]
        # Blanc d'un côté au moins : le trait sous l'en-tête touche presque le texte au-dessus.
        if voisins and min(voisins) >= Config.LIGNES_COUVERTURE_TRAIT / 2:
            continue
        plein = bool(brute[a:b + 1].max() >= Config.LIGNES_COUVERTURE_PLEIN)
        sortie.append((int(a), int(b), plein))
    return sortie


def zone_tableau(vertical, liste_regles: List[Tuple[int, int, bool]]) -> Dict:
    """Zone des lignes de données : (x0, x1, y0, y1) en pixels, ou raison si introuvable.

    Haut = premier trait sous le haut du cadre, et seulement dans le haut du cadre
    (LIGNES_PART_ENTETE_MAX) : un trait trouvé plus bas est celui du pied (6A23111PE133 p. 2,
    223111PE021 p. 2 : la zone tombait dans le pied) → comptage impossible, pas d'alerte.
    Bas = premier trait plein en dessous (bas du tableau, haut du cadre du pied), sinon bas
    des traits verticaux ; les pointillés entre deux câbles ne ferment pas la zone.
    """
    import numpy as np
    colonnes = _groupes(np.where(vertical.sum(axis=0) > 0)[0])
    if len(colonnes) < 2:
        return {'zone': None, 'raison': "traits verticaux du cadre non trouvés"}
    x0, x1 = colonnes[0][1] + 1, colonnes[-1][0] - 1
    lignes_v = np.where(vertical[:, colonnes[0][0]:colonnes[-1][1] + 1].sum(axis=1) > 0)[0]
    haut, bas = int(lignes_v.min()), int(lignes_v.max())
    marge = 10 * _echelle(vertical)
    centres = [((a + b) / 2, plein) for a, b, plein in liste_regles]
    # Haut du cadre : trait du haut s'il est au-dessus des traits verticaux (6A23111PE133
    # p. 15 : les séparateurs ne commencent que sous les pointillés de l'en-tête).
    haut = min([haut] + [y for y, _ in centres if y < haut])
    limite = haut + Config.LIGNES_PART_ENTETE_MAX * (bas - haut)
    sous_entete = [y for y, _ in centres if haut + marge < y < bas - marge]
    if not sous_entete or sous_entete[0] > limite:
        return {'zone': None, 'raison': "trait sous l'en-tête non trouvé dans le haut du cadre"}
    y0 = sous_entete[0]
    suivants = [y for y, plein in centres if plein and y > y0 + marge]
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
    vertical = traits_verticaux(noir)
    colonnes = _groupes(np.where(vertical.sum(axis=0) > 0)[0])
    liste = regles(noir, colonnes[0][1] + 1, colonnes[-1][0] - 1) if len(colonnes) >= 2 else []
    zone = zone_tableau(vertical, liste)
    if zone['raison']:
        return dict(sortie, raison=zone['raison'])
    x0, x1, y0, y1 = zone['zone']
    sortie['zone'] = zone['zone']
    traces = vertical.copy()
    for a, b, _ in liste:
        traces[a:b + 1, x0:x1] = 255
    traces = cv2.dilate(traces, np.ones((7, 7), np.uint8))
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


def decision_page(visibles: Optional[int], lues: int) -> Dict:
    """Décision pour une page seule : alerte (1 à LIGNES_ECART_ALERTE_MAX lignes d'écart),
    comptage incertain au-delà, rien si égal ou non compté."""
    if visibles is None or visibles == lues:
        return {'type': None, 'message': None}
    ecart = abs(visibles - lues)
    if ecart <= Config.LIGNES_ECART_ALERTE_MAX:
        return {'type': 'alerte', 'message': f"{visibles} lignes visibles, {lues} lues"}
    return {'type': 'incertain', 'message': (
        f"comptage incertain (écart de {ecart} lignes : {visibles} visibles, {lues} lues)")}


def decisions(pages: List[Dict]) -> Dict:
    """Alertes de page du contrôle du nombre de lignes, avec deux garde-fous.

    pages : [{'visibles': int ou None, 'lues': int}] d'un même document. Écart de 1 à
    LIGNES_ECART_ALERTE_MAX lignes : alerte ; au-delà, c'est presque toujours la zone qui est
    fausse : information « comptage incertain ». Plus de QUALITE_GARDE_FOU des pages comptées
    en écart : la mise en page trompe le compteur, une seule ligne de synthèse.
    Rend {'synthese': texte ou None, 'pages': [{'type': 'alerte'|'incertain'|None, 'message'}]}.
    """
    comptees = [p for p in pages if p.get('visibles') is not None]
    en_ecart = [p for p in comptees if p['visibles'] != p['lues']]
    sortie: Dict = {'synthese': None, 'pages': []}
    if comptees and len(en_ecart) / len(comptees) > Config.QUALITE_GARDE_FOU:
        sortie['synthese'] = (f"nombre de lignes : écart sur {len(en_ecart)} pages sur "
                              f"{len(comptees)}, mise en page non reconnue par le compteur, "
                              f"contrôle coupé pour ce document")
    for p in pages:
        sortie['pages'].append({'type': None, 'message': None} if sortie['synthese']
                               else decision_page(p.get('visibles'), p['lues']))
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
