"""
Génère un classeur Excel UNIQUE et un document Word UNIQUE
contenant tous les tableaux de borniers extraits par OCR.

Affiche une barre de progression pendant le traitement.

Usage :
    py generer_classeur.py
"""

import re
import sys
from collections import Counter
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.properties import PageSetupProperties
from docx import Document

from ocr_processor import BornierTableExtractor
from config import Config
from data_dictionary import get_dictionary


# ──────────────────────────────────────────────────────────────────────
# Barre de progression
# ──────────────────────────────────────────────────────────────────────

def barre(current: int, total: int, label: str = '', largeur: int = 40) -> None:
    """Affiche / met à jour une barre de progression en ligne."""
    pct = current / total if total > 0 else 0
    rempli = int(largeur * pct)
    b = '#' * rempli + '-' * (largeur - rempli)
    # Tronquer le label pour tenir sur une ligne
    label_court = label[:28].ljust(28)
    print(f'\r  [{b}] {pct*100:5.1f}%  {label_court}',
          end='', flush=True)
    if current >= total:
        print()  # nouvelle ligne à la fin


# ──────────────────────────────────────────────────────────────────────
# Tri numérique des fichiers (bornier_1, bornier_2, ..., bornier_100)
# ──────────────────────────────────────────────────────────────────────

def _cle_num(path: Path) -> int:
    nums = re.findall(r'\d+', path.stem)
    return int(nums[0]) if nums else 0


# ──────────────────────────────────────────────────────────────────────
# Traitement OCR de toutes les images
# ──────────────────────────────────────────────────────────────────────

def extraire_tous(
    images_dir: Path,
    extensions: List[str] = None
) -> Tuple[List[Dict], 'BornierTableExtractor']:
    """
    Traite chaque image avec OCR et retourne (résultats, extracteur).
    """
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.bmp']

    images = sorted(
        [f for f in images_dir.iterdir()
         if f.is_file() and f.suffix.lower() in extensions],
        key=_cle_num
    )

    if not images:
        print(f"\n  Aucune image trouvée dans : {images_dir}")
        return [], None

    total = len(images)
    print(f"\n  {total} images trouvées — extraction OCR en cours…\n")

    extractor = BornierTableExtractor(
        tesseract_path=Config.TESSERACT_PATH,
        language=Config.OCR_LANGUAGE
    )

    results = []
    blurry: list = []

    _METHOD_LABEL = {
        'header':     'en-tête reconnu',
        'tatr':       'IA (TATR)',
        'morpho':     'lignes verticales [repli]',
        'whitespace': 'zones blanches [repli]',
        'weighted':   'repli pondéré [repli]',
    }

    for i, img in enumerate(images):
        barre(i, total, img.name)
        result = extractor.extract(img)
        results.append(result)
        blur_pct = result.get('blur_pct', 0.0)
        if blur_pct > 40.0:
            blurry.append((img.name, blur_pct))
        method = result.get('detection_method', '?')
        label = _METHOD_LABEL.get(method, method)
        print(f"    colonnes : {label}", end='')
        if blur_pct > 40:
            print(f"  | flou {blur_pct:.0f}%", end='')
        print()

    barre(total, total, 'Extraction terminée')

    ok = sum(1 for r in results if r.get('success'))
    print(f"\n  ✓ {ok} tableaux extraits avec succès / {total} images\n")

    # Rapport d'images floues
    if blurry:
        report_path = images_dir.parent / 'images_floues.txt'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"Rapport images floues — {len(blurry)} image(s) sur {total}\n\n")
            for name, pct in blurry:
                f.write(f"  {name} : {pct:.0f}% de flou\n")
        print(f"  ⚠  {len(blurry)} image(s) floue(s) → images_floues.txt\n")

    return results, extractor


# ──────────────────────────────────────────────────────────────────────
# Filtrage des pages : chaque page écartée a une raison écrite au journal
# ──────────────────────────────────────────────────────────────────────

# Message commun des moteurs vision (claude, agent, ollama) pour une page
# qu'ils classent hors tableau.
_ERREUR_HORS_TABLEAU = 'Page ignorée (page de garde / modifications / sommaire)'


def numero_page(result: Dict) -> str:
    """Numéro de page lu dans le pied, sinon nom de l'image source."""
    page = str(result.get('metadata', {}).get('PAGE', '')).strip()
    if page:
        return page
    image = result.get('image_path')
    if image:
        return Path(image).name
    return str(result.get('page_num', '?'))


def raison_page_ignoree(result: Dict, colonnes_modele, min_rows: int,
                        densite_min: float) -> Optional[str]:
    """Raison d'écarter la page du classeur, ou None si elle est conservée."""
    if not result.get('success'):
        erreur = result.get('error')
        if erreur in (_ERREUR_HORS_TABLEAU, 'non-listing'):
            return "pas un tableau de câblage (page de garde, modifications, sommaire)"
        return erreur or "lecture impossible, aucune donnée rendue par le moteur"
    attendues = {h.upper() for h in colonnes_modele}
    lues = {h.upper() for h in result.get('headers', [])}
    if attendues and not (lues & attendues):
        return "en-tête sans colonne commune avec le modèle"
    cellules = [
        cell
        for row in result.get('rows', [])
        if row.get('type') == 'data'
        for cell in row.get('cells', [])
    ]
    n_lignes = sum(1 for row in result.get('rows', []) if row.get('type') == 'data')
    # Zéro ligne sous un en-tête reconnu = tableau vide (CABLE : RESERVE),
    # conservé tel quel ; seul un tableau partiellement lu est suspect.
    if n_lignes == 0:
        return None
    if n_lignes < min_rows:
        return f"{n_lignes} ligne(s) de données, minimum {min_rows} (MIN_DATA_ROWS)"
    lisibles = sum(1 for c in cellules if c and any(ch.isalnum() for ch in c))
    part = lisibles / max(len(cellules), 1)
    if part < densite_min:
        return (f"{part:.0%} de cellules lisibles, minimum {densite_min:.0%} "
                f"(PAGE_DENSITE_MIN)")
    return None


def marquer_illisibles(ws, marqueur: str, couleur: str) -> int:
    """Colore et commente les cellules contenant le marqueur ; renvoie leur nombre."""
    n = 0
    for ligne in ws.iter_rows():
        for cellule in ligne:
            if isinstance(cellule.value, str) and marqueur in cellule.value:
                cellule.fill = PatternFill('solid', fgColor=couleur)
                cellule.comment = Comment(
                    f"Caractère illisible ({marqueur}) laissé par la lecture :"
                    " vérifier sur le document d'origine.",
                    'TriosSeconverter',
                )
                n += 1
    return n


_NUMERO_PAGE_RE = re.compile(r'(\d+)([A-Za-z]?)')


def cle_numero_page(numero: str) -> Optional[Tuple[int, str]]:
    """(122, 'a') pour « 122a » ; None si ce n'est pas un numéro de page lisible."""
    m = _NUMERO_PAGE_RE.fullmatch(str(numero or '').strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2).lower()


