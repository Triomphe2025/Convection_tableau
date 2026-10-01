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

from pied_page import (analyser_pied, indices_revisions, logo_pied, mots_decor,
                       nettoyer_lignes_pied)
from template import DEFAULT_TEMPLATE, TableTemplate

logger = logging.getLogger(__name__)


def is_pymupdf_available() -> bool:
    """Verifie que PyMuPDF est installe."""
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


# -- Routage par page : nature de la page PDF --------------------------

VECTORIEL = 'vectoriel'
OCR_INVISIBLE = 'ocr_invisible'
SCAN = 'scan'
VIDE = 'vide'

# Mode de rendu PDF 3 = texte invisible (couche OCR posée sur une image,
# ex. Adobe Paper Capture) : ce texte n'est pas ce qu'on voit à l'écran.
_RENDU_INVISIBLE = 3


def couverture_image(page) -> float:
    """Part de la page couverte par des images (somme des aires, bornée à 1).

    Somme et non maximum : un scan peut être découpé en bandes (page de
    garde de 223400PE137 : 4 bandes).
    """
    import fitz
    aire = page.rect.width * page.rect.height
    if not aire:
        return 0.0
    total = sum(
        (fitz.Rect(info['bbox']) & page.rect).get_area()
        for info in page.get_image_info()
    )
    return min(1.0, total / aire)


def diagnostiquer_page(page) -> Dict:
    """Mesures qui décident du traitement d'une page, et la nature retenue.

    Ordre de décision :
    1. texte vectoriel exploitable (visible, ≥ PDF_MIN_CARS_VECTORIEL caractères,
       police intégrée, aucune couche invisible, pas posé sur une image pleine
       page) → VECTORIEL, lu en grille ;
    2. sinon, images cumulées ≥ PDF_SEUIL_IMAGE → pipeline scan : OCR_INVISIBLE
       si la page porte une couche texte (ignorée), SCAN sinon. Le seuil est bas
       à dessein : un scan peut être stocké en bandes de 10 % (gardes de
       223400PE137) et serait sinon perdu ;
    3. sinon, texte visible non garanti (police non intégrée) → SCAN, pour ne
       pas perdre une page qui a du contenu ;
    4. sinon → VIDE, page ignorée (le motif est journalisé).
    """
    from config import Config
    visibles = invisibles = 0
    for trace in page.get_texttrace():
        n = len(trace.get('chars', ()))
        if trace.get('type') == _RENDU_INVISIBLE:
            invisibles += n
        else:
            visibles += n
    couverture = couverture_image(page)
    polices_integrees = any(police[1] != 'n/a' for police in page.get_fonts())
    assez_de_texte = visibles >= Config.PDF_MIN_CARS_VECTORIEL

    if (assez_de_texte and polices_integrees and not invisibles
            and couverture < Config.PDF_SEUIL_IMAGE_PLEINE_PAGE):
        nature = VECTORIEL
    elif couverture >= Config.PDF_SEUIL_IMAGE:
        nature = OCR_INVISIBLE if (visibles or invisibles) else SCAN
    elif assez_de_texte:
        nature = SCAN
    else:
        nature = VIDE
    return {
        'nature': nature, 'visibles': visibles, 'invisibles': invisibles,
        'couverture': couverture,
    }


def classer_page(page) -> str:
    """Nature d'une page : VECTORIEL, OCR_INVISIBLE, SCAN ou VIDE (voir diagnostiquer_page)."""
    return diagnostiquer_page(page)['nature']


def motif_page_ignoree(diagnostic: Dict) -> str:
    """Raison lisible pour laquelle une page VIDE est ignorée."""
    from config import Config
    visibles = diagnostic.get('visibles', 0)
    texte = f"texte trop court ({visibles} caractères)" if visibles else "aucun texte"
    return f"{texte} et images sous le seuil de {round(Config.PDF_SEUIL_IMAGE * 100)} %"


# -- Lecture de la couche texte en grille de caractères ----------------

def _sens_de_lecture(span: Dict, matrice) -> Tuple[Dict, List[Dict]]:
    """Span et caractères ramenés au sens de lecture d'une page tournée.

    get_text donne les positions dans la page non tournée : sur la page des
    révisions de 223111PE011 (rotation 90°), chaque ligne lue y est verticale.
    """
    import fitz
    caracteres = [
        dict(c, origin=tuple(fitz.Point(c['origin']) * matrice),
             bbox=tuple(fitz.Rect(c['bbox']) * matrice))
        for c in span['chars']
    ]
    return dict(span, origin=tuple(fitz.Point(span['origin']) * matrice)), caracteres


