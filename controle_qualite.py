"""
Contrôle qualité d'un document converti (étape 9), sur le format pivot.

Ne modifie JAMAIS une valeur : chaque règle rend des alertes {page (indice), ligne (indice
dans rows, ou None pour la page), colonne (indice), regle, message, proposition}, que le
convertisseur range dans la feuille A VERIFIER. Chaque règle est activable dans config.py
(QUALITE_REGLES) ; ses paramètres y sont aussi.

Règles :
- coherence : un même code écrit de deux façons dans le document, à une confusion de
  caractère près (QUALITE_CONFUSIONS) ; forme minoritaire signalée, majoritaire proposée ;
  ou forme absente du lexique de référence mais à une confusion d'une forme du lexique.
- dictionnaire : la correction de data_dictionary devient une proposition, par mode.
- continuite : saut ou descente dans la suite des numéros d'une colonne.
- colonne_vide : colonne obligatoire du modèle entièrement vide sur une page.
- format : cellule hors du motif de sa colonne, par modèle de sortie.

Module pur : config et bibliothèque standard.
"""
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Set

from config import Config

# Moteurs dont la lecture est déjà exacte (texte du PDF) ou fidèle (vision) : le dictionnaire
# n'y propose rien, ou seulement si l'interrupteur du mode le permet.
METHODES_VECTORIELLES = {'pdf-grille', 'pdf'}
METHODES_VISION = {'claude-vision', 'log-replay', 'hybrid', 'ollama-vision', 'agent-vision'}
_JETON_RE = re.compile(r"[A-Z0-9][A-Z0-9/.\-+]*")
_NUMERO_RE = re.compile(r'^(\d+)([A-Z]?)$')


def _norm(texte) -> str:
    return ' '.join(str(texte or '').split()).upper()


def formes(texte) -> Set[str]:
    """Cellule entière et mots d'au moins QUALITE_LONGUEUR_MIN caractères, espaces réduits."""
    cellule = _norm(texte)
    n = Config.QUALITE_LONGUEUR_MIN
    sortie = {m for m in _JETON_RE.findall(cellule) if len(m) >= n}
    if len(cellule) >= n:
        sortie.add(cellule)
    return sortie


def variantes(texte: str) -> Iterable[str]:
    """Formes à une confusion de caractère près (une seule substitution)."""
    for i, ch in enumerate(texte):
        for a, b in Config.QUALITE_CONFUSIONS:
            if ch == a:
                yield texte[:i] + b + texte[i + 1:]
            elif ch == b:
                yield texte[:i] + a + texte[i + 1:]


def _cellules(pages: List[Dict]):
    """(page, ligne, colonne, valeur) de chaque cellule de données non vide."""
    for p, page in enumerate(pages):
        for r, row in enumerate(page.get('rows') or []):
            if row.get('type') != 'data':
                continue
            for k, valeur in enumerate(row.get('cells') or []):
                if (valeur or '').strip():
                    yield p, r, k, valeur


def _alerte(p, r, k, regle, message, proposition=None) -> Dict:
    return {'page': p, 'ligne': r, 'colonne': k, 'regle': regle, 'message': message,
            'proposition': proposition}


def regle_coherence(pages: List[Dict], lexique: Optional[Set[str]] = None) -> List[Dict]:
    """Forme écrite autrement ailleurs (majoritaire) ou dans le lexique, à une confusion près."""
    frequences = Counter(f for _, _, _, v in _cellules(pages) for f in formes(v))
    lexique = lexique or set()
    alertes = []
    for p, r, k, valeur in _cellules(pages):
        for forme in sorted(formes(valeur), key=len, reverse=True):
            if forme in lexique:
                continue
            majoritaires = sorted(
                ((frequences[v], v) for v in set(variantes(forme))
                 if frequences[v] >= Config.QUALITE_MIN_MAJORITE
                 and frequences[v] >= Config.QUALITE_RATIO_MAJORITE * frequences[forme]),
                reverse=True)
            connues = sorted(v for v in set(variantes(forme)) if v in lexique)
            if majoritaires:
                n, v = majoritaires[0]
                alertes.append(_alerte(p, r, k, 'coherence',
                                       f"« {forme} » écrit « {v} » {n} fois dans le document",
                                       v))
                break
            if connues:
                alertes.append(_alerte(p, r, k, 'coherence',
                                       f"« {forme} » absent du lexique de référence, qui porte "
                                       f"« {connues[0]} »", connues[0]))
                break
    return alertes


def _mode(page: Dict) -> str:
    methode = page.get('detection_method', '')
    if methode in METHODES_VECTORIELLES:
        return 'vectoriel'
    return 'claude' if methode in METHODES_VISION else 'ocr'


