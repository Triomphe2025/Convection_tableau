"""Mesure la précision d'une sortie TriosSeconverter contre une référence.

Usage :
    python mesurer_precision.py <sortie.xlsx> <reference.xlsx|reference.pdf>

`sortie.xlsx` est un classeur produit par TriosSeconverter (feuille "Borniers").
`reference` est soit un Excel de vérité terrain (feuilles "Verite_tableaux" +
"Verite_pieds", cf. tests/fixtures/*_verite.xlsx), soit un PDF vectoriel dont
la couche texte fait foi (--modele requis dans ce cas, pour connaître les
noms de colonnes).

Affiche pages manquantes, cellules fausses par catégorie, pieds faux,
positions fausses, et ajoute une ligne à mesures.csv (Config.MESURE_CSV_PATH).

Code retour : 0 si aucun écart, 1 sinon.
"""

import argparse
import csv
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import openpyxl

from config import Config
from mesure_precision import (
    AJOUTE, CONFUSION, CONTENU_DIFFERENT, ESPACEMENT, GLISSEMENT, MANQUANT,
    comparer_alertes, extraire_pied, formater_rapport, mesurer, remplacer_positions,
    verifier_controle_indice,
)
from template import TemplateManager

# Mêmes vocabulaires que le reformatage dans generer_classeur.py, pour
# reconnaître les mêmes lignes d'en-tête et de pied de page dans un .xlsx
# déjà produit par le pipeline.
_COL_KEYWORDS = {
    'BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES',
    'TENANT', 'ABOUTISSANT', 'FIL', 'JAR',
    'REPERE', 'DESIGNATION', 'TYPE',
}
_FOOTER_KWS_EXACT = {'MTI', 'SIEMENS', 'ALSTOM', 'SCHNEIDER', 'MATRA'}
# « PET : » sans points : pied des pages TP2 de 223400PE137.
_FOOTER_KWS_SUBSTR = {
    'P.E.T', 'PET :', 'BORNIER :', 'N° PLAN', 'NO PLAN',
    'CABLE :', 'TYPE :', 'INDICE :', 'PAGE :',
}


def _est_entete(valeurs: List[str]) -> bool:
    return any(v.strip().upper() in _COL_KEYWORDS for v in valeurs)


def _est_pied(valeurs: List[str]) -> bool:
    haut = [v.strip().upper() for v in valeurs]
    # Pied recopié tel qu'imprimé depuis l'étape 7 : « N°   PLAN », « INDICE     : ».
    joint = re.sub(r'\s*:', ' :', ' '.join(' '.join(haut).split()))
    joint = re.sub(r'N°\s*PLAN', 'N° PLAN', joint)
    return any(v for v in haut) and (
        any(mk in haut for mk in _FOOTER_KWS_EXACT)
        or any(mk in joint for mk in _FOOTER_KWS_SUBSTR)
    )


def _ligne_ou_section(cellules: List[str]) -> dict:
    """Ligne « NOM DU CABLE : … » seule dans sa 1re cellule = section, sinon donnée."""
    if (cellules and cellules[0].strip().upper().startswith(Config.MESURE_MOT_SECTION)
            and not any(c.strip() for c in cellules[1:])):
        return {'type': 'section', 'text': cellules[0].strip(), 'cells': list(cellules)}
    return {'type': 'data', 'cells': cellules, 'confidence': [100] * len(cellules)}


def lire_xlsx(chemin: Path, feuille: Optional[str] = None) -> List[dict]:
    """Lit un classeur TriosSeconverter : une page pivot par tableau (bloc
    en-tête → données → pied), regroupement par ligne d'en-tête détectée.
    """
    wb = openpyxl.load_workbook(str(chemin), data_only=True)
    ws = wb[feuille] if feuille else wb.worksheets[0]

    pages: List[dict] = []
    lignes: List[dict] = []
    pied: List[str] = []
    commence = False

    def _clore():
        if lignes or pied:
            pages.append({
                'success': True, 'rows': lignes[:], 'metadata': {}, 'pied_texte': pied[:],
            })

    for row in ws.iter_rows():
        valeurs = ['' if c.value is None else str(c.value) for c in row]
        if not any(v.strip() for v in valeurs):
            continue
        if _est_entete(valeurs):
            if commence:
                _clore()
            lignes, pied = [], []
            commence = True
            continue
        # Section testée avant le pied : « NOM DU CABLE : … » contient « CABLE : ».
        if commence and _ligne_ou_section(valeurs)['type'] == 'section':
            lignes.append(_ligne_ou_section(valeurs))
            continue
        if _est_pied(valeurs):
            # Cellule gauche du pied = logo, sans libellé dans l'Excel livré.
            if valeurs[0].strip() and any(v.strip() for v in valeurs[1:]):
                pied.append(f"LOGO : {valeurs[0].strip()}")
                pied.append(' '.join(v for v in valeurs[1:] if v.strip()))
            else:
                pied.append(' '.join(v for v in valeurs if v.strip()))
            continue
        if commence:
            lignes.append(_ligne_ou_section(valeurs))
    if commence:
        _clore()
    return pages