def grille_page(page) -> List[str]:
    """Reconstruit une page de texte vectoriel en lignes à positions exactes.

    Chaque MOT est placé d'après sa propre coordonnée x, avec le pas (largeur
    d'un caractère) mesuré sur toute la page — et non plus en comptant les
    caractères d'un span depuis son début, comme outils_reference/grille.py,
    ce qui faisait deux erreurs sur 223400PE137 :
    - un espace isolé dans son propre span était absorbé (« VERSPCC » au lieu
      de « VERS PCC », lignes 1769N, 1829N, 1843N) ;
    - un span en police plus petite (10,08 au lieu de 11,04, « D_T 02A »)
      décalait d'une colonne les mots qui le suivent.
    Placement : le 1er mot d'un span à colonne = round((x - x0) / pas), valeur
    identique d'une ligne à l'autre pour un même x ; les mots suivants du span
    à partir de ce début, avec le même pas. Placer chaque mot en absolu fait
    basculer d'une colonne les x situés pile entre deux colonnes (les champs
    ne sont pas sur une grille commune : ABOUTISSANT à 34,50 colonnes du
    TENANT), ce qui collait « G21DU » et désalignait « D_S 01B ». Un vide d'au
    moins un demi-caractère entre deux spans garde au moins un espace.
    Les mots sont regroupés en lignes avec une tolérance en y
    (Config.PDF_GRILLE_TOLERANCE_Y) plutôt que par round(y) : un TENANT posé
    0,7 pt plus haut que sa ligne formait sinon une ligne à lui seul.
    """
    from collections import Counter
    from config import Config

    # Un mot : (y du span, x du 1er caractère, x du dernier, texte, n° de span,
    # x de début du span).
    mots: List[Tuple[float, float, float, str, int, float]] = []
    ecarts: Counter = Counter()
    largeurs: Counter = Counter()
    num_span = 0
    for bloc in page.get_text('rawdict')['blocks']:
        for ligne in bloc.get('lines', []):
            for span in ligne['spans']:
                caracteres = span['chars']
                if not caracteres:
                    continue
                if page.rotation:
                    span, caracteres = _sens_de_lecture(span, page.rotation_matrix)
                num_span += 1
                xs = [c['origin'][0] for c in caracteres]
                ecarts.update(round(b - a, 2) for a, b in zip(xs, xs[1:]))
                largeurs.update(round(c['bbox'][2] - c['bbox'][0], 2) for c in caracteres)
                y = span['origin'][1]
                courant, x_mot, x_dernier = '', None, None
                for c in caracteres + [{'c': ' ', 'origin': (0, 0)}]:
                    if c['c'].isspace():
                        # Un mot fait uniquement de « _ » est un trait de cadre.
                        if courant and courant.strip('_'):
                            mots.append((y, x_mot, x_dernier, courant, num_span, xs[0]))
                        courant, x_mot = '', None
                    else:
                        if not courant:
                            x_mot = c['origin'][0]
                        courant += c['c']
                        x_dernier = c['origin'][0]
    if not mots:
        return []

    positifs = [(pas, n) for pas, n in ecarts.most_common() if pas > 0]
    # Repli si la page n'a que des mots d'un caractère : largeur d'un caractère.
    pas_page = positifs[0][0] if positifs else largeurs.most_common(1)[0][0]
    x0 = min(m[1] for m in mots)

    groupes: List[List[Tuple[float, float, str, int, float]]] = []
    y_groupe = None
    for y, x, x_der, texte, span, x_span in sorted(mots, key=lambda m: (m[0], m[1])):
        if y_groupe is None or y - y_groupe > Config.PDF_GRILLE_TOLERANCE_Y:
            groupes.append([])
            y_groupe = y
        groupes[-1].append((x, x_der, texte, span, x_span))

    sortie = []
    for groupe in groupes:
        ligne: List[str] = []
        debut_span: Dict[int, int] = {}
        fin_prec, x_der_prec = None, None
        for x, x_der, texte, span, x_span in sorted(groupe):
            if span not in debut_span:
                debut_span[span] = round((x_span - x0) / pas_page)
            k = debut_span[span] + round((x - x_span) / pas_page)
            if fin_prec is not None:
                vide = (x - (x_der_prec + pas_page)) / pas_page
                k = max(k, fin_prec + (2 if vide >= 0.5 else 1))
            if len(ligne) < k:
                ligne += [' '] * (k - len(ligne))
            ligne[k:k + len(texte)] = list(texte)
            fin_prec, x_der_prec = k + len(texte) - 1, x_der
        sortie.append(''.join(ligne).rstrip())
    return sortie


