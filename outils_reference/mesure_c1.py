"""
Mesure C1 (étape 9, contrôle qualité branché) : rejeu des 3 extraits par le convertisseur.

Outil de mesure hors de l'appli, aucun appel API : réponses Claude enregistrées rejouées
(faux client de mesure_c0), contrôles tels que branchés (cohérence + lexique, colonne
obligatoire vide, format ; conservation des pages propres), document mesuré exclu du lexique.
Le bilan porte sur l'Excel livré : cellules après la correction B3 (coquille O/0).
Donne : la couverture du lexique, les cellules encore fausses contre la vérité et l'alerte
que porte chacune, les cellules corrigées par B3, les lignes de la vérité absentes de la
lecture, les alertes de format (cellule, lu, valeur dans l'Excel, vérité), les
50 erreurs injectées (graine de C0) trouvées ou non et par quelle règle, les fausses alertes
par page.

Lancement :
    env\\Scripts\\python.exe outils_reference\\mesure_c1.py [--rapport mesures\\c1.md]
"""
import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesure_c0 as c0  # noqa: E402
from config import Config  # noqa: E402
from controle_conservation import analyser_page, texte_ligne  # noqa: E402
from converter import Converter  # noqa: E402
import controle_qualite as cq  # noqa: E402
from generer_classeur import alertes_par_cellule, corriger_coquilles_o  # noqa: E402
from lexique_reference import charger_lexique  # noqa: E402
from mesure_precision import _lignes_donnees, aligner_lignes  # noqa: E402
from mesure_precision import apparier_pages_par_contenu  # noqa: E402
from mesurer_precision import lire_verite_excel  # noqa: E402


def _norm(texte):
    return ' '.join((texte or '').split())


def convertir(doc, stem, gabarit):
    """Pages du rejeu (contrôles compris) et lectures Tesseract par page du PDF."""
    lexique = charger_lexique(Config.QUALITE_LEXIQUE_REFERENCE, exclure=doc)
    convertisseurs = []
    init = Converter.__init__

    def garder(self, *a, **kw):
        init(self, *a, **kw)
        convertisseurs.append(self)

    with patch.object(Converter, '_charger_lexique', lambda self: set(lexique)), \
            patch.object(Converter, '__init__', garder):
        pages = c0.convertir(stem, gabarit, 'claude')
    return pages, convertisseurs[-1], lexique


def page_pdf(page):
    """Numéro de la page du PDF d'une page scannée (image page_012.png), sinon None."""
    nom = Path(page.get('image_path') or '').stem
    return int(nom[5:]) if nom.startswith('page_') and nom[5:].isdigit() else None


def comparer(pages, verite):
    """Cellules fausses {(p, r, k): (lu, vrai)}, lignes de la vérité absentes {p: [texte]},
    colonnes non vides de la vérité {(p, k)}, numéros imprimés."""
    fausses, absentes, pleines = {}, defaultdict(list), set()
    numeros = {p: page.get('metadata', {}).get('PAGE') or f'rang {p + 1}'
               for p, page in enumerate(pages)}
    paires, _, _ = apparier_pages_par_contenu(verite, pages)
    for iv, ip in paires:
        ref = _lignes_donnees(verite[iv])
        lignes = [(r, row) for r, row in enumerate(pages[ip]['rows'])
                  if row.get('type') == 'data' and any((c or '').strip() for c in row['cells'])]
        for k in range(len(pages[ip].get('headers') or [])):
            if any((row['cells'][k] if k < len(row['cells']) else '').strip() for row in ref):
                pleines.add((ip, k))
        for i, j in aligner_lignes(ref, [row for _, row in lignes]):
            if i is None:
                continue
            if j is None:
                absentes[ip].append(' | '.join(_norm(c) for c in ref[i]['cells']))
                continue
            r, row = lignes[j]
            for k, vrai in enumerate(ref[i]['cells']):
                lu = row['cells'][k] if k < len(row['cells']) else ''
                if _norm(lu) != _norm(vrai):
                    fausses[(ip, r, k)] = (_norm(lu), _norm(vrai))
    return fausses, absentes, pleines, numeros