def lire_verite_excel(chemin: Path) -> Tuple[List[dict], List[str]]:
    """Lit un Excel de vérité terrain (feuilles Verite_tableaux/Verite_pieds).

    Colonnes de données déduites de l'en-tête de Verite_tableaux : tout ce
    qui suit "Ligne" et précède la 1ère colonne d'annotation ("A verifier…",
    "Valide…") — aucune liste de noms de colonnes figée.
    """
    wb = openpyxl.load_workbook(str(chemin), data_only=True)
    ws_tab = wb['Verite_tableaux']
    entetes = [str(c.value or '') for c in next(ws_tab.iter_rows(min_row=1, max_row=1))]
    debut = entetes.index('Ligne') + 1
    fin = next(
        (i for i in range(debut, len(entetes))
         if re.search(r'verifier|valide', entetes[i], re.IGNORECASE)),
        len(entetes),
    )
    colonnes = entetes[debut:fin]

    lignes_par_page: dict = {}
    for row in ws_tab.iter_rows(min_row=2):
        valeurs = [c.value for c in row]
        if valeurs[0] is None:
            continue
        extrait = int(valeurs[0])
        cellules = ['' if v is None else str(v) for v in valeurs[debut:fin]]
        # Les espaces de la vérité sont gardés tels quels et `exact` active la
        # comparaison des colonnes de début des sous-champs : les positions de
        # l'original font partie du résultat attendu (« D_T       02A »).
        ligne = _ligne_ou_section(cellules)
        if ligne['type'] == 'data':
            ligne['exact'] = True
        ligne['ligne_verite'] = valeurs[debut - 1]
        lignes_par_page.setdefault(extrait, []).append(ligne)

    if 'Verite_positions' in wb.sheetnames:
        _attacher_positions(wb['Verite_positions'], lignes_par_page, colonnes)

    pieds_par_page: dict = {}
    pieds_lus: dict = {}
    pieds_autres: dict = {}
    schema = stricts = None
    if 'Verite_pieds' in wb.sheetnames:
        ws_pied = wb['Verite_pieds']
        entetes_p = [str(c.value or '') for c in next(ws_pied.iter_rows(min_row=1, max_row=1))]
        # La page est repérée par la 1re colonne, quel que soit son nom (« Page
        # extrait », « Page PDF »…), comme dans Verite_tableaux. Les colonnes
        # d'identification, d'annotation et la « ligne brute » (recopie pour
        # contrôle humain) ne sont pas des libellés de pied.
        cle_page = entetes_p[0]
        # Deux niveaux : colonnes imprimées (ce que l'appli doit LIRE) et colonnes
        # « livré » (ce que l'Excel livré doit porter : N° PLAN normalisé, page
        # numérotée). L'Excel est comparé au niveau livré.
        hors_pied = r'^page\s+\w|brute|verifier|valide|remarque|pied dans|ecart|écart|autre texte'
        livres = {e: re.sub(r'\s+livr\w*$', '', e, flags=re.I).strip()
                  for e in entetes_p[1:] if re.search(r'livr', e, re.I)}
        libelles = [e for e in entetes_p[1:]
                    if e not in livres and not re.search(hors_pied, e, re.I)]
        autres = [e for e in entetes_p[1:] if re.search(r'autre texte', e, re.I)]
        schema = {cle for lib in libelles + list(livres.values())
                  for cle in extraire_pied(f"{lib.upper()} : X")}
        stricts = {cle for lib in livres.values() for cle in extraire_pied(f"{lib.upper()} : X")}
        if 'LOGO' in schema:
            stricts.add('LOGO')
        for row in ws_pied.iter_rows(min_row=2):
            valeurs = {entetes_p[i]: row[i].value for i in range(len(entetes_p))}
            if valeurs.get(cle_page) is None:
                continue
            extrait = int(valeurs[cle_page])
            imprime = {lib: valeurs[lib] for lib in libelles if valeurs.get(lib) not in (None, '')}
            livre = dict(imprime)
            for col, lib in livres.items():
                if valeurs.get(col) not in (None, ''):
                    livre[lib] = re.sub(r'\s*\(d[ée]duit\)\s*$', '', str(valeurs[col]), flags=re.I)
            pieds_par_page.setdefault(extrait, []).append(
                '  '.join(f"{lib.upper()} : {v}" for lib, v in livre.items()))
            pieds_lus.setdefault(extrait, []).append(
                '  '.join(f"{lib.upper()} : {v}" for lib, v in imprime.items()))
            pieds_autres.setdefault(extrait, []).extend(
                str(valeurs[a]) for a in autres if valeurs.get(a) not in (None, ''))

    pages = []
    for extrait in sorted(set(lignes_par_page) | set(pieds_par_page)):
        page = {
            'success': True,
            'rows': lignes_par_page.get(extrait, []),
            'metadata': {},
            'pied_texte': pieds_par_page.get(extrait, []),
            'pied_lu': pieds_lus.get(extrait, []),
            'pied_autre': pieds_autres.get(extrait, []),
        }
        if schema is not None:
            page['libelles_pied'] = sorted(schema)
            page['libelles_stricts'] = sorted(stricts)
        pages.append(page)
    return pages, colonnes


