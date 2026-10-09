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


def variantes(texte: str, confusions=None) -> Iterable[str]:
    """Formes à une confusion de caractère près (une seule substitution)."""
    for variante, _ in variantes_et_paires(texte, confusions):
        yield variante


def variantes_et_paires(texte: str, confusions=None):
    """(forme, « A/B ») à une substitution près ; jamais un chiffre contre un chiffre."""
    for i, ch in enumerate(texte):
        for a, b in (confusions or Config.QUALITE_CONFUSIONS):
            if a.isdigit() and b.isdigit():
                continue
            if ch == a:
                yield texte[:i] + b + texte[i + 1:], f"{a}/{b}"
            elif ch == b:
                yield texte[:i] + a + texte[i + 1:], f"{a}/{b}"


def _cellules(pages: List[Dict]):
    """(page, ligne, colonne, valeur) de chaque cellule de données non vide."""
    for p, page in enumerate(pages):
        for r, row in enumerate(page.get('rows') or []):
            if row.get('type') != 'data':
                continue
            for k, valeur in enumerate(row.get('cells') or []):
                if (valeur or '').strip():
                    yield p, r, k, valeur


def _alerte(p, r, k, regle, message, proposition=None, paire=None) -> Dict:
    return {'page': p, 'ligne': r, 'colonne': k, 'regle': regle, 'message': message,
            'proposition': proposition, 'paire': paire}


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
                ((frequences[v], v, paire) for v, paire in set(variantes_et_paires(forme))
                 if frequences[v] >= Config.QUALITE_MIN_MAJORITE
                 and frequences[v] >= Config.QUALITE_RATIO_MAJORITE * frequences[forme]),
                reverse=True)
            connues = sorted((v, paire) for v, paire in set(variantes_et_paires(
                forme, Config.QUALITE_CONFUSIONS_LEXIQUE)) if v in lexique)
            if majoritaires:
                n, v, paire = majoritaires[0]
                alertes.append(_alerte(p, r, k, 'coherence',
                                       f"« {forme} » écrit « {v} » {n} fois dans le document",
                                       v, paire))
                break
            if connues:
                v, paire = connues[0]
                alertes.append(_alerte(p, r, k, 'coherence',
                                       f"« {forme} » absent du lexique de référence, qui porte "
                                       f"« {v} »", v, paire))
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
        # Un écart d'espaces seul n'est pas une proposition (cellules aux positions d'origine)
        if corrigee and ' '.join(proposee.split()) != ' '.join(valeur.split()):
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
            # Une suite par code (« RM 11B, RM 12B » et « RA 17, RA 18 » sont deux suites
            # entremêlées), remise à zéro à chaque ligne de section.
            suites: Dict[str, list] = {}

            def dans_la_suite(avant, apres):
                return avant is not None and 0 <= apres[1] - avant[1] <= saut_max

            for r, row in enumerate(page.get('rows') or []):
                if row.get('type') == 'section':
                    suites = {}
                    continue
                if row.get('type') != 'data' or k >= len(row.get('cells') or []):
                    continue
                lu = _numero(row['cells'][k])
                if lu is None:
                    continue
                precedent, suspect = suites.get(lu[0], (None, None))
                # Après une alerte, la suite reprend de la valeur signalée (vrai saut, déjà
                # signalé une fois) ou de celle d'avant (valeur isolée) : pas de 2e alerte.
                if precedent is None or dans_la_suite(precedent, lu) or dans_la_suite(suspect, lu):
                    suites[lu[0]] = (lu, None)
                    continue
                alertes.append(_alerte(p, r, k, 'continuite',
                                       f"suite des numéros : {precedent[1]} puis {lu[1]}"))
                suites[lu[0]] = (precedent, lu)
    return alertes


