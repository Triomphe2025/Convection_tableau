"""Mesure de précision : compare une sortie .xlsx à une référence organisée.

Module pur (bibliothèque standard + config) : aucun OCR, aucun PDF, aucun Excel.
Il reçoit deux listes de pages au format pivot
    {'success', 'rows': [{'type', 'cells', 'confidence'}], 'metadata', 'pied_texte'}
('pied_texte' : lignes de texte brut du pied de page, une entrée par ligne
physique) et retourne une synthèse + la liste des écarts ; la lecture des
fichiers (.xlsx, PDF vectoriel, Excel de vérité terrain) est faite par
mesurer_precision.py.

Complémentaire de verificateur.py : cet outil compare à une vérité terrain
préparée à l'avance (pas une relecture indépendante du même scan) — utile
pour mesurer la précision du pipeline sur un jeu de test connu et suivre les
progrès de version en version, pas pour contrôler une conversion en direct
sur un document client quelconque.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from config import Config
from verificateur import normaliser, similarite

IDENTIQUE = 'IDENTIQUE'
ESPACEMENT = 'ESPACEMENT'
CONFUSION = 'CONFUSION'
CONTENU_DIFFERENT = 'CONTENU_DIFFERENT'
MANQUANT = 'MANQUANT'
AJOUTE = 'AJOUTE'

_LIGNE_MANQUANTE = 'MANQUANTE'
_LIGNE_EN_TROP = 'EN_TROP'


# ── Structures de résultat ────────────────────────────────────────────

@dataclass(frozen=True)
class EcartCellule:
    """Comparaison d'une cellule entre la référence et la sortie mesurée."""

    page_ref: int
    page_conv: int
    ligne_ref: int
    ligne_conv: int
    colonne: str
    valeur_ref: str
    valeur_conv: str
    classe: str


@dataclass(frozen=True)
class EcartPied:
    """Comparaison d'un libellé de pied de page entre les deux lectures."""

    page_ref: int
    page_conv: int
    libelle: str
    valeur_ref: str
    valeur_conv: str


@dataclass(frozen=True)
class EcartPosition:
    """Colonne de départ différente pour une cellule pourtant identique.

    Ne survient que si la référence préserve la géométrie exacte (PDF
    vectoriel reconstruit en grille) : `page_ref['rows'][i]['exact']` est vrai.
    """

    page_ref: int
    page_conv: int
    ligne_ref: int
    ligne_conv: int
    colonne: str
    decalages_ref: Tuple[int, ...]
    decalages_conv: Tuple[int, ...]


@dataclass(frozen=True)
class LigneOrpheline:
    """Ligne présente d'un seul côté après alignement."""

    cote: str  # _LIGNE_MANQUANTE ou _LIGNE_EN_TROP
    page: int
    ligne: int
    contenu: str


@dataclass
class RapportMesure:
    """Bilan d'une mesure de précision sur un document connu."""

    pages_appariees: List[Tuple[int, int]] = field(default_factory=list)
    pages_ref_orphelines: List[int] = field(default_factory=list)
    pages_conv_orphelines: List[int] = field(default_factory=list)
    lignes_orphelines: List[LigneOrpheline] = field(default_factory=list)
    ecarts_cellules: List[EcartCellule] = field(default_factory=list)
    ecarts_pieds: List[EcartPied] = field(default_factory=list)
    ecarts_positions: List[EcartPosition] = field(default_factory=list)
    nb_cellules_comparees: int = 0
    nb_cellules_identiques: int = 0

    @property
    def precision(self) -> float:
        if not self.nb_cellules_comparees:
            return 1.0
        return self.nb_cellules_identiques / self.nb_cellules_comparees

    def cellules_par_classe(self) -> Dict[str, int]:
        compte: Dict[str, int] = {}
        for e in self.ecarts_cellules:
            compte[e.classe] = compte.get(e.classe, 0) + 1
        return compte


# ── Normalisation locale ──────────────────────────────────────────────

def _espace(texte) -> str:
    """Réduit les espaces multiples à un seul, sans autre normalisation.

    Volontairement plus léger que `verificateur.normaliser` : la casse et les
    accents font partie de ce qu'on veut détecter comme écart de contenu.
    """
    return ' '.join((texte or '').split())