def recontroler(pages, conv, lexique):
    """Contrôles branchés relancés sur des pages modifiées (copies à erreurs injectées)."""
    colonnes = list(conv.template.columns)
    for page in pages:
        page['a_verifier'] = []
        numero = page_pdf(page)
        lecture = conv._lectures_tesseract.get(numero)
        if lecture is None or not Config.CONTROLE_CONSERVATION:
            continue
        analyse = analyser_page(page['rows'], colonnes, lecture)
        if analyse['taux'] is not None and not analyse['degradee']:
            conv._alertes_conservation(numero, page, colonnes, analyse, texte_ligne)
    conv._lexique = set(lexique)
    conv._controler_qualite(pages)


def raisons(cible, page):
    return sorted({t.strip() for a in alertes_par_cellule(page)
                   if a['ligne'] == cible['ligne']
                   and (cible['colonne'] is None or a['colonne'] == cible['colonne'])
                   for t in a['type'].split(',')})


def juste(a, p, fausses, absentes, pleines):
    if a['type'] == 'ligne peut-être manquante':
        return bool(absentes.get(p))
    if a['ligne'] is None:
        return (p, a['colonne']) in pleines
    return (p, a['ligne'], a['colonne']) in fausses


def mesurer_c1():
    docs, sortie = {}, ['# Mesure C1 — contrôle qualité branché (rejeu, sans API)', '']
    for nom, doc, stem, gabarit in c0.DOCUMENTS:
        verite, _ = lire_verite_excel(c0.FIX / f'{doc}_extrait_verite.xlsx')
        pivot, conv, lexique = convertir(doc, stem, gabarit)
        # Excel livré : la décision B3 corrige O1A en 01A (cellule orange), après les contrôles.
        pages, _ = corriger_coquilles_o(pivot, Config.CORRECTION_O_COLONNES)
        formes_verite = {f for p in verite for r in p['rows'] if r['type'] == 'data'
                         for c in r['cells'] for f in cq.formes(c)}
        docs[nom] = {'pages': pages, 'pivot': pivot, 'conv': conv, 'lexique': lexique,
                     'cmp': comparer(pages, verite), 'doc': doc,
                     'couverture': (len(formes_verite & lexique), len(formes_verite))}

    sortie += ['## Lexique de référence', '', "Fichiers : " + ', '.join(
        f.name for f in sorted(Config.QUALITE_LEXIQUE_REFERENCE.glob('*.xlsx'))) + '.', '']
    for nom, d in docs.items():
        a, b = d['couverture']
        sortie.append(f"- {nom} (sans {d['doc']}) : {len(d['lexique'])} formes ; couverture de "
                      f"la vérité {a}/{b} = {a / b:.0%}")
    sortie.append('')

    sortie += ['## Cellules encore fausses et leur alerte', '']
    for nom, d in docs.items():
        fausses, absentes, _, numeros = d['cmp']
        sans = 0
        sortie += [f'### {nom} : {len(fausses)} cellule(s) fausse(s)', '',
                   '| Page | Sorte | Ligne | Colonne | Lu | Vérité | Alerte |', '|' + '---|' * 7]
        for (p, r, k), (lu, vrai) in sorted(fausses.items()):
            page = d['pages'][p]
            types = raisons({'ligne': r, 'colonne': k}, page)
            sans += not types
            sortie.append(f"| {numeros[p]} | {c0.sorte(page)} | {r + 1} | "
                          f"{page['headers'][k]} | {lu or '(vide)'} | {vrai or '(vide)'} | "
                          f"{', '.join(types) or '**aucune**'} |")
        corrigees = [(p, r, k, o) for p, page in enumerate(d['pages'])
                     for r, row in enumerate(page['rows'])
                     for k, o in (row.get('corrections_o') or {}).items()]
        for p, r, k, o in corrigees:
            etat = 'fausse' if (p, r, k) in fausses else 'juste'
            sortie.append(f"| {numeros[p]} | {c0.sorte(d['pages'][p])} | {r + 1} | "
                          f"{d['pages'][p]['headers'][k]} | corrigée B3 (lu {o}) : "
                          f"{_norm(d['pages'][p]['rows'][r]['cells'][k])}, orange | — | "
                          f"{etat} dans l'Excel |")
        sortie += ['', f'Sans alerte : {sans} sur {len(fausses)}.', '']
        for p, textes in sorted(absentes.items()):
            for t in textes:
                sortie.append(f"- ligne de la vérité absente, p. {numeros[p]} "
                              f"({c0.sorte(d['pages'][p])}) : {t}")
        sortie.append('')

    sortie += ['## Alertes de format', '', '| Document | Page | Ligne | Colonne | Lu (lecture) '
               "| Dans l'Excel | Vérité |", '|' + '---|' * 7]
    for nom, d in docs.items():
        numeros = d['cmp'][3]
        for p, page in enumerate(d['pages']):
            for a in alertes_par_cellule(page):
                if 'format' in a['type'] and a['ligne'] is not None:
                    lu = _norm(d['pivot'][p]['rows'][a['ligne']]['cells'][a['colonne']])
                    livre = _norm(page['rows'][a['ligne']]['cells'][a['colonne']])
                    vrai = d['cmp'][0].get((p, a['ligne'], a['colonne']), (None, livre))[1]
                    sortie.append(f"| {nom} | {numeros[p]} | {a['ligne'] + 1} | "
                                  f"{page['headers'][a['colonne']]} | {lu} | {livre} | {vrai} |")

    sortie += ['', '## Fausses alertes par page (toutes règles branchées)', '',
               '| Document | Page | Sorte | Alertes | Fausses | Texte des fausses |',
               '|' + '---|' * 6]
    total_fausses, total_pages = 0, 0
    for nom, d in docs.items():
        fausses, absentes, pleines, numeros = d['cmp']
        for p, page in enumerate(d['pages']):
            total_pages += 1
            alertes = alertes_par_cellule(page)
            # Alerte sur une cellule corrigée par B3 : elle explique une correction faite
            # (la lecture était fausse), ni vraie ni fausse dans l'Excel livré.
            mauvaises = [a for a in alertes if not juste(a, p, fausses, absentes, pleines)
                         and not a.get('corrige')]
            total_fausses += len(mauvaises)
            textes = '<br>'.join(
                f"ligne {'—' if a['ligne'] is None else a['ligne'] + 1}, "
                f"{page['headers'][a['colonne']]} ({a['type']}) : {a['message']}"
                for a in mauvaises)
            sortie.append(f"| {nom} | {numeros[p]} | {c0.sorte(page)} | {len(alertes)} | "
                          f"{len(mauvaises)} | {textes} |")
        for s in (d['pages'][0].get('syntheses_qualite') or []):
            total_fausses += 1
            sortie.append(f"| {nom} | — | document | 1 | 1 | {s['message']} |")
    sortie += ['', f'Total : {total_fausses} fausse(s) alerte(s) sur {total_pages} pages, '
               f'{total_fausses / total_pages:.2f} par page.', '']

    copies, cibles = c0.injecter({nom: d['pivot'] for nom, d in docs.items()},
                                 random.Random(c0.GRAINE))
    for nom, d in docs.items():
        recontroler(copies[nom], d['conv'], d['lexique'])
    sortie += ['## Erreurs injectées (graine de C0)', '', '| Erreur | Document | Page | Sorte '
               '| Trouvée par | Alerte déjà là avant |', '|' + '---|' * 6]
    bilan = defaultdict(Counter)
    for cible in cibles:
        d = docs[cible['doc']]
        page = copies[cible['doc']][cible['page']]
        par = raisons(cible, page)
        avant = [] if cible['type'] in ('ligne perdue', 'lignes fusionnées') else raisons(
            cible, d['pivot'][cible['page']])
        trouve = bool(par) and not (avant and set(par) == set(avant))
        bilan[(cible['type'], cible['sorte'])]['n'] += 1
        bilan[(cible['type'], cible['sorte'])]['vues'] += trouve
        sortie.append(f"| {cible['type']} | {cible['doc']} | "
                      f"{d['cmp'][3].get(cible['page'], cible['page'])} | {cible['sorte']} | "
                      f"{', '.join(par) or 'aucune'} | {', '.join(avant) or '—'} |")
    sortie += ['', '| Erreur | Pages vectorielles | Pages scannées |', '|---|---|---|']
    for type_ in c0.SORTES_ERREURS:
        cases = [bilan[(type_, s)] for s in ('vectorielle', 'scannée')]
        sortie.append(f"| {type_} | " + ' | '.join(
            f"{b['vues']}/{b['n']}" if b['n'] else '—' for b in cases) + ' |')
    vues = sum(b['vues'] for b in bilan.values())
    sortie += ['', f'Trouvées : {vues} sur {len(cibles)}.']
    return '\n'.join(sortie)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mesure C1 du contrôle qualité branché')
    parser.add_argument('--rapport', type=Path, default=None)
    args = parser.parse_args(argv)
    texte = mesurer_c1()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(texte)
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(texte, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