def lire_attentes(chemin: Path) -> dict:
    """Attentes d'une vérité terrain hors tableau : alertes, révisions de la garde, INDICE.

    {'alertes': textes de « Alertes_attendues » (None si la feuille manque),
     'revisions': indices listés dans « Verite_garde » (None si la feuille manque),
     'indices_pages': INDICE imprimés de « Verite_pieds »}.
    """
    wb = openpyxl.load_workbook(str(chemin), data_only=True)
    attentes: dict = {'alertes': None, 'revisions': None, 'indices_pages': []}
    if 'Alertes_attendues' in wb.sheetnames:
        lignes = list(wb['Alertes_attendues'].iter_rows(values_only=True))
        col = next(k for k, e in enumerate(lignes[0]) if re.search(r'alerte', str(e or ''), re.I))
        attentes['alertes'] = [str(r[col]) for r in lignes[1:] if r[col] not in (None, '')]
    if 'Verite_garde' in wb.sheetnames:
        lignes = list(wb['Verite_garde'].iter_rows(values_only=True))
        col = next(k for k, e in enumerate(lignes[0])
                   if re.search(r'indices list', str(e or ''), re.I))
        revisions: List[str] = []
        for r in lignes[1:]:
            for morceau in str(r[col] or '').split(','):
                mots = morceau.split()
                if (mots and re.fullmatch(Config.PIED_INDICE_MOTIF, mots[0])
                        and mots[0] not in revisions):
                    revisions.append(mots[0])
        attentes['revisions'] = revisions
    if 'Verite_pieds' in wb.sheetnames:
        lignes = list(wb['Verite_pieds'].iter_rows(values_only=True))
        col = next((k for k, e in enumerate(lignes[0])
                    if str(e or '').strip().upper() == 'INDICE'), None)
        if col is not None:
            attentes['indices_pages'] = [str(r[col]).strip() for r in lignes[1:]
                                         if r[0] is not None and r[col] not in (None, '')]
    return attentes


def lire_journal_conversion(chemin: Path) -> List[str]:
    """Lignes du journal de conversion (conversion.log) ; [] s'il n'existe pas."""
    chemin = Path(chemin)
    return chemin.read_text(encoding='utf-8').splitlines() if chemin.exists() else []


