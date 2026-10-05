"""Campagne de mesure des modèles Claude sur un document de référence.

APPELLE L'API ANTHROPIC (coût réel) : hors de la suite pytest.

Usage :
    python campagne_mesure.py --modele claude-opus-5-5 --effort medium --passages 2
    python campagne_mesure.py --modele claude-haiku-4-5-20251001 --effort aucun --passages 2
    python campagne_mesure.py --modele claude-opus-5-5 --effort medium --passages 1 \\
        --pdf tests/fixtures/223400PE137.pdf --verite tests/fixtures/223400PE137.pdf \\
        --gabarit REPARTITEUR

Chaque passage convertit le PDF en mode claude avec le modèle et l'effort
demandés (surcharge en mémoire : config.py n'est jamais modifié sur le disque),
range la sortie dans mesures/<document>_<modele>_<effort>_<n>/, la mesure contre la vérité
et ajoute une ligne à mesures/campagne.csv. La campagne s'arrête avant un passage
si le coût cumulé atteint Config.CAMPAGNE_BUDGET_MAX_USD.

Clé API : variable d'environnement ANTHROPIC_API_KEY, sinon Config.CLAUDE_API_KEY.
Elle n'est écrite dans aucun fichier.
"""

import argparse
import contextlib
import copy
import csv
import io
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from config import Config

EFFORT_AUCUN = 'aucun'
DOSSIER_MESURES = Path(__file__).parent / 'mesures'
NOM_CSV = 'campagne.csv'

COLONNES_CSV = [
    'date', 'commit', 'modele', 'effort', 'passage', 'document',
    'pages_envoyees', 'pages_en_erreur', 'erreurs',
    'cellules_comparees', 'cellules_fausses',
    'espacement', 'confusion', 'contenu_different', 'manquant', 'ajoute',
    'positions_fausses', 'pieds_faux', 'lignes_manquantes', 'lignes_en_trop',
    'pages_ref_orphelines', 'tokens_entree', 'tokens_sortie', 'cout_usd', 'duree_s',
    'glissement', 'lignes_deplacees', 'alertes_manquantes', 'fausses_alertes', 'controle_indice',
    'lignes_tableau_brutes', 'lignes_hors_colonnes',
]
# Lignes de la réponse qui ne sont pas des lignes du tableau, même avec un « | ».
_PREFIXES_HORS_TABLEAU = ('TYPE_PAGE:', 'META:', 'PIED_BRUT:', 'LOGO:', 'REVISIONS:', 'SECTION:')
_EXEMPLES_HORS_COLONNES = 5


def cle_api() -> str:
    """Clé API : ANTHROPIC_API_KEY, sinon Config.CLAUDE_API_KEY ; vide si aucune."""
    return (os.environ.get('ANTHROPIC_API_KEY') or getattr(Config, 'CLAUDE_API_KEY', '')).strip()


@contextlib.contextmanager
def reglage_en_memoire(modele: str, effort: str, cle: str):
    """Mode claude, modèle, effort et clé le temps d'un passage, puis restaure Config.

    Effort « aucun » : le champ effort n'est pas envoyé (capacité coupée en mémoire).
    """
    noms = ('OCR_MODE', 'CLAUDE_OCR_MODEL', 'CLAUDE_EFFORT', 'CLAUDE_API_KEY',
            'CLAUDE_CAPACITES_MODELES')
    sauvegarde = {n: getattr(Config, n) for n in noms}
    try:
        Config.OCR_MODE = 'claude'
        Config.CLAUDE_OCR_MODEL = modele
        Config.CLAUDE_API_KEY = cle
        if effort == EFFORT_AUCUN:
            capacites = copy.deepcopy(Config.CLAUDE_CAPACITES_MODELES)
            if modele in capacites:
                capacites[modele]['effort'] = False
            Config.CLAUDE_CAPACITES_MODELES = capacites
        else:
            Config.CLAUDE_EFFORT = effort
        yield
    finally:
        for nom, valeur in sauvegarde.items():
            setattr(Config, nom, valeur)


def cout_usd(modele: str, tokens_entree: int, tokens_sortie: int) -> float:
    """Coût estimé ; KeyError si le modèle n'a pas de prix dans config.py."""
    prix_entree, prix_sortie = Config.CLAUDE_PRIX_MODELES[modele]
    return (tokens_entree * prix_entree + tokens_sortie * prix_sortie) / 1_000_000


