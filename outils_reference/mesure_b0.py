"""
Mesure B0 (étape 8) : Tesseract peut-il servir de seconde lecture et de contrôle de
conservation sans noyer l'utilisateur sous les alertes ?

Outil de mesure hors de l'appli : aucun code de l'appli modifié, aucun appel API.
Entrées : les 15 pages scannées de tableau des 3 extraits, les dernières réponses
Claude enregistrées (mesures/…_claude.jsonl), la lecture Tesseract du commit A (cache
de l'appli, sinon lue puis mise en cache) et les vérités validées.

1. Mots Claude alignés sur les mots Tesseract (alignement du commit A : lignes appariées
   par apparier_lignes, mots coupés aux traits, jumeaux par cellule).
2. Divergence = mot Claude apparié à un mot Tesseract différent. VRAIE ALERTE si le mot
   Claude est faux (vérité), FAUSSE sinon ; erreurs de Claude sans divergence = ratées.
3. Mêmes comptes aux seuils de confiance Tesseract 60, 70, 80, 90, 95.
4. 50 erreurs typiques injectées dans une copie des réponses (graine fixe).
5. Précision de Tesseract seul contre la vérité, par page et par colonne.
6. Conservation sur une autre copie : 20 mots et 5 lignes supprimés, 10 valeurs
   déplacées dans la colonne voisine ; boîtes Tesseract sans mot Claude en face.

Lancement :
    env\\Scripts\\python.exe outils_reference\\mesure_b0.py [--rapport mesures\\b0.md]
"""
import argparse
import copy
import random
import statistics
import sys
from difflib import SequenceMatcher
from pathlib import Path

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET))

import fitz  # noqa: E402
import openpyxl  # noqa: E402

import cache_lectures  # noqa: E402
import positions_scan as ps  # noqa: E402
from claude_ocr import _parse_pipe_response  # noqa: E402
from mesure_precision import _lignes_donnees, aligner_lignes, mesurer  # noqa: E402
from mesurer_precision import lire_verite_excel  # noqa: E402
from template import TemplateManager  # noqa: E402

FIX = PROJET / 'tests' / 'fixtures'
MESURES = PROJET / 'mesures'
GRAINE = 20261009
SEUILS = (0, 60, 70, 80, 90, 95)
DOCUMENTS = [
    # (nom court, PDF, vérité, modèle, pages scannées de tableau, numéros d'extrait)
    ('PE011', '223111PE011_extrait_10pages', '223111PE011_extrait_verite.xlsx',
     'REPARTITEUR 2', (1, 2, 3, 4, 5, 7, 8, 10)),
    ('PE133', '6A23111PE133_extrait_8pages', '6A23111PE133_extrait_verite.xlsx',
     'REPARTITEUR', (4, 5, 6)),
    ('PE012', '223111PE012_extrait_10pages', '223111PE012_extrait_verite.xlsx',
     'Bornier standard', (4, 6, 7, 8)),
]
N_INJECTEES, N_MOTS, N_LIGNES, N_GLISSEMENTS = 50, 20, 5, 10


# ── Chargement ─────────────────────────────────────────────────────────

def dernier_journal(stem):
    """Journal Claude du passage le plus récent de ce document."""
    journaux = sorted(MESURES.glob(f'{stem}_claude-opus-5-5_*/{stem}_claude.jsonl'),
                      key=lambda p: p.stat().st_mtime)
    if not journaux:
        raise SystemExit(f"Aucune réponse enregistrée pour {stem} dans {MESURES}")
    return journaux[-1]


def lecture_tesseract(pdf, page):
    """Lecture du commit A : cache de l'appli, sinon Tesseract puis mise en cache."""
    empreinte = cache_lectures.empreinte_fichier(pdf)
    gardee = cache_lectures.lire(empreinte, page)
    if gardee is not None:
        return ps.LecturePage.depuis_dict(gardee)
    with fitz.open(str(pdf)) as doc:
        lecture = ps.lire_page(doc[page - 1])
    cache_lectures.ecrire(empreinte, page, lecture.vers_dict())
    return lecture