def alertes_sequence_pages(resultats: List[Dict]) -> List[str]:
    """Alertes sur les numéros de page lus, dans l'ordre du document (jamais trié)."""
    alertes = []
    precedent = None
    for r in resultats:
        numero = str(r.get('metadata', {}).get('PAGE', '')).strip()
        cle = cle_numero_page(numero)
        if cle is None:
            source = Path(r.get('image_path') or '?').name
            alertes.append(f"numéro de page illisible ({numero or 'vide'}) : {source}")
            continue
        if precedent is not None:
            if cle == precedent[0]:
                alertes.append(f"page {numero} répétée (ordre du document conservé)")
            elif cle < precedent[0]:
                alertes.append(f"séquence non croissante : page {numero} après page "
                               f"{precedent[1]} (ordre du document conservé)")
        precedent = (cle, numero)
    return alertes


def _compact(valeur) -> str:
    return re.sub(r'\s+', '', str(valeur or '')).upper()


def champs_constants(nom_modele: str) -> List[str]:
    """Champs constants du modèle (config.py), sans ceux qui varient d'une page à l'autre."""
    champs = Config.CHAMPS_CONSTANTS_PAR_MODELE.get(nom_modele, Config.CHAMPS_CONSTANTS_DEFAUT)
    jamais = {c.upper() for c in Config.PIED_CHAMPS_JAMAIS_DEDUITS}
    return [c.upper() for c in champs if c.upper() not in jamais]


def deduire_champs_constants(valides: List[Dict], champs, libelles: Dict[str, str]):
    """Champs constants d'UN document : case vide reprise si les autres pages sont unanimes.

    - une case vide reçoit la valeur seulement si toutes les autres pages qui portent
      le champ donnent la même valeur ; sinon elle reste vide + alerte (pas de vote) ;
    - une valeur lue n'est jamais remplacée ; si toutes les autres pages donnent une
      autre valeur, elle est gardée + alerte « différent des autres pages » ;
    - les pages complétées portent meta['DEDUITS'] (cellule colorée, commentée).
    Ne voit que les pages d'un appel : jamais de passage d'un document à l'autre.
    Renvoie (résultats, alertes) ; les résultats reçus ne sont pas modifiés.
    """
    from pied_page import inserer_valeur, libelle_affiche
    resultats = [dict(r, metadata=dict(r.get('metadata') or {})) for r in valides]
    alertes = []
    jamais = {c.upper() for c in Config.PIED_CHAMPS_JAMAIS_DEDUITS}
    for cle in (c.upper() for c in champs):
        if cle in jamais:
            continue
        nom = libelle_affiche(cle, libelles)
        lues = [r for r in resultats if str(r['metadata'].get(cle, '')).strip()]
        vides = [r for r in resultats if not str(r['metadata'].get(cle, '')).strip()]
        for r in lues:
            valeur = str(r['metadata'][cle]).strip()
            autres = {_compact(o['metadata'][cle]) for o in lues if o is not r}
            if len(autres) == 1 and _compact(valeur) not in autres:
                autre = next(str(o['metadata'][cle]).strip() for o in lues if o is not r)
                alertes.append(f"page {numero_page(r)} : {nom} {valeur} différent des autres "
                               f"pages ({autre}), conservé")
        if not lues or not vides:
            continue
        distinctes = list(dict.fromkeys(str(r['metadata'][cle]).strip() for r in lues))
        if len({_compact(v) for v in distinctes}) > 1:
            alertes.append(f"{nom} vide, non complété : page(s) "
                           f"{', '.join(numero_page(r) for r in vides)} — les autres pages "
                           f"ne sont pas unanimes ({', '.join(distinctes)})")
            continue
        valeur = distinctes[0]
        for r in vides:
            meta = r['metadata']
            meta[cle] = valeur
            meta['DEDUITS'] = list(meta.get('DEDUITS') or []) + [cle]
            if meta.get('PIED_BRUT'):
                meta['PIED_BRUT'] = inserer_valeur(meta['PIED_BRUT'], cle, nom, valeur)
    return resultats, alertes


ALERTE_PAGE_NUMEROTEE = ("PAGE non imprimée dans tout le document : "
                         "pages numérotées dans l'ordre")


def pied_livre(valides: List[Dict], formats) -> Tuple[List[Dict], List[str]]:
    """Pied de l'Excel livré ; la lecture (metadata d'origine) reste telle qu'imprimée.

    - libellés du modèle de sortie (« P.E.T. », « N° PLAN »), valeurs lues ;
    - N° PLAN sans espaces si les pages l'impriment avec des espacements différents ;
    - si AUCUNE page de tableau ne porte de numéro : pages numérotées dans l'ordre,
      cellule « déduit », une seule ligne au journal ; sinon rien n'est déduit.
    Renvoie (résultats, lignes de journal) ; les résultats reçus ne sont pas modifiés.
    """
    from pied_page import inserer_valeur, libelles_modele, remplacer_libelles, remplacer_valeur
    libelles = libelles_modele(formats)
    resultats = [dict(r, metadata=dict(r.get('metadata') or {})) for r in valides]
    journal: List[str] = []
    for r in resultats:
        if r['metadata'].get('PIED_BRUT'):
            r['metadata']['PIED_BRUT'] = remplacer_libelles(r['metadata']['PIED_BRUT'], libelles)

    plans = [r['metadata']['NO_PLAN'] for r in resultats if r['metadata'].get('NO_PLAN')]
    if len({_compact(p) for p in plans}) == 1 and len(set(plans)) > 1:
        livre = _compact(plans[0])
        for r in resultats:
            meta = r['metadata']
            if meta.get('NO_PLAN'):
                meta['NO_PLAN'] = livre
                if meta.get('PIED_BRUT'):
                    meta['PIED_BRUT'] = remplacer_valeur(meta['PIED_BRUT'], 'NO_PLAN', livre)
        journal.append(f"  N° PLAN livré sans espaces : {livre} (imprimé "
                       f"{' / '.join(dict.fromkeys(plans))})")

    if resultats and not any(str(r['metadata'].get('PAGE', '')).strip() for r in resultats):
        etiquette = libelles.get('PAGE', 'PAGE')
        for rang, r in enumerate(resultats, start=1):
            meta = r['metadata']
            meta['PAGE'] = str(rang)
            meta['DEDUITS'] = list(meta.get('DEDUITS') or []) + ['PAGE']
            meta['COMMENTAIRES_DEDUITS'] = dict(
                meta.get('COMMENTAIRES_DEDUITS') or {},
                PAGE=f"PAGE : {rang}, non imprimée : numérotée dans l'ordre des pages de tableau")
            meta['REPERES_DEDUITS'] = dict(meta.get('REPERES_DEDUITS') or {},
                                           PAGE=f"{etiquette} : {rang}")
            if meta.get('PIED_BRUT'):
                meta['PIED_BRUT'] = inserer_valeur(meta['PIED_BRUT'], 'PAGE', etiquette,
                                                   str(rang), en_fin=True)
        journal.append(f"⚠ {ALERTE_PAGE_NUMEROTEE}")
    return resultats, journal


