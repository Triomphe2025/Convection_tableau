"""
Estimation avant lancement (phase 1B, étape 3) : pages par nature, pages déjà faites, tokens,
coût et durée — module pur, PyMuPDF seul (ni rastérisation ni Tesseract).

Ordre de grandeur affiché avant de lancer, jamais une promesse : `approche` vaut toujours True.
La nature des pages vient de la règle partagée du converter (pdf_extractor.classer_page,
métadonnées fitz seules — le cas « texte caché » compris) : jamais une 2e règle. Les moyennes de
tokens (et de secondes par page quand les journaux ont des horodatages) sont calculées par
modèle, une seule fois par session (mémoïsées), sur les ESTIMATION_JOURNAUX_MAX journaux .jsonl
les plus récents ; à défaut, des constantes documentées de config.py. L'écran peut appeler
estimer pour chaque profil (Rapide = tesseract, Précis / Difficile = un modèle Claude).
"""
import json
from datetime import datetime
from pathlib import Path

from config import Config

# Profils qui appellent l'API (coût en tokens) ; les autres (tesseract, cad, formatage,
# log-replay) ne coûtent rien.
_PROFILS_API = ('claude', 'hybrid')

# Moyennes par modèle, calculées une fois par session.
_moyennes_cache = {}


def reinitialiser_cache():
    """Vide les moyennes mémoïsées (tests, ou après de nouvelles conversions)."""
    _moyennes_cache.clear()


def _lignes(chemin):
    """Lignes JSON d'un journal .jsonl (lignes illisibles ignorées)."""
    try:
        with open(chemin, encoding='utf-8') as f:
            for ligne in f:
                ligne = ligne.strip()
                if ligne:
                    try:
                        yield json.loads(ligne)
                    except ValueError:
                        continue
    except OSError:
        return


def _instant(ts):
    """Horodatage ISO → datetime, ou None si absent / mal formé."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _journaux_recents(dossier):
    """Les ESTIMATION_JOURNAUX_MAX journaux .jsonl les plus récents du dossier (par date)."""
    dossier = Path(dossier)
    if not dossier.is_dir():
        return []
    journaux = sorted(dossier.rglob('*_claude.jsonl'),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    return journaux[:Config.ESTIMATION_JOURNAUX_MAX]


def moyennes_modele(modele):
    """(mémoïsé) {'tokens': (entrée, sortie), 'secondes': s|None, 'source': ..., 'n': ...}.

    Moyennes des lignes réussies du modèle dans les journaux récents ; à défaut des tokens, la
    constante documentée. `secondes` : moyenne des écarts d'horodatage entre pages (None si les
    journaux n'en portent pas → la durée retombe sur la constante par moteur).
    """
    if modele in _moyennes_cache:
        return _moyennes_cache[modele]
    entrees, sorties, ecarts = [], [], []
    for journal in _journaux_recents(Config.ESTIMATION_JOURNAUX_DOSSIER):
        precedent = None
        for ligne in _lignes(journal):
            if not ligne.get('success') or ligne.get('model') != modele:
                continue
            usage = ligne.get('usage') or {}
            entree, sortie = usage.get('input_tokens'), usage.get('output_tokens')
            if entree is not None and sortie is not None:
                entrees.append(entree)
                sorties.append(sortie)
            instant = _instant(ligne.get('ts'))
            if instant is not None and precedent is not None:
                ecart = (instant - precedent).total_seconds()
                # Écart aberrant (reprise le lendemain, longue pause) écarté.
                if 0 < ecart < 600:
                    ecarts.append(ecart)
            if instant is not None:
                precedent = instant
    if entrees:
        tokens = (sum(entrees) / len(entrees), sum(sorties) / len(sorties))
        source = 'journaux'
    else:
        tokens = tuple(Config.ESTIMATION_TOKENS_PAR_PAGE_DEFAUT)
        source = 'constante'
    secondes = sum(ecarts) / len(ecarts) if ecarts else None
    resultat = {'tokens': tokens, 'secondes': secondes, 'source': source, 'n': len(entrees)}
    _moyennes_cache[modele] = resultat
    return resultat


def natures(chemin):
    """Nature de chaque page d'un PDF (règle partagée pdf_extractor.classer_page) ; [] sinon."""
    chemin = Path(chemin)
    if chemin.suffix.lower() != '.pdf':
        return []
    import fitz
    from pdf_extractor import classer_page
    doc = fitz.open(str(chemin))
    try:
        return [classer_page(page) for page in doc]
    finally:
        doc.close()


