"""
Générateur de données d'entraînement Tesseract — TriosSeconverter
=================================================================

Ce script crée les paires image/transcription (.png + .gt.txt) nécessaires
pour affiner le modèle Tesseract OCR sur vos borniers électriques.

PRINCIPE
--------
Chaque ligne de tableau devient un exemple d'entraînement :
  - bornier_001_ligne_003.png  → image de la ligne, binarisée
  - bornier_001_ligne_003.gt.txt → texte exact issu de votre Excel corrigé

COMMENT UTILISER
----------------
1. Générez le classeur Excel avec le bouton « Lancer la conversion »
2. Ouvrez « tous_les_borniers.xlsx », corrigez les cellules jaunes (douteuses)
3. Enregistrez sous « tous_les_borniers_corrigé.xlsx »
4. Lancez ce script :
     python creer_donnees_entrainement.py
5. Les fichiers apparaissent dans le dossier « ground_truth/ »
6. Suivez les instructions affichées pour lancer le fine-tuning Tesseract

Usage :
    python creer_donnees_entrainement.py [--excel chemin.xlsx] [--images dossier]
                                         [--out dossier_sortie] [--min-conf 60]
"""

import argparse
import sys
import re
from pathlib import Path

import cv2
import numpy as np
import openpyxl

from config import Config
from ocr_processor import BornierTableExtractor


# ── Paramètres par défaut ─────────────────────────────────────────────────────

DEFAULT_EXCEL  = Path("tous_les_borniers_corrigé.xlsx")
DEFAULT_IMAGES = Config.get_output_folder()
DEFAULT_OUT    = Path("ground_truth")
DEFAULT_MIN_CONF = 0      # Exporter toutes les lignes (pas seulement les douteuses)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cle_num(path: Path) -> int:
    nums = re.findall(r'\d+', path.stem)
    return int(nums[0]) if nums else 0


def _preprocess_pour_gt(image_path: Path) -> np.ndarray:
    """Même pipeline de prétraitement que BornierTableExtractor._preprocess()."""
    ext = BornierTableExtractor.__new__(BornierTableExtractor)
    ext.language = Config.OCR_LANGUAGE
    binary, _ = ext._preprocess(image_path)
    return binary


def _lire_excel(excel_path: Path) -> dict[str, list[list[str]]]:
    """
    Lit le classeur Excel corrigé et retourne un dict :
      { numero_page_str : [ [cellule1, cellule2, ...], ... ] }

    Chaque entrée = liste des lignes de données d'un bornier.
    La clé est le numéro de PAGE extrait du pied de page.
    """
    wb = openpyxl.load_workbook(str(excel_path), read_only=True)
    pages: dict[str, list[list[str]]] = {}

    for ws in wb.worksheets:
        col_map: dict[int, str] = {}  # index 0-based → nom colonne
        lignes_data: list[list[str]] = []
        page_num = ''

        for row in ws.iter_rows(values_only=True):
            vals = [str(v or '').strip() for v in row]
            if not any(vals):
                continue

            vals_upper = [v.upper() for v in vals]

            # Ligne d'en-tête → construire col_map
            if ('BORNE' in vals_upper or 'TENANT' in vals_upper) and (
                'SIGNAL' in vals_upper
            ):
                col_map = {i: v.upper() for i, v in enumerate(vals) if v.strip()}
                lignes_data = []
                continue

            if not col_map:
                continue

            full = ' '.join(vals).upper()

            # Pied de page → récupérer PAGE
            m = re.search(r'PAGE\s*:?\s*(\d+)', full)
            if m:
                page_num = m.group(1)

            # Lignes structurelles à ignorer
            skip_kw = ('NOM DU CABLE', 'NO PLAN', 'P.E.T', 'M  T  I',
                       'INDICE', 'PAGE :', 'BORNIER :', 'P.E.T.')
            if any(kw in full for kw in skip_kw):
                continue

            # Ligne de données
            ligne = [vals[i] if i < len(vals) else '' for i in sorted(col_map.keys())]
            if any(ligne):
                lignes_data.append(ligne)

        if lignes_data and page_num:
            pages[page_num] = lignes_data
        elif lignes_data:
            # Pas de numéro de page → utiliser le nom de la feuille
            pages[ws.title] = lignes_data

    wb.close()
    return pages