def pages_verite(chemin):
    """{numéro d'extrait: (page pivot de vérité, numéro imprimé)}."""
    pages, colonnes = lire_verite_excel(chemin)
    wb = openpyxl.load_workbook(chemin, data_only=True)
    numeros = {}
    # Un tableau vide (223111PE011 page 104) n'a de ligne que dans Verite_pieds.
    for feuille in ('Verite_tableaux', 'Verite_pieds'):
        for r in wb[feuille].iter_rows(min_row=2, values_only=True):
            if r[0] is not None:
                numeros.setdefault(int(r[0]), str(r[1]))
    extraits = sorted(numeros)
    assert len(extraits) == len(pages), (chemin, extraits, len(pages))
    return {e: (pages[i], numeros[e]) for i, e in enumerate(extraits)}, colonnes


def charger():
    """Une entrée par page scannée de tableau."""
    import json
    sortie = []
    for nom, stem, verite, gabarit, extraits in DOCUMENTS:
        tpl = TemplateManager().get(gabarit)
        journal = dernier_journal(stem)
        brutes = {json.loads(lg)['image']: json.loads(lg)['raw']
                  for lg in journal.read_text('utf-8').splitlines() if lg.strip()}
        verites, colonnes = pages_verite(FIX / verite)
        pdf = FIX / f'{stem}.pdf'
        for e in extraits:
            rows, _, _ = _parse_pipe_response(brutes[f'page_{e:03d}.png'], tpl)
            verite_page, imprime = verites[e]
            sortie.append({'doc': nom, 'extrait': e, 'imprime': imprime, 'journal': journal,
                           'colonnes': colonnes, 'rows': rows, 'verite': verite_page,
                           'lecture': lecture_tesseract(pdf, e)})
    return sortie


# ── Géométrie et alignement (commit A) ─────────────────────────────────

def geometrie(lecture, colonnes):
    pas, phase = ps.ajuster_grille([m[0] for m in lecture.mots], ps.pas_initial(lecture.mots))
    bornes = ps.bornes_page(lecture.traits, lecture.mots, colonnes, lecture.taille[0])
    return pas, phase, bornes


def lignes_tesseract(lecture, colonnes):
    """Lignes Tesseract du cadre, mots coupés aux traits, avec colonne, confiance et y."""
    pas, phase, bornes = geometrie(lecture, colonnes)
    lignes = []
    for ligne in ps.grouper_lignes_mots(lecture.mots):
        cadre = [m for m in sorted(ligne, key=lambda m: m[0]) if bornes[0] <= m[0] < bornes[-1]]
        mots = []
        for m in ps.couper_aux_traits(cadre, bornes, pas):
            k = next((k for k in range(len(bornes) - 1) if bornes[k] <= m[0] < bornes[k + 1]),
                     None)
            if k is not None:
                mots.append({'texte': m[4], 'k': k, 'conf': m[5], 'y': (m[1] + m[3]) / 2,
                             'col': ps.colonne_caractere(m[0], pas, phase)})
        if mots:
            lignes.append(mots)
    return lignes


def mots_rang(row):
    if row.get('type') == 'section':
        return (row.get('text') or '').split()
    return [w for c in row.get('cells', []) for w in (c or '').split()]


def aligner(rows, lignes, n):
    """Alignement Claude / Tesseract d'une page.

    Retourne paires (rang de ligne lue → ligne Tesseract), mots appariés
    {(r, k, i): (mot Tesseract, égal une fois replié)}, mots Tesseract libres de la zone
    du tableau {(ligne, indice)} et la part des mots Claude appariés.
    """
    a_placer = [i for i, r in enumerate(rows) if r.get('type') in ('data', 'section')
                and mots_rang(r)]
    cles_c = [ps.replier(''.join(mots_rang(rows[i]))) for i in a_placer]
    cles_t = [ps.replier(''.join(w['texte'] for w in lg)) for lg in lignes]
    rang_paires = ps.apparier_lignes(cles_c, cles_t)
    paires = {a_placer[r]: li for r, li in rang_paires.items()}
    apparies, total = {}, 0
    pris = set()
    for r, li in paires.items():
        row = rows[r]
        if row.get('type') == 'section':
            pris.update((li, j) for j in range(len(lignes[li])))
            continue
        for k in range(n):
            cw = (row['cells'][k] if k < len(row['cells']) else '').split()
            tw = [(j, w) for j, w in enumerate(lignes[li]) if w['k'] == k]
            sm = SequenceMatcher(None, [ps.replier(x) for x in cw],
                                 [ps.replier(w['texte']) for _, w in tw], autojunk=False)
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == 'equal' or (op == 'replace' and i2 - i1 == j2 - j1):
                    for d in range(i2 - i1):
                        j, w = tw[j1 + d]
                        apparies[(r, k, i1 + d)] = (w, op == 'equal')
                        pris.add((li, j))
    for r, row in enumerate(rows):
        if row.get('type') == 'data':
            total += sum(len((c or '').split()) for c in row['cells'])
    # Zone du tableau : entre la première et la dernière ligne Tesseract appariée.
    ys = [statistics.median(w['y'] for w in lignes[li]) for li in paires.values()]
    libres = set()
    if ys:
        bas, haut = min(ys), max(ys)
        for li, lg in enumerate(lignes):
            if bas <= statistics.median(w['y'] for w in lg) <= haut:
                libres.update((li, j) for j in range(len(lg)) if (li, j) not in pris)
    part = len(apparies) / total if total else 1.0
    return {'paires': paires, 'apparies': apparies, 'libres': libres, 'part': part,
            'mots_claude': total}