def lire_journal(chemin: Path) -> Dict:
    """Pages envoyées, tokens et erreurs d'un journal *_claude.jsonl.

    Les tokens de cache (lus / écrits) sont comptés en entrée au plein tarif :
    l'estimation est un majorant (aucun cache n'est demandé par claude_ocr).
    """
    bilan = {'pages_envoyees': 0, 'tokens_entree': 0, 'tokens_sortie': 0, 'erreurs': [],
             'ids': []}
    if not chemin.exists():
        return bilan
    for ligne in chemin.read_text(encoding='utf-8').splitlines():
        if not ligne.strip():
            continue
        entree = json.loads(ligne)
        if 'image' not in entree:
            continue
        bilan['pages_envoyees'] += 1
        if entree.get('id'):
            bilan['ids'].append(entree['id'])
        usage = entree.get('usage') or {}
        bilan['tokens_entree'] += (
            usage.get('input_tokens', 0) + usage.get('cache_read_input_tokens', 0)
            + usage.get('cache_creation_input_tokens', 0)
        )
        bilan['tokens_sortie'] += usage.get('output_tokens', 0)
        # « non-listing » (page de garde) n'est pas une erreur de conversion.
        if not entree.get('success') and entree.get('error') not in (None, 'non-listing'):
            bilan['erreurs'].append(f"{entree['image']}: {entree['error']}")
    return bilan


def lignes_hors_colonnes(chemin: Path, n_colonnes: int) -> Dict:
    """Lignes de tableau des réponses brutes au nombre de segments différent du modèle.

    Mesure ce que le parseur doit répartir ou compléter (règle des segments en trop) :
    exemples = (image, nombre de segments, ligne brute), les premiers rencontrés.
    """
    bilan = {'lignes_tableau_brutes': 0, 'lignes_hors_colonnes': 0, 'exemples': []}
    if not chemin.exists():
        return bilan
    for texte in chemin.read_text(encoding='utf-8').splitlines():
        if not texte.strip():
            continue
        entree = json.loads(texte)
        for ligne in (entree.get('raw') or '').splitlines():
            ligne = ligne.strip()
            if '|' not in ligne or ligne.upper().startswith(_PREFIXES_HORS_TABLEAU):
                continue
            bilan['lignes_tableau_brutes'] += 1
            segments = len(ligne.split('|'))
            if segments != n_colonnes:
                bilan['lignes_hors_colonnes'] += 1
                if len(bilan['exemples']) < _EXEMPLES_HORS_COLONNES:
                    bilan['exemples'].append((entree.get('image', ''), segments, ligne))
    return bilan


def mesurer_sortie(xlsx: Path, verite: Path, gabarit: str, pdf: Optional[Path] = None,
                   journal: Optional[Path] = None) -> Dict:
    """Mesure une sortie contre une vérité (.xlsx de vérité terrain ou PDF vectoriel).

    pdf : document source ; les positions de ses pages vectorielles sont mesurées
    contre sa propre grille, pas contre la vérité Excel (qui ne garde pas la géométrie).
    """
    from mesure_precision import (
        AJOUTE, CONFUSION, CONTENU_DIFFERENT, ESPACEMENT, GLISSEMENT, MANQUANT, mesurer,
    )
    from mesurer_precision import (
        appliquer_attentes, lire_attentes, lire_journal_conversion, lire_pdf_vectoriel,
        lire_verite_excel, lire_xlsx, positions_contre_pdf,
    )
    from template import TemplateManager

    if verite.suffix.lower() == '.pdf':
        modele_tableau = TemplateManager().get(gabarit)
        colonnes = list(modele_tableau.columns)
        reference = lire_pdf_vectoriel(verite, colonnes, template=modele_tableau)
    else:
        reference, colonnes = lire_verite_excel(verite)
    converti = lire_xlsx(xlsx)
    rapport = mesurer(reference, converti, colonnes)
    if pdf is not None and verite.suffix.lower() != '.pdf':
        positions_contre_pdf(rapport, converti, pdf, colonnes,
                             template=TemplateManager().get(gabarit))
    if journal is not None and verite.suffix.lower() != '.pdf':
        appliquer_attentes(rapport, lire_attentes(verite), lire_journal_conversion(journal))
    compte = rapport.cellules_par_classe()
    orphelines = [o.cote for o in rapport.lignes_orphelines]
    return {
        'cellules_comparees': rapport.nb_cellules_comparees,
        'cellules_fausses': sum(compte.values()),
        'espacement': compte.get(ESPACEMENT, 0),
        'confusion': compte.get(CONFUSION, 0),
        'contenu_different': compte.get(CONTENU_DIFFERENT, 0),
        'manquant': compte.get(MANQUANT, 0),
        'ajoute': compte.get(AJOUTE, 0),
        'glissement': compte.get(GLISSEMENT, 0),
        'lignes_deplacees': len(rapport.lignes_deplacees),
        'positions_fausses': len(rapport.ecarts_positions),
        'pieds_faux': len(rapport.ecarts_pieds),
        'lignes_manquantes': orphelines.count('MANQUANTE'),
        'lignes_en_trop': orphelines.count('EN_TROP'),
        'pages_ref_orphelines': len(rapport.pages_ref_orphelines),
        'alertes_manquantes': ('' if rapport.alertes_manquantes is None
                               else len(rapport.alertes_manquantes)),
        'fausses_alertes': '' if rapport.fausses_alertes is None else len(rapport.fausses_alertes),
        'controle_indice': ('' if rapport.controle_indice is None
                            else 'conforme' if rapport.controle_indice[0] else 'NON CONFORME'),
    }