def _garde_fou(alertes_par_colonne: Dict[tuple, List[Dict]], totaux: Dict[tuple, int],
               regle: str, message) -> List[Dict]:
    """Colonne où plus de QUALITE_GARDE_FOU des cas sortent : une synthèse, contrôle coupé.

    Sur un document jamais vu, c'est alors le motif (ou la liste des colonnes
    obligatoires) qui ne convient pas, pas la lecture.
    """
    sortie = []
    for (k, nom), alertes in sorted(alertes_par_colonne.items()):
        if totaux.get((k, nom)) and len(alertes) / totaux[(k, nom)] > Config.QUALITE_GARDE_FOU:
            sortie.append(_alerte(None, None, k, regle, message(nom)))
        else:
            sortie += alertes
    return sortie


def taux_colonnes_vides(pages: List[Dict], obligatoires: Iterable[str]) -> Dict[str, float]:
    """Part des pages (qui ont des lignes) où chaque colonne obligatoire est vide."""
    vides, pages_comptees = _colonnes_vides(pages, obligatoires)
    return {nom: len(a) / pages_comptees[(k, nom)]
            for (k, nom), a in vides.items() if pages_comptees.get((k, nom))}


def _colonnes_vides(pages, obligatoires):
    vides: Dict[tuple, List[Dict]] = {}
    comptees: Dict[tuple, int] = {}
    for p, page in enumerate(pages):
        lignes = [row for row in page.get('rows') or [] if row.get('type') == 'data']
        entetes = [h.upper() for h in page.get('headers') or []]
        if not lignes:
            continue
        for nom in obligatoires:
            if nom.upper() not in entetes:
                continue
            k = entetes.index(nom.upper())
            cle = (k, nom)
            comptees[cle] = comptees.get(cle, 0) + 1
            vides.setdefault(cle, [])
            if not any((row['cells'][k] if k < len(row['cells']) else '').strip()
                       for row in lignes):
                vides[cle].append(_alerte(p, None, k, 'colonne_vide',
                                          f"colonne {nom} entièrement vide sur la page"))
    return vides, comptees


def regle_colonne_vide(pages: List[Dict], obligatoires: Iterable[str]) -> List[Dict]:
    """Colonne obligatoire du modèle entièrement vide sur une page qui a des lignes."""
    vides, comptees = _colonnes_vides(pages, obligatoires)
    return _garde_fou(vides, comptees, 'colonne_vide',
                      lambda nom: f"colonne {nom} vide sur trop de pages de ce document, "
                                  f"contrôle coupé pour cette colonne")


def _hors_format(pages, formats):
    motifs = {c.upper(): re.compile(m) for c, m in formats.items()}
    hors: Dict[tuple, List[Dict]] = {}
    totaux: Dict[tuple, int] = {}
    for p, r, k, valeur in _cellules(pages):
        entetes = [h.upper() for h in pages[p].get('headers') or []]
        nom = entetes[k] if k < len(entetes) else ''
        motif = motifs.get(nom)
        if not motif:
            continue
        totaux[(k, nom)] = totaux.get((k, nom), 0) + 1
        hors.setdefault((k, nom), [])
        if not motif.fullmatch(_norm(valeur)):
            hors[(k, nom)].append(_alerte(p, r, k, 'format',
                                          f"« {_norm(valeur)} » hors du format de {nom}"))
    return hors, totaux


def taux_hors_format(pages: List[Dict], formats: Dict[str, str]) -> Dict[str, float]:
    """Part des cellules non vides de chaque colonne hors de son motif, dans le document."""
    hors, totaux = _hors_format(pages, formats)
    return {nom: len(a) / totaux[(k, nom)] for (k, nom), a in hors.items()}


def regle_format(pages: List[Dict], formats: Dict[str, str]) -> List[Dict]:
    """Cellule hors du motif de sa colonne (espaces ramenés à un, cellule vide ignorée)."""
    hors, totaux = _hors_format(pages, formats)
    return _garde_fou(hors, totaux, 'format',
                      lambda nom: f"format de la colonne {nom} non reconnu dans ce document, "
                                  f"contrôle coupé pour cette colonne")


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
