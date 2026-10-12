"""
Contre-épreuve D1 du compteur de lignes (compte_lignes.py) sur des pages jamais vues.

Réglages figés (commit 4770c8a, mesure D0) : ce script ne règle rien, il mesure.
Documents : les PDF sources complets (doc_a_traiter) de 6A23111PE133, 223111PE012, 223111PE013,
223111PE021, 223111PE022 ; vérité = nombre de lignes de chaque page dans la feuille « Listing »
de l'Excel corrigé (references/excels_valides/). Les pages des extraits (vues pendant D0) sont
reconnues à l'image et mises à part. Une page du PDF est appariée à un bloc de l'Excel par son
contenu (mots de la couche texte, ou de Tesseract sans couche texte) ; une page sans bloc
(garde, sommaire, modifications) est hors du critère et nommée.

Par page : sorte (vectorielle / OCR invisible / scan), lignes de l'Excel, lignes comptées (couche
texte sur une page vectorielle, image sinon), pas, temps du compteur, comptage impossible.
Images annotées des écarts dans mesures/d1_images/.

Lancement :
    env\\Scripts\\python.exe outils_reference\\contre_epreuve_d1.py [--rapport mesures\\d1.md]
"""
import argparse
import re
import sys
import time
from pathlib import Path
from statistics import median

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cache_lectures  # noqa: E402
from compte_lignes import compter_lignes, lignes_couche_texte  # noqa: E402
from mesure_d0 import annoter  # noqa: E402
from positions_scan import LecturePage, dpi_de_rendu, lire_page, pas_initial  # noqa: E402
from template import TemplateManager  # noqa: E402

SOURCES = PROJET.parent / 'document listing opidis' / 'doc_a_traiter'
DOCUMENTS = [
    ('6A23111PE133', 'Repartiteur/6A23111PE133/6A23111PE133/6A23111PE133.pdf',
     '6A23111PE133_extrait_8pages.pdf'),
    ('223111PE012', 'bornier/223111PE012/223111PE012/223111PE012 TP4 Finale.pdf',
     '223111PE012_extrait_10pages.pdf'),
    ('223111PE013', 'Repartiteur/223111PE013/223111PE013/223111PE013 TP3 finale.pdf', None),
    ('223111PE021', 'Repartiteur 2/223111PE021/223111PE021/223111PE021 ED TP3.pdf', None),
    ('223111PE022', 'bornier/223111PE022/223111PE022/223111PE022 TP4 Finale.pdf', None),
]
IMAGES = PROJET / 'mesures' / 'd1_images'
_MOT = re.compile(r'[A-Z0-9]{3,}')
# Pied de page de l'Excel : un libellé suivi de « : », jamais « NOM DU CABLE : » (section) ;
# un mot seul ne suffit pas (« TS PET PORTE FERMEE PH » est une ligne de données).
_PIED = re.compile(r'(?<!NOM DU )\b(P\.?\s?E\.?\s?T\.?|N°\s*PLAN|NO\s*PLAN|INDICE|PAGE'
                   r'|BORNIER|TYPE|CABLE)\s*:')


def mots(texte) -> set:
    return set(_MOT.findall(str(texte or '').upper()))


def blocs_excel(chemin: Path):
    """Pages de la feuille Listing : [{'page', 'lignes', 'mots'}] dans l'ordre."""
    import openpyxl
    entetes = {c.upper() for n in TemplateManager().names()
               for c in TemplateManager().get(n).columns}
    wb = openpyxl.load_workbook(chemin, read_only=True, data_only=True)
    blocs, courant, dans_pied = [], None, False
    for ligne in wb['Listing'].iter_rows(values_only=True):
        valeurs = [str(v).strip() for v in ligne if v is not None and str(v).strip()]
        if not valeurs:
            continue
        if all(v.upper() in entetes for v in valeurs):
            courant = {'page': None, 'lignes': 0, 'mots': set()}
            blocs.append(courant)
            dans_pied = False
            continue
        texte = ' '.join(valeurs).upper()
        if courant is None:
            continue
        if dans_pied or _PIED.search(texte):
            dans_pied = True
            numero = re.search(r'PAGE\s*:\s*(\S+)', texte)
            if numero:
                courant['page'] = numero.group(1)
            continue
        courant['lignes'] += 1
        courant['mots'] |= mots(texte)
    wb.close()
    return blocs


