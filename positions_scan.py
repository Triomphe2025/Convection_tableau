"""
Positions d'origine des mots sur une page scannée (commit A).

Claude lit le contenu mais ramène les blancs à un : « PH A104 02 » au lieu de
« PH    A104      02 ». Ce module retrouve la colonne, en caractères, de chaque mot
lu, sans jamais changer un mot :
  page rendue à POSITIONS_DPI → mots bruts de Tesseract (boîtes, psm POSITIONS_PSM)
  → une grille de caractères par page (pas + phase, alignement circulaire des débuts)
  → mots coupés aux traits verticaux du cadre → lignes appariées (difflib, texte replié)
  → chaque mot lu prend la colonne de son jumeau Tesseract (exact, sinon par rang dans
  la cellule), un mot sans jumeau garde un espace après le précédent.
Colonne 0 d'une colonne du tableau = son caractère le plus à gauche sur la page, comme
dans le banc de mesure. N'importe pas ocr_processor : lecture distincte du moteur.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import median
from typing import Dict, List, Optional, Tuple

from config import Config
from relecture_scan import Mot, bornes_colonnes, mots_tesseract, traits_verticaux


@dataclass
class LecturePage:
    """Lecture Tesseract d'une page, gardée en cache pour la réutiliser sans 2e OCR."""

    mots: List[Mot]
    traits: Optional[List[float]]
    dpi: int
    taille: Tuple[int, int]

    def vers_dict(self) -> Dict:
        return {'mots': [list(m) for m in self.mots], 'traits': self.traits, 'dpi': self.dpi,
                'taille': list(self.taille)}

    @classmethod
    def depuis_dict(cls, donnees: Dict) -> 'LecturePage':
        traits = donnees.get('traits')
        return cls(mots=[tuple(m) for m in donnees['mots']],
                   traits=None if traits is None else list(traits),
                   dpi=donnees['dpi'], taille=tuple(donnees['taille']))


def dpi_de_rendu(largeur_pt: float, hauteur_pt: float) -> int:
    """POSITIONS_DPI pour une page A4, réduit pour une page plus grande (même nombre de pixels).

    223111PE012 p. 4 et 6 : mediabox 2481 × 3505 pt ; à 300 DPI l'image ferait
    10 337 × 14 604 px (lecture lente et mal calibrée pour Tesseract).
    """
    cote = max(largeur_pt, hauteur_pt)
    return max(1, round(Config.POSITIONS_DPI * min(1.0, Config.POSITIONS_COTE_A4_PT / cote)))


def lire_page(page) -> LecturePage:
    """Page PyMuPDF rendue à l'échelle d'un A4 à POSITIONS_DPI, lue par Tesseract."""
    import numpy as np
    from PIL import Image
    dpi = dpi_de_rendu(page.rect.width, page.rect.height)
    pix = page.get_pixmap(dpi=dpi)
    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    return LecturePage(mots=mots_tesseract(image, Config.POSITIONS_PSM),
                       traits=traits_verticaux(np.array(image.convert('L'))),
                       dpi=dpi, taille=(pix.width, pix.height))


def pas_initial(mots: List[Mot]) -> Optional[float]:
    """Pas estimé : pente de la largeur des boîtes selon le nombre de caractères.

    Largeur / nombre de caractères sous-estime le pas (la boîte du dernier caractère est
    plus étroite qu'un pas) d'une façon qui varie d'une page à l'autre (223111PE012 p. 6 :
    26,5 au lieu de 28,6) ; chaque caractère de plus ajoute, lui, exactement un pas.
    Médiane des pentes entre longueurs (au moins 3 mots par longueur), sinon médiane
    largeur / nombre de caractères.
    """
    par_longueur: Dict[int, List[float]] = {}
    for m in mots:
        if m[4].isalnum():
            par_longueur.setdefault(len(m[4]), []).append(m[2] - m[0])
    points = sorted((n, median(ls)) for n, ls in par_longueur.items() if len(ls) >= 3)
    pentes = [(l2 - l1) / (n2 - n1) for i, (n1, l1) in enumerate(points)
              for n2, l2 in points[i + 1:]]
    if pentes:
        return median(pentes)
    largeurs = [(m[2] - m[0]) / len(m[4]) for m in mots if len(m[4]) >= 2 and m[4].isalnum()]
    return median(largeurs) if largeurs else None