def corriger_numero_borne(valeur: str) -> Tuple[str, Optional[str]]:
    """(valeur, sous-champ d'origine) avec le O du 2e mot changé en 0 si c'est une coquille.

    Seul un numéro de borne en 2e et dernier mot (« D3T O1A ») est concerné ; sans
    coquille, (valeur inchangée, None).
    """
    mots = list(re.finditer(r'\S+', valeur or ''))
    if len(mots) != 2 or not re.fullmatch(Config.CORRECTION_O_MOTIF, mots[1].group()):
        return valeur, None
    debut = mots[1].start()
    return valeur[:debut] + '0' + valeur[debut + 1:], mots[1].group()


def corriger_coquilles_o(valides: List[Dict], colonnes) -> Tuple[List[Dict], List[str]]:
    """Coquilles O/0 corrigées dans les colonnes de borne ; une alerte par cellule.

    La lecture reçue n'est pas modifiée ; chaque ligne corrigée garde ses originaux
    dans 'corrections_o' {indice de colonne: sous-champ imprimé} pour le marquage.
    """
    resultats, alertes = [], []
    for r in valides:
        entetes = [h.upper() for h in r.get('headers') or []]
        cibles = [k for k, h in enumerate(entetes) if h in colonnes]
        lignes, rang = [], 0
        for row in r.get('rows') or []:
            if row.get('type') != 'blank':
                rang += 1
            if row.get('type') != 'data' or not cibles:
                lignes.append(row)
                continue
            cellules, origines = list(row.get('cells') or []), {}
            for k in cibles:
                if k >= len(cellules):
                    continue
                corrigee, origine = corriger_numero_borne(cellules[k])
                if origine:
                    alertes.append(f"page {numero_page(r)}, ligne {rang}, {entetes[k]} : Corrigé "
                                   f"O → 0 : l'original porte « {' '.join(cellules[k].split())} »")
                    cellules[k], origines[k] = corrigee, origine
            lignes.append(dict(row, cells=cellules, corrections_o=origines) if origines else row)
        resultats.append(dict(r, rows=lignes))
    return resultats, alertes


def marquer_corrections_o(ws, ligne_debut: int, resultat: Dict, couleur: str) -> int:
    """Colore et commente les cellules corrigées (même placement que _fill_worksheet)."""
    n, ligne = 0, ligne_debut + 1
    for row in resultat.get('rows') or []:
        if row.get('type') == 'blank':
            ligne += row.get('count', 1)
            continue
        for k, origine in (row.get('corrections_o') or {}).items():
            cellule = ws.cell(row=ligne, column=k + 1)
            cellule.fill = PatternFill('solid', fgColor=couleur)
            cellule.comment = Comment(f"corrigé : l'original porte {origine}", 'TriosSeconverter')
            n += 1
        ligne += 1
    return n


def texte_aux_positions(texte: str, debuts: List[int]) -> str:
    """Mots du texte posés à leur colonne de début, complétés par des espaces.

    Les mots ne changent jamais ; un nombre de débuts différent laisse le texte tel quel.
    """
    mots = (texte or '').split()
    if len(mots) != len(debuts):
        return texte
    sortie = ''
    for mot, debut in zip(mots, debuts):
        blancs = debut - len(sortie)
        sortie += ' ' * max(blancs, 1 if sortie else 0) + mot
    return sortie


def appliquer_positions(valides: List[Dict]) -> List[Dict]:
    """Cellules et sections réécrites à leurs positions d'origine (row['debuts'])."""
    resultats = []
    for r in valides:
        lignes = []
        for row in r.get('rows') or []:
            debuts = row.get('debuts')
            if not debuts:
                lignes.append(row)
            elif row.get('type') == 'section':
                lignes.append(dict(row, text=texte_aux_positions(row.get('text', ''),
                                                                 debuts.get(0, []))))
            else:
                cellules = [texte_aux_positions(c, debuts[k]) if k in debuts else c
                            for k, c in enumerate(row.get('cells') or [])]
                lignes.append(dict(row, cells=cellules))
        resultats.append(dict(r, rows=lignes))
    return resultats


def police_donnees(ws, ligne_debut: int, resultat: Dict, n_colonnes: int) -> None:
    """Police à chasse fixe sur les cellules de données et de section du bloc."""
    ligne = ligne_debut + 1
    for row in resultat.get('rows') or []:
        if row.get('type') == 'blank':
            ligne += row.get('count', 1)
            continue
        for k in range(1, n_colonnes + 1):
            cellule = ws.cell(row=ligne, column=k)
            cellule.font = Font(name=Config.POSITIONS_POLICE, size=Config.POSITIONS_TAILLE_POLICE,
                                bold=cellule.font.bold, italic=cellule.font.italic)
        ligne += 1


def marquer_deduits(ws, ligne_fin: int, meta: Dict, couleur: str) -> int:
    """Colore et commente les lignes de pied (2 dernières du bloc) portant une valeur déduite."""
    n = 0
    for cle in meta.get('DEDUITS') or []:
        valeur = str(meta.get(cle, ''))
        # Repère « PAGE : 3 » plutôt que « 3 », qui figure aussi dans le N° PLAN.
        repere = (meta.get('REPERES_DEDUITS') or {}).get(cle, valeur)
        motif = r'\s*'.join(re.escape(m) for m in repere.split())
        commentaire = (meta.get('COMMENTAIRES_DEDUITS') or {}).get(
            cle, f"{cle} : {valeur}, déduit des autres pages du document")
        for ligne in (ligne_fin - 2, ligne_fin - 1):
            cellule = ws.cell(row=ligne, column=2)
            if isinstance(cellule.value, str) and motif and re.search(motif, cellule.value):
                cellule.fill = PatternFill('solid', fgColor=couleur)
                cellule.comment = Comment(commentaire, 'TriosSeconverter')
                n += 1
                break
    return n


def bilan_controle_indice(tous: List[Dict], valides: List[Dict]) -> Optional[str]:
    """Ligne de journal d'un contrôle INDICE réussi, ou None (échec : voir alertes_pied).

    Un succès doit se voir autant qu'un échec : sans cette ligne, seule l'absence
    d'alerte disait que le contrôle avait eu lieu.
    """
    revisions = {_compact(x) for r in tous
                 for x in (r.get('metadata') or {}).get('REVISIONS') or []}
    lus = [str(r.get('metadata', {}).get('INDICE')).strip() for r in valides
           if r.get('metadata', {}).get('INDICE')]
    if not revisions or not lus or any(_compact(i) not in revisions for i in lus):
        return None
    return (f"contrôle INDICE : OK, {len(lus)} page(s), indices lus : "
            f"{', '.join(dict.fromkeys(lus))}")