def vignette(page):
    import numpy as np
    pix = page.get_pixmap(dpi=12)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)


def pages_des_extraits(doc, extrait):
    """Indices (0-based) des pages du document qui sont celles de l'extrait (même image)."""
    import fitz
    import numpy as np
    if extrait is None:
        return set()
    vues = set()
    with fitz.open(str(PROJET / 'tests' / 'fixtures' / extrait)) as ext:
        cibles = [vignette(p) for p in ext]
    vignettes = [vignette(p) for p in doc]
    for cible in cibles:
        ecarts = [(float(np.abs(v.astype(int) - cible.astype(int)).mean())
                   if v.shape == cible.shape else 1e9, i) for i, v in enumerate(vignettes)]
        ecart, i = min(ecarts)
        if ecart < 3:
            vues.add(i)
    return vues


def lecture_tesseract(doc_chemin, page, numero):
    empreinte = cache_lectures.empreinte_fichier(doc_chemin)
    gardee = cache_lectures.lire(empreinte, numero)
    if gardee is not None:
        return LecturePage.depuis_dict(gardee)
    lecture = lire_page(page)
    cache_lectures.ecrire(empreinte, numero, lecture.vers_dict())
    return lecture


_NUMERO = re.compile(r'PAGE\s*:?\s*([0-9]+[A-Za-z]?)\b', re.IGNORECASE)


def numero_imprime(texte):
    """Dernier « PAGE : N » lu sur la page (pied), ou None."""
    trouves = _NUMERO.findall(str(texte or ''))
    return trouves[-1].upper() if trouves else None


def apparier(pages_mots, blocs, numeros=None):
    """Page du PDF → indice du bloc (un pour un).

    D'abord le numéro imprimé quand l'Excel porte le même et que le contenu le confirme
    (des pages de 2 à 8 lignes se ressemblent trop pour le contenu seul, 223111PE021) ;
    sinon la part des mots du bloc retrouvés sur la page.
    """
    numeros = numeros or [None] * len(pages_mots)
    page_bloc, pris = {}, set()
    par_numero = {}
    for j, b in enumerate(blocs):
        if b['page'] and b['page'] not in par_numero:
            par_numero[b['page'].upper()] = j
    for i, (m, n) in enumerate(zip(pages_mots, numeros)):
        j = par_numero.get(n) if n else None
        if j is not None and j not in pris and blocs[j]['mots'] \
                and len(blocs[j]['mots'] & m) / len(blocs[j]['mots']) >= 0.3:
            page_bloc[i] = j
            pris.add(j)
    scores = sorted(((len(b['mots'] & m) / len(b['mots']), i, j)
                     for i, m in enumerate(pages_mots) for j, b in enumerate(blocs)
                     if b['mots']), reverse=True)
    for score, i, j in scores:
        if score < 0.3:
            break
        if i not in page_bloc and j not in pris:
            page_bloc[i] = j
            pris.add(j)
    return page_bloc