def _dossier_passage(racine: Path, document: str, modele: str, effort: str) -> Path:
    """Premier dossier <document>_<modele>_<effort>_<n> libre : jamais d'écrasement.

    Le document fait partie du nom : sans lui, la conversion de 223400PE137 avait
    pris le numéro suivant des passages de l'extrait (…_medium_3).
    """
    n = 1
    while (racine / f"{document}_{modele}_{effort}_{n}").exists():
        n += 1
    return racine / f"{document}_{modele}_{effort}_{n}"


def executer_passage(pdf: Path, verite: Path, gabarit: str, modele: str, effort: str,
                     racine: Path, cle: str) -> Dict:
    """Convertit, mesure et retourne la ligne CSV d'un passage."""
    from converter import Converter
    from mesurer_precision import _version_git
    from template import TemplateManager

    dossier = _dossier_passage(racine, pdf.stem, modele, effort)
    dossier.mkdir(parents=True)
    journal_conversion = dossier / 'conversion.log'
    debut = time.monotonic()
    with reglage_en_memoire(modele, effort, cle), \
            open(journal_conversion, 'w', encoding='utf-8') as log, \
            contextlib.redirect_stdout(io.StringIO()):
        resultat = Converter(
            word_file=pdf, output_dir=dossier, template=TemplateManager().get(gabarit),
            on_log=lambda message: log.write(message + '\n'),
        ).run()
    duree = time.monotonic() - debut

    journal = lire_journal(dossier / f"{pdf.stem}_claude.jsonl")
    colonnes = lignes_hors_colonnes(dossier / f"{pdf.stem}_claude.jsonl",
                                    len(TemplateManager().get(gabarit).columns))
    mesures = mesurer_sortie(Path(resultat['excel']), verite, gabarit, pdf=pdf,
                             journal=journal_conversion)
    return {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'commit': _version_git(),
        'modele': modele,
        'effort': effort,
        'passage': dossier.name.rsplit('_', 1)[-1],
        'document': pdf.name,
        'pages_envoyees': journal['pages_envoyees'],
        'pages_en_erreur': len(journal['erreurs']),
        'erreurs': ' ; '.join(journal['erreurs']),
        **mesures,
        'tokens_entree': journal['tokens_entree'],
        'tokens_sortie': journal['tokens_sortie'],
        'cout_usd': round(cout_usd(modele, journal['tokens_entree'], journal['tokens_sortie']), 4),
        'duree_s': round(duree, 1),
        'lignes_tableau_brutes': colonnes['lignes_tableau_brutes'],
        'lignes_hors_colonnes': colonnes['lignes_hors_colonnes'],
        '_ids': journal['ids'],
        '_exemples_hors_colonnes': colonnes['exemples'],
    }