def alertes_pied(tous: List[Dict], valides: List[Dict], champs_attendus) -> List[str]:
    """Contrôles du pied, en alerte seulement : aucune valeur n'est complétée ni corrigée."""
    alertes = []
    for r in valides:
        for alerte in r.get('metadata', {}).get('ALERTES_PIED') or []:
            alertes.append(f"page {numero_page(r)} : {alerte}")

    for cle in champs_attendus:
        # Emplacement occupé par un texte sans libellé : champ remplacé, pas absent.
        manquantes = [numero_page(r) for r in valides
                      if not str(r.get('metadata', {}).get(cle, '')).strip()
                      and not r.get('metadata', {}).get(f'EMPLACEMENT_{cle}')]
        if not manquantes:
            continue
        # Absent partout = le modèle ne correspond pas au document : une ligne, pas
        # une par page (un bruit répété apprend à ignorer les alertes).
        if len(manquantes) == len(valides):
            alertes.append(f"{cle} absent de tout le document : vérifier le modèle")
        else:
            alertes.append(f"champ {cle} absent du pied, laissé vide : "
                           f"page(s) {', '.join(manquantes)}")

    revisions = {_compact(x) for r in tous
                 for x in (r.get('metadata') or {}).get('REVISIONS') or []}
    if not revisions:
        alertes.append("contrôle INDICE impossible : aucune liste de révisions lue "
                       "sur une page de garde")
    else:
        for r in valides:
            indice = r.get('metadata', {}).get('INDICE')
            if indice and _compact(indice) not in revisions:
                alertes.append(f"page {numero_page(r)} : INDICE {indice} absent des "
                               f"révisions de la page de garde (non modifié)")

    plans = Counter(_compact(r['metadata']['NO_PLAN']) for r in valides
                    if r.get('metadata', {}).get('NO_PLAN'))
    if len(plans) > 1:
        majorite, nombre = plans.most_common(1)[0]
        for r in valides:
            plan = r.get('metadata', {}).get('NO_PLAN')
            if plan and _compact(plan) != majorite:
                alertes.append(f"page {numero_page(r)} : N° PLAN {plan} différent de la "
                               f"majorité ({majorite}, {nombre} pages), non corrigé")
    return alertes


# ──────────────────────────────────────────────────────────────────────
# Génération du classeur Excel combiné
# ──────────────────────────────────────────────────────────────────────

