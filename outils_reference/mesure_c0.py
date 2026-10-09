"""
Mesure C0 (étape 9) : chaque règle de controle_qualite, prise seule, sur les 3 extraits.

Outil de mesure hors de l'appli, aucun appel API : les dernières réponses Claude
enregistrées sont rejouées par le convertisseur (faux client), pages vectorielles comprises ;
une conversion en mode Tesseract (locale) sert à mesurer le dictionnaire hors Claude.
Pour chaque règle : alertes sur les lectures actuelles, vraies (cellule fausse selon la
vérité) ou fausses ; 50 erreurs injectées (graine fixe) signalées ; les 2 OC→CC de
223111PE011 p. 119. Le lexique de référence exclut le document mesuré.

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
import statistics
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import controle_qualite as cq  # noqa: E402
from config import Config  # noqa: E402
from converter import Converter  # noqa: E402
from data_dictionary import get_dictionary  # noqa: E402
from lexique_reference import charger_lexique  # noqa: E402
from mesure_b0 import TYPES_ERREURS  # noqa: E402
from mesure_precision import _lignes_donnees, aligner_lignes, apparier_pages_par_contenu  # noqa: E402,E501
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


# ── Pages converties (rejeu Claude et mode Tesseract) ──────────────────

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


# ── Vérité : cellules fausses ──────────────────────────────────────────

def cellules_fausses(pages, verite):
    """{(page, ligne, colonne)} des cellules lues différemment de la vérité, et cellules
    comparées ; colonnes vides à tort {(page, colonne)}."""
    fausses, comparees, colonnes_pleines = set(), set(), {}
    paires, _, _ = apparier_pages_par_contenu(verite, pages)
    for iv, ip in paires:
        ref = _lignes_donnees(verite[iv])
        lignes = [(r, row) for r, row in enumerate(pages[ip]['rows'])
                  if row.get('type') == 'data' and any((c or '').strip() for c in row['cells'])]
        for k in range(len(pages[ip].get('headers') or [])):
            colonnes_pleines[(ip, k)] = any((row['cells'][k] if k < len(row['cells']) else '')
                                            .strip() for row in ref)
        for i, j in aligner_lignes(ref, [row for _, row in lignes]):
            if i is None or j is None:
                continue
            r, row = lignes[j]
            for k, vrai in enumerate(ref[i]['cells']):
                lu = row['cells'][k] if k < len(row['cells']) else ''
                comparees.add((ip, r, k))
                if ' '.join((lu or '').split()) != ' '.join((vrai or '').split()):
                    fausses.add((ip, r, k))
    return fausses, comparees, colonnes_pleines


def classer(alertes, fausses, colonnes_pleines):
    vraies = sum(1 for a in alertes if (a['ligne'] is None
                                        and colonnes_pleines.get((a['page'], a['colonne'])))
                 or (a['page'], a['ligne'], a['colonne']) in fausses)
    return vraies, len(alertes) - vraies


# ── Erreurs injectées ──────────────────────────────────────────────────

def injecter(pages, alea, n):
    copies = copy.deepcopy(pages)
    candidats = [(p, r, k, i) for p, page in enumerate(copies)
                 for r, row in enumerate(page['rows']) if row.get('type') == 'data'
                 for k, c in enumerate(row['cells']) for i, _ in enumerate((c or '').split())]
    alea.shuffle(candidats)
    injectees = {}
    for m in range(n):
        nom, f = TYPES_ERREURS[m % len(TYPES_ERREURS)]
        for p, r, k, i in candidats:
            if (p, r, k) in injectees:
                continue
            mots = copies[p]['rows'][r]['cells'][k].split()
            nouveau = f(mots[i], alea)
            if nouveau and nouveau != mots[i]:
                injectees[(p, r, k)] = (nom, mots[i], nouveau)
                mots[i] = nouveau
                copies[p]['rows'][r]['cells'][k] = ' '.join(mots)
                break
    return copies, injectees


# ── Règles prises seules ───────────────────────────────────────────────

def regles(gabarit, lexique, dictionnaire, mode_claude):
    """{nom: fonction(pages) → alertes} : chaque règle avec ses paramètres de config.py."""
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
        sortie[f'continuite (saut ≤ {saut})'] = (
            lambda pages, s=saut: cq.regle_continuite(
                pages, Config.QUALITE_CONTINUITE.get(gabarit, ()), s))
    return sortie


def occ_cc(pages):
    """(page, ligne, colonne) des cellules « CC FS 14 50 … » lues par Claude."""
    return {(p, r, k) for p, page in enumerate(pages) for r, row in enumerate(page['rows'])
            if row.get('type') == 'data' for k, c in enumerate(row['cells'])
            if (c or '').upper().startswith('CC FS')}


def mesurer_c0():
    lignes = []
    dictionnaire = get_dictionary()
    totaux = {}
    for nom, doc, stem, gabarit in DOCUMENTS:
        verite, _ = lire_verite_excel(FIX / f"{doc}_extrait_verite.xlsx")
        lexique = charger_lexique(Config.QUALITE_LEXIQUE_DOSSIER, exclure=doc)
        for mode in ('claude', 'tesseract'):
            pages = convertir(stem, gabarit, mode)
            fausses, comparees, pleines = cellules_fausses(pages, verite)
            copies, injectees = injecter(pages, random.Random(GRAINE), N_INJECTEES)
            for regle, f in regles(gabarit, lexique, dictionnaire, mode == 'claude').items():
                if mode == 'tesseract' and regle != 'dictionnaire':
                    continue
                alertes = f(pages)
                vraies, fausses_alertes = classer(alertes, fausses, pleines)
                par_page = [sum(1 for a in alertes if a['page'] == p) for p in range(len(pages))]
                fausses_page = [sum(1 for a in alertes if a['page'] == p and not (
                    (a['page'], a['ligne'], a['colonne']) in fausses
                    or (a['ligne'] is None and pleines.get((p, a['colonne'])))))
                    for p in range(len(pages))]
                vues = {(a['page'], a['ligne'], a['colonne']) for a in f(copies)}
                inj = sum(1 for c in injectees if c in vues)
                cc = occ_cc(pages)
                cc_vus = sum(1 for a in alertes if (a['page'], a['ligne'], a['colonne']) in cc)
                cle = (regle, mode)
                t = totaux.setdefault(cle, {'pages': 0, 'vraies': 0, 'fausses': 0, 'inj': 0,
                                            'inj_n': 0, 'fausses_page': []})
                t['pages'] += len(pages)
                t['vraies'] += vraies
                t['fausses'] += fausses_alertes
                t['inj'] += inj
                t['inj_n'] += len(injectees)
                t['fausses_page'] += fausses_page
                lignes.append(
                    f"| {regle} | {mode} | {nom} | {len(pages)} | "
                    f"{statistics.mean(par_page):.2f} ({max(par_page, default=0)}) | {vraies} | "
                    f"{fausses_alertes} | {statistics.mean(fausses_page):.2f} | "
                    f"{inj}/{len(injectees)} | "
                    f"{(str(cc_vus) + '/' + str(len(cc))) if cc else '—'} |")
                for a in alertes:
                    juste = ((a['page'], a['ligne'], a['colonne']) in fausses
                             or (a['ligne'] is None and pleines.get((a['page'], a['colonne']))))
                    if not juste:
                        totaux.setdefault(('detail', regle, mode), []).append(
                            f"{nom} {mode} p.{a['page']} l.{a['ligne']} c.{a['colonne']} : "
                            f"{a['message']}")
    entete = ['# Mesure C0 — règles du contrôle qualité', '',
              f"Graine {GRAINE}, {N_INJECTEES} erreurs injectées par document et par mode ; "
              "vraie alerte = cellule lue différemment de la vérité (ou colonne vide à tort).",
              '', '| Règle | Mode | Document | Pages | Alertes/page moy (max) | Vraies | Fausses '
              '| Fausses/page | Injectées vues | OC→CC vus |', '|' + '---|' * 10]
    synthese = ['', '## Total par règle (critère : au plus 1 fausse alerte par page en moyenne)',
                '', '| Règle | Mode | Pages | Vraies | Fausses | Fausses/page | Injectées vues '
                '| Retenue |', '|' + '---|' * 8]
    for (regle, mode), t in totaux.items():
        if regle == 'detail':
            continue
        moyenne = t['fausses'] / t['pages'] if t['pages'] else 0
        synthese.append(f"| {regle} | {mode} | {t['pages']} | {t['vraies']} | {t['fausses']} "
                        f"| {moyenne:.2f} | {t['inj']}/{t['inj_n']} "
                        f"| {'oui' if moyenne <= 1 else 'non'} |")
    details = ['', '## Fausses alertes (détail)', '']
    for cle, valeurs in totaux.items():
        if cle[0] == 'detail':
            details.append(f"### {cle[1]} ({cle[2]}) : {len(valeurs)}")
            details += [f"- {v}" for v in valeurs[:40]]
    return '\n'.join(entete + lignes + synthese + details)


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