def ajouter_ligne_csv(chemin: Path, ligne: Dict) -> None:
    """Ajoute une ligne à l'historique de campagne (en-tête écrit si fichier neuf).

    Un historique à l'ancien en-tête est d'abord réécrit avec les colonnes actuelles
    (colonnes nouvelles vides) : sinon les valeurs glisseraient d'une colonne.
    """
    nouveau = not chemin.exists()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if not nouveau:
        with open(chemin, newline='', encoding='utf-8') as f:
            lecteur = csv.DictReader(f)
            anciennes = list(lecteur)
            entete = lecteur.fieldnames
        if entete != COLONNES_CSV:
            with open(chemin, 'w', newline='', encoding='utf-8') as f:
                ecrivain = csv.DictWriter(f, fieldnames=COLONNES_CSV)
                ecrivain.writeheader()
                ecrivain.writerows({c: a.get(c, '') for c in COLONNES_CSV} for a in anciennes)
    with open(chemin, 'a', newline='', encoding='utf-8') as f:
        ecrivain = csv.DictWriter(f, fieldnames=COLONNES_CSV)
        if nouveau:
            ecrivain.writeheader()
        ecrivain.writerow({c: ligne.get(c, '') for c in COLONNES_CSV})


def ids_deja_vus(racine: Path) -> set:
    """Identifiants de réponse de tous les journaux de passage déjà présents sous racine."""
    vus = set()
    for journal in racine.glob('*/*_claude.jsonl'):
        vus.update(lire_journal(journal)['ids'])
    return vus


def controle_appels_reels(ligne: Dict, vus: set) -> List[str]:
    """Signes qu'un passage n'a pas fait que de vrais appels ; ajoute ses identifiants à vus."""
    ids = ligne.get('_ids') or []
    problemes = []
    if ligne.get('pages_envoyees') and len(ids) < ligne['pages_envoyees']:
        problemes.append(f"{ligne['pages_envoyees'] - len(ids)} réponse(s) sans identifiant")
    repetes = [i for i in ids if i in vus] + [i for k, i in enumerate(ids) if i in ids[:k]]
    if repetes:
        problemes.append(f"réponse rejouée : {len(repetes)} identifiant(s) déjà vu(s) "
                         f"({', '.join(sorted(set(repetes))[:3])})")
    vus.update(ids)
    return problemes


def lancer_campagne(modele: str, effort: str, passages: int, pdf: Path, verite: Path,
                    gabarit: str, racine: Path, cle: str,
                    budget: Optional[float] = None, afficher=print,
                    rejouer: bool = False) -> List[Dict]:
    """Enchaîne les passages ; s'arrête avant un passage si le budget est atteint.

    Chaque passage fait de vrais appels : une source .jsonl (rejeu d'un journal,
    sans appel) est refusée sans rejouer=True, et un identifiant de réponse déjà
    vu dans un passage précédent est inscrit dans la colonne erreurs.
    """
    budget = Config.CAMPAGNE_BUDGET_MAX_USD if budget is None else budget
    if modele not in Config.CLAUDE_PRIX_MODELES:
        raise ValueError(f"Pas de prix pour {modele!r} dans CLAUDE_PRIX_MODELES (config.py).")
    if Path(pdf).suffix.lower() == '.jsonl' and not rejouer:
        raise ValueError(f"{Path(pdf).name} est un journal : le convertir rejouerait des réponses "
                         "enregistrées, sans appel. Utilisez --rejouer pour le vouloir.")
    vus = set() if rejouer else ids_deja_vus(racine)
    lignes: List[Dict] = []
    cumul = 0.0
    for i in range(1, passages + 1):
        if cumul >= budget:
            afficher(f"Arrêt avant le passage {i}/{passages} : coût cumulé {cumul:.2f} $ "
                     f"≥ budget {budget:.2f} $ (CAMPAGNE_BUDGET_MAX_USD).")
            break
        afficher(f"Passage {i}/{passages} — {modele}, effort {effort}…")
        ligne = executer_passage(pdf, verite, gabarit, modele, effort, racine, cle)
        if not rejouer:
            problemes = controle_appels_reels(ligne, vus)
            if problemes:
                ligne['erreurs'] = ' ; '.join(filter(None, [ligne['erreurs']] + problemes))
        ajouter_ligne_csv(racine / NOM_CSV, ligne)
        cumul += ligne['cout_usd']
        lignes.append(ligne)
        afficher(
            f"  → {ligne['pages_envoyees']} page(s) envoyée(s), {ligne['cellules_fausses']} "
            f"cellule(s) fausse(s), {ligne['cout_usd']:.4f} $, {ligne['duree_s']} s"
            + (f", ERREURS : {ligne['erreurs']}" if ligne['erreurs'] else '')
        )
        afficher(f"  → lignes de tableau brutes : {ligne['lignes_tableau_brutes']}, au mauvais "
                 f"nombre de colonnes : {ligne['lignes_hors_colonnes']}")
        for image, segments, brute in ligne['_exemples_hors_colonnes']:
            afficher(f"     {image} — {segments} segments : {brute}")
    return lignes


