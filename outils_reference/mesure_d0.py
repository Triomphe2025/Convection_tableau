"""
Mesure D0 (étape 9) : compteur de lignes visibles (compte_lignes.py) sur les 21 pages.

Outil de mesure hors de l'appli, aucun appel API : les pages lues viennent du rejeu de C1.
Par page : lignes de la vérité, lignes lues, lignes comptées sur l'image (et dans la couche
texte pour une page vectorielle), pas trouvé, sorte, « comptage impossible ». Puis deux
passages : une ligne perdue injectée sur chaque page, une fusion de deux lignes sur chaque
page ; une page est trouvée si le compte diffère des lignes lues après injection.
Images annotées (zone, cases comptées) dans mesures/d0_images/.

Lancement :
    env\\Scripts\\python.exe outils_reference\\mesure_d0.py [--rapport mesures\\d0.md]
"""
import argparse
import sys
from pathlib import Path
from statistics import median

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesure_c0 as c0  # noqa: E402
import mesure_c1 as c1  # noqa: E402
from compte_lignes import compter_lignes, lignes_couche_texte  # noqa: E402
from mesure_precision import apparier_pages_par_contenu  # noqa: E402
from mesurer_precision import lire_verite_excel  # noqa: E402
from positions_scan import dpi_de_rendu, pas_initial  # noqa: E402

IMAGES = PROJET / 'mesures' / 'd0_images'


def lignes_lues(page) -> int:
    return sum(1 for r in page['rows'] if r.get('type') == 'section'
               or (r.get('type') == 'data' and any((c or '').strip() for c in r['cells'])))


def pas_caractere_texte(mots, dpi):
    largeurs = [(m[2] - m[0]) / len(m[4]) for m in mots if len(m[4]) >= 3 and m[4].isalnum()]
    return median(largeurs) * dpi / 72 if largeurs else None


def annoter(gris, resultat, chemin):
    import cv2
    image = cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)
    if resultat['zone']:
        x0, x1, y0, y1 = resultat['zone']
        cv2.rectangle(image, (x0, y0), (x1, y1), (255, 0, 0), 2)
        for a, b in resultat['cases']:
            cv2.rectangle(image, (x0 + 2, a), (x0 + 30, b - 1), (0, 160, 0), -1)
    cv2.imwrite(str(chemin), cv2.resize(image, None, fx=0.4, fy=0.4))


def mesurer_page(doc_pdf, page, numero, lecture):
    import numpy as np
    from PIL import Image
    pdf_page = doc_pdf[numero - 1]
    dpi = dpi_de_rendu(pdf_page.rect.width, pdf_page.rect.height)
    pix = pdf_page.get_pixmap(dpi=dpi)
    gris = np.array(Image.frombytes('RGB', (pix.width, pix.height), pix.samples).convert('L'))
    mots_pdf = pdf_page.get_text('words')
    vectorielle = c0.sorte(page) == 'vectorielle'
    pas_car = (pas_caractere_texte(mots_pdf, dpi) if vectorielle
               else pas_initial(lecture.mots) if lecture is not None else None)
    if not pas_car:
        pas_car = 0.6 * 50 * dpi / 300
    resultat = compter_lignes(gris, pas_car)
    texte = None
    if vectorielle and resultat['zone']:
        x0, x1, y0, y1 = (v * 72 / dpi for v in resultat['zone'])
        texte = lignes_couche_texte(mots_pdf, (x0, x1, y0, y1))
    return resultat, texte, gris, pas_car


def mesurer_d0():
    import fitz
    IMAGES.mkdir(parents=True, exist_ok=True)
    sortie = ['# Mesure D0 — nombre de lignes visibles (rejeu, sans API)', '',
              '| Document | Page | Sorte | Vérité | Lues | Image | Couche texte | Pas (px) '
              '| Régularité | Pas caractère (px) | Comptage impossible | Alerte |',
              '|' + '---|' * 12]
    lignes_pages = []
    for nom, doc, stem, gabarit in c0.DOCUMENTS:
        verite, _ = lire_verite_excel(c0.FIX / f'{doc}_extrait_verite.xlsx')
        pages, conv, _ = c1.convertir(doc, stem, gabarit)
        paires, _, _ = apparier_pages_par_contenu(verite, pages)
        vraies = {ip: sum(1 for r in verite[iv]['rows'] if r['type'] in ('data', 'section'))
                  for iv, ip in paires}
        with fitz.open(str(c0.FIX / f'{stem}.pdf')) as doc_pdf:
            for i, page in enumerate(pages):
                numero = c1.page_pdf(page) or page['page_num'] + 1
                lecture = conv._lectures_tesseract.get(numero)
                resultat, texte, gris, pas_car = mesurer_page(doc_pdf, page, numero, lecture)
                annoter(gris, resultat, IMAGES / f'{nom}_pdf{numero}.png')
                lues = lignes_lues(page)
                vectorielle = c0.sorte(page) == 'vectorielle'
                compte = texte if vectorielle and texte is not None else resultat['lignes']
                nom_page = page.get('metadata', {}).get('PAGE') or f'pdf {numero}'
                alerte = ('' if compte is None or compte == lues
                          else f"{compte} visibles, {lues} lues")
                lignes_pages.append({'doc': nom, 'page': nom_page, 'sorte': c0.sorte(page),
                                     'lues': lues, 'compte': compte,
                                     'impossible': resultat['raison']})
                image = '—' if resultat['lignes'] is None else resultat['lignes']
                sortie.append(
                    f"| {nom} | {nom_page} (pdf {numero}) | {c0.sorte(page)} | "
                    f"{vraies.get(i, '—')} | {lues} | {image} | "
                    f"{texte if texte is not None else '—'} | "
                    f"{resultat['pas'] or 0:.1f} | {resultat['regularite'] or 0:.2f} | "
                    f"{pas_car:.1f} | {resultat['raison'] or ''} | {alerte} |")

    def liste(pages, raison=False):
        return ', '.join(f"{p['doc']} p. {p['page']}" + (f" : {p['impossible']}" if raison
                                                         else '') for p in pages) or 'aucune'

    fausses = [p for p in lignes_pages if p['compte'] is not None and p['compte'] != p['lues']]
    impossibles = [p for p in lignes_pages if p['compte'] is None]
    scannees = [p for p in lignes_pages if p['sorte'] == 'scannée']
    sortie += ['', f"Pages en fausse alerte : {len(fausses)} sur {len(lignes_pages)} "
               f"({liste(fausses)}).",
               f"Comptage impossible : {len(impossibles)} page(s) ({liste(impossibles, True)}) ; "
               f"pages scannées : {sum(1 for p in impossibles if p['sorte'] == 'scannée')} "
               f"sur {len(scannees)}.", '']
    for titre in ('ligne perdue', 'lignes fusionnées'):
        # Une ligne de moins dans la lecture dans les deux cas ; trouvée si le compte diffère.
        trouvees = [p for p in lignes_pages if p['compte'] is not None
                    and p['compte'] != p['lues'] - 1]
        manquees = [p for p in lignes_pages if p not in trouvees]
        sortie.append(f"- {titre} injectée sur chaque page : trouvée sur {len(trouvees)} sur "
                      f"{len(lignes_pages)} ; manquée : {liste(manquees)}")
    return '\n'.join(sortie)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mesure D0 du compteur de lignes')
    parser.add_argument('--rapport', type=Path, default=None)
    args = parser.parse_args(argv)
    texte = mesurer_d0()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(texte)
    if args.rapport:
        args.rapport.parent.mkdir(parents=True, exist_ok=True)
        args.rapport.write_text(texte, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