def divergences(alignement, rows):
    """Mots Claude appariés à un mot Tesseract différent : {(r, k, i): (lu, conf, replié)}."""
    sortie = {}
    for (r, k, i), (w, egal_replie) in alignement['apparies'].items():
        claude = rows[r]['cells'][k].split()[i]
        if claude.upper() != w['texte'].upper():
            sortie[(r, k, i)] = (w['texte'], w['conf'], egal_replie)
    return sortie


# ── Vérité ─────────────────────────────────────────────────────────────

def erreurs_claude(rows, verite, n):
    """Mots Claude faux selon la vérité {(r, k, i)} et cellules fausses {(r, k): (lu, vrai)}."""
    lignes_c = [(r, row) for r, row in enumerate(rows) if row.get('type') == 'data'
                and any((c or '').strip() for c in row['cells'])]
    ref = _lignes_donnees(verite)
    mots, cellules = set(), {}
    for i, j in aligner_lignes(ref, [row for _, row in lignes_c]):
        if i is None or j is None:
            continue
        r, row = lignes_c[j]
        for k in range(n):
            lu = (row['cells'][k] if k < len(row['cells']) else '').split()
            vrai = (ref[i]['cells'][k] if k < len(ref[i]['cells']) else '').split()
            if lu == vrai:
                continue
            cellules[(r, k)] = (' '.join(lu), ' '.join(vrai))
            justes = {a.a + d for a in SequenceMatcher(None, lu, vrai, autojunk=False)
                      .get_matching_blocks() for d in range(a.size)}
            mots.update((r, k, x) for x in range(len(lu)) if x not in justes)
    return mots, cellules


def precision_tesseract(lignes, verite, colonnes):
    """Part des cellules de la vérité lues à l'identique par Tesseract seul, par colonne."""
    page = {'success': True, 'metadata': {}, 'pied_texte': [], 'rows': [
        {'type': 'data', 'cells': [' '.join(w['texte'] for w in lg if w['k'] == k)
                                   for k in range(len(colonnes))],
         'confidence': [100] * len(colonnes)} for lg in lignes]}
    rapport = mesurer([verite], [page], colonnes)
    n = len(_lignes_donnees(verite))
    manquantes = sum(1 for o in rapport.lignes_orphelines if o.cote == 'MANQUANTE')
    if not rapport.pages_appariees:
        return {c: 0.0 for c in colonnes}
    return {c: max(0.0, 1 - (sum(1 for e in rapport.ecarts_cellules if e.colonne == c)
                             + manquantes) / n) if n else 1.0 for c in colonnes}


# ── Copies modifiées ──────────────────────────────────────────────────

def _bascule(a, b):
    def f(w, _alea):
        if a in w:
            return w.replace(a, b, 1)
        return w.replace(b, a, 1) if b in w else None
    return f


def _lettre_en_moins(w, alea):
    lettres = [i for i, c in enumerate(w) if c.isalpha()]
    if len(w) < 2 or not lettres:
        return None
    i = alea.choice(lettres)
    return w[:i] + w[i + 1:]


def _chiffres_inverses(w, _alea):
    for i in range(len(w) - 1):
        if w[i].isdigit() and w[i + 1].isdigit() and w[i] != w[i + 1]:
            return w[:i] + w[i + 1] + w[i] + w[i + 2:]
    return None


TYPES_ERREURS = [('O/C', _bascule('O', 'C')), ('O/0', _bascule('O', '0')),
                 ('I/1', _bascule('1', 'I')), ('S/5', _bascule('5', 'S')),
                 ('B/8', _bascule('8', 'B')), ('lettre en moins', _lettre_en_moins),
                 ('chiffres inversés', _chiffres_inverses)]


