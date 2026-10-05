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
import unicodedata
from collections import Counter
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
# Ce qui manque dans une cellule se trouve en trop dans sa voisine de la même ligne.
GLISSEMENT = 'GLISSEMENT_COLONNE'

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

    Début d'un mot = sa colonne, en caractères, comptée depuis le caractère le plus
    à gauche de cette colonne du tableau sur la page (colonne 0) : le retrait
    d'une cellule compte (« RM 03B » plus à droite que « DA 22 »).

    Ne survient que si la référence préserve la géométrie exacte (PDF
    vectoriel reconstruit en grille) : `page_ref['rows'][i]['exact']` est vrai,
    ou si la ligne porte une vérité des positions (`row['positions']`, feuille
    Verite_positions d'une vérité terrain).
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


@dataclass(frozen=True)
class LigneDeplacee:
    """Ligne de contenu identique, absente à sa place et présente ailleurs (inversion)."""

    page_ref: int
    ligne_ref: int
    page_conv: int
    ligne_conv: int
    contenu: str


@dataclass
class RapportMesure:
    """Bilan d'une mesure de précision sur un document connu."""

    pages_appariees: List[Tuple[int, int]] = field(default_factory=list)
    pages_ref_orphelines: List[int] = field(default_factory=list)
    pages_conv_orphelines: List[int] = field(default_factory=list)
    lignes_orphelines: List[LigneOrpheline] = field(default_factory=list)
    lignes_deplacees: List[LigneDeplacee] = field(default_factory=list)
    ecarts_cellules: List[EcartCellule] = field(default_factory=list)
    ecarts_pieds: List[EcartPied] = field(default_factory=list)
    ecarts_positions: List[EcartPosition] = field(default_factory=list)
    # (page de la référence de positions, page convertie) : pages dont les positions
    # ont été mesurées contre une référence géométrique (grille d'un PDF vectoriel).
    pages_positions_geometriques: List[Tuple[int, int]] = field(default_factory=list)
    # Alertes (vérité terrain « Alertes_attendues » contre lignes ⚠ du journal) :
    # None = non mesurées (pas de journal ou pas d'attentes).
    alertes_manquantes: Optional[List[str]] = None
    fausses_alertes: Optional[List[str]] = None
    # Contrôle INDICE (« Verite_garde ») : None = non mesuré, sinon (conforme, détail).
    controle_indice: Optional[Tuple[bool, str]] = None
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


def _debuts(texte, origine: int = 0) -> Tuple[int, ...]:
    """Colonne de début de chaque mot, comptée depuis `origine` (colonne 0 du tableau)."""
    return tuple(m.start() - origine for m in re.finditer(r'\S+', (texte or '').rstrip()))


def origines_colonnes(lignes: List[dict], n: int) -> List[int]:
    """Pour chaque colonne de la page : retrait de sa cellule la plus à gauche."""
    origines = []
    for k in range(n):
        retraits = [len(c) - len(c.lstrip())
                    for c in (ligne.get('cells', [])[k] if k < len(ligne.get('cells', []))
                              else '' for ligne in lignes)
                    if (c or '').strip()]
        origines.append(min(retraits, default=0))
    return origines


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

def glissements(cellules_ref: List[str], cellules_conv: List[str]) -> Set[int]:
    """Indices des cellules d'une ligne touchées par un glissement de colonne.

    Glissement entre k et k±1 : les mots perdus par l'une des deux cellules sont
    exactement les mots gagnés par l'autre (comparaison en multiensemble de mots).
    """
    n = max(len(cellules_ref), len(cellules_conv))
    ref = [Counter((cellules_ref[k] if k < len(cellules_ref) else '').split()) for k in range(n)]
    conv = [Counter((cellules_conv[k] if k < len(cellules_conv) else '').split())
            for k in range(n)]
    touchees: Set[int] = set()
    for k in range(n - 1):
        for depart, arrivee in ((k, k + 1), (k + 1, k)):
            perdus = ref[depart] - conv[depart]
            if perdus and perdus == conv[arrivee] - ref[arrivee] \
                    and not (conv[depart] - ref[depart]) and not (ref[arrivee] - conv[arrivee]):
                touchees.update((depart, arrivee))
    return touchees


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
    r"((?:N°|NO)\s*PLAN|P\.?E\.?T\.?|\bCABLE|\bTYPE|INDICE|BORNIER|REF\s+CE|COMPL[EÉ]MENT"
    r"|\bLOGO)\s*:\s*"
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
    # Texte fixe du document lu à la suite d'une valeur (« SAINT MAURICE JARRETIERAGE ») :
    # la vérité le donne à part (« Autre texte »), il n'appartient à aucune valeur.
    for decor in page_ref.get('pied_autre') or []:
        for libelle, valeur in pied_conv.items():
            pied_conv[libelle] = _espace(re.sub(rf'(?<!\S){re.escape(decor)}(?!\S)', ' ', valeur))
    schema = page_ref.get('libelles_pied')
    if schema is not None:
        libelles = set(schema)
    else:
        # Référence sans schéma (PDF vectoriel) : elle n'a pas de logo libellé.
        libelles = (set(pied_ref) | set(pied_conv)) - {'LOGO'}
    stricts = set(page_ref.get('libelles_stricts') or ())
    ecarts = []
    for libelle in sorted(libelles):
        a, b = _espace(pied_ref.get(libelle, '')), _espace(pied_conv.get(libelle, ''))
        # Libellé strict (logo, N° PLAN et PAGE livrés) : l'espacement fait partie de la valeur.
        egaux = a == b if libelle in stricts else a.replace(' ', '') == b.replace(' ', '')
        if not egaux:
            ecarts.append(EcartPied(num_ref, num_conv, libelle, a, b))
    return ecarts


# ── Sections du tableau (« NOM DU CABLE : … ») ─────────────────────────

def _sections(page: dict) -> List[str]:
    return [_espace(r.get('text', '')) for r in page.get('rows', []) if r.get('type') == 'section']


def comparer_sections(page_ref: dict, page_conv: dict, num_ref: int, num_conv: int):
    """Sections dans l'ordre : (écarts de texte, sections absentes ou en trop)."""
    ref, conv = _sections(page_ref), _sections(page_conv)
    ecarts: List[EcartCellule] = []
    orphelines: List[LigneOrpheline] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, ref, conv, autojunk=False).get_opcodes():
        if op == 'equal':
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            i, j = i1 + k, j1 + k
            if i < i2 and j < j2:
                ecarts.append(EcartCellule(num_ref, num_conv, i, j, 'SECTION', ref[i], conv[j],
                                           classer_cellule(ref[i], conv[j])))
            elif i < i2:
                orphelines.append(LigneOrpheline(_LIGNE_MANQUANTE, num_ref, i,
                                                 'SECTION ' + ref[i]))
            else:
                orphelines.append(LigneOrpheline(_LIGNE_EN_TROP, num_conv, j,
                                                 'SECTION ' + conv[j]))
    return ecarts, orphelines


