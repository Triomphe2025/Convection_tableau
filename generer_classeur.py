"""
Génère un classeur Excel UNIQUE et un document Word UNIQUE
contenant tous les tableaux de borniers extraits par OCR.

Affiche une barre de progression pendant le traitement.

Usage :
    py generer_classeur.py
"""

import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break
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
        if blur_pct > 60.0:
            blurry.append((img.name, blur_pct))
        method = result.get('detection_method', '?')
        label  = _METHOD_LABEL.get(method, method)
        print(f"    colonnes : {label}", end='')
        if blur_pct > 60:
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
# Génération du classeur Excel combiné
# ──────────────────────────────────────────────────────────────────────

def generer_excel(
    results: List[Dict],
    extractor: 'BornierTableExtractor',
    output_path: Path,
    word_results: List[Dict] = None
) -> None:
    """
    Génère le classeur Excel avec deux feuilles distinctes :
      - « Borniers »       : tableaux issus de l'OCR sur les images
      - « tableaux word »  : tableaux importés depuis un fichier Word
                             (créée uniquement si word_results est fourni)

    Chaque bornier occupe exactement Config.PAGE_SIZE lignes (simulation
    d'une page A4 à 48 lignes avec marges standard).  Un saut de page
    Excel est inséré après chaque bornier pour l'impression.

    Les borniers dont le nombre de lignes de données est inférieur à
    Config.MIN_DATA_ROWS sont ignorés (OCR raté).

    Le dictionnaire de données (data_dictionary.json) est chargé
    automatiquement et utilisé pour corriger les valeurs OCR douteuses.
    """
    page_size = Config.PAGE_SIZE
    min_rows = Config.MIN_DATA_ROWS
    station = Config.STATION_NAME
    dictionary = get_dictionary()

    # ── Filtrage des résultats invalides ─────────────────────────────
    valides = []
    ignores = 0
    for r in results:
        if not r.get('success'):
            continue
        if extractor._count_data_rows(r) >= min_rows:
            valides.append(r)
        else:
            ignores += 1

    # ── Tri par numéro de page croissant (footer PAGE) ────────────────
    def _page_sort_key(result: Dict) -> int:
        page = result.get('metadata', {}).get('PAGE', '')
        try:
            return int(page)
        except (ValueError, TypeError):
            nums = re.findall(r'\d+', Path(
                result.get('image_path', 'bornier_9999')
            ).stem)
            return int(nums[0]) if nums else 9999

    valides.sort(key=_page_sort_key)

    # Remplir PAGE manquante depuis le nom du fichier image quand l'OCR a raté
    for result in valides:
        meta = result.setdefault('metadata', {})
        page = str(meta.get('PAGE', '')).strip()
        if not page or not page.isdigit():
            nums = re.findall(r'\d+', Path(
                result.get('image_path', 'bornier_0')
            ).stem)
            meta['PAGE'] = nums[0] if nums else ''

    total = len(valides)

    if total == 0:
        print("  Aucun résultat valide à exporter en Excel.")
        return

    if ignores:
        print(f"  {ignores} bornier(s) ignoré(s) (OCR insuffisant).")
    print(f"  Génération Excel ({total} borniers, {page_size} lignes/page)…\n")

    wb = Workbook()
    ws = wb.active
    ws.title = "Borniers"

    # ── Mise en page A4 portrait ──────────────────────────────────────
    ws.page_setup.paperSize = 9          # 9 = A4
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.scale = 100
    ws.page_setup.fitToPage = False
    ws.page_margins = PageMargins(
        left=0.69, right=0.69,           # ~17.5 mm
        top=0.75,  bottom=0.75,          # ~19 mm
    )

    current_row = 1

    for i, result in enumerate(valides):
        meta = result.get('metadata', {})
        img_stem = Path(result.get('image_path', f'bornier_{i+1}')).stem
        # Nom du bornier : OCR ou nom du fichier image
        bornier_name = (meta.get('BORNIER') or img_stem).strip()

        next_row = extractor._fill_worksheet(
            ws, result,
            start_row=current_row,
            page_size=page_size,
            dictionary=dictionary,
            bornier_name=bornier_name,
            pet_name=station,
        )

        # Saut de page Excel après chaque bornier (sauf le dernier)
        if i < total - 1:
            ws.row_breaks.append(Break(id=next_row - 1))

        current_row = next_row
        barre(i + 1, total, bornier_name)

    # Zone d'impression = toute la feuille remplie
    n_cols = len(extractor._tpl.columns)
    ws.print_area = (
        f'A1:{get_column_letter(n_cols)}{current_row - 1}'
    )

    # ── Feuille « tableaux word » (si des tableaux Word sont fournis) ──
    if word_results:
        valides_w = [r for r in word_results if r.get('success')]
        valides_w.sort(key=_page_sort_key)

        if valides_w:
            ws2 = wb.create_sheet("tableaux word")
            ws2.page_setup.paperSize = 9
            ws2.page_setup.orientation = 'portrait'
            ws2.page_setup.scale = 100
            ws2.page_setup.fitToPage = False
            ws2.page_margins = PageMargins(
                left=0.69, right=0.69,
                top=0.75,  bottom=0.75,
            )

            cur2 = 1
            n_cols2 = len(extractor._tpl.columns)
            for j, result in enumerate(valides_w):
                meta = result.get('metadata', {})
                img_stem = Path(
                    result.get('image_path', f'word_{j+1}')
                ).stem
                bornier_name = (meta.get('BORNIER') or img_stem).strip()

                next_row2 = extractor._fill_worksheet(
                    ws2, result,
                    start_row=cur2,
                    page_size=page_size,
                    dictionary=dictionary,
                    bornier_name=bornier_name,
                    pet_name=station,
                )

                if j < len(valides_w) - 1:
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

    # ── Étape 3 : document Word ───────────────────────────────────────
    print('-' * 62)
    generer_word(results, extractor, out_dir / 'tous_les_borniers.docx')

    duree = time.time() - t0
    print('=' * 62)
    print(f'  TERMINÉ en {duree:.0f} s')
    print()
    print('  Fichiers créés :')
    print('    → tous_les_borniers.xlsx')
    print('    → tous_les_borniers.docx')
    print('=' * 62)
    print()


if __name__ == '__main__':
    main()
