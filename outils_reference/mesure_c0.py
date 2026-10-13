"""
Mesure C0 (étape 9) : chaque règle de controle_qualite, prise seule, sur les 3 extraits.

Outil de mesure hors de l'appli, aucun appel API : les dernières réponses Claude
enregistrées sont rejouées par le convertisseur (faux client), pages vectorielles comprises ;
une conversion en mode Tesseract (locale) mesure le dictionnaire hors Claude.
Pour chaque règle : alertes sur les lectures actuelles, vraies (cellule lue différemment de
la vérité) ou fausses, par document et par page, pages vectorielles et scannées à part ;
50 erreurs injectées (graine fixe, moitié sur chaque sorte de page) signalées ; les 2 OC→CC
de 223111PE011 p. 119 ; couverture du lexique (document mesuré exclu) ; fausses alertes par
paire de confusion ; taux de sortie de motif et de colonne vide les plus hauts.

Lancement :
    env\\Scripts\\python.exe outils_reference\\mesure_c0.py [--rapport mesures\\c0.md]
"""
import argparse
import contextlib
import copy
import io
import json
import random
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET))

import controle_qualite as cq  # noqa: E402
from config import Config  # noqa: E402
from converter import Converter  # noqa: E402
from data_dictionary import get_dictionary  # noqa: E402
from lexique_reference import charger_lexique  # noqa: E402
from mesure_precision import _lignes_donnees, aligner_lignes  # noqa: E402
from mesure_precision import apparier_pages_par_contenu  # noqa: E402
from mesurer_precision import lire_verite_excel  # noqa: E402
from template import TemplateManager  # noqa: E402

FIX = PROJET / 'tests' / 'fixtures'
MESURES = PROJET / 'mesures'
GRAINE = 20261009
N_INJECTEES = 50
SAUTS = (1, 2, 5, 10, 20)
DOCUMENTS = [('PE011', '223111PE011', '223111PE011_extrait_10pages', 'REPARTITEUR 2'),
             ('PE133', '6A23111PE133', '6A23111PE133_extrait_8pages', 'REPARTITEUR'),
             ('PE012', '223111PE012', '223111PE012_extrait_10pages', 'Bornier standard')]


# ── Pages converties ───────────────────────────────────────────────────

def _faux_client(journal):
    reponses = [json.loads(lg)['raw'] for lg in journal.read_text('utf-8').splitlines()
                if lg.strip()]

    class Faux:
        def __init__(self, api_key=None):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kw):
            return SimpleNamespace(
                id='msg_rejeu', content=[SimpleNamespace(type='text', text=reponses.pop(0))],
                stop_reason='end_turn', model=kw['model'],
                usage=SimpleNamespace(input_tokens=0, output_tokens=0,
                                      cache_read_input_tokens=0,
                                      cache_creation_input_tokens=0))
    return Faux


def convertir(stem, gabarit, mode):
    """Pages pivot du convertisseur (avant l'Excel) : 'claude' rejoué ou 'tesseract'."""
    pdf = FIX / f'{stem}.pdf'
    dossier = Path(tempfile.mkdtemp(prefix='c0_'))
    avant = (Config.OCR_MODE, Config.CLAUDE_API_KEY)
    try:
        Config.OCR_MODE, Config.CLAUDE_API_KEY = mode, 'cle-factice'
        conv = Converter(word_file=pdf, output_dir=dossier,
                         template=TemplateManager().get(gabarit), on_log=lambda m: None)
        with contextlib.redirect_stdout(io.StringIO()):
            if mode == 'claude':
                journal = sorted(MESURES.glob(f'{stem}_claude-opus-5-5_*/{stem}_claude.jsonl'),
                                 key=lambda p: p.stat().st_mtime)[-1]
                with patch('anthropic.Anthropic', _faux_client(journal)):
                    conv.run()
            else:
                conv.run()
        return [r for r in conv._derniers_resultats
                if r.get('success') and any(row.get('type') == 'data'
                                            for row in r.get('rows') or [])]
    finally:
        Config.OCR_MODE, Config.CLAUDE_API_KEY = avant
        shutil.rmtree(dossier, ignore_errors=True)