# ── Alertes et contrôle INDICE ────────────────────────────────────────

def _texte_alerte(texte: str) -> str:
    sans_accents = ''.join(c for c in unicodedata.normalize('NFKD', str(texte or ''))
                           if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9→>]+', '', sans_accents.lower().replace('->', '→'))


def comparer_alertes(attendues: List[str], emises: List[str]) -> Tuple[List[str], List[str]]:
    """(alertes attendues non émises, alertes émises non attendues = fausses alertes).

    Une alerte attendue est émise si son texte (sans accents, ponctuation ni espaces)
    figure dans une ligne ⚠ du journal ; chaque ligne n'en couvre qu'une.
    """
    restantes = list(emises)
    manquantes = []
    for attendue in attendues:
        cle = _texte_alerte(attendue)
        trouvee = next((e for e in restantes if cle and cle in _texte_alerte(e)), None)
        if trouvee is None:
            manquantes.append(attendue)
        else:
            restantes.remove(trouvee)
    return manquantes, restantes


def verifier_controle_indice(revisions: List[str], indices_pages: List[str],
                             journal: List[str]) -> Tuple[bool, str]:
    """Contrôle INDICE de la conversion contre Verite_garde et les INDICE des pieds."""
    attendu_ok = bool(revisions) and all(i in revisions for i in indices_pages)
    ok = [lg for lg in journal if 'contrôle INDICE : OK' in lg]
    if attendu_ok and not ok:
        return False, "ligne « contrôle INDICE : OK » attendue, absente du journal"
    if not attendu_ok and ok:
        return False, ("« contrôle INDICE : OK » émis alors que la vérité l'exclut : "
                       f"{ok[0].strip()}")
    if ok:
        lus = ok[0].split('indices lus :', 1)[-1]
        lus = {x.strip() for x in lus.split(',') if x.strip()}
        if lus != set(indices_pages):
            return False, f"indices lus {sorted(lus)}, attendus {sorted(set(indices_pages))}"
        return True, f"OK, indices {sorted(lus)} tous dans les révisions de la garde"
    return True, "contrôle non conclu OK, comme attendu"


# ── Comparaison d'une paire de pages ──────────────────────────────────