def appliquer_attentes(rapport, attentes: dict, journal: List[str]) -> None:
    """Alertes (attendues contre lignes ⚠ du journal) et contrôle INDICE dans le rapport."""
    if attentes.get('alertes') is not None:
        emises = [lg.split('⚠', 1)[1].strip() for lg in journal if '⚠' in lg]
        rapport.alertes_manquantes, rapport.fausses_alertes = comparer_alertes(
            attentes['alertes'], emises)
    if attentes.get('revisions') is not None:
        rapport.controle_indice = verifier_controle_indice(
            attentes['revisions'], attentes['indices_pages'], journal)


def _cle_entete(texte) -> str:
    sans_accents = unicodedata.normalize('NFKD', str(texte or ''))
    sans_accents = ''.join(c for c in sans_accents if not unicodedata.combining(c))
    return re.sub(r'[^a-z]', '', sans_accents.lower())


def _attacher_positions(ws, lignes_par_page: dict, colonnes: List[str]) -> None:
    """Feuille Verite_positions → row['positions'] = {colonne: débuts des sous-champs}.

    Une ligne de la feuille : page, ligne, colonne, sous-champ (n° du mot dans la
    cellule, à partir de 1), début (colonne du 1er caractère du sous-champ, la colonne 0
    étant le caractère le plus à gauche de cette colonne du tableau sur la page).
    Saisie humaine (jamais tirée d'un OCR) : une page, une ligne ou une colonne
    inconnue est une erreur de saisie, signalée avec sa ligne dans la feuille. Colonne
    facultative « Mot » : le mot attendu, qui doit être le n-ième mot de la cellule visée
    dans Verite_tableaux ; un désaccord est une erreur de saisie, pas un écart de conversion.
    """
    entetes = {_cle_entete(c.value): k for k, c in enumerate(next(ws.iter_rows(max_row=1)))}
    requis = {'page': 'page', 'ligne': 'ligne', 'colonne': 'colonne',
              'souschamp': 'sous-champ', 'debut': 'début'}
    manquants = [nom for cle, nom in requis.items()
                 if not any(e.startswith(cle) for e in entetes)]
    if manquants:
        raise ValueError(f"Verite_positions : colonne(s) absente(s) : {', '.join(manquants)}")
    index = {cle: next(k for e, k in entetes.items() if e.startswith(cle)) for cle in requis}
    # « Page extrait », comme la 1re colonne de Verite_tableaux, plutôt que « Page document ».
    index['page'] = entetes.get('pageextrait', index['page'])
    i_mot = next((k for e, k in entetes.items() if e.startswith('mot')), None)
    desaccords = []
    debuts: dict = {}
    for num, row in enumerate(ws.iter_rows(min_row=2), start=2):
        v = [c.value for c in row]
        if all(x in (None, '') for x in v):
            continue
        page, ligne, colonne = int(v[index['page']]), v[index['ligne']], str(v[index['colonne']])
        if colonne not in colonnes:
            raise ValueError(f"Verite_positions ligne {num} : colonne inconnue {colonne!r}")
        cible = next((r for r in lignes_par_page.get(page, [])
                      if str(r['ligne_verite']) == str(ligne)), None)
        if cible is None:
            raise ValueError(f"Verite_positions ligne {num} : page {page} ligne {ligne} "
                             "absente de Verite_tableaux")
        sous_champ = int(v[index['souschamp']])
        if i_mot is not None and v[i_mot] not in (None, ''):
            mots = cible['cells'][colonnes.index(colonne)].split()
            lu = mots[sous_champ - 1] if 0 < sous_champ <= len(mots) else None
            if str(lu) != str(v[i_mot]):
                desaccords.append(f"ligne {num} (page {page}, ligne {ligne}, {colonne}, "
                                  f"sous-champ {sous_champ}) : Mot {v[i_mot]!r}, "
                                  f"Verite_tableaux {lu!r}")
        debuts.setdefault((id(cible), colonne), (cible, {}))[1][sous_champ] = int(
            v[index['debut']])
    if desaccords:
        raise ValueError("Verite_positions : erreur(s) de saisie, mot de contrôle différent "
                         "de Verite_tableaux :\n" + '\n'.join(desaccords))
    for (_, colonne), (cible, par_mot) in debuts.items():
        cible.setdefault('positions', {})[colonne] = tuple(par_mot[k] for k in sorted(par_mot))


# ── Référence PDF vectoriel (couche texte reconstruite en grille) ────

