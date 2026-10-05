"""
Pied de page d'un tableau de câblage : lignes brutes → paires LIBELLÉ : valeur.

Module pur (config + bibliothèque standard), partagé par la lecture en grille
des pages vectorielles et par la lecture Claude : Claude recopie les lignes du
pied, ce module les structure. Aucune liste de libellés figée ; rien n'est
remplacé ni inventé : un texte libre qui ne suit aucun libellé va dans
COMPLEMENT, une valeur absente reste absente.
"""
import re
from typing import Dict, Iterable, List, Optional, Set

from config import Config

# Libellé = « N° PLAN » / « NO PLAN » ou un mot en capitales (points admis :
# « P.E.T. »), suivi de « : ». Pas précédé d'une lettre, d'un chiffre ou de « / »
# pour ne pas prendre la fin d'une valeur (« WPHR/TELMG TYPE : ») pour un libellé.
_LIBELLE_RE = re.compile(
    r"(?<![A-Za-z0-9/.\-°])"
    r"(N\s*°\s*PLAN|NO\.?\s+PLAN|[A-ZÀ-Ý][A-ZÀ-Ý.]+)\s*:"
)
_SEPARATEUR_RE = re.compile(r'^[\s|\-_=°.]*$')
_COMPTEUR_RE = re.compile(r'^\d+/\d+$')
_ESPACES_RE = re.compile(r'\s+')


def _compact(texte: str) -> str:
    return _ESPACES_RE.sub('', texte or '').upper()


def _lettres_logo(texte: str, libelle_gauche: str, seule_lettre: bool = False) -> List[str]:
    """Morceaux du bloc gauche du pied, tels qu'imprimés, si le texte en est un ; sinon [].

    Formes vues : libellé du modèle, mot seul en lettres (« SIEMENS » compact sur les
    pages vectorielles de 223111PE011, « MATRA » sur les pages TP2 de 223400PE137),
    lettres espacées (« M A T R A »), et — avec seule_lettre — une lettre isolée,
    morceau d'un logo vertical (scans de 223111PE011 : une lettre par ligne).
    Aucune conversion de forme : seuls les blancs entre morceaux sont ramenés à un.
    Un texte libre à garder en COMPLEMENT porte des chiffres (« REF CE 8707905 »).
    """
    t = texte.strip()
    mots = t.split()
    if not t:
        return []
    if libelle_gauche and _compact(t) == _compact(libelle_gauche):
        return mots
    if len(mots) == 1 and len(t) >= 3 and t.isalpha():
        return [t]
    if len(mots) >= 3 and all(len(m) == 1 and m.isalpha() for m in mots):
        return mots
    if seule_lettre and len(t) == 1 and t.isalpha():
        return [t]
    return []


def _separer_logo(lignes: Iterable[str], libelle_gauche: str):
    """(lignes du pied sans cadre ni logo, lettres du logo dans l'ordre de lecture)."""
    propres: List[str] = []
    lettres: List[str] = []
    for ligne in lignes:
        if not ligne or _SEPARATEUR_RE.match(ligne):
            continue
        texte = ligne.strip()
        if texte.startswith('|'):
            texte = texte[1:]
        if texte.endswith('|'):
            texte = texte[:-1]
        cellules = texte.split('|')
        while cellules:
            logo = _lettres_logo(cellules[0], libelle_gauche, seule_lettre=len(cellules) > 1)
            if cellules[0].strip() and not logo:
                break
            lettres.extend(logo)
            cellules.pop(0)
        texte = '|'.join(cellules).strip()
        # Logo vertical recopié sans cadre : « M   CABLE : ACC/PH01 ».
        m = re.match(r'([A-Z])\s+(?=' + _LIBELLE_RE.pattern + ')', texte)
        if m:
            lettres.append(m.group(1))
            texte = texte[m.end():]
        # Une fois cadre et logo retirés, « |  M A T R A  |-----| » n'est qu'un trait.
        if not texte or _SEPARATEUR_RE.match(texte):
            continue
        logo = _lettres_logo(texte, libelle_gauche, seule_lettre=True)
        if logo:
            lettres.extend(logo)
        else:
            propres.append(texte)
    return propres, lettres


def nettoyer_lignes_pied(lignes: Iterable[str], libelle_gauche: str = '') -> List[str]:
    """Lignes du pied sans cadre ni logo ; espaces intérieurs conservés tels quels."""
    return _separer_logo(lignes, libelle_gauche)[0]


def logo_pied(lignes: Iterable[str], libelle_gauche: str = '') -> str:
    """Bloc gauche tel qu'imprimé (« SIEMENS », « M A T R A ») ; vertical → « M A T R A » ; ''."""
    return ' '.join(_separer_logo(lignes, libelle_gauche)[1])


