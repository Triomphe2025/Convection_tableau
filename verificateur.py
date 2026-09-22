"""Vérification de conversion : compare deux lectures d'un même tableau.

Module pur (bibliothèque standard + config) : aucun OCR, aucun PDF, aucun Excel.
Il reçoit deux listes de résultats au format pivot
    {'success', 'headers', 'rows': [{'type', 'cells', 'confidence'}], 'metadata'}
et retourne un rapport ; la fabrication des résultats est faite par converter.py.

Convention : `reference` est la lecture indépendante du scan (seule sa confiance
OCR sert d'arbitre), `converti` est la sortie à contrôler.
"""

import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from config import Config

IDENTIQUE = 'IDENTIQUE'
BENIN = 'BENIN'
A_VERIFIER = 'A_VERIFIER'

Distance = Callable[[str, str], int]


# ── Normalisation ─────────────────────────────────────────────────────

def normaliser(texte) -> str:
    """Majuscules, sans accents ni espaces : base de toute comparaison."""
    if not texte:
        return ''
    decompose = unicodedata.normalize('NFD', str(texte))
    sans_accents = ''.join(c for c in decompose if not unicodedata.combining(c))
    return ''.join(sans_accents.upper().split())


@lru_cache(maxsize=8)
def _table_repli(groupes: Tuple[str, ...]) -> Dict[str, str]:
    return {car: groupe[0] for groupe in groupes for car in groupe}


def plier_confusions(texte) -> str:
    """Normalise puis replie les confusions OCR (O/0, I/1/L, S/5...)."""
    repli = _table_repli(tuple(Config.VERIF_CONFUSIONS_OCR))
    return ''.join(repli.get(c, c) for c in normaliser(texte))


def similarite(a: Sequence, b: Sequence) -> float:
    """Ratio difflib (0-1) calculé SANS l'heuristique autojunk.

    Avec autojunk actif, difflib traite comme du bruit les éléments fréquents
    dès 200 éléments : deux lectures quasi identiques d'une même page réelle
    tombent à 0.78 au lieu de 0.98 (mesuré sur le cas 6A 23111PE102).
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _distance_par_defaut(a: str, b: str) -> int:
    """Distance d'insertion/suppression via difflib (repli si rien n'est injecté)."""
    blocs = SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return len(a) + len(b) - 2 * sum(bloc.size for bloc in blocs)


# ── Structures de résultat ────────────────────────────────────────────

@dataclass(frozen=True)
class Ecart:
    """Comparaison d'une cellule (ou de deux cellules voisines) entre les lectures."""

    page_ref: int
    page_conv: int
    ligne_ref: Optional[int]
    ligne_conv: Optional[int]
    colonne: str
    valeur_ref: str
    valeur_conv: str
    classe: str
    raison: str = ''
    confiance_ref: Optional[int] = None
    distance: Optional[int] = None
    nb_cellules: int = 1


@dataclass
class RapportVerification:
    """Bilan d'une vérification ; seuls les écarts A_VERIFIER remontent."""

    pages_appariees: List[Tuple[int, int]] = field(default_factory=list)
    pages_ref_orphelines: List[int] = field(default_factory=list)
    pages_conv_orphelines: List[int] = field(default_factory=list)
    nb_cellules: int = 0
    nb_identiques: int = 0
    nb_benins: int = 0
    a_verifier: List[Ecart] = field(default_factory=list)
    benins: List[Ecart] = field(default_factory=list)

    @property
    def nb_a_verifier(self) -> int:
        return sum(e.nb_cellules for e in self.a_verifier)

    @property
    def concordance(self) -> float:
        if not self.nb_cellules:
            return 1.0
        return (self.nb_identiques + self.nb_benins) / self.nb_cellules

    @property
    def fidele(self) -> bool:
        return self.concordance >= Config.VERIF_SEUIL_CONCORDANCE

    def ajouter(self, ecarts: Iterable[Ecart]) -> None:
        for e in ecarts:
            self.nb_cellules += e.nb_cellules
            if e.classe == IDENTIQUE:
                self.nb_identiques += e.nb_cellules
            elif e.classe == BENIN:
                self.nb_benins += e.nb_cellules
                self.benins.append(e)
            else:
                self.a_verifier.append(e)