def comparer_page(
    page_ref: dict, page_conv: dict, num_ref: int, num_conv: int, colonnes: List[str],
) -> Tuple[List[EcartCellule], List[EcartPosition], List[LigneOrpheline]]:
    """Compare le contenu tableau de deux pages déjà appariées."""
    lignes_ref = _lignes_donnees(page_ref)
    lignes_conv = _lignes_donnees(page_conv)
    origine_r = origines_colonnes(lignes_ref, len(colonnes))
    origine_c = origines_colonnes(lignes_conv, len(colonnes))
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
        glisse = glissements(cellules_r, cellules_c)
        for k, nom_col in enumerate(colonnes):
            vr = cellules_r[k] if k < len(cellules_r) else ''
            vc = cellules_c[k] if k < len(cellules_c) else ''
            classe = classer_cellule(vr, vc)
            if classe != IDENTIQUE and k in glisse:
                classe = GLISSEMENT
            attendues = (r.get('positions') or {}).get(nom_col)
            if classe != IDENTIQUE:
                ecarts.append(EcartCellule(
                    num_ref, num_conv, i, j, nom_col, _espace(vr), _espace(vc), classe,
                ))
            elif attendues is not None:
                # Vérité des positions saisie à part (scans) : elle fait foi pour cette cellule.
                obtenus = _debuts(vc, origine_c[k])
                if attendues != obtenus:
                    positions.append(EcartPosition(
                        num_ref, num_conv, i, j, nom_col, attendues, obtenus,
                    ))
            elif r.get('exact'):
                attendus, obtenus = _debuts(vr, origine_r[k]), _debuts(vc, origine_c[k])
                if attendus != obtenus:
                    positions.append(EcartPosition(
                        num_ref, num_conv, i, j, nom_col, attendus, obtenus,
                    ))
    return ecarts, positions, orphelines


def apparier_deplacees(orphelines: List[LigneOrpheline], num_ref: int, num_conv: int):
    """Une ligne absente et une ligne en trop de même contenu = une ligne déplacée.

    Retourne (orphelines restantes, lignes déplacées) ; chaque ligne en trop ne
    sert qu'une fois, dans l'ordre de la page.
    """
    manquantes = [o for o in orphelines if o.cote == _LIGNE_MANQUANTE]
    en_trop = [o for o in orphelines if o.cote == _LIGNE_EN_TROP]
    deplacees: List[LigneDeplacee] = []
    prises = set()
    for m in manquantes:
        for t in en_trop:
            if id(t) not in prises and t.contenu == m.contenu:
                prises.update((id(m), id(t)))
                deplacees.append(LigneDeplacee(num_ref, m.ligne, num_conv, t.ligne, m.contenu))
                break
    return [o for o in orphelines if id(o) not in prises], deplacees


# ── Positions contre une référence géométrique ───────────────────────

def remplacer_positions(rapport: RapportMesure, positions: RapportMesure) -> None:
    """Positions des pages couvertes par `positions` (référence géométrique) à la place
    de celles du rapport ; les autres pages gardent les leurs.

    `positions` est un rapport mesuré contre une référence qui porte la géométrie
    (grille d'un PDF vectoriel) : seules ses positions et ses pages appariées servent.
    """
    couvertes = {conv for _, conv in positions.pages_appariees}
    rapport.ecarts_positions = (
        [e for e in rapport.ecarts_positions if e.page_conv not in couvertes]
        + list(positions.ecarts_positions)
    )
    rapport.pages_positions_geometriques = sorted(positions.pages_appariees)


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
        ecarts_sec, orph_sec = comparer_sections(
            reference[num_ref], converti[num_conv], num_ref, num_conv)
        ecarts = ecarts + ecarts_sec
        orphelines = orphelines + orph_sec
        orphelines, deplacees = apparier_deplacees(orphelines, num_ref, num_conv)
        rapport.ecarts_cellules.extend(ecarts)
        rapport.ecarts_positions.extend(positions)
        rapport.lignes_orphelines.extend(orphelines)
        rapport.lignes_deplacees.extend(deplacees)
        rapport.ecarts_pieds.extend(
            comparer_pieds(reference[num_ref], converti[num_conv], num_ref, num_conv),
        )
        nb_comparees = (len(_lignes_donnees(reference[num_ref])) * len(colonnes)
                        + len(_sections(reference[num_ref])))
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
    if rapport.pages_positions_geometriques:
        lignes.append(f"Positions contre la grille du PDF : "
                      f"{len(rapport.pages_positions_geometriques)} page(s) vectorielle(s)")
    if rapport.ecarts_positions:
        lignes.append(f"Écarts de position    : {len(rapport.ecarts_positions)}")
    if rapport.lignes_orphelines:
        lignes.append(f"Lignes orphelines     : {len(rapport.lignes_orphelines)}")
    if rapport.lignes_deplacees:
        lignes.append(f"Lignes déplacées      : {len(rapport.lignes_deplacees)}")
    if rapport.alertes_manquantes is not None:
        lignes.append(f"Alertes manquantes    : {len(rapport.alertes_manquantes)}")
        lignes.extend(f"    manquante : {a}" for a in rapport.alertes_manquantes)
        lignes.append(f"Fausses alertes       : {len(rapport.fausses_alertes)}")
        lignes.extend(f"    fausse : {a.strip()}" for a in rapport.fausses_alertes)
    if rapport.controle_indice is not None:
        conforme, detail = rapport.controle_indice
        lignes.append(f"Contrôle INDICE       : {'conforme' if conforme else 'NON CONFORME'} "
                      f"({detail})")
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