def _decalages(texte) -> Tuple[int, ...]:
    """Position de départ de chaque mot, relative à l'indentation de la cellule."""
    texte = (texte or '').rstrip()
    tete = len(texte) - len(texte.lstrip())
    return tuple(m.start() - tete for m in re.finditer(r'\S+', texte))


def _lignes_donnees(page: dict) -> List[dict]:
    return [
        ligne for ligne in page.get('rows', [])
        if ligne.get('type') == 'data' and any((c or '').strip() for c in ligne.get('cells', []))
    ]


def _signature_ligne(ligne: dict) -> str:
    return ' | '.join(normaliser(c) for c in ligne.get('cells', []))


def _mots_page(page: dict) -> Set[str]:
    return {
        mot for ligne in _lignes_donnees(page) for c in ligne.get('cells', [])
        for mot in re.findall(r'\w+', (c or '').upper())
    }


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _pages_utiles(pages: List[dict]) -> List[int]:
    """Pages à apparier : avec des lignes de données OU un pied de page.

    Une page « réserve » sans câblage (donc sans ligne de données) mais avec
    un pied de page réel doit quand même pouvoir être signalée absente côté
    converti — contrairement à verificateur.py, qui ne compare pas les pieds.
    """
    return [
        i for i, p in enumerate(pages)
        if p.get('success') and (_lignes_donnees(p) or p.get('pied_texte'))
    ]


# ── Appariement des pages par contenu ─────────────────────────────────

@lru_cache(maxsize=200_000)
def _similarite_texte(a: str, b: str) -> float:
    return similarite(a, b)


def _similarite_pages(sig_r: List[str], sig_c: List[str]) -> float:
    exacte = similarite(sig_r, sig_c)
    if exacte >= Config.MESURE_SEUIL_PAGE_EXACTE or not sig_r or not sig_c:
        return exacte
    court, long_ = (sig_r, sig_c) if len(sig_r) <= len(sig_c) else (sig_c, sig_r)
    meilleures = [max(_similarite_texte(a, b) for b in long_) for a in court]
    approchee = 2 * sum(meilleures) / (len(sig_r) + len(sig_c))
    return max(exacte, approchee)


