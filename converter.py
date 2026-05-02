"""
Moteur de conversion TriosSeconverter.

Orchestre le pipeline complet (extraction images → OCR → Excel → Word)
avec des callbacks de progression pour l'interface graphique.

Correction path : utilise directement ImageExtractor + ImageStorage
avec base_path explicite (plus de dépendance au CWD).
"""

import re
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from recuperer_image import ImageExtractor, ImageStorage
from generer_classeur import generer_excel, generer_word
from ocr_processor import BornierTableExtractor
from config import Config
from template import TableTemplate, DEFAULT_TEMPLATE


class Converter:
    """
    Pipeline complet avec callbacks de progression.

    Args:
        word_file:    Chemin vers le fichier Word source (.docx)
        output_dir:   Dossier de destination (Excel + Word créés ici)
        template:     Modèle de tableau à utiliser (None = défaut bornier)
        on_progress:  Callback(pct: float, message: str) — pct dans [0, 1]
        on_log:       Callback(message: str)
    """

    def __init__(
        self,
        word_file: Path,
        output_dir: Path,
        template: Optional[TableTemplate] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.word_file  = Path(word_file)
        self.output_dir = Path(output_dir)
        self.template   = template or DEFAULT_TEMPLATE
        self._on_progress = on_progress or (lambda p, m: None)
        self._on_log      = on_log      or (lambda m: None)

    # ── Helpers ───────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logging.info(msg)
        self._on_log(msg)

    def _progress(self, pct: float, msg: str) -> None:
        self._on_progress(pct, msg)

    # ── Pipeline ──────────────────────────────────────────────────────

    def run(self) -> Dict:
        """
        Exécute le pipeline en 4 étapes.

        Returns:
            dict : images, tableaux, total, excel (Path), word (Path)

        Raises:
            RuntimeError si une étape critique échoue.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ── Étape 1 : extraction des images ──────────────────────────
        # On utilise ImageExtractor + ImageStorage directement avec
        # base_path explicite — élimine toute ambiguïté sur le CWD.
        self._log("Étape 1 — Extraction des images depuis le fichier Word…")
        self._progress(0.02, "Extraction des images…")

        try:
            img_extractor = ImageExtractor(str(self.word_file))
            storage = ImageStorage('images_borniers')
            images_dir = storage.create_output_folder(
                base_path=str(self.output_dir)
            )
            raw_images = img_extractor.extract_images()
            saved, total_images = 0, len(raw_images)
            for idx, (data, ext) in enumerate(raw_images, 1):
                try:
                    storage.save_image(data, idx, ext)
                    saved += 1
                except Exception as e:
                    self._log(f"  ⚠ Image {idx} ignorée : {e}")
        except Exception as exc:
            raise RuntimeError(f"Extraction des images échouée : {exc}") from exc

        self._log(f"  → {saved} / {total_images} images extraites dans :")
        self._log(f"     {images_dir}")

        if saved == 0:
            raise RuntimeError(
                "Aucune image extraite — vérifiez que le fichier Word "
                "contient des images."
            )

        self._progress(0.25, f"{saved} images extraites.")

        # ── Étape 2 : OCR ────────────────────────────────────────────
        self._log(
            f"Étape 2 — OCR ({self.template.name}) sur chaque image…"
        )
        self._progress(0.28, "OCR en cours…")

        try:
            ocr_results, extractor = self._extraire_avec_progres(
                images_dir, saved
            )
        except Exception as exc:
            raise RuntimeError(f"OCR échoué : {exc}") from exc

        if not ocr_results:
            raise RuntimeError("Aucun résultat OCR — impossible de continuer.")

        ok = sum(1 for r in ocr_results if r.get('success'))
        self._log(f"  → {ok} / {len(ocr_results)} tableaux extraits.")
        self._progress(0.65, f"OCR terminé : {ok}/{len(ocr_results)} tableaux.")

        # ── Étape 3 : classeur Excel ──────────────────────────────────
        self._log("Étape 3 — Génération du classeur Excel…")
        self._progress(0.68, "Génération Excel…")

        excel_path = self.output_dir / 'tous_les_borniers.xlsx'
        try:
            generer_excel(ocr_results, extractor, excel_path)
            self._log(f"  → {excel_path.name} enregistré dans :")
            self._log(f"     {excel_path.parent}")
        except Exception as exc:
            self._log(f"  ⚠ Avertissement Excel : {exc}")

        self._progress(0.84, "Excel généré.")

        # ── Étape 4 : document Word ───────────────────────────────────
        self._log("Étape 4 — Génération du document Word…")
        self._progress(0.87, "Génération Word…")

        word_path = self.output_dir / 'tous_les_borniers.docx'
        try:
            generer_word(ocr_results, extractor, word_path)
            self._log(f"  → {word_path.name} enregistré dans :")
            self._log(f"     {word_path.parent}")
        except Exception as exc:
            self._log(f"  ⚠ Avertissement Word : {exc}")

        self._progress(1.0, "Conversion terminée !")
        self._log("Conversion terminée avec succès.")

        return {
            'images':   saved,
            'tableaux': ok,
            'total':    len(ocr_results),
            'excel':    excel_path,
            'word':     word_path,
        }

    # ── OCR avec progression ──────────────────────────────────────────

    def _extraire_avec_progres(
        self, images_dir: Path, total_hint: int
    ) -> Tuple[List[Dict], BornierTableExtractor]:
        """Lance l'OCR image par image en signalant la progression."""

        extensions = ['.jpg', '.jpeg', '.png', '.bmp']

        def _num(p: Path) -> int:
            nums = re.findall(r'\d+', p.stem)
            return int(nums[0]) if nums else 0

        images = sorted(
            [f for f in images_dir.iterdir()
             if f.is_file() and f.suffix.lower() in extensions],
            key=_num,
        )

        if not images:
            return [], None

        total = len(images)
        extractor = BornierTableExtractor(
            tesseract_path=Config.TESSERACT_PATH,
            language=Config.OCR_LANGUAGE,
            template=self.template,
        )

        results = []
        for i, img in enumerate(images):
            pct = 0.28 + (i / total) * 0.37   # 28 % → 65 %
            self._progress(pct, f"OCR {i + 1}/{total} : {img.name}")
            self._log(f"  OCR {i + 1}/{total} : {img.name}")
            result = extractor.extract(img)
            results.append(result)

        return results, extractor