def ajuster_grille(debuts: List[float], pas_estime: float) -> Tuple[float, float]:
    """(pas, phase) de la grille qui aligne le mieux les débuts de mots modulo le pas."""
    import numpy as np
    x = np.asarray(debuts, dtype=float)
    n = round(Config.POSITIONS_MARGE_PAS / Config.POSITIONS_PRECISION_PAS)
    meilleur = (-1.0, pas_estime, 0.0)
    for k in range(-n, n + 1):
        pas = pas_estime * (1 + k * Config.POSITIONS_PRECISION_PAS)
        somme = np.exp(2j * np.pi * x / pas).sum()
        if abs(somme) > meilleur[0]:
            meilleur = (abs(somme), pas, (np.angle(somme) / (2 * np.pi)) * pas % pas)
    return meilleur[1], float(meilleur[2])


def colonne_caractere(x: float, pas: float, phase: float) -> int:
    """Colonne de la grille où tombe l'abscisse x."""
    return int(round((x - phase) / pas))


def couper_aux_traits(mots: List[Mot], traits: List[float], pas: float) -> List[Mot]:
    """Mots coupés aux traits du cadre qu'ils chevauchent (« 0281W|C107A », « 0815B/|RM »).

    Le trait occupe une colonne de caractère : la partie droite commence à la colonne
    qui le suit, et les caractères qui le figurent (« | », « / ») ne sont pas des mots.
    """
    sortie: List[Mot] = []
    for x0, y0, x1, y1, texte, conf in mots:
        for debut, morceau in _couper_morceau(x0, max(x1, x0 + len(texte) * pas), texte,
                                              traits, pas):
            sortie.extend(_couper_au_trait_lu(debut, y0, y1, morceau, conf, pas))
    return sortie


def _couper_morceau(x0, x1, texte, traits, pas) -> List[Tuple[float, str]]:
    for trait in traits:
        if not x0 + pas / 2 < trait < x1 - pas / 2:
            continue
        n = int(round((trait - x0) / pas))
        a = next((i for i in (n, n - 1, n + 1) if 0 <= i < len(texte)
                  and texte[i] in Config.POSITIONS_CARACTERES_TRAIT), None)
        if a is None:
            gauche, droite = texte[:n], texte[n:]
        else:
            b = a
            while b < len(texte) and texte[b] in Config.POSITIONS_CARACTERES_TRAIT:
                b += 1
            while a > 0 and texte[a - 1] in Config.POSITIONS_CARACTERES_TRAIT:
                a -= 1
            gauche, droite = texte[:a], texte[b:]
        suite = _couper_morceau(trait + pas / 2, x1, droite, traits, pas) if droite else []
        return ([(x0, gauche)] if gauche else []) + suite
    return [(x0, texte)]


def _couper_au_trait_lu(x0, y0, y1, texte, conf, pas) -> List[Mot]:
    """« | » lu hors d'un trait du cadre : coupé sur place, chaque caractère d'une colonne."""
    sortie, decalage = [], 0
    for morceau in texte.split('|'):
        if morceau:
            debut = x0 + decalage * pas
            sortie.append((debut, y0, debut + len(morceau) * pas, y1, morceau, conf))
        decalage += len(morceau) + 1
    return sortie


def replier(texte: str) -> str:
    """Texte comparable : confusions POSITIONS_REPLIS repliées, majuscules."""
    return ''.join(Config.POSITIONS_REPLIS.get(c, c) for c in texte).upper()


# ── Appariement des lignes ────────────────────────────────────────────