def _pages_non_pdf(chemin):
    """Nombre de « pages » d'un fichier non PDF (lignes d'un journal, sinon 1)."""
    chemin = Path(chemin)
    if chemin.suffix.lower() == '.jsonl':
        return sum(1 for _ in _lignes(chemin))
    return 1


def _pages_faites(chemin, modele, dossier_sortie):
    """(pages déjà faites, cache connu) depuis un journal partiel du MÊME document.

    Cherche <radical>*_claude.jsonl dans le dossier de sortie et compte ses pages réussies pour
    le modèle. Sans dossier (ou sans journal correspondant) : (0, False) → l'écran affiche « au
    plus ».
    """
    if not dossier_sortie:
        return 0, False
    dossier = Path(dossier_sortie)
    if not dossier.is_dir():
        return 0, False
    journaux = list(dossier.glob(Path(chemin).stem + '*_claude.jsonl'))
    if not journaux:
        return 0, False
    faites = sum(1 for journal in journaux for ligne in _lignes(journal)
                 if ligne.get('success') and ligne.get('model') == modele)
    return faites, True


def _duree_par_page(profil, modele):
    """Secondes par page lue : horodatages des journaux si le profil est API, sinon la
    constante du moteur (Tesseract ou le modèle)."""
    if profil in _PROFILS_API:
        mesure = moyennes_modele(modele)['secondes']
        if mesure is not None:
            return mesure
        moteur = modele
    elif profil == 'tesseract':
        moteur = 'tesseract'
    else:
        moteur = profil
    return Config.ESTIMATION_SECONDES_PAR_PAGE.get(
        moteur, Config.ESTIMATION_SECONDES_PAR_PAGE_DEFAUT)


def estimer(chemin, type=None, profil=None, lot=False, modele=None, dossier_sortie=None):
    """Estimation avant lancement d'un document pour un profil donné (voir module)."""
    from pdf_extractor import OCR_INVISIBLE, SCAN, VECTORIEL, VIDE
    chemin = Path(chemin)
    if profil is None:
        profil = getattr(type, 'profil_lecture', '') or ''
    modele = modele or Config.CLAUDE_OCR_MODEL

    liste = natures(chemin)
    compte = {VECTORIEL: 0, SCAN: 0, OCR_INVISIBLE: 0, VIDE: 0}
    for nature in liste:
        compte[nature] = compte.get(nature, 0) + 1
    total = len(liste) if liste else _pages_non_pdf(chemin)
    pages = {'total': total, VECTORIEL: compte[VECTORIEL], SCAN: compte[SCAN],
             OCR_INVISIBLE: compte[OCR_INVISIBLE], VIDE: compte[VIDE]}

    # Seules les pages scan / couche OCR invisible sont lues par un moteur ; le reste (grille,
    # vide) ne coûte rien et ne prend pas de temps de lecture.
    payantes = compte[SCAN] + compte[OCR_INVISIBLE]
    pages_en_cache, cache_connu = _pages_faites(chemin, modele, dossier_sortie)
    pages_en_cache = min(pages_en_cache, payantes)
    a_lire = max(0, payantes - pages_en_cache)

    api = profil in _PROFILS_API
    moyennes = moyennes_modele(modele)
    tok_entree, tok_sortie = moyennes['tokens']
    tokens = {'entree': a_lire * tok_entree, 'sortie': a_lire * tok_sortie}

    if api:
        prix_entree, prix_sortie = Config.CLAUDE_PRIX_MODELES.get(modele, (0.0, 0.0))
        cout = (tokens['entree'] * prix_entree + tokens['sortie'] * prix_sortie) / 1_000_000
        if lot:
            cout *= 0.5
    else:
        cout = 0.0

    if lot:
        duree = {'secondes': None, 'texte': Config.ESTIMATION_DUREE_LOT_TEXTE}
    else:
        secondes = a_lire * _duree_par_page(profil, modele)
        duree = {'secondes': secondes, 'texte': _texte_duree(secondes)}

    return {
        'approche': True,
        'modele': modele,
        'profil': profil,
        'pages': pages,
        'pages_payantes': payantes,
        'pages_en_cache': pages_en_cache,
        'cache_connu': cache_connu,
        'pages_a_lire': a_lire,
        'source_tokens': moyennes['source'],
        'tokens': tokens,
        'cout_usd': cout,
        'duree': duree,
    }


def _texte_duree(secondes):
    """Durée lisible « ~ m min » / « ~ s s » (ordre de grandeur)."""
    if secondes < 90:
        return f"~ {round(secondes)} s"
    return f"~ {round(secondes / 60)} min"