def mesurer_d1():
    import fitz
    import numpy as np
    from PIL import Image
    from pdf_extractor import VECTORIEL, diagnostiquer_page
    IMAGES.mkdir(parents=True, exist_ok=True)
    sortie = ['# Contre-épreuve D1 — compteur de lignes sur des pages jamais vues', '',
              'Réglages figés au commit 4770c8a (aucun ajustement pendant la mesure).', '']
    bilan, temps, details = [], [], []
    for nom, source, extrait in DOCUMENTS:
        chemin = SOURCES / source
        blocs = blocs_excel(PROJET / 'references' / 'excels_valides' / f'{nom}.xlsx')
        with fitz.open(str(chemin)) as doc:
            vues = pages_des_extraits(doc, extrait)
            natures, pages_mots, lectures, numeros = [], [], {}, []
            for i, page in enumerate(doc):
                nature = diagnostiquer_page(page)['nature']
                natures.append(nature)
                texte = page.get_text()
                if not texte.strip():
                    lectures[i] = lecture_tesseract(chemin, page, i + 1)
                    texte = ' '.join(m[4] for m in lectures[i].mots)
                pages_mots.append(mots(texte))
                numeros.append(numero_imprime(texte))
            page_bloc = apparier(pages_mots, blocs, numeros)
            for i, page in enumerate(doc):
                ligne = {'doc': nom, 'pdf': i + 1, 'nature': natures[i], 'vue': i in vues,
                         'bloc': page_bloc.get(i)}
                if ligne['bloc'] is None:
                    bilan.append(dict(ligne, excel=None, compte=None, raison='hors listing'))
                    continue
                bloc = blocs[ligne['bloc']]
                dpi = dpi_de_rendu(page.rect.width, page.rect.height)
                pix = page.get_pixmap(dpi=dpi)
                gris = np.array(Image.frombytes('RGB', (pix.width, pix.height),
                                                pix.samples).convert('L'))
                mots_pdf = page.get_text('words')
                if natures[i] == VECTORIEL:
                    largeurs = [(m[2] - m[0]) / len(m[4]) for m in mots_pdf
                                if len(m[4]) >= 3 and m[4].isalnum()]
                    pas_car = median(largeurs) * dpi / 72 if largeurs else None
                else:
                    lecture = lectures.get(i) or lecture_tesseract(chemin, page, i + 1)
                    pas_car = pas_initial(lecture.mots)
                pas_car = pas_car or 0.6 * 50 * max(gris.shape) / 3508
                debut = time.perf_counter()
                resultat = compter_lignes(gris, pas_car)
                compte = resultat['lignes']
                if natures[i] == VECTORIEL and resultat['zone']:
                    x0, x1, y0, y1 = (v * 72 / dpi for v in resultat['zone'])
                    compte = lignes_couche_texte(mots_pdf, (x0, x1, y0, y1))
                temps.append(time.perf_counter() - debut)
                ligne.update(excel=bloc['lignes'], page=bloc['page'], compte=compte,
                             pas=resultat['pas'], raison=resultat['raison'])
                bilan.append(ligne)
                if compte != bloc['lignes']:
                    annoter(gris, resultat, IMAGES / f'{nom}_pdf{i + 1}.png')
    jugees = [b for b in bilan if not b['vue'] and b['excel'] is not None]
    sortie += ['## Par document', '', '| Document | Pages | Hors listing | Pages des extraits '
               '| Jugées | Comptées comme l\'Excel | Écarts | Comptage impossible |',
               '|' + '---|' * 8]
    for nom, _, _ in DOCUMENTS:
        b = [x for x in bilan if x['doc'] == nom]
        j = [x for x in jugees if x['doc'] == nom]
        sortie.append(
            f"| {nom} | {len(b)} | {sum(1 for x in b if x['excel'] is None)} | "
            f"{sum(1 for x in b if x['vue'])} | {len(j)} | "
            f"{sum(1 for x in j if x['compte'] == x['excel'])} | "
            f"{sum(1 for x in j if x['compte'] is not None and x['compte'] != x['excel'])} | "
            f"{sum(1 for x in j if x['compte'] is None)} |")
    sortie += ['', f"Temps du compteur par page : médiane {median(temps):.2f} s, "
               f"maximum {max(temps):.2f} s ({len(temps)} pages).", '',
               '## Écarts et comptages impossibles (pages jugées)', '',
               '| Document | Page pdf | Page imprimée | Sorte | Excel | Compteur | Pas | Raison '
               '| Image |', '|' + '---|' * 9]
    for x in jugees:
        if x['compte'] != x['excel']:
            compte = '—' if x['compte'] is None else x['compte']
            sortie.append(f"| {x['doc']} | {x['pdf']} | {x.get('page') or '—'} | "
                          f"{x['nature']} | {x['excel']} | {compte} | "
                          f"{(x['pas'] or 0):.1f} | {x['raison'] or ''} | "
                          f"d1_images/{x['doc']}_pdf{x['pdf']}.png |")
    sortie += ['', '## Pages des extraits (vues pendant D0, hors du critère)', '']
    for x in bilan:
        if x['vue']:
            sortie.append(f"- {x['doc']} pdf {x['pdf']} : Excel {x['excel']}, compteur "
                          f"{x['compte']}")
    sortie += ['', '## Pages hors listing (sans bloc dans l\'Excel)', '']
    for nom, _, _ in DOCUMENTS:
        hors = [str(x['pdf']) for x in bilan if x['doc'] == nom and x['excel'] is None]
        sortie.append(f"- {nom} : pdf {', '.join(hors) or 'aucune'}")
    details.append(len(jugees))
    return '\n'.join(sortie)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Contre-épreuve D1 du compteur de lignes')
    parser.add_argument('--rapport', type=Path, default=None)
    args = parser.parse_args(argv)
    texte = mesurer_d1()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(texte)
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(texte, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
