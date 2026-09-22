"""
Moteur de conversion TriosSeconverter.

Orchestre le pipeline complet :
  - Mode Word  : extraction images → OCR → Excel
  - Mode PDF   : extraction couche texte PDF → Excel (plus rapide, sans Tesseract)

Utilise des callbacks de progression pour l'interface graphique.
"""

import re
import logging
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from recuperer_image import ImageExtractor, ImageStorage
from generer_classeur import generer_excel
from ocr_processor import BornierTableExtractor
from config import Config
from template import TableTemplate, DEFAULT_TEMPLATE


@contextmanager
def _mode_ocr_tesseract():
    """Force OCR_MODE='tesseract' le temps d'une lecture, puis le restaure.

    BornierTableExtractor.extract() et PdfTableExtractor délèguent à Claude
    quand OCR_MODE='claude' : sans ce verrou, la « seconde lecture
    indépendante » reprendrait le moteur à contrôler (et coûterait des appels API).
    """
    ancien = Config.OCR_MODE
    Config.OCR_MODE = 'tesseract'
    try:
        yield
    finally:
        Config.OCR_MODE = ancien


class Converter:
    """
    Pipeline complet avec callbacks de progression.

    Args:
        word_file:        Chemin vers le fichier source — .docx (Word avec images)
                          ou .pdf (PDF avec couche texte vectorielle).
        output_dir:       Dossier de destination (classeur Excel créé ici)
        template:         Modèle de tableau à utiliser (None = défaut bornier)
        tables_word_file: (Optionnel) Fichier Word contenant des tableaux déjà structurés
                          à fusionner dans la feuille « tableaux word » du classeur Excel.
        on_progress:      Callback(pct: float, message: str) — pct dans [0, 1]
        on_log:           Callback(message: str)
        on_validation:    (Optionnel) Callback(page_done, page_total,
                          result, image_path) → str|None
                          Appelé après chaque page extraite avec succès.
                          Retourne un commentaire (str) ou None si approuvée.
                          Le commentaire est stocké dans result['user_comment'].
        on_column_mapping: (Optionnel) Callback(candidate_blocks,
                          template_columns, image_path)
                          -> Optional[Dict[str, List[int]]]
                          Appelé quand le template dépasse
                          Config.MAX_AUTO_COLUMNS colonnes, pour demander un
                          classement manuel bloc→colonne. None = comportement
                          automatique standard (aucune interaction).
        on_wide_template_confirm: (Optionnel) Callback(template_columns,
                          ocr_mode) -> bool
                          Appelé quand le template dépasse
                          Config.MAX_AUTO_COLUMNS colonnes ET que le moteur
                          OCR actif n'est pas 'tesseract' (donc sans mapping
                          bloc→colonne possible). Retourne False pour annuler
                          la conversion. None = pas de confirmation, seul un
                          avertissement est loggé.
        cancel_event:     (Optionnel) threading.Event — settée par
                          l'utilisateur pour arrêter la conversion en cours.
                          Vérifiée entre chaque image/page ; les résultats
                          déjà extraits sont conservés (arrêt coopératif,
                          jamais de kill de thread).
    """

    def __init__(
        self,
        word_file: Path,
        output_dir: Path,
        template: Optional[TableTemplate] = None,
        tables_word_file: Optional[Path] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_validation: Optional[Callable] = None,
        on_column_mapping: Optional[Callable] = None,
        on_wide_template_confirm: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None,
    ):
        self.word_file = Path(word_file)
        self.output_dir = Path(output_dir)
        self.template = template or DEFAULT_TEMPLATE
        self.tables_word_file = Path(tables_word_file) if tables_word_file else None
        self._on_progress = on_progress or (lambda p, m: None)
        self._on_log = on_log or (lambda m: None)
        self._on_validation = on_validation  # None = pas de validation interactive
        self._on_column_mapping = on_column_mapping  # None = mapping auto standard
        self._on_wide_template_confirm = on_wide_template_confirm  # None = pas de confirmation
        self._cancel_event = cancel_event  # None = pas d'annulation possible
        self._derniers_resultats: Optional[List[Dict]] = None  # lus par verifier_conversion

    # ── Apprentissage depuis les résultats validés ─────────────────────

    def _apprendre_corrections(self, result: dict) -> None:
        """Enrichit le dictionnaire OCR avec les valeurs validées par l'utilisateur."""
        try:
            from data_dictionary import get_dictionary
            dico = get_dictionary()
            headers = result.get('headers', [])
            added = 0
            for row in result.get('rows', []):
                if row.get('type') != 'data':
                    continue
                for col_name, val in zip(headers, row.get('cells', [])):
                    if dico.add_value(col_name, val):
                        added += 1
            if added > 0:
                dico.save()
                self._log(f"  ✓ Dictionnaire enrichi : {added} valeur(s) mémorisée(s).")
        except Exception as e:
            self._log(f"  ⚠ Apprentissage dictionnaire : {e}")

    # ── Helpers ───────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logging.info(msg)
        self._on_log(msg)

    def _progress(self, pct: float, msg: str) -> None:
        self._on_progress(pct, msg)

    def _est_annule(self) -> bool:
        """Vrai si l'utilisateur a demandé l'arrêt de la conversion."""
        return self._cancel_event is not None and self._cancel_event.is_set()

    def _verifier_template_large(self) -> None:
        """Avertit (et si moteur vision, demande confirmation) si le template
        dépasse Config.MAX_AUTO_COLUMNS colonnes — évite le silence total en
        mode Claude Vision où le mapping bloc→colonne par image n'existe pas.
        """
        n = len(self.template.columns)
        seuil = Config.MAX_AUTO_COLUMNS
        if n <= seuil:
            return
        ocr_mode = getattr(Config, 'OCR_MODE', 'tesseract').lower()
        self._log(
            f"⚠ Modèle « {self.template.name} » à {n} colonnes"
            f" (> {seuil} recommandées) — classification automatique"
            f" moins fiable avec le moteur {ocr_mode}."
        )
        # Mode tesseract : le mapping bloc→colonne par image (on_column_mapping)
        # couvre déjà ce cas — cette confirmation ne concerne que les moteurs
        # vision, qui n'ont pas de notion de blocs pixel à faire classer.
        if ocr_mode == 'tesseract' or self._on_wide_template_confirm is None:
            return
        ok = self._on_wide_template_confirm(list(self.template.columns), ocr_mode)
        if not ok:
            raise RuntimeError(
                "Conversion annulée — modèle trop large pour ce moteur."
            )

    # ── Pipeline ──────────────────────────────────────────────────────

    def run(self) -> Dict:
        """
        Exécute le pipeline de conversion.

        Mode Word (.docx)              : extraction images → OCR → Excel
        Mode PDF  — tesseract/docling  : extraction couche texte PDF → Excel
        Mode PDF  — claude/ollama/hybrid : rastérisation page par page → OCR vision

        Returns:
            dict : tableaux, total, excel (Path)

        Raises:
            RuntimeError si une étape critique échoue.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._verifier_template_large()

        source_ext = self.word_file.suffix.lower()

        if source_ext == '.pdf':
            _ocr_mode = getattr(Config, 'OCR_MODE', 'tesseract').lower()
            if _ocr_mode in ('claude', 'ollama', 'hybrid', 'agent'):
                # Modes vision : rastériser le PDF page par page et envoyer
                # les images au moteur OCR (contourne la couche texte PDF
                # qui peut être imprécise sur les documents industriels).
                ocr_results, extractor = self._extraire_pdf_comme_images()
            else:
                ocr_results, extractor = self._extraire_depuis_pdf()
            saved = 0
        elif source_ext == '.jsonl':
            ocr_results, extractor = self._extraire_depuis_log()
            saved = 0
        elif self.word_file.is_dir():
            ocr_results, extractor = self._extraire_depuis_images()
            saved = 0
        else:
            saved, ocr_results, extractor = self._extraire_depuis_word()

        ok = sum(1 for r in ocr_results if r.get('success'))
        self._derniers_resultats = ocr_results

        if self._est_annule():
            self._log(
                f"  ⏹ Conversion arrêtée par l'utilisateur —"
                f" {ok}/{len(ocr_results)} tableau(x) extrait(s) avant l'arrêt."
            )
        self._log(f"  → {ok} / {len(ocr_results)} tableaux extraits.")
        self._progress(0.65, f"Extraction terminée : {ok}/{len(ocr_results)} tableaux.")

        # ── Import tableaux Word structurés (optionnel) ───────────────
        # Les tableaux Word sont gardés SÉPARÉS des résultats OCR afin
        # de ne pas perturber la mise en forme du pied de page de la
        # feuille « Borniers ». Ils seront placés dans une feuille dédiée
        # « tableaux word » dans le classeur Excel.
        word_results: List[Dict] = []

        if self.tables_word_file and self.tables_word_file.exists():
            self._log(
                f"Étape 2b — Import tableaux Word : {self.tables_word_file.name}…"
            )
            self._progress(0.66, "Import tableaux Word…")

            suffix = self.tables_word_file.suffix.lower()
            if suffix != '.docx':
                self._log(
                    f"  ✗ Format non supporté ({suffix}) — "
                    f"utilisez un fichier .docx (pas .doc)."
                )
            else:
                try:
                    from word_table_importer import WordTableImporter
                    importer = WordTableImporter(extractor)
                    word_results = importer.extract_tables(self.tables_word_file)

                    if not word_results:
                        self._log(
                            "  ⚠ Aucun tableau valide trouvé dans le fichier Word."
                            " Vérifiez que le document contient des tableaux avec"
                            " au moins une ligne de données."
                        )
                    else:
                        self._log(
                            f"  → {len(word_results)} tableau(x) trouvé(s) :"
                        )
                        for r in word_results:
                            meta = r.get('metadata', {})
                            bornier = meta.get('BORNIER', '—')
                            page = meta.get('PAGE', '—')
                            n_data = sum(
                                1 for row in r.get('rows', [])
                                if row.get('type') == 'data'
                            )
                            self._log(
                                f"     Bornier={bornier}  "
                                f"Page={page}  "
                                f"Lignes={n_data}"
                            )
                        self._log(
                            f"  ✓ {len(word_results)} tableau(x) Word → "
                            f"feuille 'tableaux word' (séparée des borniers OCR)."
                        )

                except Exception as exc:
                    self._log(
                        f"  ✗ Erreur import tableaux Word : {exc}"
                    )
                    import traceback
                    self._log(traceback.format_exc())

        elif self.tables_word_file:
            self._log(
                f"  ✗ Fichier Word tableaux introuvable : {self.tables_word_file}"
            )

        # ── Génération du classeur Excel ──────────────────────────────
        self._log("Génération du classeur Excel…")
        self._progress(0.68, "Génération Excel…")

        source_stem = self.word_file.stem if self.word_file.is_file() else self.word_file.name
        excel_path = self.output_dir / f"{source_stem}.xlsx"
        try:
            generer_excel(
                ocr_results, extractor, excel_path,
                word_results=word_results if word_results else None,
            )
            self._log(f"  → {excel_path.name} enregistré dans :")
            self._log(f"     {excel_path.parent}")
        except Exception as exc:
            self._log(f"  ⚠ Avertissement Excel : {exc}")

        self._progress(1.0, "Conversion terminée !")
        self._log("Conversion terminée avec succès.")

        # Chemins des journaux selon le mode OCR
        mode = getattr(Config, 'OCR_MODE', 'tesseract').lower()
        source_stem_r = (
            self.word_file.stem if self.word_file.is_file() else self.word_file.name
        )
        log_path_out = None
        log_ollama_path_out = None

        if mode in ('claude', 'hybrid'):
            c = self.output_dir / f"{source_stem_r}_claude.jsonl"
            if c.exists():
                log_path_out = c

        if mode in ('ollama', 'hybrid'):
            # Retourner le chemin attendu même si le fichier est vide ou absent :
            # l'en-tête de session est écrit dès _activer_log_claude(), donc le
            # fichier devrait toujours exister. S'il est absent, l'interface
            # affichera un message d'avertissement.
            log_ollama_path_out = (
                self.output_dir / f"{source_stem_r}_ollama.jsonl"
            )

        return {
            'tableaux':    ok,
            'total':       len(ocr_results) + len(word_results),
            'excel':       excel_path,
            'log':         log_path_out,
            'log_ollama':  log_ollama_path_out,
        }

    # ── Extraction PDF → images → OCR vision ─────────────────────────

    def _extraire_pdf_comme_images(self) -> Tuple[List[Dict], object]:
        """
        Rastérise chaque page du PDF en image PNG et les traite via le moteur
        OCR vision configuré (claude / ollama / hybrid).

        Utilisé à la place de _extraire_depuis_pdf() quand la couche texte
        du PDF est absente ou de mauvaise qualité.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF (fitz) n'est pas installé.\n"
                "Installez-le avec : pip install pymupdf"
            )

        ocr_mode = getattr(Config, 'OCR_MODE', 'tesseract').lower()
        self._log(
            f"Étape 1 — Rastérisation du PDF "
            f"({ocr_mode}) : {self.word_file.name}…"
        )
        self._progress(0.03, "Rastérisation du PDF en images…")

        images_dir = self.output_dir / "images_pdf"
        images_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(self.word_file))
        total_pages = len(doc)
        saved = 0

        for i, page in enumerate(doc, 1):
            if self._est_annule():
                self._log(f"  ⏹ Rastérisation arrêtée — {i}/{total_pages} pages traitées.")
                break
            try:
                # Matrix(3, 3) ≈ 216 DPI — bon compromis qualité / taille
                pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
                img_path = images_dir / f"page_{i:03d}.png"
                pix.save(str(img_path))
                saved += 1
            except Exception as e:
                self._log(f"  ⚠ Rastérisation page {i} ignorée : {e}")
            pct = 0.03 + (i / total_pages) * 0.22   # 3 % → 25 %
            self._progress(pct, f"Rastérisation {i}/{total_pages}…")

        doc.close()
        self._log(
            f"  → {saved} / {total_pages} pages rastérisées : {images_dir}"
        )
        self._progress(0.25, f"{saved} pages rastérisées.")
        self._log(
            f"Étape 2 — OCR ({self.template.name}) sur chaque page…"
        )
        self._progress(0.28, "OCR en cours…")
        self._activer_log_claude()

        try:
            results, extractor = self._extraire_avec_progres(images_dir, saved)
        except Exception as exc:
            raise RuntimeError(f"OCR échoué : {exc}") from exc

        return results, extractor

    # ── Extraction depuis PDF (couche texte vectorielle) ──────────────

    def _extraire_depuis_pdf(self) -> Tuple[List[Dict], object]:
        """Extrait les tableaux depuis la couche texte vectorielle du PDF."""
        from pdf_extractor import PdfTableExtractor, is_pymupdf_available

        if not is_pymupdf_available():
            raise RuntimeError(
                "PyMuPDF (fitz) n'est pas installé.\n"
                "Installez-le avec : pip install pymupdf"
            )

        self._log("Étape 1 — Extraction des tableaux depuis le PDF…")
        self._progress(0.05, "Lecture du PDF…")

        pdf_ext = PdfTableExtractor(template=self.template)
        self._activer_log_claude()

        # Extracteur de re-tentatives sur image (pages PDF avec OCR de repli).
        # On choisit le même moteur que la conversion principale pour que le
        # feedback atteigne l'API choisie par l'utilisateur.
        _ocr_mode_pdf = getattr(Config, 'OCR_MODE', 'tesseract').lower()
        if _ocr_mode_pdf == 'claude':
            from claude_ocr import ClaudeVisionExtractor
            _retry_extractor = ClaudeVisionExtractor(self.template)
        elif _ocr_mode_pdf == 'docling':
            from docling_ocr import DoclingExtractor
            _retry_extractor = DoclingExtractor(self.template)
        elif _ocr_mode_pdf == 'ollama':
            from ollama_ocr import OllamaVisionExtractor
            _retry_extractor = OllamaVisionExtractor(self.template)
        elif _ocr_mode_pdf == 'hybrid':
            from hybrid_ocr import HybridVisionExtractor
            _retry_extractor = HybridVisionExtractor(self.template)
        elif _ocr_mode_pdf == 'agent':
            from agent_ocr import AgentVisionExtractor
            _retry_extractor = AgentVisionExtractor(self.template)
        else:
            _retry_extractor = BornierTableExtractor(
                tesseract_path=Config.TESSERACT_PATH,
                language=Config.OCR_LANGUAGE,
                template=self.template,
            )
        _retry_label = {
            'claude':  'Claude Vision',
            'docling': 'Docling',
            'ollama':  'Ollama Vision',
            'hybrid':  'Hybride (Ollama+Claude)',
        }.get(_ocr_mode_pdf, 'Tesseract')

        def _page_callback(done: int, total: int, result: dict) -> None:
            pct = 0.05 + (done / total) * 0.55   # 5 % → 60 %
            rows = sum(1 for r in result.get('rows', []) if r.get('type') == 'data')
            ok_flag = f"{rows} lignes" if result.get('success') else "vide"
            method = result.get('detection_method', '')
            engine = "Claude" if 'claude' in method else (
                "OCR" if 'ocr' in method else "PDF")
            self._progress(pct, f"Page {done}/{total} [{engine}] — {ok_flag}")
            if done % 10 == 0 or not result.get('success'):
                self._log(f"  Page {done}/{total} [{engine}] : {ok_flag}")

            # Mode validation interactive — boucle de re-traitement
            if self._on_validation is not None and result.get('success'):
                image_path_str = result.get('image_path', '')

                # Pour les pages PDF couche-texte, aucune image n'est sauvegardée.
                # Si le chemin stocké n'existe pas, on rend la page depuis le PDF
                # via PyMuPDF afin de pouvoir l'envoyer à Claude Vision.
                if image_path_str and not Path(image_path_str).exists():
                    image_path_str = ''
                if not image_path_str:
                    try:
                        import fitz  # PyMuPDF — déjà requis dans requirements.txt
                        doc = fitz.open(str(self.word_file))
                        page_idx = done - 1
                        if 0 <= page_idx < len(doc):
                            pix = doc[page_idx].get_pixmap(matrix=fitz.Matrix(2, 2))
                            tmp_img = self.output_dir / f"_retry_page_{done}.png"
                            pix.save(str(tmp_img))
                            image_path_str = str(tmp_img)
                            self._log(
                                f"  → Image PDF rendue pour retry : "
                                f"{tmp_img.name}"
                            )
                        doc.close()
                    except Exception as exc:
                        self._log(f"  ⚠ Rendu image PDF impossible : {exc}")
                attempt = 1
                while True:
                    result['_attempt'] = attempt
                    response = self._on_validation(done, total, result, image_path_str)
                    if (isinstance(response, tuple)
                            and len(response) == 2
                            and response[0] == 'retry'
                            and image_path_str):
                        feedback = response[1]
                        attempt += 1
                        self._log(
                            f"  ↺ Tentative #{attempt} [{_retry_label}] "
                            f"— feedback : « {feedback[:60]} »"
                        )
                        new_r = _retry_extractor.extract(
                            Path(image_path_str), feedback=feedback)
                        if new_r.get('success'):
                            result.update(new_r)
                            result.pop('_retry_error', None)
                        else:
                            err = new_r.get('error', 'erreur inconnue')
                            self._log(f"    ✗ Re-tentative échouée : {err}")
                            result['_retry_error'] = err
                        continue
                    else:
                        if response and not isinstance(response, tuple):
                            result['user_comment'] = response
                        self._apprendre_corrections(result)
                        break

        results, extractor = pdf_ext.extract_all(
            self.word_file, on_page_done=_page_callback, cancel_check=self._est_annule
        )

        ok = sum(1 for r in results if r.get('success'))
        total = len(results)
        self._log(f"  → {ok} / {total} pages avec tableaux reconnus.")
        self._progress(0.60, f"PDF lu : {ok}/{total} pages.")

        # Remonter l'erreur du premier échec dans le journal UI
        if ok == 0 and total > 0:
            first_err = next(
                (r.get('error') for r in results if r.get('error')), None
            )
            if first_err:
                self._log(f"  ✗ Erreur OCR : {first_err}")

        return results, extractor

    # ── Helpers communs ───────────────────────────────────────────────

    def _activer_log_claude(self) -> None:
        """Active les journaux JSONL selon le mode OCR."""
        import importlib

        mode = getattr(Config, 'OCR_MODE', 'tesseract').lower()
        source_stem = (
            self.word_file.stem if self.word_file.is_file() else self.word_file.name
        )

        # Journal Claude (modes claude et hybrid)
        try:
            import claude_ocr
            importlib.reload(claude_ocr)   # toujours la version disque
            if mode in ('claude', 'hybrid', 'agent'):
                log_path = self.output_dir / f"{source_stem}_claude.jsonl"
                claude_ocr.set_api_log_path(log_path)
                self._log(f"  Journal Claude : {log_path.name}")
                self._log(
                    "  (conservez ce fichier pour régénérer l'Excel sans appel API)"
                )
            else:
                claude_ocr.set_api_log_path(None)
        except Exception as e:
            self._log(f"  ⚠ Journal Claude non activé : {e}")

        # Journal Ollama (modes ollama et hybrid)
        try:
            import ollama_ocr
            importlib.reload(ollama_ocr)   # toujours la version disque
            if mode in ('ollama', 'hybrid'):
                log_path = self.output_dir / f"{source_stem}_ollama.jsonl"
                ollama_ocr.set_ollama_log_path(log_path)
                self._log(f"  Journal Ollama  : {log_path}")
                # En-tête de session : écrit immédiatement dans le fichier
                # pour que celui-ci existe dès le début de la conversion.
                ollama_ocr.write_ollama_session(
                    source_file=str(self.word_file),
                    output_dir=str(self.output_dir),
                    ocr_mode=mode,
                    template_columns=list(self.template.columns),
                )
            else:
                ollama_ocr.set_ollama_log_path(None)
        except Exception as e:
            if mode in ('ollama', 'hybrid'):
                self._log(f"  ⚠ Journal Ollama non activé : {e}")

    # ── Extraction depuis log JSONL (replay sans API) ─────────────────

    def _extraire_depuis_log(self) -> Tuple[List[Dict], object]:
        """Rejoue un journal claude_api_log.jsonl sans appeler l'API."""
        from claude_ocr import LogReplayer

        self._log(f"Étape 1 — Relecture du journal : {self.word_file.name}…")
        self._progress(0.05, "Lecture du journal…")

        replayer = LogReplayer(self.word_file, self.template)
        results = replayer.replay_all()

        ok = sum(1 for r in results if r.get('success'))
        total = len(results)
        self._log(f"  → {ok} / {total} pages relues depuis le journal.")
        self._progress(0.65, f"Journal relu : {ok}/{total} pages.")

        extractor = BornierTableExtractor(
            tesseract_path=Config.TESSERACT_PATH,
            language=Config.OCR_LANGUAGE,
            template=self.template,
        )
        return results, extractor

    # ── Extraction depuis dossier d'images ────────────────────────────

    def _extraire_depuis_images(self) -> Tuple[List[Dict], object]:
        """Traite directement un dossier d'images (sans Word ni PDF)."""
        images_dir = self.word_file   # ici word_file pointe vers un dossier

        self._log(f"Étape 1 — Dossier d'images : {images_dir.name}…")
        self._progress(0.25, "Traitement des images…")

        self._activer_log_claude()

        try:
            results, extractor = self._extraire_avec_progres(images_dir, 0)
        except Exception as exc:
            raise RuntimeError(f"OCR échoué : {exc}") from exc

        if not results:
            raise RuntimeError(
                "Aucune image trouvée dans le dossier.\n"
                "Vérifiez que le dossier contient des fichiers .jpg, .png ou .bmp."
            )
        return results, extractor

    # ── Extraction depuis Word (images + OCR) ─────────────────────────

    def _extraire_depuis_word(self) -> Tuple[int, List[Dict], BornierTableExtractor]:
        """Extrait les images du Word et les traite par OCR."""
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
        self._log(f"Étape 2 — OCR ({self.template.name}) sur chaque image…")
        self._progress(0.28, "OCR en cours…")
        self._activer_log_claude()

        try:
            ocr_results, extractor = self._extraire_avec_progres(images_dir, saved)
        except Exception as exc:
            raise RuntimeError(f"OCR échoué : {exc}") from exc

        if not ocr_results:
            raise RuntimeError("Aucun résultat OCR — impossible de continuer.")

        return saved, ocr_results, extractor

    # ── OCR avec progression ──────────────────────────────────────────

    def _extraire_avec_progres(
        self, images_dir: Path, total_hint: int
    ) -> Tuple[List[Dict], BornierTableExtractor]:
        """Lance l'OCR image par image en signalant la progression.

        Routage selon Config.OCR_MODE :
          "tesseract" — BornierTableExtractor (corrections + re-OCR colonne activés)
          "claude"    — ClaudeVisionExtractor (positionnement pipe, pas de correction)
          "docling"   — DoclingExtractor (IA locale IBM, pas de correction)
        """

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
        ocr_mode = getattr(Config, 'OCR_MODE', 'tesseract').lower()

        # BornierTableExtractor est toujours créé : generer_excel en a besoin
        # pour les informations de template (colonnes, pied de page, etc.).
        extractor = BornierTableExtractor(
            tesseract_path=Config.TESSERACT_PATH,
            language=Config.OCR_LANGUAGE,
            template=self.template,
            on_column_mapping=self._on_column_mapping,
        )

        # Préparer le moteur alternatif si nécessaire
        # on_column_mapping est transmis à TOUS les moteurs : Tesseract s'en
        # sert pour les blocs pixel de l'en-tête, les moteurs vision s'en
        # servent quand leur réponse contient plus de segments pipe que de
        # colonnes template (Claude/Ollama/Agent partagent _parse_pipe_response
        # ; Docling a sa propre détection de structure, hors périmètre ici).
        if ocr_mode == 'claude':
            from claude_ocr import ClaudeVisionExtractor
            vision_extractor = ClaudeVisionExtractor(
                self.template, on_column_mapping=self._on_column_mapping
            )
            self._log(
                f"  Moteur OCR : Claude Vision "
                f"({getattr(Config, 'CLAUDE_OCR_MODEL', '?')}) — "
                "insertion positionnelle, sans correction post-API"
            )
        elif ocr_mode == 'docling':
            from docling_ocr import DoclingExtractor
            vision_extractor = DoclingExtractor(self.template)
            self._log("  Moteur OCR : Docling (IBM Research) — IA locale")
        elif ocr_mode == 'ollama':
            from ollama_ocr import OllamaVisionExtractor
            vision_extractor = OllamaVisionExtractor(
                self.template, on_column_mapping=self._on_column_mapping
            )
            self._log(
                f"  Moteur OCR : Ollama Vision local "
                f"({getattr(Config, 'OLLAMA_MODEL', 'qwen2.5vl:7b')}) — "
                "sans API externe, sans correction post-OCR"
            )
        elif ocr_mode == 'hybrid':
            from hybrid_ocr import HybridVisionExtractor
            vision_extractor = HybridVisionExtractor(
                self.template, on_column_mapping=self._on_column_mapping
            )
            self._log(
                f"  Moteur OCR : Hybride — structure Ollama "
                f"({getattr(Config, 'OLLAMA_MODEL', 'qwen2.5vl:7b')}) + "
                f"valeurs Claude ({getattr(Config, 'CLAUDE_OCR_MODEL', '?')})"
            )
        elif ocr_mode == 'agent':
            from agent_ocr import AgentVisionExtractor
            vision_extractor = AgentVisionExtractor(
                self.template, on_column_mapping=self._on_column_mapping
            )
            _sid = getattr(Config, 'CLAUDE_AGENT_SESSION_ID', '?')
            self._log(
                f"  Moteur OCR : Agent Image Data Extractor "
                f"(session …{_sid[-8:] if _sid else '?'})"
            )
        else:
            vision_extractor = None
            self._log(
                "  Moteur OCR : Tesseract "
                f"(re-OCR par colonne : {getattr(Config, 'OCR_PER_COLUMN', False)})"
            )

        _METHOD_LABEL = {
            'header':        '✓ en-tête reconnu',
            'tatr':          '✓ IA (TATR)',
            'morpho':        '⚠ lignes verticales',
            'weighted':      '⚠ repli pondéré',
            'claude-vision': '✓ Claude Vision',
            'docling':       '✓ Docling',
            'ollama-vision': '✓ Ollama Vision local',
            'hybrid':        '✓ Hybride Ollama+Claude',
            'agent-vision':  '✓ Agent Image Data Extractor',
        }

        results = []
        for i, img in enumerate(images):
            if self._est_annule():
                self._log(f"  ⏹ Conversion arrêtée — {i}/{total} images traitées.")
                break
            pct = 0.28 + (i / total) * 0.37   # 28 % → 65 %
            self._progress(pct, f"OCR {i + 1}/{total} : {img.name}")
            self._log(f"  OCR {i + 1}/{total} : {img.name}")

            if vision_extractor is not None:
                result = vision_extractor.extract(img)
            else:
                result = extractor.extract(img)

            method = result.get('detection_method', '')
            label = _METHOD_LABEL.get(method, method)
            blur = result.get('blur_pct', 0.0)
            blur_s = f"  flou {blur:.0f}%" if blur > 60 else ""
            self._log(f"    → {label}{blur_s}")

            # Mode validation interactive — boucle de re-traitement par feedback
            if self._on_validation is not None and result.get('success'):
                _eng_label = (
                    'Claude Vision' if vision_extractor is not None
                    else 'Tesseract'
                )
                attempt = 1
                while True:
                    result['_attempt'] = attempt
                    response = self._on_validation(i + 1, total, result, str(img))
                    if (isinstance(response, tuple)
                            and len(response) == 2
                            and response[0] == 'retry'):
                        feedback = response[1]
                        attempt += 1
                        self._log(
                            f"  ↺ Tentative #{attempt} [{_eng_label}] "
                            f"— feedback : « {feedback[:60]} »"
                        )
                        self._progress(pct, f"Tentative #{attempt} [{_eng_label}]…")
                        if vision_extractor is not None:
                            new_r = vision_extractor.extract(img, feedback=feedback)
                        else:
                            new_r = extractor.extract(img, feedback=feedback)
                        if new_r.get('success'):
                            result = new_r
                            result.pop('_retry_error', None)
                            lbl = _METHOD_LABEL.get(
                                result.get('detection_method', ''), '')
                            self._log(f"    → {lbl}")
                        else:
                            err = new_r.get('error', 'erreur inconnue')
                            self._log(f"    ✗ Re-tentative échouée : {err}")
                            # Mémoriser l'erreur dans result pour l'afficher
                            # dans le prochain dialog (l'utilisateur peut retenter)
                            result['_retry_error'] = err
                        # Dans tous les cas, reboucler pour présenter le résultat
                        # courant à l'utilisateur (il peut retenter ou accepter)
                        continue
                    else:
                        if response and not isinstance(response, tuple):
                            result['user_comment'] = response
                        self._apprendre_corrections(result)
                        break

            results.append(result)

        return results, extractor

    # ── Vérification de conversion ────────────────────────────────────

    def verifier_conversion(self, reference=None, converti=None):
        """Compare la lecture indépendante du scan à la conversion, cellule par cellule.

        reference : chemin (.pdf, .jsonl, .docx, dossier d'images) ou liste de
                    résultats ; None = document source (Doc. 1), relu par Tesseract.
        converti  : idem ; None = résultats de la dernière conversion en mémoire.
        """
        from data_dictionary import get_dictionary
        from verificateur import verifier

        if reference is None:
            reference = self.word_file
        if converti is None:
            if self._derniers_resultats is None:
                raise RuntimeError(
                    "Aucune conversion en mémoire : indiquez le document converti."
                )
            converti = self._derniers_resultats

        self._log("Vérification de la conversion — lecture indépendante du scan (Tesseract)…")
        ref = self._charger_pivots(reference)
        self._log("  Lecture du document converti…")
        conv = self._charger_pivots(converti)

        self._progress(0.95, "Comparaison des deux lectures…")
        dictionnaire = get_dictionary()
        rapport = verifier(
            ref, conv, colonnes=list(self.template.columns),
            valeurs_connues={c: dictionnaire.get_all(c) for c in self.template.columns},
            distance=BornierTableExtractor._levenshtein,
        )
        self._log(
            f"  → {len(rapport.a_verifier)} divergence(s) à vérifier — "
            f"concordance {rapport.concordance * 100:.1f} % "
            f"({len(rapport.pages_appariees)} page(s) appariée(s))"
        )
        if rapport.pages_ref_orphelines or rapport.pages_conv_orphelines:
            self._log(
                f"  ⚠ Pages sans partenaire — scan : {rapport.pages_ref_orphelines or 'aucune'}"
                f", converti : {rapport.pages_conv_orphelines or 'aucune'}"
            )
        self._progress(1.0, "Vérification terminée.")
        return rapport

    def _charger_pivots(self, source) -> List[Dict]:
        """Transforme une source (résultats, .pdf, .jsonl, .docx, dossier) en résultats pivot."""
        if isinstance(source, dict):
            return [source]
        if isinstance(source, (list, tuple)):
            return list(source)
        chemin = Path(source)
        if not chemin.exists():
            raise FileNotFoundError(f"Introuvable : {chemin}")
        suffixe = chemin.suffix.lower()
        with _mode_ocr_tesseract():
            if suffixe == '.pdf':
                from pdf_extractor import PdfTableExtractor
                resultats, _ = PdfTableExtractor(template=self.template).extract_all(
                    chemin, cancel_check=self._est_annule
                )
                return resultats
            if suffixe == '.jsonl':
                from claude_ocr import LogReplayer
                return LogReplayer(chemin, self.template).replay_all()
            if chemin.is_dir():
                return self._lire_images_tesseract(self._images_du_dossier(chemin))
            if suffixe == '.docx':
                with tempfile.TemporaryDirectory() as tmp:
                    for i, (donnees, ext) in enumerate(
                            ImageExtractor(str(chemin)).extract_images(), 1):
                        (Path(tmp) / f"bornier_{i}.{ext}").write_bytes(donnees)
                    return self._lire_images_tesseract(self._images_du_dossier(Path(tmp)))
        raise ValueError(
            f"Format non supporté pour la vérification : {chemin.name}\n"
            "Formats acceptés : .pdf, .jsonl, .docx, dossier d'images."
        )

    @staticmethod
    def _images_du_dossier(dossier: Path) -> List[Path]:
        def _num(p: Path) -> int:
            nums = re.findall(r'\d+', p.stem)
            return int(nums[0]) if nums else 0

        return sorted(
            (f for f in dossier.iterdir()
             if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp')),
            key=_num,
        )

    def _lire_images_tesseract(self, images: List[Path]) -> List[Dict]:
        """OCR Tesseract image par image, sans callbacks interactifs."""
        extracteur = BornierTableExtractor(
            tesseract_path=Config.TESSERACT_PATH,
            language=Config.OCR_LANGUAGE,
            template=self.template,
        )
        resultats: List[Dict] = []
        for i, image in enumerate(images):
            if self._est_annule():
                self._log(f"  ⏹ Lecture arrêtée — {i}/{len(images)} images lues.")
                break
            self._progress(
                0.9 * i / max(len(images), 1), f"Lecture Tesseract {i + 1}/{len(images)}…"
            )
            resultats.append(extracteur.extract(image))
        return resultats


def main(argv: Optional[List[str]] = None) -> int:
    """Ligne de commande : python converter.py verifier <scan> <converti>."""
    import argparse
    import sys

    from verificateur import formater_rapport

    parser = argparse.ArgumentParser(prog='converter.py')
    sous = parser.add_subparsers(dest='commande', required=True)
    v = sous.add_parser('verifier', help="Compare un scan à sa conversion")
    v.add_argument('scan', help="Document scanné d'origine (.pdf, .docx, .jsonl, dossier)")
    v.add_argument('converti', help="Document converti (.pdf ou .jsonl)")
    v.add_argument('--modele', default=None, help="Nom du modèle de tableau")
    v.add_argument('--rapport', default=None, help="Fichier texte où écrire le rapport")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    template = None
    if args.modele:
        from template import TemplateManager
        template = TemplateManager().get(args.modele)
    conv = Converter(
        word_file=Path(args.scan), output_dir=Path('.'), template=template,
        on_log=lambda message: print(message),
    )
    rapport = conv.verifier_conversion(reference=args.scan, converti=args.converti)
    texte = formater_rapport(rapport)
    print(texte)
    if args.rapport:
        Path(args.rapport).write_text(texte, encoding='utf-8')
    return 1 if rapport.a_verifier else 0


if __name__ == '__main__':
    raise SystemExit(main())