def regle_dictionnaire(pages: List[Dict], dictionnaire) -> List[Dict]:
    """Valeur que data_dictionary aurait corrigée : alerte et proposition, jamais remplacée.

    Jamais sur une page vectorielle (texte exact) ; ailleurs selon QUALITE_DICTIONNAIRE_MODES.
    """
    alertes = []
    for p, r, k, valeur in _cellules(pages):
        page = pages[p]
        if _mode(page) == 'vectoriel' or not Config.QUALITE_DICTIONNAIRE_MODES.get(_mode(page)):
            continue
        entetes = page.get('headers') or []
        colonne = entetes[k] if k < len(entetes) else ''
        proposee, corrigee = dictionnaire.correct(colonne, valeur)
        if corrigee and proposee != valeur:
            alertes.append(_alerte(p, r, k, 'dictionnaire',
                                   f"« {valeur} » : le dictionnaire propose « {proposee} »",
                                   proposee))
    return alertes


def _numero(valeur: str):
    """(code, numéro) du dernier mot numérique de la cellule (« PA 01 » → (« PA », 1))."""
    mots = _norm(valeur).split()
    if not mots:
        return None
    m = _NUMERO_RE.match(mots[-1])
    return (' '.join(mots[:-1]), int(m.group(1))) if m else None


def regle_continuite(pages: List[Dict], colonnes: Iterable[str], saut_max: int) -> List[Dict]:
    """Numéro qui descend ou saute de plus de saut_max dans la suite d'un même code."""
    alertes = []
    for p, page in enumerate(pages):
        entetes = [h.upper() for h in page.get('headers') or []]
        for nom in colonnes:
            if nom.upper() not in entetes:
                continue
            k = entetes.index(nom.upper())
            precedent, suspect = None, None

            def dans_la_suite(avant, apres):
                return (avant is not None and avant[0] == apres[0]
                        and 0 <= apres[1] - avant[1] <= saut_max)

            for r, row in enumerate(page.get('rows') or []):
                if row.get('type') != 'data' or k >= len(row.get('cells') or []):
                    continue
                lu = _numero(row['cells'][k])
                if lu is None:
                    continue
                # Après une alerte, la suite reprend de la valeur signalée (vrai saut, déjà
                # signalé une fois) ou de celle d'avant (valeur isolée) : pas de 2e alerte.
                if (precedent is None or precedent[0] != lu[0] or dans_la_suite(precedent, lu)
                        or dans_la_suite(suspect, lu)):
                    precedent, suspect = lu, None
                    continue
                alertes.append(_alerte(p, r, k, 'continuite',
                                       f"suite des numéros : {precedent[1]} puis {lu[1]}"))
                suspect = lu
    return alertes


def regle_colonne_vide(pages: List[Dict], obligatoires: Iterable[str]) -> List[Dict]:
    """Colonne obligatoire du modèle entièrement vide sur une page qui a des lignes."""
    alertes = []
    for p, page in enumerate(pages):
        lignes = [row for row in page.get('rows') or [] if row.get('type') == 'data']
        entetes = [h.upper() for h in page.get('headers') or []]
        if not lignes:
            continue
        for nom in obligatoires:
            if nom.upper() not in entetes:
                continue
            k = entetes.index(nom.upper())
            if not any((row['cells'][k] if k < len(row['cells']) else '').strip()
                       for row in lignes):
                alertes.append(_alerte(p, None, k, 'colonne_vide',
                                       f"colonne {nom} entièrement vide sur la page"))
    return alertes


def regle_format(pages: List[Dict], formats: Dict[str, str]) -> List[Dict]:
    """Cellule hors du motif de sa colonne (espaces ramenés à un, cellule vide ignorée)."""
    alertes = []
    motifs = {c.upper(): re.compile(m) for c, m in formats.items()}
    for p, r, k, valeur in _cellules(pages):
        entetes = [h.upper() for h in pages[p].get('headers') or []]
        motif = motifs.get(entetes[k]) if k < len(entetes) else None
        if motif and not motif.fullmatch(_norm(valeur)):
            alertes.append(_alerte(p, r, k, 'format',
                                   f"« {_norm(valeur)} » hors du format de {entetes[k]}"))
    return alertes


def controler_document(pages: List[Dict], modele: str, lexique: Optional[Set[str]] = None,
                       dictionnaire=None) -> List[Dict]:
    """Alertes des règles actives (QUALITE_REGLES) sur les pages d'un même document."""
    regles = Config.QUALITE_REGLES
    alertes: List[Dict] = []
    if regles.get('coherence'):
        alertes += regle_coherence(pages, lexique)
    if regles.get('dictionnaire') and dictionnaire is not None:
        alertes += regle_dictionnaire(pages, dictionnaire)
    if regles.get('continuite'):
        alertes += regle_continuite(pages, Config.QUALITE_CONTINUITE.get(modele, ()),
                                    Config.QUALITE_SAUT_MAX)
    if regles.get('colonne_vide'):
        alertes += regle_colonne_vide(pages, Config.QUALITE_COLONNES_OBLIGATOIRES.get(modele, ()))
    if regles.get('format'):
        alertes += regle_format(pages, Config.QUALITE_FORMATS.get(modele, {}))
    return alertes