def cle_libelle(libelle: str) -> str:
    """Clé de métadonnée d'un libellé : « N° PLAN » → NO_PLAN, « P.E.T. » → PET."""
    compact = _compact(libelle).replace('°', 'O').replace('.', '')
    if compact in ('NOPLAN', 'NPLAN'):
        return 'NO_PLAN'
    return re.sub(r'[^A-Z0-9]+', '_', compact).strip('_')


def libelle_affiche(cle: str, libelles: Optional[Dict[str, str]] = None) -> str:
    """Libellé lisible d'une clé pour le journal : PET → « P.E.T. », NO_PLAN → « N° PLAN »."""
    if libelles and libelles.get(cle):
        return libelles[cle]
    return {'PET': 'P.E.T.', 'NO_PLAN': 'N° PLAN'}.get(cle, cle)


def mots_decor(formats: Iterable[str]) -> Set[str]:
    """Mots fixes des formats de pied du modèle (« JARRETIERAGE »), hors libellés."""
    decor: Set[str] = set()
    for fmt in formats:
        texte = _LIBELLE_RE.sub(' ', re.sub(r'\{[^}]*\}', ' ', fmt or ''))
        decor.update(m for m in re.findall(r'[A-ZÀ-Ý]{3,}', texte))
    return decor


def _texte_a_l_emplacement(segment: str, decor: Set[str]):
    """(mots de la valeur, texte posé après elle) d'un segment en fin de ligne.

    Le texte posé suit un grand blanc, ou est fait des mots fixes du modèle qui
    terminent le segment (Claude ramène les blancs à un).
    """
    morceaux = re.split(r'\s{%d,}' % Config.PIED_ECART_EMPLACEMENT, segment.strip())
    if len(morceaux) > 1:
        return morceaux[0].split(), ' '.join(' '.join(morceaux[1:]).split())
    mots = segment.split()
    k = len(mots)
    while k and mots[k - 1].upper() in decor:
        k -= 1
    return mots[:k], ' '.join(mots[k:])