def generer_excel(
    results: List[Dict],
    extractor: 'BornierTableExtractor',
    output_path: Path,
    word_results: List[Dict] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Génère le classeur Excel avec deux feuilles distinctes :
      - « Borniers »       : tableaux issus de l'OCR sur les images
      - « tableaux word »  : tableaux importés depuis un fichier Word
                             (créée uniquement si word_results est fourni)

    Chaque bornier occupe exactement Config.PAGE_SIZE lignes (simulation
    d'une page A4 à 48 lignes avec marges standard).  Un saut de page
    Excel est inséré après chaque bornier pour l'impression.

    Les pages écartées (lecture ratée, hors tableau, moins de
    Config.MIN_DATA_ROWS lignes, illisibles) sont écrites dans on_log
    (« page ignorée : <numéro> <raison> ») ; un tableau vide est conservé.

    Le dictionnaire de données (data_dictionary.json) est chargé
    automatiquement et utilisé pour corriger les valeurs OCR douteuses.
    """
    log = on_log or print
    page_size = Config.PAGE_SIZE
    dictionary = get_dictionary()

    valides = []
    ignores = 0
    for r in results:
        raison = raison_page_ignoree(r, extractor._tpl.columns, Config.MIN_DATA_ROWS,
                                     Config.PAGE_DENSITE_MIN)
        if raison:
            ignores += 1
            log(f"  page ignorée : {numero_page(r)} {raison}")
            continue
        valides.append(r)

    champs_attendus = [fd.get('key', '') for fd in extractor._tpl.footer_extract_fields]
    libelles = {fd.get('key', '').upper(): fd.get('label', '')
                for fd in extractor._tpl.footer_extract_fields}
    valides, alertes_deduction = deduire_champs_constants(
        valides, champs_constants(extractor._tpl.name), libelles)
    for alerte in alertes_deduction:
        log(f"  ⚠ {alerte}")
    valides, lignes_livre = pied_livre(
        valides, [extractor._tpl.footer_row1_format, extractor._tpl.footer_row2_format])
    for ligne in lignes_livre:
        log(f"  {ligne.strip()}")
    # Ordre du document conservé, numéros tels que lus (ou numérotés ci-dessus quand
    # aucune page n'en porte) : un tri masquerait une page manquante ou mal lue.
    for alerte in alertes_sequence_pages(valides):
        log(f"  ⚠ {alerte}")
    for alerte in alertes_pied(results, valides, champs_attendus):
        log(f"  ⚠ {alerte}")
    bilan_indice = bilan_controle_indice(results, valides)
    if bilan_indice:
        log(f"  ✓ {bilan_indice}")
    valides, alertes_coquilles = corriger_coquilles_o(valides, Config.CORRECTION_O_COLONNES)
    for alerte in alertes_coquilles:
        log(f"  ⚠ {alerte}")
    if Config.POSITIONS_ORIGINALES:
        valides = appliquer_positions(valides)

    total = len(valides)

    if total == 0:
        log("  Aucun résultat valide à exporter en Excel.")
        return

    if ignores:
        log(f"  {ignores} page(s) ignorée(s), raisons ci-dessus.")
    print(f"  Génération Excel ({total} borniers, {page_size} lignes/page)…\n")

    wb = Workbook()
    ws = wb.active
    ws.title = "Borniers"

    # ── Mise en page A4 portrait — 1 tableau = 1 page ────────────────
    ws.page_setup.paperSize = 9          # 9 = A4
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.scale = None           # désactiver le % fixe sinon fitToWidth ignoré
    ws.page_setup.fitToWidth = 1         # largeur : 1 page
    ws.page_setup.fitToHeight = total    # hauteur : autant de pages que de tableaux
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    # 0.9 cm = 0.354 in (unité openpyxl = pouces)
    ws.page_margins = PageMargins(
        left=0.69, right=0.69,
        top=0.354, bottom=0.354,
        header=0, footer=0,
    )
    ws.print_options.horizontalCentered = True
    ws.print_options.verticalCentered = True

    current_row = 1

    for i, result in enumerate(valides):
        # Aucun nom de bornier ni P.E.T. de repli : un champ absent du pied
        # reste vide (alerte ci-dessus), jamais tiré du nom de fichier.
        next_row = extractor._fill_worksheet(
            ws, result,
            start_row=current_row,
            page_size=page_size,
            dictionary=dictionary,
            bornier_name=None,
            pet_name=None,
        )

        marquer_deduits(ws, next_row, result.get('metadata', {}), Config.COULEUR_DEDUIT)
        marquer_corrections_o(ws, current_row, result, Config.COULEUR_CORRIGE)
        if Config.POSITIONS_ORIGINALES:
            police_donnees(ws, current_row, result, len(extractor._tpl.columns))

        if i < total - 1:
            ws.row_breaks.append(Break(id=next_row - 1))
        current_row = next_row

        barre(i + 1, total, numero_page(result))

    # Zone d'impression = toute la feuille remplie
    n_cols = len(extractor._tpl.columns)
    ws.print_area = (
        f'A1:{get_column_letter(n_cols)}{current_row - 1}'
    )
    n_illisibles = marquer_illisibles(ws, Config.MARQUEUR_ILLISIBLE, Config.COULEUR_ILLISIBLE)
    if n_illisibles:
        log(f"  ⚠ {n_illisibles} cellule(s) avec « {Config.MARQUEUR_ILLISIBLE} » (caractère "
            f"illisible) colorée(s) dans l'Excel : à vérifier sur l'original.")

    # ── Feuille « tableaux word » (si des tableaux Word sont fournis) ──
    if word_results:
        valides_w = [r for r in word_results if r.get('success')]
        for alerte in alertes_sequence_pages(valides_w):
            log(f"  ⚠ tableaux word : {alerte}")

        if valides_w:
            n_word = len(valides_w)
            ws2 = wb.create_sheet("tableaux word")
            ws2.page_setup.paperSize = 9
            ws2.page_setup.orientation = 'portrait'
            ws2.page_setup.scale = None
            ws2.page_setup.fitToWidth = 1
            ws2.page_setup.fitToHeight = n_word
            ws2.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
            ws2.page_margins = PageMargins(
                left=0.69, right=0.69,
                top=0.75,  bottom=0.75,
            )

            cur2 = 1
            n_cols2 = len(extractor._tpl.columns)
            for j, result in enumerate(valides_w):
                next_row2 = extractor._fill_worksheet(
                    ws2, result,
                    start_row=cur2,
                    page_size=page_size,
                    dictionary=dictionary,
                    bornier_name=None,
                    pet_name=None,
                )

                if j < n_word - 1:
                    ws2.row_breaks.append(Break(id=next_row2 - 1))
                cur2 = next_row2

            ws2.print_area = (
                f'A1:{get_column_letter(n_cols2)}{cur2 - 1}'
            )
            print(
                f"  ✓ Feuille 'tableaux word' : {len(valides_w)} tableau(x)\n"
            )

    wb.save(str(output_path))
    print(
        f"\n  ✓ Classeur Excel enregistré : {output_path.name}"
        f"  ({total} borniers OCR, {current_row - 1} lignes)\n"
    )


# ──────────────────────────────────────────────────────────────────────
# Reformatage d'un Excel existant
# ──────────────────────────────────────────────────────────────────────

def reformatter_excel(
    input_path: Path,
    output_path: Path,
    on_log=None,
    on_progress=None,
    row_height: float = None,
    col_width_default: float = None,
    col_width_signal: float = None,
    margin_top: float = None,
    margin_bottom: float = None,
    margin_left: float = None,
    margin_right: float = None,
    margin_header: float = None,
    margin_footer: float = None,
    sheets: list = None,
    n_cols_override: int = 0,
    sheet_cols: dict = None,
    page_size_override: int = 0,
    sheet_page_sizes: dict = None,
) -> int:
    """
    Reformate un classeur Excel existant avec les règles de mise en page
    définies dans Config :
      - PAGE_SIZE lignes par tableau (59)
      - Hauteur de ligne 12.6 pt
      - Saut de page direct après chaque tableau, zéro ligne vide entre
      - Ajustement automatique : 1 page en largeur, N pages en hauteur

    Détecte les tableaux par leurs lignes d'en-tête (fond gris D9D9D9
    ou mots-clés de colonnes). Copie les valeurs et la mise en forme
    cellule par cellule dans un nouveau classeur reformaté.

    Retourne le nombre de tableaux reformatés.
    """
    from copy import copy as _copy
    from openpyxl import load_workbook
    from openpyxl.cell.cell import MergedCell

    def _log(msg):
        if on_log:
            on_log(msg)

    def _copy_cell(src, dst):
        # has_style omis intentionnellement : certaines cellules avec bordures
        # ne le rapportent pas (style hérité de la ligne/colonne source).
        if isinstance(dst, MergedCell):
            return
        if isinstance(src, MergedCell):
            dst.value = None
            return
        dst.value = src.value
        dst.font = _copy(src.font)
        dst.border = _copy(src.border)
        dst.fill = _copy(src.fill)
        dst.alignment = _copy(src.alignment)
        dst.number_format = src.number_format

    from openpyxl.styles import Side, Border
    from openpyxl.worksheet.properties import WorksheetProperties

    page_size = Config.PAGE_SIZE
    if row_height is None:
        row_height = getattr(Config, 'FORMAT_ROW_HEIGHT', 12.6)
    if col_width_default is None:
        col_width_default = getattr(Config, 'FORMAT_COL_WIDTH_DEFAULT', 19)
    if col_width_signal is None:
        col_width_signal = getattr(Config, 'FORMAT_COL_WIDTH_SIGNAL', 33)
    if margin_top is None:
        margin_top = getattr(Config, 'FORMAT_MARGIN_TOP', 0.9)
    if margin_bottom is None:
        margin_bottom = getattr(Config, 'FORMAT_MARGIN_BOTTOM', 0.9)
    if margin_left is None:
        margin_left = getattr(Config, 'FORMAT_MARGIN_LEFT', 1.75)
    if margin_right is None:
        margin_right = getattr(Config, 'FORMAT_MARGIN_RIGHT', 1.75)
    if margin_header is None:
        margin_header = getattr(Config, 'FORMAT_MARGIN_HEADER', 0.0)
    if margin_footer is None:
        margin_footer = getattr(Config, 'FORMAT_MARGIN_FOOTER', 0.0)

    def _cm(v):
        """Convertit des centimètres en pouces (unité openpyxl PageMargins)."""
        return round(v / 2.54, 5)

    _log(f"Ouverture de {input_path.name}…")
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='.*wmf image.*', category=UserWarning)
        wb_in = load_workbook(str(input_path))
    wb_out = Workbook()

    # Supprimer la feuille vide créée par défaut
    default = wb_out.active
    if default:
        wb_out.remove(default)

    # Styles réutilisables
    _thin = Side(style='thin')
    _ns = Side(style=None)
    _data_border = Border(left=_thin, right=_thin, top=_ns, bottom=_ns)

    # Empreintes de fond considérées comme « en-tête »
    GREY_FILLS = {'FFD9D9D9', 'D9D9D9'}
    ORANGE_FILLS = {'FFFFA500', 'FFA500'}
    COL_KEYWORDS = {
        'BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES',
        'TENANT', 'ABOUTISSANT', 'FIL', 'JAR',
        'REPERE', 'DESIGNATION', 'TYPE',
    }
    # Marqueurs de pied de page
    # — Mots courts : correspondance EXACTE de valeur de cellule
    #   (évite les faux positifs sur les signaux du type "IN_MTI_001",
    #    "CABLE_ALSTOM_xxx", etc. qui contiennent le mot en sous-chaîne)
    FOOTER_KWS_EXACT = {'MTI', 'SIEMENS', 'ALSTOM', 'SCHNEIDER'}
    # — Phrases : recherche en sous-chaîne dans le texte joint (ok car peu
    #   probable dans un nom de signal)
    FOOTER_KWS_SUBSTR = {'P.E.T', 'BORNIER :', 'N° PLAN', 'NO PLAN'}

    def _is_footer(row_cells):
        vals = [str(c.value or '').strip().upper() for c in row_cells]
        joined = ' '.join(vals)
        return (
            any(v for v in vals if v) and
            (
                any(mk in vals for mk in FOOTER_KWS_EXACT) or
                any(mk in joined for mk in FOOTER_KWS_SUBSTR)
            )
        )

    def _has_value(row_cells):
        return any(
            c.value is not None and str(c.value).strip()
            for c in row_cells
        )

    def _measure_table(src_rows):
        """Retourne (n_main, n_footer) pour un bloc de lignes source.

        Reproduit exactement la logique du reformatage principal afin que
        le pré-calcul du maximum soit cohérent avec la taille réelle écrite.
        """
        last_content = 0
        for i, row in enumerate(src_rows):
            if _has_value(row):
                last_content = i
        content_rows = src_rows[:last_content + 1]

        footer_idxs = []
        for k in range(min(3, len(content_rows))):
            ri = len(content_rows) - 1 - k
            if _is_footer(content_rows[ri]):
                footer_idxs.insert(0, ri)
            elif _has_value(content_rows[ri]):
                break

        n_footer = len(footer_idxs)
        main_rows_m = list(
            content_rows[:footer_idxs[0]] if n_footer else content_rows
        )
        while main_rows_m and not _has_value(main_rows_m[-1]):
            main_rows_m.pop()
        return len(main_rows_m), n_footer

    total_tables = 0

    for sheet_name in wb_in.sheetnames:
        if sheets is not None and sheet_name not in sheets:
            _log(f"  ○ Feuille « {sheet_name} » ignorée.")
            continue
        ws_in = wb_in[sheet_name]
        _log(f"  Feuille « {sheet_name} »…")

        # ── Charger toutes les lignes ──────────────────────────────────
        all_rows = list(ws_in.iter_rows())
        if not all_rows:
            _log("  ⚠  Feuille vide — ignorée.")
            continue
        n_cols = max((len(r) for r in all_rows), default=1)

        # ── Détecter les lignes d'en-tête ─────────────────────────────
        header_indices = []
        for ri, row in enumerate(all_rows):
            vals = [str(c.value or '').strip().upper() for c in row]
            non_empty = [v for v in vals if v]
            if len(non_empty) < 2:
                continue
            has_kw = any(v in COL_KEYWORDS for v in vals)
            has_grey = any(
                c.fill and c.fill.fgColor and
                str(c.fill.fgColor.rgb).upper() in GREY_FILLS | ORANGE_FILLS
                for c in row
            )
            if (has_kw or has_grey) and not _is_footer(row):
                header_indices.append(ri)

        if not header_indices:
            _log("  ⚠  Aucun en-tête détecté — feuille copiée sans modification.")
            ws_cp = wb_out.create_sheet(title=sheet_name)
            for row in all_rows:
                for cell in row:
                    _copy_cell(cell, ws_cp.cell(row=cell.row, column=cell.column))
            for ltr, dim in ws_in.column_dimensions.items():
                ws_cp.column_dimensions[ltr].width = dim.width or 10
            continue

        n_tables = len(header_indices)
        total_tables += n_tables
        _log(f"  → {n_tables} tableau(x) détecté(s)")

        # Lignes par tableau : override par feuille > global > config.
        _ps = (sheet_page_sizes or {}).get(sheet_name, 0) or page_size_override
        _page_size = _ps if _ps > 0 else page_size

        # ── Pré-calcul : taille du plus grand tableau de la feuille ───────
        # Garantit que TOUS les tableaux ont exactement le même nombre de
        # lignes : celui du tableau le plus grand (données + en-tête + pied).
        max_content = 0
        for _ti, _h_idx in enumerate(header_indices):
            _nxt = header_indices[_ti + 1] if _ti + 1 < n_tables else len(all_rows)
            _n_main, _n_footer = _measure_table(all_rows[_h_idx:_nxt])
            max_content = max(max_content, _n_main + _n_footer)
        uniform_block_size = max(_page_size, max_content)
        _log(
            f"  → Bloc uniforme : {uniform_block_size} lignes / tableau"
            f" (max contenu={max_content}, page_size={_page_size})"
        )

        # Largeur réelle du tableau : override manuel > auto depuis l'en-tête.
        # L'override par feuille prend la priorité sur l'override global.
        _override = (sheet_cols or {}).get(sheet_name, 0) or n_cols_override
        if _override > 0:
            tbl_n_cols = _override
        else:
            # Auto : colonnes avec un nom reconnu dans l'en-tête, sans COLONNE_X.
            # Arrêt dès 2 cellules vides consécutives après la dernière colonne
            # nommée : évite que des cellules fantômes hors tableau (résidu d'un
            # reformatage défectueux) gonflent tbl_n_cols.
            tbl_n_cols = 0
            _empty_streak = 0
            for _tc in all_rows[header_indices[0]]:
                v = str(_tc.value or '').strip().upper()
                if v and not v.startswith('COLONNE_'):
                    tbl_n_cols = max(tbl_n_cols, _tc.column)
                    _empty_streak = 0
                elif tbl_n_cols > 0:
                    _empty_streak += 1
                    if _empty_streak >= 2:
                        break   # 2 vides consécutifs = fin de la zone en-tête
            if tbl_n_cols == 0:
                tbl_n_cols = n_cols

        # ── Créer la feuille de sortie ─────────────────────────────────
        ws_out = wb_out.create_sheet(title=sheet_name)
        ws_out.page_setup.paperSize = 9
        ws_out.page_setup.orientation = 'portrait'
        ws_out.page_setup.scale = None   # désactiver le pourcentage fixe
        ws_out.page_setup.fitToWidth = 1
        ws_out.page_setup.fitToHeight = n_tables  # 1 page par tableau
        # fitToPage doit être activé dans sheetProperties, pas dans page_setup
        if ws_out.sheet_properties is None:
            ws_out.sheet_properties = WorksheetProperties()
        ws_out.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws_out.page_margins = PageMargins(
            left=_cm(margin_left),
            right=_cm(margin_right),
            top=_cm(margin_top),
            bottom=_cm(margin_bottom),
            header=_cm(margin_header),
            footer=_cm(margin_footer),
        )
        ws_out.print_options.horizontalCentered = True

        # Détecter la colonne SIGNAL pour lui affecter une largeur spéciale
        signal_col_letter = None
        if header_indices:
            for _hcell in all_rows[header_indices[0]]:
                if 'SIGNAL' in str(_hcell.value or '').strip().upper():
                    signal_col_letter = get_column_letter(_hcell.column)
                    break

        # Largeurs fixes : SIGNAL = col_width_signal, autres = col_width_default
        # Limité à tbl_n_cols pour ne pas créer de colonnes fantômes au-delà du tableau.
        for ci in range(1, tbl_n_cols + 1):
            ltr = get_column_letter(ci)
            ws_out.column_dimensions[ltr].width = (
                col_width_signal if ltr == signal_col_letter
                else col_width_default
            )

        out_row = 1

        for ti, h_idx in enumerate(header_indices):
            _log(f"  ▶ Tableau {ti + 1} / {n_tables}…")
            if on_progress:
                on_progress(ti + 1, n_tables)
            # Étendue du tableau source (jusqu'au prochain en-tête ou fin)
            nxt = header_indices[ti + 1] if ti + 1 < n_tables else len(all_rows)
            src_rows = all_rows[h_idx:nxt]

            # Trouver la dernière ligne avec une valeur
            last_content = 0
            for i, row in enumerate(src_rows):
                if _has_value(row):
                    last_content = i
            content_rows = src_rows[:last_content + 1]

            # ── Séparer pied de page / corps ──────────────────────────
            # Scan de bas en haut : collecter les lignes de pied (max 3)
            footer_rows = []   # lignes de pied (ordre chronologique)
            footer_idxs = []   # indices dans content_rows
            for k in range(min(3, len(content_rows))):
                ri = len(content_rows) - 1 - k
                if _is_footer(content_rows[ri]):
                    footer_rows.insert(0, content_rows[ri])
                    footer_idxs.insert(0, ri)
                elif _has_value(content_rows[ri]):
                    break   # ligne non-pied avec valeur → arrêt

            n_footer = len(footer_rows)

            # Corps = tout jusqu'au pied, sans rembourrage vide en fin
            main_rows = list(
                content_rows[:footer_idxs[0]] if n_footer else content_rows
            )
            while main_rows and not _has_value(main_rows[-1]):
                main_rows.pop()
            n_main = len(main_rows)

            # ── Calcul du bloc ─────────────────────────────────────────
            # uniform_block_size : taille du plus grand tableau de la feuille.
            # Tous les tableaux sont mis à la même taille pour cohérence visuelle.
            block_size = uniform_block_size
            n_padding = block_size - n_main - n_footer
            end_row = out_row + block_size

            # Hauteur de ligne uniforme sur tout le bloc
            for ri in range(out_row, end_row):
                ws_out.row_dimensions[ri].height = row_height

            # ── 1. Corps (en-tête + données) ───────────────────────────
            main_src_start = h_idx + 1   # 1-based dans openpyxl
            main_offset = out_row - main_src_start
            for mr in list(ws_in.merged_cells.ranges):
                if (mr.min_row >= main_src_start
                        and mr.max_row <= main_src_start + n_main - 1
                        and mr.min_col <= tbl_n_cols):   # limiter aux colonnes du tableau
                    try:
                        ws_out.merge_cells(
                            start_row=mr.min_row + main_offset,
                            start_column=mr.min_col,
                            end_row=mr.max_row + main_offset,
                            end_column=min(mr.max_col, tbl_n_cols),
                        )
                    except Exception:
                        pass
            for i, row in enumerate(main_rows):
                dst_r = out_row + i
                for cell in row:
                    if cell.column > tbl_n_cols:   # ne pas écrire hors du tableau
                        break
                    _copy_cell(cell, ws_out.cell(row=dst_r, column=cell.column))

            # ── 2. Rembourrage — cellules vides avec bordures ──────────
            # IMPORTANT : écrire de vraies cellules (même vides) oblige
            # openpyxl à inclure ces lignes dans le XML. Sans cela,
            # max_row s'arrête à la dernière cellule écrite et les lignes
            # de rembourrage "disparaissent" du fichier.
            for ri in range(out_row + n_main, out_row + n_main + n_padding):
                for ci in range(1, tbl_n_cols + 1):
                    ws_out.cell(row=ri, column=ci).border = _data_border

            # ── 3. Pied de page (toujours en dernière position) ────────
            if footer_rows:
                foot_dst_start = out_row + n_main + n_padding
                foot_src_start = h_idx + footer_idxs[0] + 1   # 1-based
                foot_offset = foot_dst_start - foot_src_start

                # A — valeurs + styles AVANT les fusions.
                # Les cellules non-maîtresses sont encore des Cell normaux
                # à ce stade ; merge_cells() ne supprime pas les données
                # déjà écrites dans ws._cells, donc bordures et valeurs
                # survivent à la fusion dans le XML final.
                for i, row in enumerate(footer_rows):
                    dst_r = foot_dst_start + i
                    for cell in row:
                        if (not isinstance(cell, MergedCell)
                                and cell.column <= tbl_n_cols):
                            dst = ws_out.cell(row=dst_r, column=cell.column)
                            dst.value = cell.value
                            dst.font = _copy(cell.font)
                            dst.fill = _copy(cell.fill)
                            dst.alignment = _copy(cell.alignment)
                            dst.number_format = cell.number_format

                # B — bordures complètes sur toutes les positions du pied
                # (avant fusion, toutes les cellules sont encore accessibles)
                _full = Border(
                    left=_thin, right=_thin,
                    top=_thin, bottom=_thin,
                )
                for i in range(n_footer):
                    dst_r = foot_dst_start + i
                    for ci in range(1, tbl_n_cols + 1):
                        ws_out.cell(row=dst_r, column=ci).border = _full

                # C — fusions APRÈS valeurs et bordures
                for mr in list(ws_in.merged_cells.ranges):
                    if (mr.min_row >= foot_src_start
                            and mr.max_row <= foot_src_start + n_footer - 1
                            and mr.min_col <= tbl_n_cols):
                        try:
                            ws_out.merge_cells(
                                start_row=mr.min_row + foot_offset,
                                start_column=mr.min_col,
                                end_row=mr.max_row + foot_offset,
                                end_column=min(mr.max_col, tbl_n_cols),
                            )
                        except Exception:
                            pass

            # ── Saut de page après ce tableau (sauf le dernier) ────────
            if ti < n_tables - 1:
                ws_out.row_breaks.append(Break(id=end_row - 1))

            out_row = end_row

            _log(f"  ✓ Tableau {ti + 1}/{n_tables} "
                 f"({n_main} données + {n_padding} rembourrage + {n_footer} pied)")

        # Zone d'impression
        ws_out.print_area = f"A1:{get_column_letter(tbl_n_cols)}{out_row - 1}"

    try:
        wb_out.save(str(output_path))
    finally:
        wb_in.close()   # ferme le verrou Windows sur le fichier source
    _log(f"\n  ✓ Fichier reformaté : {output_path.name}  ({total_tables} tableau(x))")
    return total_tables


# ──────────────────────────────────────────────────────────────────────
# Mise à jour des espacements depuis un PDF source
# ──────────────────────────────────────────────────────────────────────

def appliquer_espacements_pdf(
    excel_path: Path,
    pdf_path: Path,
    output_path: Path,
    template=None,
    on_log=None,
    on_progress=None,
) -> int:
    """
    Lit les espacements proportionnels depuis le PDF source et les applique
    dans un Excel existant sans modifier les valeurs texte des cellules.

    Principe :
    1. Extraire les cellules du PDF avec OCR_PRESERVE_INTRA_CELL_SPACING=True
       → les positions PDF donnent les écarts réels entre blocs de mots.
    2. Construire un index normalisé : texte_sans_espaces → texte_espacé.
    3. Pour chaque cellule Excel dont la version normalisée est dans l'index,
       remplacer le contenu par la version avec espacements proportionnels.
       Les cellules sans correspondance ne sont pas touchées.

    Retourne le nombre de cellules modifiées.
    """
    from openpyxl import load_workbook
    from pdf_extractor import PdfTableExtractor, is_pymupdf_available
    from template import DEFAULT_TEMPLATE

    def _log(msg: str) -> None:
        if on_log:
            on_log(msg)

    if not is_pymupdf_available():
        raise RuntimeError(
            "PyMuPDF (fitz) requis.\n"
            "Installez-le avec : pip install pymupdf"
        )

    tpl = template or DEFAULT_TEMPLATE

    # ── Étape 1 : extraire les cellules avec espacements depuis le PDF ──
    _log(f"  Lecture du PDF : {pdf_path.name}...")
    if on_progress:
        on_progress(0, 3)

    pdf_ext = PdfTableExtractor(template=tpl)
    results, _ = pdf_ext.extract_all(pdf_path)

    # Index normalisé → version espacée (uniquement les cellules multi-espaces)
    # La clé supprime tous les espaces et met en majuscules pour la comparaison.
    spacing_map: Dict[str, str] = {}
    pages_ok = sum(1 for r in results if r.get('success'))

    for result in results:
        if not result.get('success'):
            continue
        for row in result.get('rows', []):
            if row.get('type') != 'data':
                continue
            for cell_val in row.get('cells', []):
                if not cell_val or '  ' not in cell_val:
                    continue  # pas d'espacement multiple → rien à apporter
                key = re.sub(r'\s+', '', cell_val.upper())
                if key and key not in spacing_map:
                    spacing_map[key] = cell_val

    _log(
        f"  → {pages_ok} pages PDF lues, "
        f"{len(spacing_map)} motif(s) d'espacement détecté(s)."
    )
    if on_progress:
        on_progress(1, 3)

    if not spacing_map:
        _log(
            "  Aucun espacement multiple trouvé dans le PDF.\n"
            "  Conseil : vérifiez que le PDF contient une couche texte\n"
            "  avec des positions de caractères précises (PDF natif ou\n"
            "  exporté depuis logiciel, pas un scan simple)."
        )
        if on_progress:
            on_progress(3, 3)
        return 0

    # ── Étape 2 : appliquer dans l'Excel ───────────────────────────────
    _log(f"  Application dans : {excel_path.name}...")
    wb = load_workbook(str(excel_path))
    updated = 0

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                if not isinstance(val, str) or ' ' not in val:
                    continue
                key = re.sub(r'\s+', '', val.upper())
                if not key:
                    continue
                spaced = spacing_map.get(key)
                # Appliquer uniquement si la version espacée DIFFÈRE
                # et contient bien les mêmes caractères (hors espaces)
                if spaced and spaced != val:
                    cell.value = spaced
                    updated += 1

    if on_progress:
        on_progress(2, 3)

    wb.save(str(output_path))
    if on_progress:
        on_progress(3, 3)

    _log(f"  → {updated} cellule(s) mise(s) à jour.")
    _log(f"  → Enregistré : {output_path.name}")
    return updated


# ──────────────────────────────────────────────────────────────────────
# Génération du document Word combiné
# ──────────────────────────────────────────────────────────────────────

def generer_word(
    results: List[Dict],
    extractor: 'BornierTableExtractor',
    output_path: Path,
    word_source_path: Path = None,
) -> None:
    """Tous les tableaux dans un seul document Word, séparés par sauts de page.

    Si word_source_path est fourni, les tableaux du fichier Word source sont
    copiés fidèlement (copier-coller XML) — toute la mise en forme est préservée.
    """
    import copy as _copy

    succes = [r for r in results if r.get('success')]
    total_ocr = len(succes)

    # Charger les tableaux Word source si fournis
    src_tables = []
    if word_source_path and Path(word_source_path).exists():
        try:
            src_doc = Document(str(word_source_path))
            src_tables = src_doc.tables
        except Exception as e:
            print(f"  ⚠ Impossible d'ouvrir {word_source_path.name} : {e}")

    total_word = len(src_tables)
    total = total_ocr + total_word

    if total == 0:
        print("  Aucun résultat à exporter en Word.")
        return

    msg_word = f" + {total_word} tableau(x) Word copiés" if total_word else ""
    print(f"  Génération Word ({total_ocr} tableau(x) OCR{msg_word})…\n")

    doc = Document()
    premier = True

    # ── Partie 1 : borniers OCR (reconstruits) ───────────────────────────
    for i, result in enumerate(succes):
        meta = result.get('metadata', {})
        img_stem = Path(result.get('image_path', '')).stem
        titre = (meta.get('BORNIER') or img_stem).strip()

        if not premier:
            doc.add_page_break()
        premier = False

        doc.add_heading(f'Bornier : {titre}', level=2)
        extractor._add_table_to_doc(doc, result)
        barre(i + 1, total, titre)

    # ── Partie 2 : tableaux Word — copie XML fidèle ──────────────────────
    for j, table in enumerate(src_tables):
        if not premier:
            doc.add_page_break()
        premier = False
        # Copie profonde du XML — préserve largeurs colonnes, bordures, polices
        doc.element.body.append(_copy.deepcopy(table._tbl))
        barre(total_ocr + j + 1, total, f'Tableau Word {j + 1}')

    doc.save(str(output_path))
    print(f"\n  ✓ Document Word enregistré : {output_path.name}\n")


# ──────────────────────────────────────────────────────────────────────
# Point d'entrée
# ──────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print()
    print('=' * 62)
    print('   GÉNÉRATION DU CLASSEUR UNIQUE — BORNIERS')
    print('=' * 62)

    images_dir = Config.get_output_folder()

    if not images_dir.exists():
        print(f"\n  Dossier introuvable : {images_dir}")
        print("  Lancez d'abord run.py pour extraire les images.")
        sys.exit(1)

    # ── Étape 1 : extraction OCR ──────────────────────────────────────
    t0 = time.time()
    results, extractor = extraire_tous(images_dir)

    if not results:
        sys.exit(1)

    out_dir = Path.cwd()

    # ── Étape 2 : classeur Excel ──────────────────────────────────────
    print('-' * 62)
    generer_excel(results, extractor, out_dir / 'tous_les_borniers.xlsx')

    duree = time.time() - t0
    print('=' * 62)
    print(f'  TERMINÉ en {duree:.0f} s')
    print()
    print('  Fichier créé :')
    print('    → tous_les_borniers.xlsx')
    print('=' * 62)
    print()


if __name__ == '__main__':
    main()