def sorte(page):
    return 'vectorielle' if page.get('detection_method') in cq.METHODES_VECTORIELLES \
        else 'scannée'


# ── Vérité ─────────────────────────────────────────────────────────────

def comparer_a_la_verite(pages, verite):
    """Cellules lues différemment de la vérité {(p, r, k)}, colonnes non vides de la vérité
    {(p, k)}, numéro imprimé de chaque page."""
    fausses, pleines = set(), set()
    numeros = {ip: page.get('metadata', {}).get('PAGE') or f'rang {ip + 1}'
               for ip, page in enumerate(pages)}
    paires, _, _ = apparier_pages_par_contenu(verite, pages)
    for iv, ip in paires:
        ref = _lignes_donnees(verite[iv])
        lignes = [(r, row) for r, row in enumerate(pages[ip]['rows'])
                  if row.get('type') == 'data' and any((c or '').strip() for c in row['cells'])]
        for k in range(len(pages[ip].get('headers') or [])):
            if any((row['cells'][k] if k < len(row['cells']) else '').strip() for row in ref):
                pleines.add((ip, k))
        for i, j in aligner_lignes(ref, [row for _, row in lignes]):
            if i is None or j is None:
                continue
            r, row = lignes[j]
            for k, vrai in enumerate(ref[i]['cells']):
                lu = row['cells'][k] if k < len(row['cells']) else ''
                if ' '.join((lu or '').split()) != ' '.join((vrai or '').split()):
                    fausses.add((ip, r, k))
    return fausses, pleines, numeros


def juste(alerte, fausses, pleines):
    if alerte['page'] is None:
        return False                      # synthèse « motif non reconnu » : rien à corriger
    if alerte['ligne'] is None:
        return (alerte['page'], alerte['colonne']) in pleines
    return (alerte['page'], alerte['ligne'], alerte['colonne']) in fausses


# ── Erreurs injectées ──────────────────────────────────────────────────

def _bascule(a, b):
    def f(mot, _alea):
        if a in mot:
            return mot.replace(a, b, 1)
        return mot.replace(b, a, 1) if b in mot else None
    return f


def _caractere_perdu(mot, alea):
    if len(mot) < 2:
        return None
    i = alea.randrange(len(mot))
    return mot[:i] + mot[i + 1:]


SORTES_ERREURS = ['O/C', 'O/0', 'I/1', 'S/5', 'B/8', 'caractère perdu', 'espace perdu',
                  'espace ajouté', 'colonne voisine', 'ligne perdue', 'lignes fusionnées']
_MOTS = {'O/C': _bascule('O', 'C'), 'O/0': _bascule('O', '0'), 'I/1': _bascule('1', 'I'),
         'S/5': _bascule('5', 'S'), 'B/8': _bascule('8', 'B'),
         'caractère perdu': _caractere_perdu}