def analyser_pied(lignes: Iterable[str],
                  libelles_un_mot: Optional[Iterable[str]] = None,
                  libelles_compteur: Optional[Iterable[str]] = None,
                  decor: Iterable[str] = (),
                  emplacements: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Toutes les paires LIBELLÉ : valeur des lignes, plus COMPLEMENT (texte libre).

    Les mots de decor (texte fixe imprimé par le modèle) ne sont ni une valeur
    ni un complément ; ils restent visibles dans les lignes brutes. Un texte sans
    libellé à l'emplacement d'un champ non imprimé (PIED_EMPLACEMENTS) est rendu
    sous EMPLACEMENT_<champ>.
    """
    decor = {d.upper() for d in decor}
    emplacements = Config.PIED_EMPLACEMENTS if emplacements is None else emplacements
    champ_apres = {cle_libelle(avant): champ for champ, avant in emplacements.items()}
    poses: Dict[str, str] = {}
    un_mot = {cle_libelle(x) for x in (
        Config.PIED_LIBELLES_UN_MOT if libelles_un_mot is None else libelles_un_mot)}
    compteur = {cle_libelle(x) for x in (
        Config.PIED_LIBELLES_COMPTEUR if libelles_compteur is None else libelles_compteur)}
    # « PAGE 32 » : le compteur se passe parfois du « : » (223400PE137, pages TP2).
    sans_deux_points = re.compile(
        r"(?<![A-Za-z0-9/.\-°])(" + '|'.join(re.escape(c) for c in sorted(compteur))
        + r")\s*:?\s*(?=\d)"
    ) if compteur else None
    meta: Dict[str, str] = {}
    complement: List[str] = []
    for ligne in lignes:
        texte = ligne.replace('|', '  ')
        trouves = sorted(
            list(_LIBELLE_RE.finditer(texte))
            + [m for m in (sans_deux_points.finditer(texte) if sans_deux_points else [])
               if not texte[m.end(1):m.end()].strip()],
            key=lambda m: m.start(),
        )
        trouves = [m for k, m in enumerate(trouves)
                   if k == 0 or m.start() >= trouves[k - 1].end()]
        avant = texte[:trouves[0].start()] if trouves else texte
        complement.extend(m for m in avant.split() if m.upper() not in decor)
        for k, m in enumerate(trouves):
            fin = trouves[k + 1].start() if k + 1 < len(trouves) else len(texte)
            cle = cle_libelle(m.group(1))
            segment = texte[m.end():fin]
            if cle in champ_apres and k == len(trouves) - 1 and cle not in un_mot:
                mots, pose = _texte_a_l_emplacement(segment, decor)
                if pose:
                    poses.setdefault(champ_apres[cle], pose)
            else:
                mots = segment.split()
            mots = [x for x in mots if x.upper() not in decor]
            if cle in un_mot:
                valeur, reste = mots[:1], mots[1:]
            else:
                valeur, reste = mots, []
                if cle not in compteur:
                    # Un « 8/10 » en fin de valeur est un diamètre, pas un compteur.
                    while valeur and _COMPTEUR_RE.match(valeur[-1]):
                        reste.insert(0, valeur.pop())
            # Première lecture conservée : un libellé répété ne l'écrase pas.
            if valeur and cle not in meta:
                meta[cle] = ' '.join(valeur)
            complement.extend(reste)
    for champ, pose in poses.items():
        if champ in meta:
            complement.append(pose)
        else:
            meta[f'EMPLACEMENT_{champ}'] = pose
    if complement:
        meta['COMPLEMENT'] = ' '.join(complement)
    return meta


def libelles_modele(formats: Iterable[str]) -> Dict[str, str]:
    """Libellé de chaque clé dans les formats de pied du modèle de sortie (« N° PLAN »)."""
    libelles: Dict[str, str] = {}
    for fmt in formats:
        for m in re.finditer(r'([^\s{}|:][^{}|:]*?)\s*:\s*\{(\w+)', fmt or ''):
            libelles.setdefault(m.group(2).upper(), ' '.join(m.group(1).split()))
    return libelles


def remplacer_libelles(lignes: List[str], libelles: Dict[str, str]) -> List[str]:
    """Libellés imprimés remplacés par ceux du modèle de sortie ; valeurs inchangées."""
    sortie = []
    for ligne in lignes:
        morceaux, debut = [], 0
        for m in _LIBELLE_RE.finditer(ligne):
            cle = cle_libelle(m.group(1))
            if cle in libelles:
                morceaux += [ligne[debut:m.start(1)], libelles[cle]]
                debut = m.end(1)
        sortie.append(''.join(morceaux) + ligne[debut:])
    return sortie


def remplacer_valeur(lignes: List[str], cle: str, valeur: str) -> List[str]:
    """Valeur d'un libellé remplacée (jusqu'au libellé ou au « | » suivant) ; reste inchangé."""
    sortie = list(lignes)
    for i, ligne in enumerate(sortie):
        trouves = list(_LIBELLE_RE.finditer(ligne))
        for k, m in enumerate(trouves):
            if cle_libelle(m.group(1)) != cle:
                continue
            fin = trouves[k + 1].start() if k + 1 < len(trouves) else len(ligne)
            segment = ligne[m.end():fin].split('|')[0]
            ancienne = segment.strip()
            if ancienne:
                depart = m.end() + segment.index(ancienne)
                sortie[i] = ligne[:depart] + valeur + ligne[depart + len(ancienne):]
            return sortie
    return sortie


def inserer_valeur(lignes: List[str], cle: str, libelle: str, valeur: str,
                   en_fin: bool = False) -> List[str]:
    """Lignes du pied avec la valeur posée après son libellé vide, ou ajoutée en fin de ligne.

    Sert à afficher une valeur reprise ou numérotée : le reste des lignes brutes est
    inchangé. Ajout en fin de 1re ligne, ou de la dernière avec en_fin (PAGE, qui
    suit N° PLAN et INDICE).
    """
    lignes = list(lignes)
    for i, ligne in enumerate(lignes):
        for m in _LIBELLE_RE.finditer(ligne):
            if cle_libelle(m.group(1)) == cle:
                lignes[i] = f"{ligne[:m.end()]} {valeur}{ligne[m.end():]}"
                return lignes
    ajout = f"{libelle} : {valeur}"
    if not lignes:
        return [ajout]
    k = -1 if en_fin else 0
    lignes[k] = f"{lignes[k]}     {ajout}"
    return lignes


def indices_revisions(lignes: Iterable[str]) -> List[str]:
    """Indices de la 1re colonne d'un tableau des révisions (page de garde), dans l'ordre."""
    entetes = tuple(e.upper() for e in Config.PIED_ENTETES_REVISIONS)
    indices: List[str] = []
    dans_tableau = False
    for ligne in lignes:
        mots = ligne.replace('|', ' ').split()
        if not mots:
            continue
        if mots[0].upper().startswith(entetes):
            dans_tableau = True
            continue
        premier = mots[0]
        if (dans_tableau and re.fullmatch(Config.PIED_INDICE_MOTIF, premier)
                and premier not in indices):
            indices.append(premier)
    return indices