def injecter_erreurs(pages, alea):
    """Copie des réponses avec N_INJECTEES erreurs typiques ; {(page, r, k, i): (type, avant)}."""
    copies = [copy.deepcopy(p['rows']) for p in pages]
    candidats = [(p, r, k, i) for p, rows in enumerate(copies) for r, row in enumerate(rows)
                 if row.get('type') == 'data' for k, c in enumerate(row['cells'])
                 for i, _ in enumerate((c or '').split())]
    alea.shuffle(candidats)
    injectees = {}
    for n in range(N_INJECTEES):
        nom, f = TYPES_ERREURS[n % len(TYPES_ERREURS)]
        for cle in candidats:
            p, r, k, i = cle
            if cle in injectees:
                continue
            mots = copies[p][r]['cells'][k].split()
            nouveau = f(mots[i], alea)
            if nouveau and nouveau != mots[i]:
                injectees[cle] = (nom, mots[i])
                mots[i] = nouveau
                copies[p][r]['cells'][k] = ' '.join(mots)
                break
    return copies, injectees


def conservation(pages, alea):
    """Copie avec mots et lignes supprimés, valeurs déplacées dans la colonne voisine."""
    copies = [copy.deepcopy(p['rows']) for p in pages]
    lignes = [(p, r) for p, rows in enumerate(copies) for r, row in enumerate(rows)
              if row.get('type') == 'data' and any((c or '').strip() for c in row['cells'])]
    alea.shuffle(lignes)
    supprimees = lignes[:N_LIGNES]
    reste = lignes[N_LIGNES:]
    deplacees, mots_suppr = [], []
    for p, r in reste:
        if len(deplacees) == N_GLISSEMENTS:
            break
        cells = copies[p][r]['cells']
        k = alea.choice([k for k, c in enumerate(cells) if (c or '').strip()])
        voisins = [v for v in (k - 1, k + 1) if 0 <= v < len(cells)]
        v = alea.choice(voisins)
        avant = list(cells)
        if v > k:
            cells[v] = ' '.join(x for x in (cells[k], cells[v]) if x.strip())
        else:
            cells[v] = ' '.join(x for x in (cells[v], cells[k]) if x.strip())
        cells[k] = ''
        deplacees.append((p, r, avant))
    utilisees = {(p, r) for p, r, _ in deplacees}
    for p, r in reste:
        if len(mots_suppr) == N_MOTS:
            break
        if (p, r) in utilisees:
            continue
        cells = copies[p][r]['cells']
        k = alea.choice([k for k, c in enumerate(cells) if (c or '').strip()])
        mots = cells[k].split()
        i = alea.randrange(len(mots))
        mots_suppr.append((p, r, k, mots.pop(i)))
        cells[k] = ' '.join(mots)
        utilisees.add((p, r))
    # Lignes supprimées en dernier : les indices des autres modifications restent valables
    # dans la copie complète ; la copie amputée est construite à part.
    amputees = [[row for r, row in enumerate(rows) if (p, r) not in set(supprimees)]
                for p, rows in enumerate(copies)]
    index = [[r for r in range(len(rows)) if (p, r) not in set(supprimees)]
             for p, rows in enumerate(copies)]
    return copies, amputees, index, supprimees, mots_suppr, deplacees


# ── Mesure ─────────────────────────────────────────────────────────────

def ressemble(a, b):
    a, b = ps.replier(a), ps.replier(b)
    return a == b or SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.5


def mesurer_b0():
    pages = charger()
    for p in pages:
        p['lignes'] = lignes_tesseract(p['lecture'], p['colonnes'])
        n = len(p['colonnes'])
        p['n'] = n
        p['align'] = aligner(p['rows'], p['lignes'], n)
        p['div'] = divergences(p['align'], p['rows'])
        p['err_mots'], p['err_cells'] = erreurs_claude(p['rows'], p['verite'], n)
        p['precision'] = precision_tesseract(p['lignes'], p['verite'], p['colonnes'])
        _, bilan = ps.placer_page(p['rows'], p['colonnes'], p['lecture'])
        p['deplaces_origine'] = bilan['deplaces']

    alea = random.Random(GRAINE)
    inj_rows, injectees = injecter_erreurs(pages, alea)
    inj_div = []
    for idx, p in enumerate(pages):
        al = aligner(inj_rows[idx], p['lignes'], p['n'])
        inj_div.append(divergences(al, inj_rows[idx]))

    alea = random.Random(GRAINE + 1)
    cons_rows, amputees, index, suppr_lignes, suppr_mots, deplacees = conservation(pages, alea)
    cons = []
    for idx, p in enumerate(pages):
        al = aligner(amputees[idx], p['lignes'], p['n'])
        # Ligne de la copie amputée → rang dans la copie complète.
        al['paires_completes'] = {index[idx][r]: li for r, li in al['paires'].items()}
        places, bilan = ps.placer_page(amputees[idx], p['colonnes'], p['lecture'])
        cons.append({'align': al, 'places': places, 'bilan': bilan})
    return pages, injectees, inj_div, cons, cons_rows, suppr_lignes, suppr_mots, deplacees