def injecter(documents, alea):
    """Copies des documents avec N_INJECTEES erreurs ; cibles finales par erreur.

    Moitié sur pages vectorielles, moitié sur pages scannées ; une ligne ne reçoit qu'une
    erreur. Cible : (document, page, ligne, colonne ou None = toute la ligne).
    """
    copies = {nom: copy.deepcopy(pages) for nom, pages in documents.items()}
    lignes = {'vectorielle': [], 'scannée': []}
    for nom, pages in copies.items():
        for p, page in enumerate(pages):
            for r, row in enumerate(page['rows']):
                if row.get('type') == 'data' and any((c or '').strip() for c in row['cells']):
                    lignes[sorte(page)].append((nom, p, r))
    for liste in lignes.values():
        alea.shuffle(liste)
    prises, operations = set(), []
    for n in range(N_INJECTEES):
        type_ = SORTES_ERREURS[n % len(SORTES_ERREURS)]
        liste = lignes['vectorielle' if n % 2 == 0 else 'scannée']
        for nom, p, r in liste:
            if (nom, p, r) in prises or (nom, p, r + 1) in prises or (nom, p, r - 1) in prises:
                continue
            op = _preparer(copies[nom][p], r, type_, alea)
            if op:
                prises.add((nom, p, r))
                operations.append((nom, p, r, type_, sorte(copies[nom][p]), op))
                break
    # Opérations de cellule d'abord ; lignes ensuite, de bas en haut, page par page.
    cibles = []
    for nom, p, r, type_, genre, op in operations:
        if op[0] == 'cellule':
            _, k, valeur = op
            copies[nom][p]['rows'][r]['cells'][k] = valeur
        elif op[0] == 'voisine':
            _, k, v, valeur_k, valeur_v = op
            cells = copies[nom][p]['rows'][r]['cells']
            cells[k], cells[v] = valeur_k, valeur_v
    retirees = defaultdict(list)
    for nom, p, r, type_, genre, op in sorted(operations, key=lambda o: -o[2]):
        rows = copies[nom][p]['rows']
        if op[0] == 'perdue':
            del rows[r]
            retirees[(nom, p)].append(r)
        elif op[0] == 'fusion':
            rows[r]['cells'] = [' '.join(x for x in (a, b) if (x or '').strip())
                                for a, b in zip(rows[r]['cells'], rows[r + 1]['cells'])]
            del rows[r + 1]
            retirees[(nom, p)].append(r + 1)
    for nom, p, r, type_, genre, op in operations:
        decal = sum(1 for x in retirees[(nom, p)] if x < r)
        rf = r - decal
        if op[0] == 'perdue':
            rf = min(rf, len(copies[nom][p]['rows']) - 1)
        colonne = op[1] if op[0] == 'cellule' else None
        cibles.append({'doc': nom, 'page': p, 'ligne': rf, 'colonne': colonne,
                       'type': type_, 'sorte': genre})
    return copies, cibles


def _preparer(page, r, type_, alea):
    cells = page['rows'][r]['cells']
    remplies = [k for k, c in enumerate(cells) if (c or '').strip()]
    alea.shuffle(remplies)
    if type_ in _MOTS:
        for k in remplies:
            mots = cells[k].split()
            for i in alea.sample(range(len(mots)), len(mots)):
                nouveau = _MOTS[type_](mots[i], alea)
                if nouveau is not None and nouveau != mots[i]:
                    mots[i] = nouveau
                    return ('cellule', k, ' '.join(m for m in mots if m))
        return None
    if type_ == 'espace perdu':
        for k in remplies:
            mots = cells[k].split()
            if len(mots) >= 2:
                i = alea.randrange(len(mots) - 1)
                return ('cellule', k, ' '.join(mots[:i] + [mots[i] + mots[i + 1]] + mots[i + 2:]))
        return None
    if type_ == 'espace ajouté':
        for k in remplies:
            mots = cells[k].split()
            longs = [i for i, m in enumerate(mots) if len(m) >= 4]
            if longs:
                i = alea.choice(longs)
                j = alea.randrange(1, len(mots[i]))
                mots[i] = mots[i][:j] + ' ' + mots[i][j:]
                return ('cellule', k, ' '.join(mots))
        return None
    if type_ == 'colonne voisine':
        for k in remplies:
            for v in (k + 1, k - 1):
                if 0 <= v < len(cells):
                    joint = ' '.join(x for x in ((cells[v], cells[k]) if v < k
                                                 else (cells[k], cells[v])) if x.strip())
                    return ('voisine', k, v, '', joint)
        return None
    if type_ == 'ligne perdue':
        return ('perdue',) if r + 1 < len(page['rows']) else None
    if type_ == 'lignes fusionnées':
        suivante = page['rows'][r + 1] if r + 1 < len(page['rows']) else None
        if suivante and suivante.get('type') == 'data':
            return ('fusion',)
    return None


