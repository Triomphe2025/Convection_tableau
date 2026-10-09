"""
Contrôle d'une page scannée lue par Claude, à partir de la lecture Tesseract du commit A.

Indicateur de page : taux de divergence = mots Claude appariés (alignement du commit A :
lignes appariées, mots coupés aux traits, jumeaux par cellule) à un mot Tesseract de texte
différent / mots appariés. Au-dessus de PAGE_DEGRADEE, Tesseract lit trop mal la page pour
contrôler quoi que ce soit (mesure B0 : 18 à 50 % sur les scans de 223111PE011, 1 à 6 % sur
ceux de 6A23111PE133 et 223111PE012). La lecture de Claude n'est jamais modifiée.

Module pur : config, positions_scan et bibliothèque standard.
"""
from difflib import SequenceMatcher
from typing import Dict, List

from config import Config
from positions_scan import LecturePage, apparier_rangs, lignes_page, replier


def apparier_mots(cellule_claude: List[str], mots_tesseract: List[str]):
    """(Claude, Tesseract) appariés d'une cellule : identiques une fois repliés, ou de même
    rang dans un bloc différent de même longueur ; les autres restent seuls."""
    sm = SequenceMatcher(None, [replier(m) for m in cellule_claude],
                         [replier(m) for m in mots_tesseract], autojunk=False)
    paires = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal' or (op == 'replace' and i2 - i1 == j2 - j1):
            paires += [(i1 + d, j1 + d) for d in range(i2 - i1)]
    return paires


def analyser_page(rows: List[Dict], colonnes: List[str], lecture: LecturePage) -> Dict:
    """Taux de divergence Claude / Tesseract de la page et classement (dégradée ou non)."""
    page = lignes_page(lecture, colonnes)
    analyse = {'taux': None, 'degradee': False, 'divergences': 0, 'mots_apparies': 0,
               'raison': page['raison']}
    if page['raison']:
        return analyse
    lignes_t = page['lignes']
    _, paires = apparier_rangs(rows, lignes_t)
    for r, li in paires.items():
        row = rows[r]
        if row.get('type') != 'data':
            continue
        coupes = lignes_t[li][0]
        for k in range(len(colonnes)):
            claude = (row['cells'][k] if k < len(row['cells']) else '').split()
            tess = [t[0] for t in coupes if t[2] == k]
            for i, j in apparier_mots(claude, tess):
                analyse['mots_apparies'] += 1
                analyse['divergences'] += claude[i].upper() != tess[j].upper()
    if analyse['mots_apparies']:
        analyse['taux'] = analyse['divergences'] / analyse['mots_apparies']
        analyse['degradee'] = analyse['taux'] > Config.PAGE_DEGRADEE
    return analyse