def tableau_comparatif(chemin_csv: Path) -> str:
    """Par réglage (modèle, effort, document) : moyennes et écart entre passages."""
    if not chemin_csv.exists():
        return "Aucune mesure enregistrée."
    with open(chemin_csv, encoding='utf-8') as f:
        lignes = list(csv.DictReader(f))
    groupes: Dict[tuple, List[Dict]] = {}
    for ligne in lignes:
        groupes.setdefault((ligne['modele'], ligne['effort'], ligne['document']), []).append(ligne)
    sortie = [
        f"{'Modèle':28} {'Effort':7} {'Document':34} {'N':>2} {'Fausses moy.':>12} "
        f"{'Écart':>6} {'Pos.':>5} {'Pieds':>5} {'Coût moy. $':>11} {'Erreurs':>7}",
    ]
    for (modele, effort, document), groupe in sorted(groupes.items()):
        fausses = [int(g['cellules_fausses']) for g in groupe]
        sortie.append(
            f"{modele:28} {effort:7} {document[:34]:34} {len(groupe):>2} "
            f"{statistics.mean(fausses):>12.1f} {max(fausses) - min(fausses):>6} "
            f"{statistics.mean(int(g['positions_fausses']) for g in groupe):>5.1f} "
            f"{statistics.mean(int(g['pieds_faux']) for g in groupe):>5.1f} "
            f"{statistics.mean(float(g['cout_usd']) for g in groupe):>11.4f} "
            f"{sum(int(g['pages_en_erreur']) for g in groupe):>7}"
        )
    total = sum(float(g['cout_usd']) for g in lignes)
    sortie.append(f"Coût total enregistré : {total:.4f} $ sur {len(lignes)} passage(s).")
    return '\n'.join(sortie)


def main(argv: Optional[List[str]] = None) -> int:
    racine_projet = Path(__file__).parent
    parser = argparse.ArgumentParser(
        prog='campagne_mesure.py',
        description="Campagne de mesure des modèles Claude (appelle l'API, coût réel).",
    )
    parser.add_argument('--modele', required=True, help='Identifiant du modèle Claude')
    parser.add_argument('--effort', required=True,
                        choices=['low', 'medium', 'high', 'xhigh', 'max', EFFORT_AUCUN])
    parser.add_argument('--passages', type=int, default=1)
    parser.add_argument(
        '--pdf', type=Path,
        default=racine_projet / 'tests' / 'fixtures' / '223111PE011_extrait_10pages.pdf',
    )
    parser.add_argument(
        '--verite', type=Path,
        default=racine_projet / 'tests' / 'fixtures' / '223111PE011_extrait_verite.xlsx',
    )
    parser.add_argument('--gabarit', default='REPARTITEUR 2', help='Nom du modèle de tableau')
    parser.add_argument('--budget', type=float, default=None,
                        help='Plafond en $ (défaut : CAMPAGNE_BUDGET_MAX_USD)')
    parser.add_argument('--rejouer', action='store_true',
                        help="Autorise --pdf <journal .jsonl> : rejeu sans appel ni coût")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cle = cle_api()
    if not cle and not args.rejouer:
        print("Clé API absente : définissez ANTHROPIC_API_KEY dans ce terminal.")
        return 2
    for chemin in (args.pdf, args.verite):
        if not chemin.exists():
            print(f"Fichier introuvable : {chemin}")
            return 2

    try:
        lancer_campagne(args.modele, args.effort, args.passages, args.pdf, args.verite,
                        args.gabarit, DOSSIER_MESURES, cle, budget=args.budget,
                        rejouer=args.rejouer)
    except ValueError as exc:
        print(exc)
        return 2
    print()
    print(tableau_comparatif(DOSSIER_MESURES / NOM_CSV))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
