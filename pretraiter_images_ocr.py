"""
Applique le pretraitement OpenCV sur les images raster existantes
(dossier _ocr_pages) et sauvegarde les resultats dans _images_pretaitees
pour inspection visuelle avant de relancer le traitement complet.

Usage :
    python pretraiter_images_ocr.py "chemin/vers/le/pdf.pd"
"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        # Cherche automatiquement un dossier _ocr_pages dans le dossier courant
        candidates = list(Path.cwd().rglob("*_ocr_pages"))
        if not candidates:
            print("Usage : python pretraiter_images_ocr.py <chemin_pdf>")
            print("  ou placez-vous dans un dossier contenant un sous-dossier _ocr_pages")
            sys.exit(1)
        ocr_dir = candidates[0]
        preprocess_dir = ocr_dir.parent / (ocr_dir.stem.replace("_ocr_pages", "") + "_images_pretaitees")
    else:
        pdf_path = Path(sys.argv[1])
        ocr_dir = pdf_path.parent / (pdf_path.stem + "_ocr_pages")
        preprocess_dir = pdf_path.parent / (pdf_path.stem + "_images_pretaitees")

    if not ocr_dir.exists():
        print(f"Dossier introuvable : {ocr_dir}")
        sys.exit(1)

    images = sorted(ocr_dir.glob("page_*.png"))
    if not images:
        print(f"Aucune image page_*.png dans {ocr_dir}")
        sys.exit(1)

    try:
        import cv2
        import numpy as np
    except ImportError:
        print("OpenCV non disponible. Installez-le : pip install opencv-python")
        sys.exit(1)

    preprocess_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  {len(images)} image(s) à prétraiter")
    print(f"  Source      : {ocr_dir.name}")
    print(f"  Destination : {preprocess_dir.name}\n")

    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"  ! Impossible de lire {img_path.name}")
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # CLAHE : normalise le contraste local
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Filtre bilatéral : lisse le bruit sans détruire les bords
        denoised = cv2.bilateralFilter(enhanced, d=7, sigmaColor=50, sigmaSpace=50)

        # Accentuation (unsharp masking)
        blur_g = cv2.GaussianBlur(denoised, (0, 0), sigmaX=3)
        sharpened = cv2.addWeighted(denoised, 1.5, blur_g, -0.5, 0)

        # Binarisation Otsu
        _, binarized = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Fermeture morphologique
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(binarized, cv2.MORPH_CLOSE, kernel)

        out_path = preprocess_dir / img_path.name
        cv2.imwrite(str(out_path), cleaned)
        print(f"  ✓ {img_path.name}  →  {out_path.name}")

    print("\n  Prétraitement terminé. Ouvrez le dossier pour comparer :")
    print(f"  {preprocess_dir}\n")


if __name__ == "__main__":
    main()