def _groupe_lignes_image(binary: np.ndarray) -> list[tuple[int, int]]:
    """
    Détecte les bandes horizontales de texte dans l'image binarisée.
    Retourne une liste de (y_debut, y_fin) pour chaque ligne de texte.
    """
    h, w = binary.shape[:2]
    inverted = cv2.bitwise_not(binary)

    # Profil horizontal : somme des pixels noirs par rangée
    profile = inverted.sum(axis=1).astype(np.float32)
    threshold = profile.max() * 0.03  # ligne active si > 3 % du max

    # Identifier les bandes consécutives actives
    bands: list[tuple[int, int]] = []
    in_band = False
    y_start = 0
    for y in range(h):
        if profile[y] > threshold:
            if not in_band:
                y_start = y
                in_band = True
        else:
            if in_band:
                if y - y_start >= 4:  # ignorer les bandes < 4 px
                    bands.append((y_start, y))
                in_band = False
    if in_band:
        bands.append((y_start, h))

    # Fusionner les bandes trop proches (mots sur la même ligne)
    merged: list[tuple[int, int]] = []
    merge_gap = max(3, h // 60)
    for band in bands:
        if merged and band[0] - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], band[1])
        else:
            merged.append(list(band))

    return [tuple(b) for b in merged]


def _texte_ligne(ligne_cells: list[str], separator: str = ' | ') -> str:
    """Construit le texte ground-truth d'une ligne à partir de ses cellules."""
    return separator.join(c.strip() for c in ligne_cells if c.strip())


# ── Génération des fichiers ground-truth ──────────────────────────────────────