# ── Sélection des données ─────────────────────────────────────────────

def _en_liste(pages, nom: str) -> List[dict]:
    if isinstance(pages, dict):
        return [pages]
    if isinstance(pages, (list, tuple)) and all(isinstance(p, dict) for p in pages):
        return list(pages)
    raise TypeError(
        f"{nom} : liste de résultats (dict) attendue, reçu {type(pages).__name__}"
    )


def _lignes_donnees(page: dict) -> List[dict]:
    """Lignes 'data' ayant au moins une cellule non vide."""
    return [
        r for r in page.get('rows', [])
        if r.get('type') == 'data'
        and any(str(c or '').strip() for c in r.get('cells', []))
    ]


def _signature_ligne(ligne: dict) -> str:
    # Concaténation sans frontières de colonnes : un découpage qui glisse
    # entre deux colonnes ne change pas la signature.
    return plier_confusions(''.join(str(c or '') for c in ligne.get('cells', [])))


def _pages_utiles(pages: List[dict]) -> List[int]:
    return [i for i, p in enumerate(pages) if p.get('success') and _lignes_donnees(p)]


# ── Appariement des pages ─────────────────────────────────────────────

@lru_cache(maxsize=200_000)
def _similarite_texte(a: str, b: str) -> float:
    return similarite(a, b)


def _similarite_pages(sig_r: List[str], sig_c: List[str]) -> float:
    """Similarité de deux pages : lignes identiques, ou lignes proches.

    Deux moteurs OCR lisent rarement toutes les lignes à l'identique : sans
    tolérance, une page mal lue ne serait jamais appariée, donc jamais vérifiée.
    """
    exacte = similarite(sig_r, sig_c)
    if exacte >= Config.VERIF_SEUIL_PAGE_EXACTE or not sig_r or not sig_c:
        return exacte
    court, long_ = (sig_r, sig_c) if len(sig_r) <= len(sig_c) else (sig_c, sig_r)
    meilleures = [max(_similarite_texte(a, b) for b in long_) for a in court]
    approchee = 2 * sum(meilleures) / (len(sig_r) + len(sig_c))
    return max(exacte, approchee)


def apparier_pages(reference, converti, seuil: Optional[float] = None):
    """Apparie les pages par contenu en conservant l'ordre.

    Retourne (paires, ref_sans_partenaire, conv_sans_partenaire), indices 0-based
    dans les listes d'origine. Les pages sans tableau (garde, sommaire) sont ignorées.
    """
    seuil = Config.VERIF_SEUIL_PAGE if seuil is None else seuil
    ref, conv = _en_liste(reference, 'reference'), _en_liste(converti, 'converti')
    ri, ci = _pages_utiles(ref), _pages_utiles(conv)
    sig_r = [[_signature_ligne(lg) for lg in _lignes_donnees(ref[i])] for i in ri]
    sig_c = [[_signature_ligne(lg) for lg in _lignes_donnees(conv[i])] for i in ci]
    n, m = len(ri), len(ci)
    sim = [[_similarite_pages(sig_r[a], sig_c[b]) for b in range(m)] for a in range(n)]

    # Programmation dynamique : appariement monotone de similarité totale maximale.
    total = [[0.0] * (m + 1) for _ in range(n + 1)]
    for a in range(n - 1, -1, -1):
        for b in range(m - 1, -1, -1):
            choix = [total[a + 1][b], total[a][b + 1]]
            if sim[a][b] >= seuil:
                choix.append(sim[a][b] + total[a + 1][b + 1])
            total[a][b] = max(choix)

    paires: List[Tuple[int, int]] = []
    a = b = 0
    while a < n and b < m:
        if sim[a][b] >= seuil and abs(
                sim[a][b] + total[a + 1][b + 1] - total[a][b]) < 1e-9:
            paires.append((ri[a], ci[b]))
            a, b = a + 1, b + 1
        elif abs(total[a + 1][b] - total[a][b]) < 1e-9:
            a += 1
        else:
            b += 1
    prises_r = {p[0] for p in paires}
    prises_c = {p[1] for p in paires}
    return (
        paires,
        [i for i in ri if i not in prises_r],
        [i for i in ci if i not in prises_c],
    )