def apparier_pages_par_contenu(
    reference: List[dict], converti: List[dict], seuil: Optional[float] = None,
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """Apparie les pages par CONTENU — ni par numéro, ni par position.

    Le numéro peut différer (la vérité nomme « 122a » une page que la sortie
    nomme « 128 ») et l'ordre aussi (la sortie la range en fin de document) :
    une contrainte d'ordre laisserait alors une des deux pages croisées sans
    partenaire. Appariement glouton sur la meilleure similarité ; à égalité,
    la paire la plus proche en rang l'emporte. Retourne (paires triées par
    page de référence, ref_sans_partenaire, conv_sans_partenaire), indices
    0-based dans les listes d'origine.
    """
    seuil = Config.MESURE_SEUIL_PAGE if seuil is None else seuil
    ri, ci = _pages_utiles(reference), _pages_utiles(converti)
    sig_r = [[_signature_ligne(lg) for lg in _lignes_donnees(reference[i])] for i in ri]
    sig_c = [[_signature_ligne(lg) for lg in _lignes_donnees(converti[i])] for i in ci]
    mots_r = [_mots_page(reference[i]) for i in ri]
    mots_c = [_mots_page(converti[i]) for i in ci]
    candidats = []
    for a in range(len(ri)):
        # Similarité fine (ligne à ligne) seulement sur les pages converties qui
        # partagent le plus de mots : sinon 48 × 48 pages × 55 × 55 lignes sur
        # 223400PE137, soit ~7 millions de comparaisons. Une page mal lue garde
        # l'essentiel de ses mots, son vrai partenaire reste parmi les premiers.
        proches = sorted(
            range(len(ci)), key=lambda b: (-_jaccard(mots_r[a], mots_c[b]), abs(a - b)),
        )[:Config.MESURE_CANDIDATS_PAGE]
        for b in proches:
            s = _similarite_pages(sig_r[a], sig_c[b])
            if s >= seuil:
                candidats.append((-s, abs(a - b), a, b))
    candidats.sort()

    paires: List[Tuple[int, int]] = []
    prises_a: Set[int] = set()
    prises_b: Set[int] = set()
    for _, _, a, b in candidats:
        if a in prises_a or b in prises_b:
            continue
        paires.append((ri[a], ci[b]))
        prises_a.add(a)
        prises_b.add(b)
    paires.sort()
    prises_r = {p[0] for p in paires}
    prises_c = {p[1] for p in paires}
    return (
        paires,
        [i for i in ri if i not in prises_r],
        [i for i in ci if i not in prises_c],
    )


# ── Alignement des lignes : difflib puis Needleman-Wunsch ────────────

def _nw(a: List[str], b: List[str]) -> List[Tuple[Optional[int], Optional[int]]]:
    """Alignement optimal (Needleman-Wunsch) de deux petits blocs de lignes."""
    n, m = len(a), len(b)
    if n * m > Config.MESURE_NW_MAX_PAIRES:
        return [(i, i if i < m else None) for i in range(n)] + [(None, j) for j in range(n, m)]
    gap = Config.MESURE_PENALITE_GAP
    bonus = Config.MESURE_BONUS_APPARIEMENT
    sim = [[similarite(x, y) for y in b] for x in a]
    f = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        f[i][0] = i * gap
    for j in range(1, m + 1):
        f[0][j] = j * gap
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            f[i][j] = max(
                f[i - 1][j - 1] + sim[i - 1][j - 1] - bonus,
                f[i - 1][j] + gap,
                f[i][j - 1] + gap,
            )
    couples: List[Tuple[Optional[int], Optional[int]]] = []
    i, j = n, m
    while i or j:
        if i and j and abs(f[i][j] - (f[i - 1][j - 1] + sim[i - 1][j - 1] - bonus)) < 1e-9:
            couples.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and abs(f[i][j] - (f[i - 1][j] + gap)) < 1e-9:
            couples.append((i - 1, None))
            i -= 1
        else:
            couples.append((None, j - 1))
            j -= 1
    return couples[::-1]


def aligner_lignes(
    lignes_ref: List[dict], lignes_conv: List[dict],
) -> List[Tuple[Optional[int], Optional[int]]]:
    """Aligne les lignes par contenu : difflib pour les blocs identiques,
    Needleman-Wunsch pour affiner l'appariement dans les blocs différents.
    """
    sig_r = [_signature_ligne(lg) for lg in lignes_ref]
    sig_c = [_signature_ligne(lg) for lg in lignes_conv]
    couples: List[Tuple[Optional[int], Optional[int]]] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, sig_r, sig_c, autojunk=False).get_opcodes():
        if op == 'equal':
            couples.extend(zip(range(i1, i2), range(j1, j2)))
        else:
            for i, j in _nw(sig_r[i1:i2], sig_c[j1:j2]):
                couples.append((None if i is None else i1 + i, None if j is None else j1 + j))
    return couples


# ── Classement d'une cellule ──────────────────────────────────────────

@lru_cache(maxsize=4)
def _table_confusions(paires: Tuple[str, ...]) -> Set[FrozenSet[str]]:
    return {frozenset(p) for p in paires}


def classer_cellule(valeur_ref, valeur_conv) -> str:
    """Classe l'écart entre deux valeurs de cellule déjà mises en regard."""
    a, b = _espace(valeur_ref), _espace(valeur_conv)
    if a == b:
        return IDENTIQUE
    if a.replace(' ', '') == b.replace(' ', ''):
        return ESPACEMENT
    confusions = _table_confusions(tuple(Config.MESURE_CONFUSIONS_OCR))
    changements = [
        (a[i1:i2], b[j1:j2])
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        if tag != 'equal'
    ]
    if len(changements) <= 2 and all(
        len(x) <= 1 and len(y) <= 1 and (x == '' or y == '' or frozenset((x, y)) in confusions)
        for x, y in changements
    ):
        return CONFUSION
    if not a:
        return AJOUTE
    if not b:
        return MANQUANT
    return CONTENU_DIFFERENT


# ── Pieds de page : paires LIBELLÉ : valeur, sans liste figée ─────────