def compter(seuil, pages, injectees, inj_div, cons, suppr_lignes, suppr_mots, deplacees,
            index_pages, replie=False):
    """Comptes d'un seuil sur un sous-ensemble de pages (indices)."""
    garde = set(index_pages)

    def actif(conf, egal):
        return conf >= seuil and not (replie and egal)

    alertes, vraies, fausses, ratees = [], 0, 0, 0
    connues = connues_total = 0
    for idx in index_pages:
        p = pages[idx]
        div = {c: v for c, v in p['div'].items() if actif(v[1], v[2])}
        alertes.append(len(div))
        vraies += sum(1 for c in div if c in p['err_mots'])
        fausses += sum(1 for c in div if c not in p['err_mots'])
        ratees += sum(1 for c in p['err_mots'] if c not in div)
        for (r, k) in p['err_cells']:
            connues_total += 1
            connues += any(c[0] == r and c[1] == k for c in div)
    inj = [c for c in injectees if c[0] in garde]
    inj_vues = sum(1 for (pi, r, k, i) in inj
                   if (r, k, i) in inj_div[pi] and actif(inj_div[pi][(r, k, i)][1],
                                                        inj_div[pi][(r, k, i)][2]))
    mots = [m for m in suppr_mots if m[0] in garde]
    mots_vus = 0
    for pi, r, k, mot in mots:
        li = cons[pi]['align']['paires_completes'].get(r)
        lg = pages[pi]['lignes'][li] if li is not None else []
        mots_vus += any((li, j) in cons[pi]['align']['libres'] and w['k'] == k
                        and w['conf'] >= seuil and ressemble(w['texte'], mot)
                        for j, w in enumerate(lg))
    lignes = [s for s in suppr_lignes if s[0] in garde]
    lignes_vues = 0
    for pi, r in lignes:
        li = pages[pi]['align']['paires'].get(r)
        if li is None or li in cons[pi]['align']['paires'].values():
            continue
        lg = pages[pi]['lignes'][li]
        lignes_vues += statistics.median(w['conf'] for w in lg) >= seuil
    bruit = [sum(1 for (li, j) in pages[idx]['align']['libres']
                 if pages[idx]['lignes'][li][j]['conf'] >= seuil) for idx in index_pages]
    return {'alertes': alertes, 'vraies': vraies, 'fausses': fausses, 'ratees': ratees,
            'connues': (connues, connues_total), 'injectees': (inj_vues, len(inj)),
            'mots': (mots_vus, len(mots)), 'lignes': (lignes_vues, len(lignes)), 'bruit': bruit}


def glissements(pages, cons, cons_rows, deplacees, index_pages, suppr_lignes):
    """(remis, déplacés, à tort sur les réponses non modifiées, à tort sur la copie)."""
    garde = set(index_pages)
    remis = total = 0
    for pi, r, avant in deplacees:
        if pi not in garde:
            continue
        total += 1
        # Rang de la ligne dans la copie amputée (lignes supprimées retirées).
        decal = sum(1 for (p2, r2) in suppr_lignes if p2 == pi and r2 < r)
        apres = cons[pi]['places'][r - decal]['cells']
        remis += [' '.join(c.split()) for c in apres] == [' '.join(c.split()) for c in avant]
    a_tort_origine = sum(len(pages[i]['deplaces_origine']) for i in index_pages)
    attendus = {(pi, r) for pi, r, _ in deplacees}
    a_tort_copie = 0
    for pi in index_pages:
        rangs = [r for r in range(len(cons_rows[pi]))
                 if (pi, r) not in set(suppr_lignes)]
        for d in cons[pi]['bilan']['deplaces']:
            if (pi, rangs[d['ligne'] - 1]) not in attendus:
                a_tort_copie += 1
    return remis, total, a_tort_origine, a_tort_copie


# ── Rapport ───────────────────────────────────────────────────────────