# ── Alignement des lignes ─────────────────────────────────────────────

def _apparier_bloc(sig_r, sig_c, i1, i2, j1, j2, seuil):
    """Apparie, dans l'ordre, les lignes voisines mais lues différemment."""
    couples: List[Tuple[Optional[int], Optional[int]]] = []
    j = j1
    for i in range(i1, i2):
        cible, score = None, seuil
        for jj in range(j, j2):
            s = similarite(sig_r[i], sig_c[jj])
            if s >= score and (cible is None or s > score):
                cible, score = jj, s
        if cible is None:
            couples.append((i, None))
            continue
        couples.extend((None, k) for k in range(j, cible))
        couples.append((i, cible))
        j = cible + 1
    couples.extend((None, k) for k in range(j, j2))
    return couples


def aligner_lignes(lignes_ref, lignes_conv, seuil: Optional[float] = None):
    """Aligne les lignes par contenu (difflib), jamais par clé de borne.

    Une borne mal lue reste ainsi appariée à sa ligne. Retourne des couples
    (indice_ref | None, indice_conv | None) dans l'ordre du document.
    """
    seuil = Config.VERIF_SEUIL_LIGNE if seuil is None else seuil
    sig_r = [_signature_ligne(lg) for lg in lignes_ref]
    sig_c = [_signature_ligne(lg) for lg in lignes_conv]
    couples: List[Tuple[Optional[int], Optional[int]]] = []
    ops = SequenceMatcher(None, sig_r, sig_c, autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        if op == 'equal':
            couples.extend((i1 + k, j1 + k) for k in range(i2 - i1))
        elif op == 'delete':
            couples.extend((i, None) for i in range(i1, i2))
        elif op == 'insert':
            couples.extend((None, j) for j in range(j1, j2))
        else:
            couples.extend(_apparier_bloc(sig_r, sig_c, i1, i2, j1, j2, seuil))
    return couples


# ── Classement d'un écart ─────────────────────────────────────────────

def _raison_repli(a: str, b: str) -> str:
    """MISE_EN_FORME (espaces, casse, accents) ou CONFUSION_OCR (O/0, I/1...)."""
    return 'MISE_EN_FORME' if normaliser(a) == normaliser(b) else 'CONFUSION_OCR'


def _classer(vr: str, vc: str, conf: Optional[int], connu_r: bool, connu_c: bool,
             distance: Optional[Distance]) -> Tuple[str, str, Optional[int]]:
    """Coeur du classement, à partir de valeurs et d'indices déjà calculés."""
    if vr == vc:
        return IDENTIQUE, '', 0
    fr, fc = plier_confusions(vr), plier_confusions(vc)
    if fr == fc:
        return BENIN, _raison_repli(vr, vc), 0
    if not fr:
        return BENIN, 'REFERENCE_VIDE', None
    d = (distance or _distance_par_defaut)(fr, fc)
    if conf is not None and conf < Config.OCR_REOCR_THRESHOLD:
        return BENIN, 'CONFIANCE_BASSE', d
    moyenne = conf is not None and conf < Config.VERIF_CONFIANCE_SURE
    if moyenne and connu_c and not connu_r:
        return BENIN, 'REFERENCE_INCONNUE', d
    if moyenne and d <= Config.VERIF_DISTANCE_BENIGNE:
        return BENIN, 'ECART_MINEUR', d
    if not fc:
        return A_VERIFIER, 'CONTENU_PERDU', d
    return A_VERIFIER, ('CONVERTI_INCONNU' if connu_r and not connu_c else 'DIVERGENCE'), d


def classer_ecart(valeur_ref, valeur_conv, confiance_ref: Optional[int] = None,
                  connues: Optional[Set[str]] = None,
                  distance: Optional[Distance] = None) -> Tuple[str, str, Optional[int]]:
    """Classe un écart : retourne (classe, raison, distance).

    `connues` est un ensemble de valeurs déjà passées par `normaliser`.
    """
    vr, vc = str(valeur_ref or ''), str(valeur_conv or '')
    connu_c = bool(connues) and normaliser(vc) in connues
    connu_r = bool(connues) and normaliser(vr) in connues
    return _classer(vr, vc, confiance_ref, connu_r, connu_c, distance)


def _classer_region(seg_ref: str, seg_conv: str, conf: Optional[int],
                    connu_r: bool, connu_c: bool, distance: Optional[Distance]):
    # Un texte présent seulement dans le converti est d'abord un oubli de la
    # lecture du scan ; il ne redevient suspect que s'il n'est pas une valeur connue.
    if not seg_ref:
        if connu_c:
            return BENIN, 'REFERENCE_INCOMPLETE', len(seg_conv)
        return A_VERIFIER, 'AJOUT_CONVERTI', len(seg_conv)
    return _classer(seg_ref, seg_conv, conf, connu_r, connu_c, distance)


# ── Comparaison cellule par cellule ───────────────────────────────────

def _confiance(ligne: dict, k: int) -> Optional[int]:
    confs = ligne.get('confidence') or []
    if k < len(confs) and isinstance(confs[k], (int, float)):
        return int(confs[k])
    return None


def _moyenne(valeurs: List[Optional[int]]) -> Optional[int]:
    utiles = [v for v in valeurs if v is not None]
    return round(sum(utiles) / len(utiles)) if utiles else None


def _spans(textes: List[str]) -> List[Tuple[int, int]]:
    """Position (début, fin) de chaque cellule dans la ligne concaténée."""
    spans, debut = [], 0
    for texte in textes:
        spans.append((debut, debut + len(texte)))
        debut += len(texte)
    return spans


def _cellules_touchees(spans: List[Tuple[int, int]], debut: int, fin: int) -> List[int]:
    return [k for k, (a, b) in enumerate(spans) if a < fin and b > debut]


def _zones_divergentes(sr: str, sc: str) -> List[List[Tuple[int, int, int, int]]]:
    """Zones où les deux textes diffèrent ; chaque zone liste ses opérations (i1, i2, j1, j2).

    Les opérations séparées de moins de VERIF_FUSION_ECARTS caractères identiques
    forment une seule zone : un mot lu de travers donne un seul écart.
    """
    zones: List[List[Tuple[int, int, int, int]]] = []
    ops = SequenceMatcher(None, sr, sc, autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        if op == 'equal':
            continue
        if zones and i1 - zones[-1][-1][1] < Config.VERIF_FUSION_ECARTS:
            zones[-1].append((i1, i2, j1, j2))
        else:
            zones.append([(i1, i2, j1, j2)])
    return zones


def comparer_cellules(ligne_ref: dict, ligne_conv: dict,
                      colonnes: Optional[List[str]] = None,
                      connues: Optional[Dict[str, Set[str]]] = None,
                      distance: Optional[Distance] = None,
                      page_ref: int = 0, page_conv: int = 0,
                      num_ref: Optional[int] = None,
                      num_conv: Optional[int] = None) -> List[Ecart]:
    """Compare deux lignes appariées, sur la ligne entière puis colonne par colonne.

    Les deux lignes sont comparées concaténées : un texte qui glisse d'une
    colonne à l'autre (débordement) n'est pas une divergence. Seules les zones
    réellement différentes sont classées, puis rattachées à leurs colonnes.
    Une entrée par zone divergente et par cellule non vide sinon.
    """
    cr = [str(c or '') for c in ligne_ref.get('cells', [])]
    cc = [str(c or '') for c in ligne_conv.get('cells', [])]
    n = max(len(cr), len(cc))
    cr += [''] * (n - len(cr))
    cc += [''] * (n - len(cc))
    noms = list(colonnes or [])
    connues = connues or {}

    def nom(k: int) -> str:
        return noms[k] if k < len(noms) else f"COL{k + 1}"

    def ecart(ks, classe, raison, conf, dist, vr, vc):
        return Ecart(page_ref, page_conv, num_ref, num_conv,
                     '+'.join(nom(k) for k in ks), vr, vc, classe, raison,
                     conf, dist, len(ks))

    def connu(cellules: List[str], k: int) -> bool:
        ensemble = connues.get(nom(k).upper())
        return bool(ensemble) and normaliser(cellules[k]) in ensemble

    fr = [plier_confusions(c) for c in cr]
    fc = [plier_confusions(c) for c in cc]
    unites: List[Tuple[int, Ecart]] = []
    touchees: Set[int] = set()

    # Les cellules identiques servent d'ancres : le diff ne porte que sur les
    # suites de cellules qui diffèrent, sans entraîner leurs voisines.
    k = 0
    while k < n:
        if fr[k] == fc[k]:
            k += 1
            continue
        fin = k
        while fin + 1 < n and fr[fin + 1] != fc[fin + 1]:
            fin += 1
        run_r, run_c = fr[k:fin + 1], fc[k:fin + 1]
        sr, sc = ''.join(run_r), ''.join(run_c)
        if sr != sc:
            spans_r, spans_c = _spans(run_r), _spans(run_c)
            for ops in _zones_divergentes(sr, sc):
                kr = {k + x for i1, i2, _, _ in ops
                      for x in _cellules_touchees(spans_r, i1, i2)}
                kc = {k + x for _, _, j1, j2 in ops
                      for x in _cellules_touchees(spans_c, j1, j2)}
                ks = sorted(kr | kc) or [fin]
                touchees.update(ks)
                seg_r = sr[ops[0][0]:ops[-1][1]]
                seg_c = sc[ops[0][2]:ops[-1][3]]
                vr = ' '.join(cr[x] for x in ks if cr[x].strip())
                vc = ' '.join(cc[x] for x in ks if cc[x].strip())
                conf = _moyenne([_confiance(ligne_ref, x) for x in sorted(kr) or ks])
                connu_r = len(ks) == 1 and connu(cr, ks[0])
                connu_c = any(connu(cc, x) for x in ks)
                classe, raison, dist = _classer_region(
                    seg_r, seg_c, conf, connu_r, connu_c, distance)
                unites.append((ks[0], ecart(ks, classe, raison, conf, dist, vr, vc)))
        k = fin + 1

    for k in range(n):
        if k in touchees or (not cr[k].strip() and not cc[k].strip()):
            continue
        if cr[k] == cc[k]:
            unites.append((k, ecart([k], IDENTIQUE, '', None, 0, cr[k], cc[k])))
        elif fr[k] == fc[k]:
            raison = _raison_repli(cr[k], cc[k])
            unites.append((k, ecart([k], BENIN, raison, None, 0, cr[k], cc[k])))
        else:
            unites.append((k, ecart([k], BENIN, 'DEBORDEMENT_COLONNE', None, 0,
                                    cr[k], cc[k])))
    unites.sort(key=lambda u: u[0])
    return [e for _, e in unites]


def _ecart_orphelin(ligne: dict, cote: str, page_ref: int, page_conv: int,
                    num: int) -> Ecart:
    """Ligne présente d'un seul côté : manquante (scan) ou en trop (converti)."""
    cellules = [str(c or '') for c in ligne.get('cells', [])]
    texte = ' '.join(c for c in cellules if c.strip())
    nb = sum(1 for c in cellules if c.strip())
    dans_ref = cote == 'ref'
    conf = _moyenne([_confiance(ligne, k) for k in range(len(cellules))]) if dans_ref else None
    alnum = sum(1 for c in normaliser(texte) if c.isalnum())
    if alnum < Config.VERIF_LIGNE_BRUIT_MIN_CARS:
        classe, raison = BENIN, 'LIGNE_BRUIT'
    elif dans_ref and conf is not None and conf < Config.OCR_REOCR_THRESHOLD:
        classe, raison = BENIN, 'CONFIANCE_BASSE'
    else:
        classe, raison = A_VERIFIER, 'LIGNE_MANQUANTE' if dans_ref else 'LIGNE_EN_TROP'
    return Ecart(
        page_ref, page_conv, num if dans_ref else None, None if dans_ref else num,
        '(ligne)', texte if dans_ref else '', '' if dans_ref else texte,
        classe, raison, conf, None, max(nb, 1),
    )


# ── Vérification complète ─────────────────────────────────────────────

def verifier(reference, converti, colonnes: Optional[List[str]] = None,
             valeurs_connues: Optional[Dict[str, Iterable[str]]] = None,
             distance: Optional[Distance] = None) -> RapportVerification:
    """Compare deux lectures d'un même document et classe chaque divergence.

    reference, converti : liste de résultats pivot (un par page) ou un seul dict.
    valeurs_connues     : {colonne: valeurs valides}, ex. data_dictionary.json.
    distance            : fonction d'édition injectée (ex. _levenshtein).
    """
    ref, conv = _en_liste(reference, 'reference'), _en_liste(converti, 'converti')
    connues = {
        col.upper(): {normaliser(v) for v in vals}
        for col, vals in (valeurs_connues or {}).items()
    }
    paires, ref_orph, conv_orph = apparier_pages(ref, conv)
    rapport = RapportVerification(
        pages_appariees=[(a + 1, b + 1) for a, b in paires],
        pages_ref_orphelines=[i + 1 for i in ref_orph],
        pages_conv_orphelines=[i + 1 for i in conv_orph],
    )
    for ir, ic in paires:
        noms = colonnes or ref[ir].get('headers') or conv[ic].get('headers') or []
        lr, lc = _lignes_donnees(ref[ir]), _lignes_donnees(conv[ic])
        for a, b in aligner_lignes(lr, lc):
            if a is not None and b is not None:
                rapport.ajouter(comparer_cellules(
                    lr[a], lc[b], noms, connues, distance, ir + 1, ic + 1, a + 1, b + 1))
            elif a is not None:
                rapport.ajouter([_ecart_orphelin(lr[a], 'ref', ir + 1, ic + 1, a + 1)])
            else:
                rapport.ajouter([_ecart_orphelin(lc[b], 'conv', ir + 1, ic + 1, b + 1)])
    return rapport


def formater_rapport(rapport: RapportVerification,
                     max_ecarts: Optional[int] = None) -> str:
    """Texte lisible du rapport (interface et ligne de commande)."""
    lignes = [
        f"Pages appariées : {len(rapport.pages_appariees)} "
        f"(scan sans partenaire : {rapport.pages_ref_orphelines or 'aucune'} ; "
        f"converti sans partenaire : {rapport.pages_conv_orphelines or 'aucune'})",
        f"Cellules comparées : {rapport.nb_cellules} — identiques {rapport.nb_identiques}, "
        f"bénignes {rapport.nb_benins}, à vérifier {rapport.nb_a_verifier} — "
        f"concordance {rapport.concordance * 100:.1f} %",
    ]
    ecarts = rapport.a_verifier if max_ecarts is None else rapport.a_verifier[:max_ecarts]
    if not rapport.a_verifier:
        lignes.append("Aucune divergence à vérifier.")
    else:
        lignes.append(f"À VÉRIFIER ({len(rapport.a_verifier)}) :")
    for e in ecarts:
        lignes.append(
            f"  page scan {e.page_ref} / converti {e.page_conv}, "
            f"ligne {e.ligne_ref or e.ligne_conv}, {e.colonne} : "
            f"scan « {e.valeur_ref} » ≠ converti « {e.valeur_conv} » "
            f"[{e.raison}, confiance scan {e.confiance_ref}, distance {e.distance}]"
        )
    return '\n'.join(lignes)