_LABEL_PIED_RE = re.compile(
    r"((?:N°|NO)\s?PLAN|P\.?E\.?T\.?|\bCABLE|\bTYPE|INDICE|BORNIER|REF\s+CE|COMPL[EÉ]MENT)\s*:\s*"
    r"|(PAGE)\s*:?\s*(?=\w)",
    re.IGNORECASE,
)


def extraire_pied(texte: str) -> Dict[str, str]:
    """Toutes les paires LIBELLÉ : valeur d'une ligne de pied de page.

    Aucune liste de libellés figée : un nouveau champ de pied de page
    (ajouté à un template) est détecté sans modification de ce module.
    """
    texte = (texte or '').replace('|', '  ')
    correspondances = list(_LABEL_PIED_RE.finditer(texte))
    paires: Dict[str, str] = {}
    for k, m in enumerate(correspondances):
        fin = correspondances[k + 1].start() if k + 1 < len(correspondances) else len(texte)
        valeur = texte[m.end():fin].strip()
        cle = re.sub(r'\s+', ' ', (m.group(1) or m.group(2)).upper())
        cle = cle.replace('NO PLAN', 'N° PLAN').replace('N°PLAN', 'N° PLAN')
        cle = cle.replace('P.E.T.', 'PET').replace('P.E.T', 'PET')
        cle = cle.replace('COMPLÉMENT', 'COMPLEMENT')
        if valeur:
            paires[cle] = ' '.join(valeur.split())
    return paires


def _pied_page(page: dict) -> Dict[str, str]:
    """Paires du pied d'une page, le complément séparé de la valeur qu'il suit.

    Une vérité donne le complément sous son propre libellé (« COMPLEMENT : 8/10 ») ;
    une sortie l'écrit en texte libre après la valeur du TYPE (« TYPE : 2P.279 8/10 »).
    Pour chaque libellé de Config.MESURE_LIBELLES_A_COMPLEMENT sans complément
    explicite, la valeur est son 1er mot et le reste devient COMPLEMENT : les deux
    formes se comparent champ par champ, et un complément perdu reste un pied faux.
    """
    fusion: Dict[str, str] = {}
    for ligne in page.get('pied_texte') or []:
        fusion.update(extraire_pied(ligne))
    if 'COMPLEMENT' not in fusion:
        for libelle in getattr(Config, 'MESURE_LIBELLES_A_COMPLEMENT', ()):
            valeur, _, reste = fusion.get(libelle, '').partition(' ')
            if valeur:
                fusion[libelle] = valeur
                fusion['COMPLEMENT'] = reste.strip()
    return fusion


def comparer_pieds(
    page_ref: dict, page_conv: dict, num_ref: int, num_conv: int,
) -> List[EcartPied]:
    """Compare toutes les paires LIBELLÉ : valeur des pieds de page de deux pages appariées."""
    pied_ref, pied_conv = _pied_page(page_ref), _pied_page(page_conv)
    ecarts = []
    for libelle in sorted(set(pied_ref) | set(pied_conv)):
        a, b = _espace(pied_ref.get(libelle, '')), _espace(pied_conv.get(libelle, ''))
        if a.replace(' ', '') != b.replace(' ', ''):
            ecarts.append(EcartPied(num_ref, num_conv, libelle, a, b))
    return ecarts


# ── Comparaison d'une paire de pages ──────────────────────────────────