def _est_entete_grille(ligne: str, colonnes: List[str]) -> bool:
    mots = {re.sub(r'[^A-Z0-9]', '', m.upper()) for m in ligne.split()}
    return all(re.sub(r'[^A-Z0-9]', '', c.upper()) in mots for c in colonnes)


def positions_contre_pdf(rapport, converti: List[dict], pdf: Path, colonnes: List[str],
                         template=None) -> None:
    """Positions des pages vectorielles du PDF source mesurées contre sa propre grille.

    Remplace, pour ces pages, les positions mesurées contre une vérité Excel qui
    ne garde pas la géométrie. Les pages scannées ou à couche OCR invisible ne
    sont pas une référence de positions : elles sont écartées.
    """
    import fitz
    from pdf_extractor import VECTORIEL, classer_page

    with fitz.open(str(pdf)) as doc:
        vectorielles = {i for i, page in enumerate(doc) if classer_page(page) == VECTORIEL}
    reference = [
        page if i in vectorielles else {'success': True, 'rows': [], 'metadata': {},
                                        'pied_texte': []}
        for i, page in enumerate(lire_pdf_vectoriel(pdf, colonnes, template=template))
    ]
    remplacer_positions(rapport, mesurer(reference, converti, colonnes))


def lire_pdf_vectoriel(chemin: Path, colonnes: List[str], template=None) -> List[dict]:
    """Lit un PDF vectoriel : une page pivot par page PDF, lignes gardant leur
    espacement d'origine (`exact=True`) pour la comparaison de position.

    Pages à cadre : découpage indépendant aux « | ». Pages sans cadre (TP2) :
    découpage de pdf_extractor.extract_page_grille — le découpage en colonnes
    de ces pages n'est donc PAS vérifié indépendamment (même découpeur que la
    conversion) ; les caractères et la chaîne d'écriture le sont.
    """
    import dataclasses

    import fitz
    from pdf_extractor import PdfTableExtractor, grille_page
    from template import DEFAULT_TEMPLATE

    tpl = template or dataclasses.replace(DEFAULT_TEMPLATE, columns=list(colonnes))
    lecteur = PdfTableExtractor(tpl)
    doc = fitz.open(str(chemin))
    n = len(colonnes)
    pages = []
    for num, pdf_page in enumerate(doc):
        texte_lignes = grille_page(pdf_page)
        a_cadre = any(lg.count('|') >= n + 1 for lg in texte_lignes)
        lignes, pied = [], []
        for ligne in texte_lignes:
            if _est_pied([ligne]):
                pied.append(ligne)
                continue
            if not a_cadre or _est_entete_grille(ligne, colonnes):
                continue
            segs = ligne.split('|')[1:-1]
            if len(segs) != n:
                continue
            cellules = [s[1:].rstrip() if s.startswith(' ') else s.rstrip() for s in segs]
            if not any(re.search(r'[A-Za-z0-9]', c) for c in cellules):
                continue   # ligne vide du cadre ou soulignement « °°°° »
            lignes.append({
                'type': 'data', 'cells': cellules, 'confidence': [100] * n, 'exact': True,
            })
        if not a_cadre:
            lignes = [
                dict(row, exact=True)
                for row in lecteur.extract_page_grille(pdf_page, num)['rows']
            ]
        pages.append({'success': True, 'rows': lignes, 'metadata': {}, 'pied_texte': pied})
    return pages


# ── Historique CSV ─────────────────────────────────────────────────────

def _version_git() -> str:
    try:
        resultat = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, cwd=str(Path(__file__).parent), timeout=5,
        )
        return resultat.stdout.strip() or '?'
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return '?'


ENTETE_MESURES_CSV = [
    'date', 'document', 'version_git', 'precision',
    'cellules_comparees', 'cellules_identiques',
    'espacement', 'confusion', 'contenu_different', 'manquant', 'ajoute',
    'pages_ref_orphelines', 'pages_conv_orphelines',
    'ecarts_pieds', 'ecarts_positions', 'glissement', 'lignes_deplacees',
]


