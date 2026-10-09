"""
Contrôle d'une page scannée lue par Claude, à partir de la lecture Tesseract du commit A.

Indicateur de page : taux de divergence = mots Claude appariés (alignement du commit A :
lignes appariées, mots coupés aux traits, jumeaux par cellule) à un mot Tesseract de texte
différent / mots appariés. Au-dessus de PAGE_DEGRADEE, Tesseract lit trop mal la page pour
contrôler quoi que ce soit (mesure B0 : 18 à 50 % sur les scans de 223111PE011, 1 à 6 % sur
ceux de 6A23111PE133 et 223111PE012).

Contrôle de conservation (CONTROLE_CONSERVATION, pages non dégradées) : un mot Tesseract
(confiance ≥ CONSERVATION_CONFIANCE_MIN) sans mot Claude en face est un élément peut-être
omis de sa cellule ; une ligne Tesseract de la zone du tableau sans ligne Claude est une
ligne peut-être manquante. La lecture de Claude n'est jamais modifiée.

Module pur : config, positions_scan et bibliothèque standard.
"""
from difflib import SequenceMatcher
from statistics import median
from typing import Dict, List

from config import Config
from positions_scan import LecturePage, apparier_rangs, lignes_page, replier


def apparier_mots(cellule_claude: List[str], mots_tesseract: List[str]):
    """(Claude, Tesseract) appariés d'une cellule et indices Tesseract couverts.

    Appariés : identiques une fois repliés, ou de même rang dans un bloc différent de
    même longueur. Couverts sans paire : un bloc Tesseract égal, une fois recollé, au bloc
    Claude d'en face (« 1B » pour « 1 B ») — rien n'y manque.
    """
    sm = SequenceMatcher(None, [replier(m) for m in cellule_claude],
                         [replier(m) for m in mots_tesseract], autojunk=False)
    paires, couverts = [], set()
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal' or (op == 'replace' and i2 - i1 == j2 - j1):
            paires += [(i1 + d, j1 + d) for d in range(i2 - i1)]
            couverts.update(range(j1, j2))
        elif (replier(''.join(cellule_claude[i1:i2]))
              == replier(''.join(mots_tesseract[j1:j2]))):
            couverts.update(range(j1, j2))
    return paires, couverts


def _texte_ligne(row: Dict) -> str:
    if row.get('type') == 'section':
        return ' '.join((row.get('text') or '').split())
    return ' | '.join(' '.join((c or '').split()) for c in row.get('cells', []))


def analyser_page(rows: List[Dict], colonnes: List[str], lecture: LecturePage) -> Dict:
    """Taux de divergence et classement de la page ; omissions et lignes manquantes.

    omissions : {ligne (indice dans rows), colonne (indice), lecture, confiance} ;
    lignes_manquantes : {avant, apres (indices dans rows ou None), lecture, confiance}.
    """
    page = lignes_page(lecture, colonnes)
    analyse = {'taux': None, 'degradee': False, 'divergences': 0, 'mots_apparies': 0,
               'raison': page['raison'], 'controle_impossible': False, 'omissions': [],
               'lignes_manquantes': []}
    if page['raison']:
        return analyse
    lignes_t = page['lignes']
    _, paires = apparier_rangs(rows, lignes_t)
    libres_par_cellule: Dict[tuple, List[tuple]] = {}
    for r, li in paires.items():
        row = rows[r]
        if row.get('type') != 'data':
            continue
        coupes = lignes_t[li][0]
        for k in range(len(colonnes)):
            claude = (row['cells'][k] if k < len(row['cells']) else '').split()
            tess = [t for t in coupes if t[2] == k]
            appariees, couverts = apparier_mots(claude, [t[0] for t in tess])
            for i, j in appariees:
                analyse['mots_apparies'] += 1
                analyse['divergences'] += claude[i].upper() != tess[j][0].upper()
            libres_par_cellule[(r, k)] = [t for j, t in enumerate(tess) if j not in couverts]
    if analyse['mots_apparies']:
        analyse['taux'] = analyse['divergences'] / analyse['mots_apparies']
        analyse['degradee'] = analyse['taux'] > Config.PAGE_DEGRADEE
    if not Config.CONTROLE_CONSERVATION:
        return analyse
    if analyse['degradee']:
        analyse['controle_impossible'] = True
        return analyse
    seuil = Config.CONSERVATION_CONFIANCE_MIN
    for (r, k), libres in sorted(libres_par_cellule.items()):
        surs = [t for t in libres if t[3] >= seuil]
        if surs:
            analyse['omissions'].append({'ligne': r, 'colonne': k,
                                         'lecture': ' '.join(t[0] for t in surs),
                                         'confiance': min(t[3] for t in surs)})
    analyse['lignes_manquantes'] = _lignes_manquantes(rows, lignes_t, paires, seuil)
    return analyse


def _lignes_manquantes(rows, lignes_t, paires, seuil) -> List[Dict]:
    """Lignes Tesseract de la zone du tableau sans ligne Claude, entre leurs voisines lues."""
    def y(li):
        return median(t[4] for t in lignes_t[li][0])

    appariees = sorted(((y(li), r) for r, li in paires.items()))
    if not appariees:
        return []
    haut, bas = appariees[0][0], appariees[-1][0]
    prises = set(paires.values())
    manquantes = []
    for li, (coupes, _) in enumerate(lignes_t):
        if li in prises or not haut < y(li) < bas:
            continue
        confiance = median(t[3] for t in coupes)
        if confiance < seuil:
            continue
        avant = max((r for yy, r in appariees if yy < y(li)), default=None,
                    key=lambda r: paires[r])
        apres = min((r for yy, r in appariees if yy > y(li)), default=None,
                    key=lambda r: paires[r])
        manquantes.append({'avant': avant, 'apres': apres, 'confiance': confiance,
                           'lecture': ' '.join(t[0] for t in coupes)})
    return manquantes


def texte_ligne(rows: List[Dict], r) -> str:
    """Texte d'une ligne lue pour les messages (« 01 | PH A104 01 | … »), vide si None."""
    return _texte_ligne(rows[r]) if r is not None else ''
