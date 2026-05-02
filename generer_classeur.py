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
from docx import Document

from ocr_processor import BornierTableExtractor
from config import Config


# ──────────────────────────────────────────────────────────────────────
# Barre de progression
# ──────────────────────────────────────────────────────────────────────

def barre(current: int, total: int, label: str = '', largeur: int = 40) -> None:
    """Affiche / met à jour une barre de progression en ligne."""
    pct = current / total if total > 0 else 0
    rempli = int(largeur * pct)
    b = '█' * rempli + '░' * (largeur - rempli)
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
    for i, img in enumerate(images):
        barre(i, total, img.name)
        result = extractor.extract(img)
        results.append(result)

    barre(total, total, 'Extraction terminée')

    ok = sum(1 for r in results if r.get('success'))
    print(f"\n  ✓ {ok} tableaux extraits avec succès / {total} images\n")
    return results, extractor


# ──────────────────────────────────────────────────────────────────────
# Génération du classeur Excel combiné
# ──────────────────────────────────────────────────────────────────────

def generer_excel(
    results: List[Dict],
    extractor: 'BornierTableExtractor',
    output_path: Path
) -> None:
    """
    Tous les tableaux sur UNE SEULE feuille Excel, empilés verticalement.
    Un séparateur de 2 lignes vides entre chaque tableau.
    """
    succes = [r for r in results if r.get('success')]
    total = len(succes)

    if total == 0:
        print("  Aucun résultat à exporter en Excel.")
        return

    print(f"  Génération Excel ({total} tableaux sur une feuille)…\n")

    wb = Workbook()
    ws = wb.active
    ws.title = "Borniers"

    current_row = 1   # ligne de départ du premier tableau

    for i, result in enumerate(succes):
        meta = result.get('metadata', {})
        img_stem = Path(result.get('image_path', f'bornier_{i+1}')).stem
        label = (meta.get('BORNIER') or img_stem).strip()

        # _fill_worksheet retourne la 1re ligne libre après le pied
        next_row = extractor._fill_worksheet(ws, result,
                                             start_row=current_row)
        # 2 lignes vides de séparation entre les tableaux
        current_row = next_row + 2

        barre(i + 1, total, label)

    wb.save(str(output_path))
    print(f"\n  ✓ Classeur Excel enregistré : {output_path.name}\n")


# ──────────────────────────────────────────────────────────────────────
# Génération du document Word combiné
# ──────────────────────────────────────────────────────────────────────

def generer_word(
    results: List[Dict],
    extractor: 'BornierTableExtractor',
    output_path: Path
) -> None:
    """Tous les tableaux dans un seul document Word, séparés par sauts de page."""
    succes = [r for r in results if r.get('success')]
    total = len(succes)

    if total == 0:
        print("  Aucun résultat à exporter en Word.")
        return

    print(f"  Génération Word ({total} tableaux)…\n")

    doc = Document()
    premier = True

    for i, result in enumerate(succes):
        meta = result.get('metadata', {})
        img_stem = Path(result.get('image_path', '')).stem
        titre = (meta.get('BORNIER') or img_stem).strip()

        if not premier:
            doc.add_page_break()
        premier = False

        # Titre de section au-dessus du tableau
        doc.add_heading(f'Bornier : {titre}', level=2)
        extractor._add_table_to_doc(doc, result)

        barre(i + 1, total, titre)

    doc.save(str(output_path))
    print(f"\n  ✓ Document Word enregistré : {output_path.name}\n")


# ──────────────────────────────────────────────────────────────────────
# Point d'entrée
# ──────────────────────────────────────────────────────────────────────

def main():
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