def signalee(cible, alertes):
    return any(a['page'] == cible['page'] and a['ligne'] == cible['ligne']
               and (cible['colonne'] is None or a['colonne'] == cible['colonne'])
               for a in alertes)


# ── Règles ─────────────────────────────────────────────────────────────

def regles(gabarit, lexique, dictionnaire, mode_claude):
    def dico(pages):
        with patch.object(Config, 'QUALITE_DICTIONNAIRE_MODES',
                          {'claude': mode_claude, 'ocr': True}):
            return cq.regle_dictionnaire(pages, dictionnaire)

    sortie = {
        'coherence (document seul)': lambda pages: cq.regle_coherence(pages),
        'coherence + lexique': lambda pages: cq.regle_coherence(pages, lexique),
        'dictionnaire': dico,
        'colonne_vide': lambda pages: cq.regle_colonne_vide(
            pages, Config.QUALITE_COLONNES_OBLIGATOIRES.get(gabarit, ())),
        'format': lambda pages: cq.regle_format(pages, Config.QUALITE_FORMATS.get(gabarit, {})),
    }
    for saut in SAUTS:
        sortie[f'continuite saut ≤ {saut}'] = (
            lambda pages, s=saut: cq.regle_continuite(
                pages, Config.QUALITE_CONTINUITE.get(gabarit, ()), s))
    return sortie


def cellules_cc(pages):
    return {(p, r, k) for p, page in enumerate(pages) for r, row in enumerate(page['rows'])
            if row.get('type') == 'data' for k, c in enumerate(row['cells'])
            if (c or '').upper().startswith('CC FS')}