def comparer_page(
    page_ref: dict, page_conv: dict, num_ref: int, num_conv: int, colonnes: List[str],
) -> Tuple[List[EcartCellule], List[EcartPosition], List[LigneOrpheline]]:
    """Compare le contenu tableau de deux pages déjà appariées."""
    lignes_ref = _lignes_donnees(page_ref)
    lignes_conv = _lignes_donnees(page_conv)
    ecarts: List[EcartCellule] = []
    positions: List[EcartPosition] = []
    orphelines: List[LigneOrpheline] = []
    for i, j in aligner_lignes(lignes_ref, lignes_conv):
        if j is None:
            r = lignes_ref[i]
            orphelines.append(LigneOrpheline(_LIGNE_MANQUANTE, num_ref, i, _signature_ligne(r)))
            continue
        if i is None:
            c = lignes_conv[j]
            orphelines.append(LigneOrpheline(_LIGNE_EN_TROP, num_conv, j, _signature_ligne(c)))
            continue
        r, c = lignes_ref[i], lignes_conv[j]
        cellules_r, cellules_c = r.get('cells', []), c.get('cells', [])
        for k, nom_col in enumerate(colonnes):
            vr = cellules_r[k] if k < len(cellules_r) else ''
            vc = cellules_c[k] if k < len(cellules_c) else ''
            classe = classer_cellule(vr, vc)
            if classe != IDENTIQUE:
                ecarts.append(EcartCellule(
                    num_ref, num_conv, i, j, nom_col, _espace(vr), _espace(vc), classe,
                ))
            elif r.get('exact') and _decalages(vr) != _decalages(vc):
                positions.append(EcartPosition(
                    num_ref, num_conv, i, j, nom_col, _decalages(vr), _decalages(vc),
                ))
    return ecarts, positions, orphelines


# ── Orchestration ──────────────────────────────────────────────────────

def mesurer(reference: List[dict], converti: List[dict], colonnes: List[str]) -> RapportMesure:
    """Compare une référence organisée à une sortie mesurée, page par page."""
    paires, ref_orph, conv_orph = apparier_pages_par_contenu(reference, converti)
    rapport = RapportMesure(
        pages_appariees=paires,
        pages_ref_orphelines=ref_orph,
        pages_conv_orphelines=conv_orph,
    )
    for num_ref, num_conv in paires:
        ecarts, positions, orphelines = comparer_page(
            reference[num_ref], converti[num_conv], num_ref, num_conv, colonnes,
        )
        rapport.ecarts_cellules.extend(ecarts)
        rapport.ecarts_positions.extend(positions)
        rapport.lignes_orphelines.extend(orphelines)
        rapport.ecarts_pieds.extend(
            comparer_pieds(reference[num_ref], converti[num_conv], num_ref, num_conv),
        )
        nb_comparees = len(_lignes_donnees(reference[num_ref])) * len(colonnes)
        rapport.nb_cellules_comparees += nb_comparees
        rapport.nb_cellules_identiques += nb_comparees - len(ecarts)
    return rapport


def formater_rapport(rapport: RapportMesure, max_ecarts: Optional[int] = None) -> str:
    """Rapport texte lisible : pages manquantes, écarts par catégorie, pieds, positions."""
    lignes = [
        'MESURE DE PRÉCISION',
        '=' * 60,
        f"Pages appariées      : {len(rapport.pages_appariees)}",
        f"Pages réf. orphelines : {rapport.pages_ref_orphelines or 'aucune'}",
        f"Pages conv. orphelines : {rapport.pages_conv_orphelines or 'aucune'}",
        f"Précision cellules    : {rapport.precision:.1%} "
        f"({rapport.nb_cellules_identiques}/{rapport.nb_cellules_comparees})",
    ]
    compte = rapport.cellules_par_classe()
    if compte:
        lignes.append('Écarts cellules par catégorie :')
        for classe, n in sorted(compte.items(), key=lambda kv: -kv[1]):
            lignes.append(f"  {classe:20} {n}")
    if rapport.ecarts_pieds:
        lignes.append(f"Écarts pied de page   : {len(rapport.ecarts_pieds)}")
    if rapport.ecarts_positions:
        lignes.append(f"Écarts de position    : {len(rapport.ecarts_positions)}")
    if rapport.lignes_orphelines:
        lignes.append(f"Lignes orphelines     : {len(rapport.lignes_orphelines)}")
    lignes.append('-' * 60)
    a_afficher = rapport.ecarts_cellules[:max_ecarts] if max_ecarts else rapport.ecarts_cellules
    for e in a_afficher:
        lignes.append(
            f"p.{e.page_ref}→{e.page_conv} l.{e.ligne_ref} [{e.colonne}] {e.classe:20} "
            f"réf={e.valeur_ref!r} conv={e.valeur_conv!r}",
        )
    if max_ecarts and len(rapport.ecarts_cellules) > max_ecarts:
        restants = len(rapport.ecarts_cellules) - max_ecarts
        lignes.append(f"  ... {restants} écart(s) supplémentaire(s)")
    return '\n'.join(lignes)