# Libellés de pied de page reconnus dans une grille (repris de
# outils_reference/comparateur.py) : la détection par mots-clés du modèle
# rate « P.E.T. : » et « N° PLAN » sur 223400PE137.
_PIED_GRILLE_RE = re.compile(
    r"N°\s?PLAN|NO\s?PLAN|P\.?E\.?T\.?\s*:|CABLE\s*:|TYPE\s*:|INDICE\s*:"
    r"|PAGE\s*:?\s*\d|M\s?A\s?T\s?R\s?A|SIEMENS|JARRETIERAGE",
    re.IGNORECASE,
)
_SEPARATEUR_RE = re.compile(r'^[\s|\-_°=]*$')


def _mot_cle(texte: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', texte.upper())


def _positions_entete(ligne: str, colonnes: List[str]) -> Optional[List[int]]:
    """Colonne de départ de chaque titre de colonne dans la ligne, dans l'ordre."""
    positions = []
    debut = 0
    mots = [(m.start(), _mot_cle(m.group())) for m in re.finditer(r'\S+', ligne)]
    for nom in colonnes:
        cible = _mot_cle(nom)
        trouve = next((p for p, mot in mots if p >= debut and mot == cible), None)
        if trouve is None:
            return None
        positions.append(trouve)
        debut = trouve + 1
    return positions


def _coupures_par_gouttieres(lignes: List[str], entete: List[int]) -> List[int]:
    """Frontières de colonnes d'une page sans cadre (format TP2).

    Les titres sont centrés au-dessus des colonnes (SIGNAL commence 11
    caractères après ses données sur 223400PE137) : couper au début de chaque
    titre enverrait le SIGNAL dans ABOUTISSANT. Entre deux titres
    consécutifs, la frontière est posée après la plus large bande de colonnes
    vide sur toutes les lignes de données (repli : début du titre suivant).
    """
    largeur = max((len(lg) for lg in lignes), default=0)
    occupe = [False] * largeur
    for lg in lignes:
        for i, c in enumerate(lg):
            if c != ' ':
                occupe[i] = True

    coupures = [0]
    for k in range(1, len(entete)):
        gauche, droite = entete[k - 1], entete[k]
        meilleure, taille = None, 0
        i = gauche
        while i < min(droite, largeur):
            if occupe[i]:
                i += 1
                continue
            j = i
            while j < min(droite, largeur) and not occupe[j]:
                j += 1
            if j - i > taille:
                meilleure, taille = j, j - i
            i = j
        coupures.append(meilleure if meilleure is not None else droite)
    return coupures


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
        if getattr(Config, 'PDF_ROUTAGE_VECTORIEL', False):
            return self._extract_page_routee(page, page_num)
        return self._extract_page_v17(page, page_num)

    def _extract_page_routee(self, page, page_num: int) -> Dict:
        """Routage par nature de page (tous modes passant par extract_all).

        Le diagnostic est joint au résultat (clé 'routage') pour que
        l'appelant journalise le mode choisi.
        """
        diagnostic = diagnostiquer_page(page)
        nature = diagnostic['nature']
        if nature == VECTORIEL:
            result = self.extract_page_grille(page, page_num)
        elif nature == OCR_INVISIBLE:
            # Couche Paper Capture illisible : elle suffisait à sauter le repli
            # image (assez de mots) puis faisait échouer l'analyse — 5 pages
            # sur 10 sans aucune ligne sur l'extrait 223111PE011.
            result = self._extract_page_ocr(page, page_num)
        elif nature == VIDE:
            result = self._fail(page_num)
            result['detection_method'] = 'pdf-vide'
        else:
            result = self._extract_page_v17(page, page_num)
        result['routage'] = diagnostic
        return result

    def _extract_page_v17(self, page, page_num: int) -> Dict:
        """Chemin v1.7 : couche texte, repli OCR si la page n'a pas de mots."""
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

    # -- Lecture exacte d'une page vectorielle (grille) --------------------

    def extract_page_grille(self, page, page_num: int) -> Dict:
        """Lit une page VECTORIEL en grille de caractères, sans OCR.

        Cellules découpées aux séparateurs « | » (pages à cadre) ou aux
        colonnes de l'en-tête (pages sans cadre). Les espaces intérieurs des
        cellules sont conservés tels quels ; seuls le blanc de marge après
        « | » et les espaces de fin sont retirés. Une page sans ligne
        d'en-tête du modèle (garde, modifications) rend success=False.
        """
        colonnes = list(self._tpl.columns)
        n = len(colonnes)
        lignes = grille_page(page)

        idx_entete, entete = None, None
        for i, lg in enumerate(lignes):
            entete = _positions_entete(lg, colonnes)
            if entete is not None:
                idx_entete = i
                break
        if idx_entete is None:
            result = self._fail(page_num)
            result['detection_method'] = 'pdf-grille'
            result['error'] = "pas d'en-tête du modèle (page de garde, modifications…)"
            revisions = indices_revisions(lignes)
            if revisions:
                result['metadata'] = {'REVISIONS': revisions}
            return result

        # Lignes de section (« NOM DU CABLE : GAT/CA 01 ») testées AVANT le pied :
        # « CABLE : » est aussi un libellé de pied, et la section suit l'en-tête.
        corps, pied, sections = [], [], {}
        for lg in lignes[idx_entete + 1:]:
            if not pied and self._is_section(lg.upper()):
                sections[len(corps)] = ' '.join(lg.split())
            elif pied or _PIED_GRILLE_RE.search(lg) or self._is_footer(lg.upper()):
                pied.append(lg)
            elif not _SEPARATEUR_RE.match(lg):
                corps.append(lg)

        a_cadre = lignes[idx_entete].count('|') >= n + 1
        if a_cadre:
            cellules_par_ligne = []
            for lg in corps:
                segments = lg.split('|')[1:-1]
                if len(segments) != n:
                    continue
                cellules_par_ligne.append([
                    (s[1:] if s.startswith(' ') else s).rstrip() for s in segments
                ])
        else:
            coupures = _coupures_par_gouttieres(corps, entete) + [None]
            cellules_par_ligne = [
                [lg[coupures[k]:coupures[k + 1]].rstrip() for k in range(n)]
                for lg in corps
            ]
            # Marge commune retirée colonne par colonne : elle vient de la
            # position de la coupure, pas du document ; l'alignement relatif
            # des lignes entre elles est conservé.
            for k in range(n):
                marges = [
                    len(c[k]) - len(c[k].lstrip()) for c in cellules_par_ligne if c[k].strip()
                ]
                retrait = min(marges, default=0)
                for c in cellules_par_ligne:
                    c[k] = c[k][retrait:]

        rows = []
        for i, cellules in enumerate(cellules_par_ligne):
            if i in sections:
                rows.append({'type': 'section', 'text': sections[i]})
            if any(c.strip() for c in cellules):
                rows.append({'type': 'data', 'cells': cellules, 'confidence': [100] * n})
        if len(cellules_par_ligne) in sections:
            rows.append({'type': 'section', 'text': sections[len(cellules_par_ligne)]})
        pied_brut = nettoyer_lignes_pied(pied, self._tpl.footer_left_label)
        meta = analyser_pied(pied_brut, decor=self._decor_pied())
        meta['PIED_BRUT'] = pied_brut
        logo = logo_pied(pied, self._tpl.footer_left_label)
        if logo:
            meta['LOGO'] = logo
        # En-tête reconnu = tableau, même sans ligne (CABLE : RESERVE) : la page
        # vide est conservée telle quelle dans le classeur.
        return {
            'success': True,
            'page_num': page_num + 1,
            'image_path': f'page_{page_num + 1}',
            'headers': colonnes,
            'rows': rows,
            'metadata': meta,
            'detection_method': 'pdf-grille',
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

    def _decor_pied(self):
        return mots_decor([self._tpl.footer_row1_format, self._tpl.footer_row2_format])

    def _extract_meta(self, footer_lines: List[List]) -> Dict:
        """Paires LIBELLÉ : valeur du pied (pied_page), lignes brutes dans PIED_BRUT."""
        lignes = [' '.join(w[4] for w in line) for line in footer_lines]
        pied_brut = nettoyer_lignes_pied(lignes, self._tpl.footer_left_label)
        meta = analyser_pied(pied_brut, decor=self._decor_pied())
        meta['PIED_BRUT'] = pied_brut
        logo = logo_pied(lignes, self._tpl.footer_left_label)
        if logo:
            meta['LOGO'] = logo
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