def fraction(t):
    return f"{t[0]}/{t[1]}"


def rapport(resultats):
    pages, injectees, inj_div, cons, cons_rows, suppr_lignes, suppr_mots, deplacees = resultats
    lignes = ['# Mesure B0 — Tesseract seconde lecture et contrôle de conservation', '']
    lignes.append('Réponses Claude : ' + ', '.join(sorted({p['journal'].parent.name
                                                          for p in pages})))
    lignes.append(f'Graine : {GRAINE} ; {len(pages)} pages scannées de tableau.')
    groupes = [(nom, [i for i, p in enumerate(pages) if p['doc'] == nom])
               for nom, *_ in DOCUMENTS] + [('Total', list(range(len(pages))))]
    for replie, titre in ((False, 'Divergences brutes (texte différent)'),
                          (True, 'Variante : divergences hors O/0, I/1, l/1 (texte replié)')):
        lignes += ['', f'## {titre}', '',
                   '| Seuil | Document | Alertes/page moy (max) | Vraies | Fausses | Ratées '
                   '| Cellules fausses de Claude signalées | Injectées signalées | Mots retrouvés '
                   '| Lignes retrouvées | Glissements remis | Dépl. à tort (origine / copie) '
                   '| Bruit de conservation/page moy (max) |',
                   '|' + '---|' * 13]
        for seuil in SEUILS:
            for nom, idx in groupes:
                c = compter(seuil, pages, injectees, inj_div, cons, suppr_lignes, suppr_mots,
                            deplacees, idx, replie)
                remis, total, tort_o, tort_c = glissements(pages, cons, cons_rows, deplacees,
                                                           idx, suppr_lignes)
                lignes.append(
                    f"| {seuil or 'aucun'} | {nom} | {statistics.mean(c['alertes']):.1f} "
                    f"({max(c['alertes'])}) | {c['vraies']} | {c['fausses']} | {c['ratees']} "
                    f"| {fraction(c['connues'])} | {fraction(c['injectees'])} "
                    f"| {fraction(c['mots'])} | {fraction(c['lignes'])} | {remis}/{total} "
                    f"| {tort_o} / {tort_c} | {statistics.mean(c['bruit']):.1f} "
                    f"({max(c['bruit'])}) |")
    lignes += ['', '## Par page', '',
               '| Document | Page | Mots Claude | Part alignée | Lignes Claude | Lignes Tesseract '
               '(zone) | Divergences (aucun seuil) | Bruit de conservation | Précision Tesseract '
               'par colonne |', '|' + '---|' * 9]
    for p in pages:
        n_claude = sum(1 for r in p['rows'] if r.get('type') in ('data', 'section'))
        libres_lignes = {li for li, _ in p['align']['libres']}
        zone = len(set(p['align']['paires'].values()) | libres_lignes)
        prec = ', '.join(f"{c} {v:.0%}" for c, v in p['precision'].items())
        lignes.append(
            f"| {p['doc']} | {p['imprime']} | {p['align']['mots_claude']} "
            f"| {p['align']['part']:.0%} | {n_claude} | {zone} | {len(p['div'])} "
            f"| {len(p['align']['libres'])} | {prec} |")
    lignes += ['', '## Cellules fausses de Claude (vérité) et divergences', '']
    for p in pages:
        for (r, k), (lu, vrai) in sorted(p['err_cells'].items()):
            div = [(p['rows'][r]['cells'][k].split()[i], v[0], v[1])
                   for (r2, k2, i), v in p['div'].items() if (r2, k2) == (r, k)]
            lignes.append(f"- {p['doc']} p. {p['imprime']} {p['colonnes'][k]} : lu « {lu} », "
                          f"vrai « {vrai} » ; divergences (Claude, Tesseract, conf) : {div}")
    lignes += ['', '## Erreurs injectées par type (aucun seuil)', '']
    par_type = {}
    for (pi, r, k, i), (nom, _) in injectees.items():
        vue = (r, k, i) in inj_div[pi]
        tot = par_type.setdefault(nom, [0, 0])
        tot[0] += vue
        tot[1] += 1
    lignes += [f"- {nom} : {v}/{t}" for nom, (v, t) in par_type.items()]
    return '\n'.join(lignes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--rapport', type=Path, default=None,
                        help='Fichier Markdown où écrire le rapport (sinon écran seul)')
    args = parser.parse_args(argv)
    texte = rapport(mesurer_b0())
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(texte)
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(texte, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
