"""
Synthese de mesures/campagne.csv : par modele, effort et document, agrege la qualite
(cellules fausses / comparees, pieds faux, lignes manquantes, pages en erreur) et le cout
moyen par page. Lecture seule, aucun appel API.

Lancement :
    env\\Scripts\\python.exe mesures\\resumer_campagne.py
    env\\Scripts\\python.exe mesures\\resumer_campagne.py autre_fichier.csv
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

CSV_DEFAUT = Path(__file__).parent / 'campagne.csv'


def _entier(v):
    try:
        return int(v or 0)
    except ValueError:
        return 0


def _flottant(v):
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def charger(chemin: Path):
    """Agrege les passages par (modele, effort, document). Rend une liste de dicts tries."""
    cumul = defaultdict(lambda: defaultdict(float))
    with open(chemin, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            cle = (r['modele'], r['effort'], r['document'])
            a = cumul[cle]
            a['passages'] += 1
            a['pages'] += _entier(r['pages_envoyees'])
            a['pages_erreur'] += _entier(r['pages_en_erreur'])
            a['comparees'] += _entier(r['cellules_comparees'])
            a['fausses'] += _entier(r['cellules_fausses'])
            a['pieds_faux'] += _entier(r['pieds_faux'])
            a['lignes_manq'] += _entier(r['lignes_manquantes'])
            a['cout'] += _flottant(r['cout_usd'])
    lignes = []
    for (modele, effort, document), a in cumul.items():
        pages = a['pages'] or 1
        comparees = a['comparees'] or 1
        lignes.append({
            'modele': modele, 'effort': effort, 'document': document[:22],
            'passages': int(a['passages']),
            'fausses': int(a['fausses']), 'comparees': int(a['comparees']),
            'taux_faux': 100 * a['fausses'] / comparees,
            'pieds_faux': int(a['pieds_faux']), 'lignes_manq': int(a['lignes_manq']),
            'pages_erreur': int(a['pages_erreur']),
            'cout_page': a['cout'] / pages,
        })
    return sorted(lignes, key=lambda d: (d['document'], d['modele'], d['effort']))


def afficher(lignes):
    entete = (f"{'modele':24}{'effort':7}{'document':23}{'pass':>5}"
              f"{'faux/comp':>12}{'%':>6}{'pieds':>6}{'l.manq':>7}{'p.err':>6}{'$/page':>9}")
    print(entete)
    print('-' * len(entete))
    for d in lignes:
        fc = f"{d['fausses']}/{d['comparees']}"
        ref = '  (ref.)' if d['modele'] == 'claude-opus-5-5' and d['effort'] == 'medium' else ''
        print(f"{d['modele']:24}{d['effort']:7}{d['document']:23}{d['passages']:>5}"
              f"{fc:>12}{d['taux_faux']:>6.1f}{d['pieds_faux']:>6}{d['lignes_manq']:>7}"
              f"{d['pages_erreur']:>6}{d['cout_page']:>9.4f}{ref}")


def main(argv):
    chemin = Path(argv[0]) if argv else CSV_DEFAUT
    if not chemin.exists():
        print(f"Introuvable : {chemin}")
        return 2
    afficher(charger(chemin))
    print("\nLes passages claude-opus-5-5 effort medium servent de reference.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