def mesurer_c0():
    dictionnaire = get_dictionary()
    documents, contextes = {}, {}
    for nom, doc, stem, gabarit in DOCUMENTS:
        verite, colonnes = lire_verite_excel(FIX / f'{doc}_extrait_verite.xlsx')
        pages = convertir(stem, gabarit, 'claude')
        lexique = charger_lexique(Config.QUALITE_LEXIQUE_REFERENCE, exclure=doc)
        fausses, pleines, numeros = comparer_a_la_verite(pages, verite)
        formes_verite = {f for p in verite for r in p['rows'] if r['type'] == 'data'
                         for c in r['cells'] for f in cq.formes(c)}
        documents[nom] = pages
        contextes[nom] = {'gabarit': gabarit, 'lexique': lexique, 'fausses': fausses,
                          'pleines': pleines, 'numeros': numeros, 'verite': verite,
                          'couverture': (len(formes_verite & lexique), len(formes_verite)),
                          'stem': stem, 'doc': doc}
    copies, cibles = injecter(documents, random.Random(GRAINE))

    sortie = ['# Mesure C0 — règles du contrôle qualité', '',
              f"Graine {GRAINE} ; {N_INJECTEES} erreurs injectées ({', '.join(SORTES_ERREURS)}),"
              " moitié sur pages vectorielles, moitié sur pages scannées ; vraie alerte = cellule"
              " lue différemment de la vérité (ou colonne vide à tort) ; une synthèse « motif non"
              " reconnu » compte comme fausse.", '']
    sortie += ['## Lexique de référence', '',
               f"Dossier : `{Config.QUALITE_LEXIQUE_REFERENCE}` (hors de git) ; "
               "fichiers : " + ', '.join(
                   p.name for p in sorted(Config.QUALITE_LEXIQUE_REFERENCE.glob('*.xlsx'))) + '.',
               '']
    for nom, c in contextes.items():
        a, b = c['couverture']
        sortie.append(f"- {nom} (sans {c['doc']}) : {len(c['lexique'])} formes ; couverture de "
                      f"la vérité {a}/{b} = {a / b:.0%}")

    total = defaultdict(lambda: {'vraies': 0, 'fausses': 0, 'pages': 0,
                                 'fausses_par_sorte': Counter(), 'pages_par_sorte': Counter(),
                                 'inj': Counter(), 'inj_n': Counter()})
    lignes_doc, lignes_pages, detail, paires = [], [], defaultdict(list), Counter()
    for nom, pages in documents.items():
        c = contextes[nom]
        for regle, f in regles(c['gabarit'], c['lexique'], dictionnaire, True).items():
            alertes = f(pages)
            alertes_copie = f(copies[nom])
            t = total[regle]
            vraies = sum(1 for a in alertes if juste(a, c['fausses'], c['pleines']))
            t['vraies'] += vraies
            t['fausses'] += len(alertes) - vraies
            t['pages'] += len(pages)
            for p, page in enumerate(pages):
                t['pages_par_sorte'][sorte(page)] += 1
            for a in alertes:
                if juste(a, c['fausses'], c['pleines']):
                    continue
                genre = sorte(pages[a['page']]) if a['page'] is not None else 'document'
                t['fausses_par_sorte'][genre] += 1
                page = c['numeros'].get(a['page'], '—') if a['page'] is not None else '—'
                detail[regle].append(f"{nom} p. {page} ({genre}), ligne "
                                     f"{'—' if a['ligne'] is None else a['ligne'] + 1} : "
                                     f"{a['message']}")
                if a.get('paire'):
                    paires[(regle, a['paire'])] += 1
            for cible in cibles:
                if cible['doc'] == nom:
                    t['inj_n'][cible['sorte']] += 1
                    t['inj'][cible['sorte']] += signalee(cible, alertes_copie)
            cc = cellules_cc(pages)
            cc_vus = len({(a['page'], a['ligne'], a['colonne']) for a in alertes} & cc)
            par_page = Counter(a['page'] for a in alertes)
            fausses_page = Counter(a['page'] for a in alertes
                                   if not juste(a, c['fausses'], c['pleines']))
            lignes_doc.append(
                f"| {regle} | {nom} | {len(alertes)} | {vraies} | {len(alertes) - vraies} "
                f"| {(str(cc_vus) + '/' + str(len(cc))) if cc else '—'} |")
            for p, page in enumerate(pages):
                if par_page[p]:
                    lignes_pages.append(f"| {regle} | {nom} | {c['numeros'].get(p, p)} "
                                        f"| {sorte(page)} | {par_page[p]} | {fausses_page[p]} |")
    # Dictionnaire en mode Tesseract (conversion locale, sans API).
    for nom, doc, stem, gabarit in DOCUMENTS:
        pages_t = convertir(stem, gabarit, 'tesseract')
        fausses_t, pleines_t, numeros_t = comparer_a_la_verite(pages_t, contextes[nom]['verite'])
        alertes = cq.regle_dictionnaire(pages_t, dictionnaire)
        vraies = sum(1 for a in alertes if juste(a, fausses_t, pleines_t))
        t = total['dictionnaire (mode Tesseract)']
        t['vraies'] += vraies
        t['fausses'] += len(alertes) - vraies
        t['pages'] += len(pages_t)
        lignes_doc.append(f"| dictionnaire (mode Tesseract) | {nom} | {len(alertes)} | {vraies}"
                          f" | {len(alertes) - vraies} | — |")
        for a in alertes:
            if not juste(a, fausses_t, pleines_t):
                detail['dictionnaire (mode Tesseract)'].append(
                    f"{nom} p. {numeros_t.get(a['page'], a['page'])} "
                    f"({sorte(pages_t[a['page']])}), ligne {a['ligne'] + 1} : {a['message']}")

    sortie += ['', '## Synthèse par règle (critère : au plus 1 fausse alerte par page en moyenne)',
               '', '| Règle | Pages | Vraies | Fausses | Fausses/page | Fausses sur pages '
               'vectorielles / scannées / document | Injectées vues : vectorielles / scannées '
               '| Retenue |', '|' + '---|' * 8]
    for regle, t in total.items():
        moy = t['fausses'] / t['pages'] if t['pages'] else 0
        fs = t['fausses_par_sorte']
        sortie.append(
            f"| {regle} | {t['pages']} | {t['vraies']} | {t['fausses']} | {moy:.2f} | "
            f"{fs['vectorielle']} / {fs['scannée']} / {fs['document']} | "
            f"{t['inj']['vectorielle']}/{t['inj_n']['vectorielle']} / "
            f"{t['inj']['scannée']}/{t['inj_n']['scannée']} | {'oui' if moy <= 1 else 'non'} |")
    sortie += ['', '## Par document', '', '| Règle | Document | Alertes | Vraies | Fausses '
               '| CC FS signalés |', '|' + '---|' * 6] + lignes_doc
    sortie += ['', '## Par page (pages avec alertes)', '', '| Règle | Document | Page | Sorte '
               '| Alertes | Fausses |', '|' + '---|' * 6] + lignes_pages
    sortie += ['', '## Erreurs injectées', '', '| Erreur | Document | Page | Sorte | Signalée '
               'par |', '|' + '---|' * 5]
    for cible in cibles:
        c = contextes[cible['doc']]
        par = [regle for regle, f in regles(c['gabarit'], c['lexique'], dictionnaire, True).items()
               if signalee(cible, f(copies[cible['doc']]))]
        sortie.append(f"| {cible['type']} | {cible['doc']} | "
                      f"{c['numeros'].get(cible['page'], cible['page'])} | {cible['sorte']} | "
                      f"{', '.join(par) or 'aucune'} |")
    retenues = [regle for regle, t in total.items()
                if t['pages'] and t['fausses'] / t['pages'] <= 1 and t['inj_n']]
    vues = Counter()
    for cible in cibles:
        c = contextes[cible['doc']]
        fonctions = regles(c['gabarit'], c['lexique'], dictionnaire, True)
        if any(signalee(cible, fonctions[regle](copies[cible['doc']])) for regle in retenues):
            vues[cible['sorte']] += 1
    sortie += ['', f"Règles retenues ensemble ({', '.join(retenues)}) : erreurs injectées vues "
               f"{vues['vectorielle']}/{N_INJECTEES // 2} sur pages vectorielles, "
               f"{vues['scannée']}/{N_INJECTEES - N_INJECTEES // 2} sur pages scannées."]
    sortie += ['', '## Marge des motifs (taux le plus haut observé)', '']
    for nom, pages in documents.items():
        g = contextes[nom]['gabarit']
        hors = cq.taux_hors_format(pages, Config.QUALITE_FORMATS.get(g, {}))
        vides = cq.taux_colonnes_vides(pages, Config.QUALITE_COLONNES_OBLIGATOIRES.get(g, ()))
        sortie.append(f"- {nom} ({g}) : hors format "
                      f"{', '.join(f'{k} {v:.0%}' for k, v in hors.items()) or '—'} ; "
                      "colonne obligatoire vide "
                      + (', '.join(f'{k} {v:.0%}' for k, v in vides.items()) or '—'))
    sortie += ['', '## Fausses alertes par paire de confusion (cohérence)', '']
    sortie += [f"- {regle} {paire} : {n}" for (regle, paire), n in sorted(paires.items())] or \
        ['- aucune']
    sortie += ['', '## Fausses alertes (texte exact)', '']
    for regle, textes in detail.items():
        sortie.append(f"### {regle} : {len(textes)}")
        sortie += [f"- {t}" for t in textes]
    return '\n'.join(sortie)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mesure C0 du contrôle qualité')
    parser.add_argument('--rapport', type=Path, default=None)
    args = parser.parse_args(argv)
    texte = mesurer_c0()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(texte)
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(texte, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