def _ressemblance(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _apparier_bloc(cles_c, cles_t, i0, j0) -> List[Tuple[int, int]]:
    """Appariement monotone de ressemblance totale maximale (seuil POSITIONS_SEUIL_LIGNE)."""
    n, m = len(cles_c), len(cles_t)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            r = _ressemblance(cles_c[i], cles_t[j])
            pris = r + score[i + 1][j + 1] if r >= Config.POSITIONS_SEUIL_LIGNE else -1.0
            score[i][j] = max(pris, score[i + 1][j], score[i][j + 1])
    paires, i, j = [], 0, 0
    while i < n and j < m:
        r = _ressemblance(cles_c[i], cles_t[j])
        if r >= Config.POSITIONS_SEUIL_LIGNE and score[i][j] == r + score[i + 1][j + 1]:
            paires.append((i0 + i, j0 + j))
            i, j = i + 1, j + 1
        elif score[i][j] == score[i + 1][j]:
            i += 1
        else:
            j += 1
    return paires


def apparier_lignes(cles_c: List[str], cles_t: List[str]) -> Dict[int, int]:
    """Ligne lue → ligne Tesseract : blocs identiques, puis ressemblance dans le reste."""
    paires: Dict[int, int] = {}
    sm = SequenceMatcher(None, cles_c, cles_t, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            paires.update(zip(range(i1, i2), range(j1, j2)))
        elif op == 'replace':
            paires.update(_apparier_bloc(cles_c[i1:i2], cles_t[j1:j2], i1, j1))
    return paires


# ── Jumeaux d'une ligne ───────────────────────────────────────────────

def _jumeaux_exacts(mots_c: List[str], mots_t: List[str]) -> Dict[int, int]:
    sm = SequenceMatcher(None, [replier(m) for m in mots_c], [replier(m) for m in mots_t],
                         autojunk=False)
    return {a.a + d: a.b + d for a in sm.get_matching_blocks() for d in range(a.size)}


def _placer_ligne(cellules: List[List[str]], tess: List[Tuple[str, int, int]], n: int,
                  traits: List[float]):
    """Mots d'une ligne de données placés : ([[mot, colonne, source]] par cellule, déplacés).

    tess : mots Tesseract (texte, colonne de grille, colonne du tableau), triés en x ;
    traits : abscisses des traits du cadre, en colonnes de la grille. Jumeau cherché
    d'abord dans la cellule (exact, puis par rang) ; seul un mot de bord resté sans
    jumeau peut passer dans la cellule voisine, où son jumeau exact est lu.
    """
    par_colonne = [[i for i, t in enumerate(tess) if t[2] == k] for k in range(n)]
    places: List[List[list]] = [[[w, None, None] for w in cellules[k]] for k in range(n)]
    utilises = set()
    for k in range(n):
        jumeaux = _jumeaux_exacts(cellules[k], [tess[i][0] for i in par_colonne[k]])
        for a, b in jumeaux.items():
            places[k][a][1:] = [tess[par_colonne[k][b]][1], 'exact']
            utilises.add(par_colonne[k][b])
    for k in range(n):
        if len(par_colonne[k]) != len(places[k]):
            continue
        for mot, i in zip(places[k], par_colonne[k]):
            if mot[1] is None and i not in utilises:
                mot[1:] = [tess[i][1], 'rang']
                utilises.add(i)
    deplaces = []
    for k in range(n):
        while k > 0 and places[k] and places[k][0][1] is None:
            i = _jumeau_voisin(places[k][0][0], par_colonne[k - 1], tess, utilises,
                               places[k - 1], vers_la_gauche=True, trait=traits[k])
            if i is None:
                break
            mot = places[k].pop(0)
            places[k - 1].append([mot[0], tess[i][1], 'exact'])
            utilises.add(i)
            deplaces.append((mot[0], k, k - 1))
        while k < n - 1 and places[k] and places[k][-1][1] is None:
            i = _jumeau_voisin(places[k][-1][0], par_colonne[k + 1], tess, utilises,
                               places[k + 1], vers_la_gauche=False, trait=traits[k + 1])
            if i is None:
                break
            mot = places[k].pop()
            places[k + 1].insert(0, [mot[0], tess[i][1], 'exact'])
            utilises.add(i)
            deplaces.append((mot[0], k, k + 1))
    return places, deplaces


def _jumeau_voisin(mot: str, candidats: List[int], tess, utilises, places_voisine,
                   vers_la_gauche: bool, trait: float) -> Optional[int]:
    """Jumeau exact libre du mot dans la colonne voisine, au bord qui la touche, ou None.

    Vers la gauche, le jumeau doit finir à POSITIONS_MARGE_DEBORDEMENT caractères au
    moins du trait : un mot imprimé à cheval sur le trait (223111PE011 p. 4, « PH » de
    TENANT) appartient à sa propre colonne.
    """
    libres = [i for i in candidats if i not in utilises and replier(tess[i][0]) == replier(mot)]
    if not libres:
        return None
    i = libres[-1] if vers_la_gauche else libres[0]
    occupees = [m[1] for m in places_voisine if m[1] is not None]
    if vers_la_gauche:
        if tess[i][1] + len(tess[i][0]) > trait - Config.POSITIONS_MARGE_DEBORDEMENT:
            return None
        if occupees and tess[i][1] <= max(occupees):
            return None
    elif occupees and tess[i][1] >= min(occupees):
        return None
    return i


def _placer_section(texte: str, tess: List[Tuple[str, int, int]]):
    mots = texte.split()
    jumeaux = _jumeaux_exacts(mots, [t[0] for t in tess])
    places = [[w, None, None] for w in mots]
    for i, t in jumeaux.items():
        places[i][1:] = [tess[t][1], 'exact']
    if len(mots) == len(tess):
        utilises = set(jumeaux.values())
        for i, mot in enumerate(places):
            if mot[1] is None and i not in utilises:
                mot[1:] = [tess[i][1], 'rang']
    return places


def _debuts(places: List[list], origine: int) -> List[int]:
    """Débuts depuis l'origine ; chaque mot laisse la place du précédent plus un espace."""
    debuts: List[int] = []
    minimum = 0
    for mot, colonne, _ in places:
        voulu = colonne - origine if colonne is not None else minimum
        debuts.append(max(voulu, minimum))
        minimum = debuts[-1] + len(mot) + 1
    return debuts


# ── Page ──────────────────────────────────────────────────────────────

def grouper_lignes_mots(mots: List[Mot]) -> List[List[Mot]]:
    """Mots regroupés en lignes par leur centre vertical, marques « | » seules écartées.

    Un trait isolé lu « | » (3 px de haut) fait dériver la moyenne glissante et coupe une
    ligne en deux (223111PE011 p. 52, ligne 1) : il n'est pas un mot.
    """
    lignes: List[List[Mot]] = []
    courante: List[Mot] = []
    ref = None
    for m in sorted((m for m in mots if m[4].strip('|')),
                    key=lambda m: ((m[1] + m[3]) / 2, m[0])):
        centre = (m[1] + m[3]) / 2
        if ref is None or abs(centre - ref) <= Config.POSITIONS_TOL_LIGNE:
            courante.append(m)
            ref = centre if ref is None else (ref + centre) / 2
        else:
            lignes.append(courante)
            courante, ref = [m], centre
    if courante:
        lignes.append(courante)
    return lignes


def _lignes_tesseract(lecture: LecturePage, bornes: List[float], pas: float, phase: float):
    """Par ligne de la page : (mots coupés aux traits avec leur colonne, mots bruts)."""
    lignes = []
    for ligne in grouper_lignes_mots(lecture.mots):
        ligne = sorted(ligne, key=lambda m: m[0])
        dans_cadre = [m for m in ligne if bornes[0] <= m[0] < bornes[-1]]
        coupes = []
        for m in couper_aux_traits(dans_cadre, bornes, pas):
            k = next((k for k in range(len(bornes) - 1) if bornes[k] <= m[0] < bornes[k + 1]),
                     None)
            if k is not None:
                coupes.append((m[4], colonne_caractere(m[0], pas, phase), k))
        bruts = [(m[4], colonne_caractere(m[0], pas, phase), 0) for m in dans_cadre]
        if coupes:
            lignes.append((coupes, bruts))
    return lignes


def _mots_ligne(row: Dict) -> List[str]:
    if row.get('type') == 'section':
        return (row.get('text') or '').split()
    return [w for c in row.get('cells', []) for w in (c or '').split()]


def placer_page(rows: List[Dict], colonnes: List[str],
                lecture: LecturePage) -> Tuple[List[Dict], Dict]:
    """Lignes lues avec 'debuts' {colonne: débuts des mots} ; bilan du placement.

    Le contenu ne change pas : seul un mot dont le jumeau est dans la colonne voisine
    passe dans cette cellule (bilan['deplaces']). Les lignes reçues ne sont pas modifiées.
    """
    bilan = {'exacts': 0, 'par_rang': 0, 'sans_jumeau': 0, 'deplaces': [],
             'lignes_sans_partenaire': 0, 'pas': None, 'raison': None}
    sortie = [dict(r) for r in rows]
    pas0 = pas_initial(lecture.mots)
    bornes = bornes_colonnes(lecture.traits, lecture.mots, colonnes) if lecture.mots else None
    if pas0 is None or bornes is None:
        bilan['raison'] = ("aucun mot lu par Tesseract" if pas0 is None
                           else "colonnes du cadre non trouvées")
        return sortie, bilan
    pas, phase = ajuster_grille([m[0] for m in lecture.mots], pas0)
    bilan['pas'] = pas
    lignes_t = _lignes_tesseract(lecture, bornes, pas, phase)
    traits = [(b - phase) / pas for b in bornes]
    a_placer = [i for i, r in enumerate(rows) if r.get('type') in ('data', 'section')
                and _mots_ligne(r)]
    cles_c = [replier(''.join(_mots_ligne(rows[i]))) for i in a_placer]
    cles_t = [replier(''.join(t[0] for t in coupes)) for coupes, _ in lignes_t]
    paires = apparier_lignes(cles_c, cles_t)
    bilan['lignes_sans_partenaire'] = len(a_placer) - len(paires)

    n = len(colonnes)
    placees: Dict[int, object] = {}
    for rang, i in enumerate(a_placer):
        if rang not in paires:
            continue
        coupes, bruts = lignes_t[paires[rang]]
        row = rows[i]
        if row.get('type') == 'section':
            placees[i] = _placer_section(row.get('text', ''), bruts)
            continue
        cellules = [(row['cells'][k] if k < len(row['cells']) else '').split() for k in range(n)]
        places, deplaces = _placer_ligne(cellules, coupes, n, traits)
        placees[i] = places
        for mot, de, vers in deplaces:
            bilan['deplaces'].append({'ligne': i + 1, 'mot': mot, 'de': colonnes[de],
                                      'vers': colonnes[vers]})

    origines = []
    for k in range(n):
        cols = [m[1] for i, p in placees.items() if rows[i].get('type') == 'data'
                for m in p[k] if m[1] is not None]
        origines.append(min(cols) if cols else 0)
    for i, places in placees.items():
        row = sortie[i]
        cellules = [places] if rows[i].get('type') == 'section' else places
        for mots in cellules:
            for m in mots:
                cle = {'exact': 'exacts', 'rang': 'par_rang', None: 'sans_jumeau'}[m[2]]
                bilan[cle] += 1
        if rows[i].get('type') == 'section':
            row['debuts'] = {0: _debuts(places, origines[0])}
            continue
        if any(len(places[k]) != len(rows[i]['cells'][k].split()) if k < len(rows[i]['cells'])
               else places[k] for k in range(n)):
            row['cells'] = [' '.join(m[0] for m in places[k]) for k in range(n)]
        row['debuts'] = {k: _debuts(places[k], origines[k]) for k in range(n) if places[k]}
    return sortie, bilan