def ecrire_mesure_csv(chemin_csv: Path, document: Path, rapport) -> None:
    """Ajoute une ligne de mesure à l'historique CSV (créé si absent).

    Un historique à l'ancien en-tête est complété (colonnes nouvelles vides).
    """
    chemin_csv = Path(chemin_csv)
    nouveau = not chemin_csv.exists()
    if not nouveau:
        with open(chemin_csv, newline='', encoding='utf-8') as f:
            anciennes = list(csv.reader(f))
        if anciennes and anciennes[0] != ENTETE_MESURES_CSV:
            n = len(ENTETE_MESURES_CSV)
            with open(chemin_csv, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(ENTETE_MESURES_CSV)
                w.writerows((a + [''] * n)[:n] for a in anciennes[1:])
    compte = rapport.cellules_par_classe()
    with open(chemin_csv, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if nouveau:
            w.writerow(ENTETE_MESURES_CSV)
        w.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            document.name,
            _version_git(),
            f"{rapport.precision:.4f}",
            rapport.nb_cellules_comparees,
            rapport.nb_cellules_identiques,
            compte.get(ESPACEMENT, 0),
            compte.get(CONFUSION, 0),
            compte.get(CONTENU_DIFFERENT, 0),
            compte.get(MANQUANT, 0),
            compte.get(AJOUTE, 0),
            len(rapport.pages_ref_orphelines),
            len(rapport.pages_conv_orphelines),
            len(rapport.ecarts_pieds),
            len(rapport.ecarts_positions),
            compte.get(GLISSEMENT, 0),
            len(rapport.lignes_deplacees),
        ])


# ── Ligne de commande ──────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog='mesurer_precision.py',
        description="Mesure la précision d'une sortie TriosSeconverter contre une référence.",
    )
    parser.add_argument('sortie', help='Classeur .xlsx produit par TriosSeconverter')
    parser.add_argument(
        'reference', help='Excel de vérité terrain (.xlsx) ou PDF vectoriel (.pdf)',
    )
    parser.add_argument(
        '--modele', default=None, help='Nom du template (requis si référence = PDF)',
    )
    parser.add_argument('--max-ecarts', type=int, default=30, help='Écarts affichés au maximum')
    parser.add_argument(
        '--csv', default=None, help='Chemin du fichier de mesures (défaut : config)',
    )
    parser.add_argument(
        '--journal', default=None,
        help="conversion.log : alertes et contrôle INDICE comparés à la vérité",
    )
    parser.add_argument(
        '--pdf', default=None,
        help="PDF source : positions de ses pages vectorielles mesurées contre sa grille",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    chemin_sortie = Path(args.sortie)
    chemin_reference = Path(args.reference)
    if not chemin_sortie.exists():
        raise FileNotFoundError(f"Sortie introuvable : {chemin_sortie}")
    if not chemin_reference.exists():
        raise FileNotFoundError(f"Référence introuvable : {chemin_reference}")

    if chemin_reference.suffix.lower() == '.xlsx':
        reference, colonnes = lire_verite_excel(chemin_reference)
    elif chemin_reference.suffix.lower() == '.pdf':
        if not args.modele:
            raise ValueError("--modele est requis quand la référence est un PDF vectoriel")
        modele = TemplateManager().get(args.modele)
        colonnes = list(modele.columns)
        reference = lire_pdf_vectoriel(chemin_reference, colonnes, template=modele)
    else:
        raise ValueError(f"Référence non supportée : {chemin_reference.suffix}")

    converti = lire_xlsx(chemin_sortie)
    rapport = mesurer(reference, converti, colonnes)
    if args.pdf:
        modele = TemplateManager().get(args.modele) if args.modele else None
        positions_contre_pdf(rapport, converti, Path(args.pdf), colonnes, template=modele)
    if args.journal and chemin_reference.suffix.lower() == '.xlsx':
        appliquer_attentes(rapport, lire_attentes(chemin_reference),
                           lire_journal_conversion(Path(args.journal)))

    print(formater_rapport(rapport, max_ecarts=args.max_ecarts))

    chemin_csv = Path(args.csv) if args.csv else Path(Config.MESURE_CSV_PATH)
    ecrire_mesure_csv(chemin_csv, chemin_sortie, rapport)

    a_des_ecarts = bool(
        rapport.ecarts_cellules or rapport.pages_ref_orphelines or rapport.ecarts_pieds,
    )
    return 1 if a_des_ecarts else 0


if __name__ == '__main__':
    raise SystemExit(main())