def generer_ground_truth(
    excel_path: Path,
    images_dir: Path,
    out_dir: Path,
    min_conf: int = 0,
) -> int:
    """
    Génère les paires .png / .gt.txt dans out_dir.
    Retourne le nombre de paires créées.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Lire le classeur corrigé ──────────────────────────────────────────
    print(f"\n  Lecture de {excel_path.name}…")
    try:
        pages = _lire_excel(excel_path)
    except Exception as e:
        print(f"  ✗ Impossible de lire {excel_path.name} : {e}")
        return 0

    if not pages:
        print("  ✗ Aucune donnée trouvée dans le classeur.")
        return 0
    print(f"  ✓ {len(pages)} bornier(s) chargé(s) depuis le classeur")

    # ── Indexer les images par numéro ────────────────────────────────────
    extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    images = {
        _cle_num(f): f
        for f in images_dir.iterdir()
        if f.is_file() and f.suffix.lower() in extensions
    }
    if not images:
        print(f"  ✗ Aucune image dans : {images_dir}")
        return 0
    print(f"  ✓ {len(images)} image(s) trouvée(s)\n")

    total = 0
    erreurs = 0

    for page_num, lignes_excel in pages.items():
        # Trouver l'image correspondant à ce numéro de page
        try:
            page_int = int(page_num)
        except ValueError:
            page_int = None

        img_path = images.get(page_int) if page_int is not None else None
        if img_path is None:
            print(f"  ⚠ Aucune image pour PAGE={page_num}")
            continue

        print(f"  Traitement bornier PAGE {page_num} ({img_path.name})…", end=' ')

        try:
            binary = _preprocess_pour_gt(img_path)
        except Exception as e:
            print(f"✗ prétraitement : {e}")
            erreurs += 1
            continue

        bands = _groupe_lignes_image(binary)

        # Associer les bandes détectées aux lignes Excel
        # On ignore les premières et dernières bandes (en-tête + pied de page)
        # On garde uniquement autant de bandes que de lignes de données
        data_bands = bands[1:-2] if len(bands) > 3 else bands
        n_match = min(len(data_bands), len(lignes_excel))

        n_created = 0
        for i in range(n_match):
            y0, y1 = data_bands[i]
            # Ajouter un léger padding vertical
            y0 = max(0, y0 - 2)
            y1 = min(binary.shape[0], y1 + 2)
            crop = binary[y0:y1, :]
            if crop.size == 0:
                continue

            texte = _texte_ligne(lignes_excel[i])
            if not texte:
                continue

            nom = f"p{page_num:>04s}_l{i+1:03d}"
            png_path = out_dir / f"{nom}.png"
            gt_path  = out_dir / f"{nom}.gt.txt"

            cv2.imwrite(str(png_path), crop)
            gt_path.write_text(texte, encoding='utf-8')
            n_created += 1

        total += n_created
        print(f"✓ {n_created} ligne(s)")

    if erreurs:
        print(f"\n  ⚠ {erreurs} image(s) en erreur.")

    return total


# ── Instructions pour le fine-tuning ─────────────────────────────────────────

def afficher_instructions(out_dir: Path, n_fichiers: int) -> None:
    print()
    print('=' * 64)
    print('  DONNÉES D\'ENTRAÎNEMENT PRÊTES')
    print('=' * 64)
    print(f'  {n_fichiers} paires image/texte créées dans : {out_dir}')
    print()
    print('  ÉTAPES SUIVANTES POUR FINE-TUNER TESSERACT')
    print('  ─────────────────────────────────────────')
    print()
    print('  1. Télécharger le modèle LSTM haute précision (une seule fois) :')
    print('       https://github.com/tesseract-ocr/tessdata_best/raw/main/fra.traineddata')
    print('     → Copier dans : C:\\Tesseract\\TesseractOCR\\tessdata\\')
    print('       (remplace fra.traineddata actuel — sauvegardez l\'original)')
    print()
    print('  2. Installer WSL2 (Ubuntu) depuis le Microsoft Store')
    print('     puis dans le terminal WSL2 :')
    print()
    print('       sudo apt install tesseract-ocr libtesseract-dev make')
    print('       git clone https://github.com/tesseract-ocr/tesstrain')
    print('       cd tesstrain && pip3 install -r requirements.txt')
    print()
    print('  3. Copier vos données ground-truth dans WSL2 :')
    gt_wsl = str(out_dir).replace('\\', '/').replace('C:', '/mnt/c')
    print(f'       cp -r {gt_wsl} ~/tesstrain/data/fra_bornier-ground-truth/')
    print()
    print('  4. Lancer le fine-tuning (dans le dossier tesstrain) :')
    print()
    print('       make training \\')
    print('         MODEL_NAME=fra_bornier \\')
    print('         START_MODEL=fra \\')
    print('         GROUND_TRUTH_DIR=data/fra_bornier-ground-truth \\')
    print('         MAX_ITERATIONS=400 \\')
    print('         LEARNING_RATE=0.001')
    print()
    print('  5. Récupérer le modèle entraîné :')
    print('       data/fra_bornier/fra_bornier.traineddata')
    print('     → Copier dans : C:\\Tesseract\\TesseractOCR\\tessdata\\')
    print()
    print('  6. Dans config.py, changer :')
    print('       OCR_LANGUAGE = "fra_bornier"')
    print()
    print('  💡 Conseil : commencez avec 30 à 50 paires bien corrigées.')
    print('     Chaque cycle d\'entraînement prend 5 à 20 minutes sur CPU.')
    print('     Après le premier modèle, corrigez les nouvelles cellules jaunes')
    print('     et relancez avec MAX_ITERATIONS=200 (fine-tuning incrémental).')
    print('=' * 64)
    print()


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description='Génère les données d\'entraînement Tesseract depuis un Excel corrigé.'
    )
    parser.add_argument('--excel',  default=str(DEFAULT_EXCEL),
                        help=f'Classeur Excel corrigé (défaut : {DEFAULT_EXCEL})')
    parser.add_argument('--images', default=str(DEFAULT_IMAGES),
                        help=f'Dossier des images (défaut : {DEFAULT_IMAGES})')
    parser.add_argument('--out',    default=str(DEFAULT_OUT),
                        help=f'Dossier de sortie ground-truth (défaut : {DEFAULT_OUT})')
    parser.add_argument('--min-conf', type=int, default=DEFAULT_MIN_CONF,
                        help='Confiance minimale des cellules à inclure (défaut : 0 = toutes)')
    args = parser.parse_args()

    excel_path  = Path(args.excel)
    images_dir  = Path(args.images)
    out_dir     = Path(args.out)

    print()
    print('=' * 64)
    print('  GÉNÉRATION DONNÉES ENTRAÎNEMENT TESSERACT — BORNIERS')
    print('=' * 64)

    if not excel_path.exists():
        print(f'\n  ✗ Fichier Excel introuvable : {excel_path}')
        print('  Créez « tous_les_borniers_corrigé.xlsx » en corrigeant')
        print('  les cellules jaunes de « tous_les_borniers.xlsx ».')
        sys.exit(1)

    if not images_dir.exists():
        print(f'\n  ✗ Dossier d\'images introuvable : {images_dir}')
        print('  Lancez d\'abord la conversion pour extraire les images.')
        sys.exit(1)

    n = generer_ground_truth(excel_path, images_dir, out_dir, args.min_conf)

    if n == 0:
        print('\n  Aucun fichier créé. Vérifiez votre Excel et les images.')
        sys.exit(1)

    afficher_instructions(out_dir, n)


if __name__ == '__main__':
    main()
