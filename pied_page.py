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


def _est_logo(texte: str, libelle_gauche: str) -> bool:
    """Bloc gauche du pied : libellé du modèle ou logo en lettres espacées (« M A T R A »)."""
    t = texte.strip()
    if not t:
        return False
    if libelle_gauche and _compact(t) == _compact(libelle_gauche):
        return True
    mots = t.split()
    # Un mot seul en lettres (« MATRA », « SIEMENS ») est une marque ; un texte
    # libre à garder en COMPLEMENT porte des chiffres (« REF CE 8707905 »).
    if len(mots) == 1 and len(t) >= 3 and t.isalpha():
        return True
    return len(mots) >= 3 and all(len(m) == 1 and m.isalpha() for m in mots)


def nettoyer_lignes_pied(lignes: Iterable[str], libelle_gauche: str = '') -> List[str]:
    """Lignes du pied sans cadre ni logo ; espaces intérieurs conservés tels quels."""
    propres = []
    for ligne in lignes:
        if not ligne or _SEPARATEUR_RE.match(ligne):
            continue
        texte = ligne.strip()
        if texte.startswith('|'):
            texte = texte[1:]
        if texte.endswith('|'):
            texte = texte[:-1]
        cellules = texte.split('|')
        while cellules and (not cellules[0].strip()
                            or _est_logo(cellules[0], libelle_gauche)):
            cellules.pop(0)
        texte = '|'.join(cellules).strip()
        # Une fois cadre et logo retirés, « |  M A T R A  |-----| » n'est qu'un trait.
        if texte and not _SEPARATEUR_RE.match(texte) and not _est_logo(texte, libelle_gauche):
            propres.append(texte)
    return propres


def cle_libelle(libelle: str) -> str:
    """Clé de métadonnée d'un libellé : « N° PLAN » → NO_PLAN, « P.E.T. » → PET."""
    compact = _compact(libelle).replace('°', 'O').replace('.', '')
    if compact in ('NOPLAN', 'NPLAN'):
        return 'NO_PLAN'
    return re.sub(r'[^A-Z0-9]+', '_', compact).strip('_')


def mots_decor(formats: Iterable[str]) -> Set[str]:
    """Mots fixes des formats de pied du modèle (« JARRETIERAGE »), hors libellés."""
    decor: Set[str] = set()
    for fmt in formats:
        texte = _LIBELLE_RE.sub(' ', re.sub(r'\{[^}]*\}', ' ', fmt or ''))
        decor.update(m for m in re.findall(r'[A-ZÀ-Ý]{3,}', texte))
    return decor


def analyser_pied(lignes: Iterable[str],
                  libelles_un_mot: Optional[Iterable[str]] = None,
                  libelles_compteur: Optional[Iterable[str]] = None,
                  decor: Iterable[str] = ()) -> Dict[str, str]:
    """Toutes les paires LIBELLÉ : valeur des lignes, plus COMPLEMENT (texte libre).

    Les mots de decor (texte fixe imprimé par le modèle) ne sont ni une valeur
    ni un complément ; ils restent visibles dans les lignes brutes.
    """
    decor = {d.upper() for d in decor}
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
            mots = [x for x in texte[m.end():fin].split() if x.upper() not in decor]
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
    if complement:
        meta['COMPLEMENT'] = ' '.join(complement)
    return meta


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
