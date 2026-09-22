"""
Extraction de tableaux de borniers depuis un PDF avec couche texte vectorielle.

Utilise PyMuPDF (fitz) pour lire les mots avec leurs coordonnees x,y.
Compatible avec les PDFs "cherchables" (image scannee + couche OCR integree)
et les PDFs purement raster (pages image sans couche texte -- OCR Tesseract).

Produit le meme format de resultat que BornierTableExtractor.extract()
pour une integration transparente avec _fill_worksheet() et generer_excel().
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from template import DEFAULT_TEMPLATE, TableTemplate

logger = logging.getLogger(__name__)


def is_pymupdf_available() -> bool:
    """Verifie que PyMuPDF est installe."""
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


class PdfTableExtractor:
    """Extrait les tableaux de borniers depuis les pages d'un PDF."""

    # Nombre minimum de mots pour considerer qu'une page a une couche texte
    _MIN_WORDS = 5

    # Colonnes dont les valeurs doivent suivre le patron JAR : 4 chiffres + 1 lettre
    _JAR_COLS = {'JAR'}
    _JAR_PATTERN = re.compile(r'^(\d{4})([A-Z])$')
    _JAR_NORMALIZE = str.maketrans('OolIi', '00111')

    # Colonnes dont les codes suivent le patron BORNE : 1-3 chiffres + 1 lettre
    # (ex: 05E, 12A) — confusions Adobe OCR : S↔5, O↔0 dans la partie numérique
    _BORNE_COLS = {'BORNE'}
    _BORNE_NORMALIZE = str.maketrans('OoSsIil', '0055111')

    def __init__(self, template: Optional[TableTemplate] = None):
        self._tpl = template or DEFAULT_TEMPLATE
        self._ws_delegate = None  # BornierTableExtractor -- charge paresseusement
        self._ocr_dir: Optional[Path] = None       # dossier images raster brutes pour OCR
        self._preprocess_dir: Optional[Path] = None  # dossier images preprocessees (debug)
        # Frontières de colonnes de la dernière page réussie — réutilisées pour les
        # pages de continuation (sans ligne d'en-tête) du même tableau
        self._last_bounds: Optional[List[int]] = None

    # -- Point d'entree --------------------------------------------------

    def extract_all(
        self, pdf_path: Path, on_page_done=None, cancel_check=None
    ) -> Tuple[List[Dict], 'PdfTableExtractor']:
        """
        Extrait tous les tableaux du PDF.
        Les pages sans couche texte sont traitees par OCR Tesseract.
        Retourne (resultats, self).

        cancel_check : Optional[Callable[[], bool]] — vérifié en début de
        chaque page ; si vrai, arrête l'extraction et retourne les résultats
        déjà accumulés (arrêt coopératif, jamais d'exception).
        """
        import fitz
        pdf_path = Path(pdf_path)
        self._ocr_dir = pdf_path.parent / (pdf_path.stem + '_ocr_pages')
        self._preprocess_dir = pdf_path.parent / (pdf_path.stem + '_images_pretaitees')

        self._last_bounds = None  # Réinitialiser pour chaque nouveau document
        doc = fitz.open(str(pdf_path))
        results = []
        for page_num in range(len(doc)):
            if cancel_check and cancel_check():
                break
            page = doc[page_num]
            result = self._extract_page(page, page_num)
            results.append(result)
            if on_page_done:
                on_page_done(page_num + 1, len(doc), result)
        doc.close()
        return results, self

    # -- Extraction d'une page -------------------------------------------

    def _extract_page(self, page, page_num: int) -> Dict:
        """
        Essaie l'extraction vectorielle (rawdict puis mots simples),
        puis bascule sur OCR si la page est purement raster.

        Exception : si OCR_MODE est 'claude' ou 'docling', la page est
        toujours rendue comme image et envoyée au moteur IA sélectionné,
        quelle que soit la présence d'une couche texte vectorielle.
        """
        from config import Config
        ocr_mode = getattr(Config, 'OCR_MODE', 'tesseract').lower().strip()

        # Moteur IA : rendre toutes les pages comme images (ignore la couche texte)
        if ocr_mode in ('claude', 'docling'):
            return self._extract_page_ocr(page, page_num)

        words = page.get_text("words")
        if len(words) < self._MIN_WORDS:
            return self._extract_page_ocr(page, page_num)

        # Essai 1 : extraction par position de caractere (rawdict)
        char_words = self._get_char_words(page)
        if char_words:
            result = self._extract_from_words(char_words, page_num, use_char_pos=True)
            if result['success']:
                return result

        # Essai 2 : extraction par mot simple (repli)
        return self._extract_from_words(words, page_num, use_char_pos=False)

    # -- Extraction des positions caractere (rawdict) --------------------

    def _get_char_words(self, page) -> Optional[List]:
        """
        Retourne les mots avec les positions x de chaque caractere via rawdict.
        Format : (x0, y0, x1, y1, text, [char_x0, ...])
        Retourne None si le rawdict ne donne pas de caracteres utilisables.
        """
        try:
            raw = page.get_text("rawdict", flags=0)
        except Exception:
            return None

        all_words: List = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    buf_chars: List[str] = []
                    buf_xs: List[float] = []
                    bx0 = bx1 = by0 = by1 = 0.0

                    for ch in chars:
                        c = ch.get("c", "")
                        bb = ch.get("bbox", (0.0, 0.0, 0.0, 0.0))
                        if c in (' ', '\t', '\xa0', '\n'):
                            if buf_chars:
                                all_words.append(
                                    (bx0, by0, bx1, by1,
                                     ''.join(buf_chars), buf_xs[:])
                                )
                                buf_chars, buf_xs = [], []
                        else:
                            if not buf_chars:
                                bx0, by0 = bb[0], bb[1]
                            bx1, by1 = bb[2], bb[3]
                            buf_chars.append(c)
                            buf_xs.append(bb[0])

                    if buf_chars:
                        all_words.append(
                            (bx0, by0, bx1, by1,
                             ''.join(buf_chars), buf_xs[:])
                        )

        return all_words if len(all_words) >= self._MIN_WORDS else None

    # -- Logique d'extraction commune ------------------------------------

    def _extract_from_words(self, words, page_num: int,
                            use_char_pos: bool) -> Dict:
        """Extrait le tableau depuis une liste de mots."""
        lines = self._group_lines(words)
        col_names = self._tpl.columns
        bounds, header_idx = self._find_header(lines, col_names)

        if bounds is None:
            # Page de continuation : pas d'en-tête, réutiliser les frontières
            # de la dernière page réussie du même document
            if self._last_bounds is not None:
                bounds = self._last_bounds
                header_idx = -1  # Traiter toutes les lignes comme données
            else:
                return self._fail(page_num)
        else:
            self._last_bounds = bounds  # Mémoriser pour les pages suivantes

        rows = []
        footer_lines = []
        footer_started = False  # Une fois le 1er label de pied trouvé, tout ce qui suit est pied

        # Préparation de la détection des écarts verticaux entre blocs
        from config import Config as _Cfg
        import numpy as _np
        _preserve_sp = getattr(_Cfg, 'OCR_PRESERVE_SPACING', True)
        _prev_data_y_max = None
        if _preserve_sp and words:
            _word_heights = [w[3] - w[1] for w in words if w[3] > w[1]]
            _med_h = int(_np.median(_word_heights)) if _word_heights else 0
            _sp_thr = getattr(_Cfg, 'OCR_SPACING_THRESHOLD', 1.6) * _med_h
        else:
            _med_h, _sp_thr = 0, 0

        for li, line in enumerate(lines):
            if li <= header_idx:
                continue
            line_text = ' '.join(w[4] for w in line).upper()

            if footer_started or self._is_footer(line_text):
                footer_started = True
                footer_lines.append(line)
                continue
            if self._is_section(line_text):
                text = ' '.join(self._clean(w[4]) for w in line).strip()
                if text:
                    rows.append({'type': 'section', 'text': text})
                continue

            # Détection de l'écart vertical avec la ligne de données précédente
            if _sp_thr > 0 and _prev_data_y_max is not None:
                _cur_y_min = min(w[1] for w in line)
                _gap = _cur_y_min - _prev_data_y_max
                if _gap > _sp_thr:
                    _n_blanks = min(3, max(1, round(_gap / _med_h) - 1))
                    rows.append({'type': 'blank', 'count': _n_blanks})

            if use_char_pos:
                cells = self._assign_cols_chars(line, bounds, len(col_names))
            else:
                cells = self._assign_cols(line, bounds, len(col_names))
            cells = [self._clean(c) for c in cells]
            cells = self._fix_jar_cells(cells, col_names)
            cells = self._fix_borne_cells(cells, col_names)
            # Ignorer les lignes entièrement vides de caractères alphanumériques
            # (artefacts PDF : séparateurs, tirets, pipes)
            # Seuil = 0 pour ne pas filtrer les valeurs à 1 caractère (ex: borne "5")
            total_alnum = sum(sum(1 for ch in c if ch.isalnum()) for c in cells)
            if total_alnum == 0:
                continue
            if any(cells):
                rows.append({
                    'type': 'data',
                    'cells': cells,
                    'confidence': [90] * len(col_names),
                })
                _prev_data_y_max = max(w[3] for w in line)

        rows = self._merge_partial_rows(rows)
        meta = self._extract_meta(footer_lines)
        return {
            'success': bool(rows),
            'page_num': page_num + 1,
            'image_path': f'page_{page_num + 1}',
            'headers': col_names,
            'rows': rows,
            'metadata': meta,
            'detection_method': 'pdf',
            'blur_pct': 0.0,
        }

    # -- OCR de repli pour les pages raster ------------------------------

    def _extract_page_ocr(self, page, page_num: int) -> Dict:
        """
        Rend la page comme image PNG et la traite par OCR Tesseract.
        Utilise pour les pages sans couche texte vectorielle.
        """
        import fitz

        if self._ocr_dir is None:
            return self._fail(page_num)

        try:
            self._ocr_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Impossible de creer le dossier OCR : %s", e)
            return self._fail(page_num)

        img_path = self._ocr_dir / f"page_{page_num + 1}.png"
        try:
            # Zoom 3x -> ~216 DPI pour Tesseract
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
            pix.save(str(img_path))
        except Exception as e:
            logger.warning("Rendu page %d echoue : %s", page_num + 1, e)
            return self._fail(page_num)

        # Prétraitement OpenCV pour améliorer la netteté avant Tesseract
        img_to_ocr = self._preprocess_raster(img_path)

        try:
            ocr_result = self._get_ws_delegate().extract(img_to_ocr)
        except Exception as e:
            logger.warning("OCR de repli echoue page %d : %s", page_num + 1, e)
            return self._fail(page_num)

        ocr_result['page_num'] = page_num + 1
        ocr_result['image_path'] = f'page_{page_num + 1}'
        ocr_result['detection_method'] = 'pdf_ocr'
        return ocr_result

    # -- Prétraitement OpenCV pour pages raster --------------------------

    def _preprocess_raster(self, img_path: Path) -> Path:
        """
        Pipeline OpenCV avant Tesseract pour améliorer la netteté des contours :
        CLAHE -> debruitage bilateral -> accentuation -> binarisation Otsu -> nettoyage morph.
        Sauvegarde l'image prétraitée dans _preprocess_dir pour inspection visuelle.
        Retourne le chemin de l'image à utiliser pour l'OCR.
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            logger.warning("opencv-python non disponible — prétraitement ignoré")
            return img_path

        img = cv2.imread(str(img_path))
        if img is None:
            return img_path

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # CLAHE : normalise le contraste local (utile pour scans inégaux)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Filtre bilatéral : lisse le bruit tout en préservant les bords
        denoised = cv2.bilateralFilter(enhanced, d=7, sigmaColor=50, sigmaSpace=50)

        # Accentuation (unsharp masking) : renforce les contours des caractères
        blur_g = cv2.GaussianBlur(denoised, (0, 0), sigmaX=3)
        sharpened = cv2.addWeighted(denoised, 1.5, blur_g, -0.5, 0)

        if self._preprocess_dir is not None:
            try:
                self._preprocess_dir.mkdir(parents=True, exist_ok=True)
                # Image binaire pour inspection visuelle
                _, binarized = cv2.threshold(
                    sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                k = np.ones((2, 2), np.uint8)
                debug_img = cv2.morphologyEx(binarized, cv2.MORPH_CLOSE, k)
                cv2.imwrite(str(self._preprocess_dir / img_path.name), debug_img)
            except Exception as e:
                logger.warning("Impossible de sauvegarder l'image prétraitée : %s", e)

        # Retourner le niveaux-de-gris amélioré (pas binaire) pour que
        # _preprocess() interne à BornierTableExtractor finalise la binarisation
        # sur une image de meilleure qualité.
        try:
            ocr_path = self._ocr_dir / ('enh_' + img_path.name)
            cv2.imwrite(str(ocr_path), sharpened)
            return ocr_path
        except Exception:
            return img_path

    # -- Fusion des lignes partielles ------------------------------------

    @staticmethod
    def _merge_partial_rows(rows: List[Dict]) -> List[Dict]:
        """
        Fusionne les lignes data consécutives dont les colonnes non-vides
        sont complémentaires (cas d'une cellule PDF sur 2 lignes de texte).

        Ex : row N   = ['05E', '',     'CTB4-',  '']
             row N+1 = ['',    'ROUGE', '01A',   '']
             → merged = ['05E', 'ROUGE', 'CTB4-01A', '']
        """
        merged: List[Dict] = []
        for row in rows:
            if row.get('type') != 'data' or not merged or merged[-1].get('type') != 'data':
                merged.append(row)
                continue

            prev = merged[-1]
            pc = prev['cells']
            cc = row['cells']

            # Les deux lignes sont complémentaires si aucune colonne n'est
            # non-vide dans LES DEUX en même temps
            conflict = any(pc[i] and cc[i] for i in range(min(len(pc), len(cc))))
            if conflict:
                merged.append(row)
                continue

            # Fusion : concatène les contenus complémentaires
            for i in range(min(len(pc), len(cc))):
                if cc[i]:
                    pc[i] = (pc[i] + ' ' + cc[i]).strip() if pc[i] else cc[i]
            # Ne pas ajouter row séparément

        return merged

    # -- Groupement des mots en lignes -----------------------------------

    def _group_lines(self, words, tol: int = 6) -> List[List]:
        """Groupe les mots par position y (tolerance +/- tol pts).
        6 pts pour absorber les variations de baseline entre caractères hauts/bas."""
        lines: List[List] = []
        for w in words:
            y = w[1]
            placed = False
            for line in lines:
                if abs(line[0][1] - y) <= tol:
                    line.append(w)
                    placed = True
                    break
            if not placed:
                lines.append([w])
        for line in lines:
            line.sort(key=lambda w: w[0])
        lines.sort(key=lambda ln: ln[0][1])
        return lines

    # -- Detection de l'en-tete et des frontieres de colonnes ------------

    def _find_header(
        self, lines: List[List], col_names: List[str]
    ) -> Tuple[Optional[List[int]], int]:
        """
        Cherche la ligne contenant les noms de colonnes du template.
        Retourne (bounds, index_ligne) ou (None, -1).
        bounds = [0, b1, b2, ..., bn, 10000].
        """
        col_up = [re.sub(r'[^A-Z0-9]', '', c.upper()) for c in col_names]

        for li, line in enumerate(lines):
            found: Dict[int, Tuple[float, float]] = {}
            for w in line:
                wt = re.sub(r'[^A-Z0-9]', '', w[4].upper())
                for ci, c in enumerate(col_up):
                    if len(c) >= 3 and c in wt and ci not in found:
                        found[ci] = (w[0], w[2])

            if len(found) < max(2, len(col_up) // 2):
                continue

            bounds = [0]
            for i in range(len(col_names) - 1):
                if i in found and (i + 1) in found:
                    mid = int((found[i][1] + found[i + 1][0]) / 2)
                elif i in found:
                    mid = int(found[i][1] + 15)
                elif (i + 1) in found:
                    mid = int(found[i + 1][0] - 15)
                else:
                    mid = bounds[-1] + 80
                bounds.append(mid)
            bounds.append(10000)
            return bounds, li

        return None, -1

    # -- Affectation par position de caractere ---------------------------

    def _assign_cols_chars(self, line: List, bounds: List[int],
                           n_cols: int) -> List[str]:
        """
        Affecte les mots aux colonnes en utilisant la position de chaque
        caractere. Divise les tokens qui chevauchent plusieurs colonnes.
        L'espacement proportionnel est appliqué aux mots entièrement dans
        une seule colonne (les mots découpés gardent un espace simple).
        """
        from config import Config as _Cfg
        cells = [''] * n_cols
        last_x1: dict = {}  # col → bord droit du dernier mot (pour espacement)

        for w in line:
            text = w[4].strip()
            if not text:
                continue

            char_xs: Optional[List[float]] = w[5] if len(w) > 5 else None

            # Cas sans positions de caractères : repli bord gauche
            if char_xs is None or len(char_xs) != len(text):
                col = self._find_col(w[0], bounds, n_cols)
                if getattr(_Cfg, 'OCR_PRESERVE_INTRA_CELL_SPACING', True) and cells[col]:
                    gap = w[0] - last_x1.get(col, w[0])
                    char_w = max(1.0, (w[2] - w[0]) / len(text))
                    n_sp = max(1, min(12, round(gap / char_w)))
                    cells[col] = cells[col] + ' ' * n_sp + text
                else:
                    cells[col] = (cells[col] + ' ' + text).strip() if cells[col] else text
                last_x1[col] = w[2]
                continue

            char_cols = [self._find_col(cx, bounds, n_cols) for cx in char_xs]

            if len(set(char_cols)) == 1:
                col = char_cols[0]
                if getattr(_Cfg, 'OCR_PRESERVE_INTRA_CELL_SPACING', True) and cells[col]:
                    gap = w[0] - last_x1.get(col, w[0])
                    char_w = max(1.0, (w[2] - w[0]) / len(text))
                    n_sp = max(1, min(12, round(gap / char_w)))
                    cells[col] = cells[col] + ' ' * n_sp + text
                else:
                    cells[col] = (cells[col] + ' ' + text).strip() if cells[col] else text
                last_x1[col] = w[2]
            else:
                # Token chevauchant plusieurs colonnes : decouper caractere par caractere
                # (pas d'espacement proportionnel sur les fragments découpés)
                cur_col = char_cols[0]
                cur_chars: List[str] = [text[0]]
                for i in range(1, len(text)):
                    if char_cols[i] == cur_col:
                        cur_chars.append(text[i])
                    else:
                        part = ''.join(cur_chars).strip()
                        if part:
                            cells[cur_col] = (cells[cur_col] + ' ' + part).strip()
                        cur_col = char_cols[i]
                        cur_chars = [text[i]]
                part = ''.join(cur_chars).strip()
                if part:
                    cells[cur_col] = (cells[cur_col] + ' ' + part).strip()

        return cells

    # -- Affectation par bord gauche (repli) -----------------------------

    def _assign_cols(self, line: List, bounds: List[int], n_cols: int) -> List[str]:
        """Repli : affecte chaque mot selon son bord gauche (x0).

        Quand OCR_PRESERVE_INTRA_CELL_SPACING est True, insère des espaces
        proportionnels à l'écart visuel entre mots d'une même colonne
        (ex: TENANT = "TGV   TE203A   C12" au lieu de "TGV TE203A C12").
        Les coordonnées PDF sont en points — précision supérieure aux pixels OCR.
        """
        from config import Config as _Cfg
        cells = [''] * n_cols
        last_x1 = [None] * n_cols  # bord droit du dernier mot par colonne

        for w in line:
            col = self._find_col(w[0], bounds, n_cols)
            txt = w[4].strip()
            if not txt:
                continue
            if getattr(_Cfg, 'OCR_PRESERVE_INTRA_CELL_SPACING', True) and cells[col]:
                gap = w[0] - (last_x1[col] or w[0])
                char_w = max(1.0, (w[2] - w[0]) / len(txt))
                n_sp = max(1, min(12, round(gap / char_w)))
                cells[col] = cells[col] + ' ' * n_sp + txt
            else:
                cells[col] = (cells[col] + ' ' + txt).strip() if cells[col] else txt
            last_x1[col] = w[2]

        return cells

    def _find_col(self, x: float, bounds: List[int], n_cols: int) -> int:
        for i in range(len(bounds) - 1):
            if bounds[i] <= x < bounds[i + 1]:
                return i
        return n_cols - 1

    # -- Nettoyage des valeurs -------------------------------------------

    def _clean(self, val: str) -> str:
        """
        Corrige les artefacts OCR courants dans la couche texte du PDF.

        En plus des regles standard (O/0, l/1), ajoute deux corrections
        specifiques aux PDFs cherchables crees par des outils OCR tiers :
        - codes de bornes 3 chars (OlA->01A, lOB->10B)  : l et O mal encodes
        - suffixes numeriques apres lettre minuscule (FSbll-31->FSb11-31)
        """
        if not val:
            return ''
        val = (val
               .replace('€', 'E').replace('\xa3', 'E').replace('\xa2', 'C')
               .replace('\xa0', ' ').replace('’', "'"))
        # l minuscule -> 1 dans les sequences numeriques
        val = re.sub(r'(?<=\d)l(?=\d)', '1', val)
        val = re.sub(r'(?<=\d)l\b', '1', val)
        val = re.sub(r'\bl(?=\d)', '1', val)
        # ll apres lettre minuscule avant - ou chiffre (FSbll-31 -> FSb11-31)
        val = re.sub(r'(?<=[a-z])ll(?=[-\d])', '11', val)
        # Codes de bornes : 2 chars {l,O,0-9} suivis d'une lettre majuscule
        val = re.sub(
            r'\b([lO0-9])([lO0-9])([A-Z])\b',
            lambda m: (
                m.group(1).replace('O', '0').replace('l', '1') +
                m.group(2).replace('O', '0').replace('l', '1') +
                m.group(3)
            ),
            val,
        )
        val = val.strip('|[]\\').strip()
        if not val or not any(c.isalnum() for c in val):
            return ''
        # Rejeter uniquement si TOUTE la valeur est un caractère répété (ex: "-----")
        # search() était trop agressif : il rejetait "CTB4-FFFFF-01" (nom de signal valide)
        if re.fullmatch(r'(.)\1{4,}', val):
            return ''

        def _fix_o0(word: str) -> str:
            if len(word) > 12 or not any(c.isdigit() for c in word):
                return word
            w = re.sub(r'^[Oo](?=\d)', '0', word)
            w = re.sub(r'(?<=\d)[Oo](?=\d)', '0', w)
            return w

        val = ' '.join(_fix_o0(w) for w in val.split())
        return val

    # -- Validation des valeurs JAR (4 chiffres + 1 lettre couleur) ------

    def _fix_jar_value(self, val: str) -> str:
        """
        Valide et corrige une valeur de colonne JAR : patron \\d{4}[A-Z].
        - Supprime les espaces internes (artefact PDF multi-mots : '0 0 12W')
        - Remplace les artefacts d'encodage CAO : W → \\AJ, \\I'J, \\AI selon la police
        - Remplace O→0, o→0, l→1, I→1, i→1
        - Met en majuscule la lettre finale
        - Complète par des zéros à gauche si moins de 4 chiffres (ex: '1R' → '0001R')
        """
        if not val:
            return val
        # Espaces internes parasites dans les numéros (ex: '0 0 12W' → '0012W')
        val = val.replace(' ', '')
        # Artefacts d'encodage police CAO : la lettre W est stockée en plusieurs glyphes
        # PyMuPDF extrait ces glyphes comme \AJ, \I'J, \AI, \AK au lieu de W
        val = re.sub(r"\\[A-Z]['\"']?[A-Z]", 'W', val)
        normalized = val.translate(self._JAR_NORMALIZE)
        # Lettre finale en majuscule
        normalized = re.sub(
            r'^([0-9]{1,5})([a-z])$',
            lambda m: m.group(1) + m.group(2).upper(),
            normalized
        )
        m = re.match(r'^(\d{1,5})([A-Z])$', normalized)
        if m:
            digits = m.group(1).zfill(4)[-4:]
            return digits + m.group(2)
        return val

    def _fix_jar_cells(self, cells: List[str], col_names: List[str]) -> List[str]:
        """Applique _fix_jar_value() sur toutes les colonnes de type JAR."""
        for i, name in enumerate(col_names):
            if name.upper() in self._JAR_COLS and i < len(cells):
                cells[i] = self._fix_jar_value(cells[i])
        return cells

    # -- Validation des codes de borne (1-3 chiffres + 1 lettre) --------

    def _fix_borne_value(self, val: str) -> str:
        """
        Corrige un code de borne extrait d'un PDF Adobe (confusion S↔5, O↔0).
        Patron attendu : 1-3 chiffres + 1 lettre majuscule (ex: 05E, 12A, 7B).
        Seule la partie numérique est normalisée ; la lettre suffixe est conservée.
        """
        if not val or len(val) < 2:
            return val
        # Dernier caractère = lettre suffixe ; tout le reste = partie numérique
        suffix = val[-1]
        numeric = val[:-1]
        # Lettre suffixe en majuscule (par sécurité)
        if not suffix.isalpha():
            return val
        suffix = suffix.upper()
        # Vérifier que la partie numérique ne contient que des chiffres/confusions
        if not re.match(r'^[0-9OoSsIil]+$', numeric):
            return val
        numeric_fixed = numeric.translate(self._BORNE_NORMALIZE)
        return numeric_fixed + suffix

    def _fix_borne_cells(self, cells: List[str], col_names: List[str]) -> List[str]:
        """Applique _fix_borne_value() sur toutes les colonnes de type BORNE."""
        for i, name in enumerate(col_names):
            if name.upper() in self._BORNE_COLS and i < len(cells):
                cells[i] = self._fix_borne_value(cells[i])
        return cells

    # -- Classification des lignes ---------------------------------------

    def _is_footer(self, text: str) -> bool:
        # Vérifier si la ligne est l'étiquette gauche du pied (ex: "SIEMENS", "M T I")
        left = re.sub(r'\s+', ' ', self._tpl.footer_left_label).upper().strip()
        if left and left in text and len(text.strip()) <= len(left) + 8:
            return True
        # Normalise chaque mot-clé : retire le ':' ou espace trailing pour
        # toujours tester la forme "LABEL\s{0,10}[:|]" — évite les faux positifs
        # sur les noms de signal contenant le même mot (ex: "INDICE_MOTEUR")
        for kw in self._tpl.footer_detect_keywords:
            kw_clean = kw.upper().rstrip(': ')
            if not kw_clean:
                continue
            if re.search(rf'{re.escape(kw_clean)}\s{{0,10}}[:\|]', text):
                return True
        return False

    def _is_section(self, text: str) -> bool:
        return self._tpl.section_keyword.upper() in text

    # -- Extraction des metadonnees --------------------------------------

    def _extract_meta(self, footer_lines: List[List]) -> Dict:
        """Extrait BORNIER, PAGE, PET, INDICE, NO_PLAN depuis les lignes de pied."""
        text = ' '.join(w[4] for line in footer_lines for w in line).upper()
        meta: Dict = {}

        m = re.search(
            r'P\.?E\.?T\.?\s*[:\-]?\s*([A-Z][A-Z0-9\s\-]{1,30}?)(?:BORNIER|JARRET|\||\Z)',
            text)
        if m:
            meta['PET'] = m.group(1).strip()

        m = re.search(r'BORNIER\s*[:\-]?\s*([A-Z0-9\-]{2,20})', text)
        if m:
            meta['BORNIER'] = m.group(1).strip()

        m = re.search(
            r'(?:NO\.?\s*PLAN|N\xb0\s*PLAN)\s*[:\-]?\s*([A-Z0-9\s]{3,30}?)(?:\||INDICE|\Z)',
            text)
        if m:
            meta['NO_PLAN'] = m.group(1).strip()

        m = re.search(r'INDICE\s*[:\-]?\s*([0-9A-Z]{1,5})', text)
        if m:
            meta['INDICE'] = m.group(1).strip().replace('O', '0')

        m = re.search(r'PAGE\s*[:\-]?\s*(\d+)', text)
        if m:
            meta['PAGE'] = m.group(1).strip()

        # Champs personnalisés définis dans footer_extract_fields (ex: CABLE, TYPE)
        # Analyse ligne par ligne : évite que "10/10" (compteur de pages en fin de
        # ligne TYPE) ne pollue le pattern qui travaillait sur le texte joint.
        _standard = {'PET', 'BORNIER', 'NO_PLAN', 'INDICE', 'PAGE'}
        line_texts = [' '.join(w[4] for w in line).upper() for line in footer_lines]
        for fdef in self._tpl.footer_extract_fields:
            key   = fdef.get('key', '').upper()
            label = fdef.get('label', '').upper()
            if not key or not label or key in _standard or key in meta:
                continue
            label_re = re.sub(r'\.', r'\\.?', re.escape(label))
            label_re = label_re.replace(r'\ ', r'\\s+')
            for lt in line_texts:
                m = re.search(
                    rf'{label_re}\s*[:\-]\s*([A-Z0-9/][A-Z0-9\s\-/]{{0,50}}?)'
                    rf'(?:\s+\d+/\d+)?$',
                    lt.strip()
                )
                if m:
                    meta[key] = m.group(1).strip()
                    break

        return meta

    # -- Methodes compatibles avec generer_classeur.py -------------------

    def _count_data_rows(self, result: Dict) -> int:
        return sum(1 for r in result.get('rows', []) if r.get('type') == 'data')

    def _fill_worksheet(self, ws, result, start_row, page_size,
                        dictionary, bornier_name, pet_name):
        """Delegue la mise en forme Excel a BornierTableExtractor."""
        return self._get_ws_delegate()._fill_worksheet(
            ws, result, start_row, page_size, dictionary, bornier_name, pet_name
        )

    def _get_ws_delegate(self):
        """Charge paresseusement un BornierTableExtractor pour l'OCR et la mise en forme."""
        if self._ws_delegate is None:
            from ocr_processor import BornierTableExtractor
            from config import Config
            self._ws_delegate = BornierTableExtractor(
                tesseract_path=Config.TESSERACT_PATH,
                language=Config.OCR_LANGUAGE,
                template=self._tpl,
            )
        return self._ws_delegate

    # -- Resultat vide ---------------------------------------------------

    def _fail(self, page_num: int) -> Dict:
        return {
            'success': False,
            'page_num': page_num + 1,
            'image_path': f'page_{page_num + 1}',
            'headers': self._tpl.columns,
            'rows': [],
            'metadata': {},
            'detection_method': 'pdf',
            'blur_pct': 0.0,
        }
