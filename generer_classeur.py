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
from openpyxl.worksheet.properties import PageSetupProperties
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
        if blur_pct > 40.0:
            blurry.append((img.name, blur_pct))
        method = result.get('detection_method', '?')
        label = _METHOD_LABEL.get(method, method)
        print(f"    colonnes : {label}", end='')
        if blur_pct > 40:
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
    expected_set = set(h.upper() for h in extractor._tpl.columns)
    for r in results:
        if not r.get('success'):
            continue
        if extractor._count_data_rows(r) < min_rows:
            ignores += 1
            continue
        # Au moins une colonne doit correspondre au template actif.
        # Élimine les pages de garde, sommaires, images de texte libre.
        headers_set = set(h.upper() for h in r.get('headers', []))
        if expected_set and not (headers_set & expected_set):
            ignores += 1
            continue
        # Densité minimale : ≥ 15 % des cellules de données doivent
        # contenir au moins un caractère alphanumérique.
        # Élimine les pages quasi-vides ou entièrement codées en gribouillage.
        all_cells = [
            cell
            for row in r.get('rows', [])
            if row.get('type') == 'data'
            for cell in row.get('cells', [])
        ]
        non_empty = sum(1 for c in all_cells if c and any(ch.isalnum() for ch in c))
        if non_empty / max(len(all_cells), 1) < 0.15:
            ignores += 1
            continue
        valides.append(r)

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

    # ── Mise en page A4 portrait — 1 tableau = 1 page ────────────────
    ws.page_setup.paperSize = 9          # 9 = A4
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.scale = None           # désactiver le % fixe sinon fitToWidth ignoré
    ws.page_setup.fitToWidth = 1         # largeur : 1 page
    ws.page_setup.fitToHeight = total    # hauteur : autant de pages que de tableaux
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    # 0.9 cm = 0.354 in (unité openpyxl = pouces)
    ws.page_margins = PageMargins(
        left=0.69, right=0.69,
        top=0.354, bottom=0.354,
        header=0, footer=0,
    )
    ws.print_options.horizontalCentered = True
    ws.print_options.verticalCentered = True

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
            n_word = len(valides_w)
            ws2 = wb.create_sheet("tableaux word")
            ws2.page_setup.paperSize = 9
            ws2.page_setup.orientation = 'portrait'
            ws2.page_setup.scale = None
            ws2.page_setup.fitToWidth = 1
            ws2.page_setup.fitToHeight = n_word
            ws2.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
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

                if j < n_word - 1:
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
# Reformatage d'un Excel existant
# ──────────────────────────────────────────────────────────────────────

def reformatter_excel(
    input_path: Path,
    output_path: Path,
    on_log=None,
    on_progress=None,
    row_height: float = None,
    col_width_default: float = None,
    col_width_signal: float = None,
    margin_top: float = None,
    margin_bottom: float = None,
    margin_left: float = None,
    margin_right: float = None,
    margin_header: float = None,
    margin_footer: float = None,
    sheets: list = None,
    n_cols_override: int = 0,
    sheet_cols: dict = None,
    page_size_override: int = 0,
    sheet_page_sizes: dict = None,
) -> int:
    """
    Reformate un classeur Excel existant avec les règles de mise en page
    définies dans Config :
      - PAGE_SIZE lignes par tableau (59)
      - Hauteur de ligne 12.6 pt
      - Saut de page direct après chaque tableau, zéro ligne vide entre
      - Ajustement automatique : 1 page en largeur, N pages en hauteur

    Détecte les tableaux par leurs lignes d'en-tête (fond gris D9D9D9
    ou mots-clés de colonnes). Copie les valeurs et la mise en forme
    cellule par cellule dans un nouveau classeur reformaté.

    Retourne le nombre de tableaux reformatés.
    """
    from copy import copy as _copy
    from openpyxl import load_workbook
    from openpyxl.cell.cell import MergedCell

    def _log(msg):
        if on_log:
            on_log(msg)

    def _copy_cell(src, dst):
        # has_style omis intentionnellement : certaines cellules avec bordures
        # ne le rapportent pas (style hérité de la ligne/colonne source).
        if isinstance(dst, MergedCell):
            return
        if isinstance(src, MergedCell):
            dst.value = None
            return
        dst.value = src.value
        dst.font = _copy(src.font)
        dst.border = _copy(src.border)
        dst.fill = _copy(src.fill)
        dst.alignment = _copy(src.alignment)
        dst.number_format = src.number_format

    from openpyxl.styles import Side, Border
    from openpyxl.worksheet.properties import WorksheetProperties

    page_size = Config.PAGE_SIZE
    if row_height is None:
        row_height = getattr(Config, 'FORMAT_ROW_HEIGHT', 12.6)
    if col_width_default is None:
        col_width_default = getattr(Config, 'FORMAT_COL_WIDTH_DEFAULT', 19)
    if col_width_signal is None:
        col_width_signal = getattr(Config, 'FORMAT_COL_WIDTH_SIGNAL', 33)
    if margin_top is None:
        margin_top = getattr(Config, 'FORMAT_MARGIN_TOP', 0.9)
    if margin_bottom is None:
        margin_bottom = getattr(Config, 'FORMAT_MARGIN_BOTTOM', 0.9)
    if margin_left is None:
        margin_left = getattr(Config, 'FORMAT_MARGIN_LEFT', 1.75)
    if margin_right is None:
        margin_right = getattr(Config, 'FORMAT_MARGIN_RIGHT', 1.75)
    if margin_header is None:
        margin_header = getattr(Config, 'FORMAT_MARGIN_HEADER', 0.0)
    if margin_footer is None:
        margin_footer = getattr(Config, 'FORMAT_MARGIN_FOOTER', 0.0)

    def _cm(v):
        """Convertit des centimètres en pouces (unité openpyxl PageMargins)."""
        return round(v / 2.54, 5)

    _log(f"Ouverture de {input_path.name}…")
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='.*wmf image.*', category=UserWarning)
        wb_in = load_workbook(str(input_path))
    wb_out = Workbook()

    # Supprimer la feuille vide créée par défaut
    default = wb_out.active
    if default:
        wb_out.remove(default)

    # Styles réutilisables
    _thin = Side(style='thin')
    _ns = Side(style=None)
    _data_border = Border(left=_thin, right=_thin, top=_ns, bottom=_ns)

    # Empreintes de fond considérées comme « en-tête »
    GREY_FILLS = {'FFD9D9D9', 'D9D9D9'}
    ORANGE_FILLS = {'FFFFA500', 'FFA500'}
    COL_KEYWORDS = {
        'BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES',
        'TENANT', 'ABOUTISSANT', 'FIL', 'JAR',
        'REPERE', 'DESIGNATION', 'TYPE',
    }
    # Marqueurs de pied de page
    # — Mots courts : correspondance EXACTE de valeur de cellule
    #   (évite les faux positifs sur les signaux du type "IN_MTI_001",
    #    "CABLE_ALSTOM_xxx", etc. qui contiennent le mot en sous-chaîne)
    FOOTER_KWS_EXACT = {'MTI', 'SIEMENS', 'ALSTOM', 'SCHNEIDER'}
    # — Phrases : recherche en sous-chaîne dans le texte joint (ok car peu
    #   probable dans un nom de signal)
    FOOTER_KWS_SUBSTR = {'P.E.T', 'BORNIER :', 'N° PLAN', 'NO PLAN'}

    def _is_footer(row_cells):
        vals = [str(c.value or '').strip().upper() for c in row_cells]
        joined = ' '.join(vals)
        return (
            any(v for v in vals if v) and
            (
                any(mk in vals for mk in FOOTER_KWS_EXACT) or
                any(mk in joined for mk in FOOTER_KWS_SUBSTR)
            )
        )

    def _has_value(row_cells):
        return any(
            c.value is not None and str(c.value).strip()
            for c in row_cells
        )

    def _measure_table(src_rows):
        """Retourne (n_main, n_footer) pour un bloc de lignes source.

        Reproduit exactement la logique du reformatage principal afin que
        le pré-calcul du maximum soit cohérent avec la taille réelle écrite.
        """
        last_content = 0
        for i, row in enumerate(src_rows):
            if _has_value(row):
                last_content = i
        content_rows = src_rows[:last_content + 1]

        footer_idxs = []
        for k in range(min(3, len(content_rows))):
            ri = len(content_rows) - 1 - k
            if _is_footer(content_rows[ri]):
                footer_idxs.insert(0, ri)
            elif _has_value(content_rows[ri]):
                break

        n_footer = len(footer_idxs)
        main_rows_m = list(
            content_rows[:footer_idxs[0]] if n_footer else content_rows
        )
        while main_rows_m and not _has_value(main_rows_m[-1]):
            main_rows_m.pop()
        return len(main_rows_m), n_footer

    total_tables = 0

    for sheet_name in wb_in.sheetnames:
        if sheets is not None and sheet_name not in sheets:
            _log(f"  ○ Feuille « {sheet_name} » ignorée.")
            continue
        ws_in = wb_in[sheet_name]
        _log(f"  Feuille « {sheet_name} »…")

        # ── Charger toutes les lignes ──────────────────────────────────
        all_rows = list(ws_in.iter_rows())
        if not all_rows:
            _log("  ⚠  Feuille vide — ignorée.")
            continue
        n_cols = max((len(r) for r in all_rows), default=1)

        # ── Détecter les lignes d'en-tête ─────────────────────────────
        header_indices = []
        for ri, row in enumerate(all_rows):
            vals = [str(c.value or '').strip().upper() for c in row]
            non_empty = [v for v in vals if v]
            if len(non_empty) < 2:
                continue
            has_kw = any(v in COL_KEYWORDS for v in vals)
            has_grey = any(
                c.fill and c.fill.fgColor and
                str(c.fill.fgColor.rgb).upper() in GREY_FILLS | ORANGE_FILLS
                for c in row
            )
            if (has_kw or has_grey) and not _is_footer(row):
                header_indices.append(ri)

        if not header_indices:
            _log("  ⚠  Aucun en-tête détecté — feuille copiée sans modification.")
            ws_cp = wb_out.create_sheet(title=sheet_name)
            for row in all_rows:
                for cell in row:
                    _copy_cell(cell, ws_cp.cell(row=cell.row, column=cell.column))
            for ltr, dim in ws_in.column_dimensions.items():
                ws_cp.column_dimensions[ltr].width = dim.width or 10
            continue

        n_tables = len(header_indices)
        total_tables += n_tables
        _log(f"  → {n_tables} tableau(x) détecté(s)")

        # Lignes par tableau : override par feuille > global > config.
        _ps = (sheet_page_sizes or {}).get(sheet_name, 0) or page_size_override
        _page_size = _ps if _ps > 0 else page_size

        # ── Pré-calcul : taille du plus grand tableau de la feuille ───────
        # Garantit que TOUS les tableaux ont exactement le même nombre de
        # lignes : celui du tableau le plus grand (données + en-tête + pied).
        max_content = 0
        for _ti, _h_idx in enumerate(header_indices):
            _nxt = header_indices[_ti + 1] if _ti + 1 < n_tables else len(all_rows)
            _n_main, _n_footer = _measure_table(all_rows[_h_idx:_nxt])
            max_content = max(max_content, _n_main + _n_footer)
        uniform_block_size = max(_page_size, max_content)
        _log(
            f"  → Bloc uniforme : {uniform_block_size} lignes / tableau"
            f" (max contenu={max_content}, page_size={_page_size})"
        )

        # Largeur réelle du tableau : override manuel > auto depuis l'en-tête.
        # L'override par feuille prend la priorité sur l'override global.
        _override = (sheet_cols or {}).get(sheet_name, 0) or n_cols_override
        if _override > 0:
            tbl_n_cols = _override
        else:
            # Auto : colonnes avec un nom reconnu dans l'en-tête, sans COLONNE_X.
            # Arrêt dès 2 cellules vides consécutives après la dernière colonne
            # nommée : évite que des cellules fantômes hors tableau (résidu d'un
            # reformatage défectueux) gonflent tbl_n_cols.
            tbl_n_cols = 0
            _empty_streak = 0
            for _tc in all_rows[header_indices[0]]:
                v = str(_tc.value or '').strip().upper()
                if v and not v.startswith('COLONNE_'):
                    tbl_n_cols = max(tbl_n_cols, _tc.column)
                    _empty_streak = 0
                elif tbl_n_cols > 0:
                    _empty_streak += 1
                    if _empty_streak >= 2:
                        break   # 2 vides consécutifs = fin de la zone en-tête
            if tbl_n_cols == 0:
                tbl_n_cols = n_cols

        # ── Créer la feuille de sortie ─────────────────────────────────
        ws_out = wb_out.create_sheet(title=sheet_name)
        ws_out.page_setup.paperSize = 9
        ws_out.page_setup.orientation = 'portrait'
        ws_out.page_setup.scale = None   # désactiver le pourcentage fixe
        ws_out.page_setup.fitToWidth = 1
        ws_out.page_setup.fitToHeight = n_tables  # 1 page par tableau
        # fitToPage doit être activé dans sheetProperties, pas dans page_setup
        if ws_out.sheet_properties is None:
            ws_out.sheet_properties = WorksheetProperties()
        ws_out.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws_out.page_margins = PageMargins(
            left=_cm(margin_left),
            right=_cm(margin_right),
            top=_cm(margin_top),
            bottom=_cm(margin_bottom),
            header=_cm(margin_header),
            footer=_cm(margin_footer),
        )
        ws_out.print_options.horizontalCentered = True

        # Détecter la colonne SIGNAL pour lui affecter une largeur spéciale
        signal_col_letter = None
        if header_indices:
            for _hcell in all_rows[header_indices[0]]:
                if 'SIGNAL' in str(_hcell.value or '').strip().upper():
                    signal_col_letter = get_column_letter(_hcell.column)
                    break

        # Largeurs fixes : SIGNAL = col_width_signal, autres = col_width_default
        # Limité à tbl_n_cols pour ne pas créer de colonnes fantômes au-delà du tableau.
        for ci in range(1, tbl_n_cols + 1):
            ltr = get_column_letter(ci)
            ws_out.column_dimensions[ltr].width = (
                col_width_signal if ltr == signal_col_letter
                else col_width_default
            )

        out_row = 1

        for ti, h_idx in enumerate(header_indices):
            _log(f"  ▶ Tableau {ti + 1} / {n_tables}…")
            if on_progress:
                on_progress(ti + 1, n_tables)
            # Étendue du tableau source (jusqu'au prochain en-tête ou fin)
            nxt = header_indices[ti + 1] if ti + 1 < n_tables else len(all_rows)
            src_rows = all_rows[h_idx:nxt]

            # Trouver la dernière ligne avec une valeur
            last_content = 0
            for i, row in enumerate(src_rows):
                if _has_value(row):
                    last_content = i
            content_rows = src_rows[:last_content + 1]

            # ── Séparer pied de page / corps ──────────────────────────
            # Scan de bas en haut : collecter les lignes de pied (max 3)
            footer_rows = []   # lignes de pied (ordre chronologique)
            footer_idxs = []   # indices dans content_rows
            for k in range(min(3, len(content_rows))):
                ri = len(content_rows) - 1 - k
                if _is_footer(content_rows[ri]):
                    footer_rows.insert(0, content_rows[ri])
                    footer_idxs.insert(0, ri)
                elif _has_value(content_rows[ri]):
                    break   # ligne non-pied avec valeur → arrêt

            n_footer = len(footer_rows)

            # Corps = tout jusqu'au pied, sans rembourrage vide en fin
            main_rows = list(
                content_rows[:footer_idxs[0]] if n_footer else content_rows
            )
            while main_rows and not _has_value(main_rows[-1]):
                main_rows.pop()
            n_main = len(main_rows)

            # ── Calcul du bloc ─────────────────────────────────────────
            # uniform_block_size : taille du plus grand tableau de la feuille.
            # Tous les tableaux sont mis à la même taille pour cohérence visuelle.
            block_size = uniform_block_size
            n_padding = block_size - n_main - n_footer
            end_row = out_row + block_size

            # Hauteur de ligne uniforme sur tout le bloc
            for ri in range(out_row, end_row):
                ws_out.row_dimensions[ri].height = row_height

            # ── 1. Corps (en-tête + données) ───────────────────────────
            main_src_start = h_idx + 1   # 1-based dans openpyxl
            main_offset = out_row - main_src_start
            for mr in list(ws_in.merged_cells.ranges):
                if (mr.min_row >= main_src_start
                        and mr.max_row <= main_src_start + n_main - 1
                        and mr.min_col <= tbl_n_cols):   # limiter aux colonnes du tableau
                    try:
                        ws_out.merge_cells(
                            start_row=mr.min_row + main_offset,
                            start_column=mr.min_col,
                            end_row=mr.max_row + main_offset,
                            end_column=min(mr.max_col, tbl_n_cols),
                        )
                    except Exception:
                        pass
            for i, row in enumerate(main_rows):
                dst_r = out_row + i
                for cell in row:
                    if cell.column > tbl_n_cols:   # ne pas écrire hors du tableau
                        break
                    _copy_cell(cell, ws_out.cell(row=dst_r, column=cell.column))

            # ── 2. Rembourrage — cellules vides avec bordures ──────────
            # IMPORTANT : écrire de vraies cellules (même vides) oblige
            # openpyxl à inclure ces lignes dans le XML. Sans cela,
            # max_row s'arrête à la dernière cellule écrite et les lignes
            # de rembourrage "disparaissent" du fichier.
            for ri in range(out_row + n_main, out_row + n_main + n_padding):
                for ci in range(1, tbl_n_cols + 1):
                    ws_out.cell(row=ri, column=ci).border = _data_border

            # ── 3. Pied de page (toujours en dernière position) ────────
            if footer_rows:
                foot_dst_start = out_row + n_main + n_padding
                foot_src_start = h_idx + footer_idxs[0] + 1   # 1-based
                foot_offset = foot_dst_start - foot_src_start

                # A — valeurs + styles AVANT les fusions.
                # Les cellules non-maîtresses sont encore des Cell normaux
                # à ce stade ; merge_cells() ne supprime pas les données
                # déjà écrites dans ws._cells, donc bordures et valeurs
                # survivent à la fusion dans le XML final.
                for i, row in enumerate(footer_rows):
                    dst_r = foot_dst_start + i
                    for cell in row:
                        if (not isinstance(cell, MergedCell)
                                and cell.column <= tbl_n_cols):
                            dst = ws_out.cell(row=dst_r, column=cell.column)
                            dst.value = cell.value
                            dst.font = _copy(cell.font)
                            dst.fill = _copy(cell.fill)
                            dst.alignment = _copy(cell.alignment)
                            dst.number_format = cell.number_format

                # B — bordures complètes sur toutes les positions du pied
                # (avant fusion, toutes les cellules sont encore accessibles)
                _full = Border(
                    left=_thin, right=_thin,
                    top=_thin, bottom=_thin,
                )
                for i in range(n_footer):
                    dst_r = foot_dst_start + i
                    for ci in range(1, tbl_n_cols + 1):
                        ws_out.cell(row=dst_r, column=ci).border = _full

                # C — fusions APRÈS valeurs et bordures
                for mr in list(ws_in.merged_cells.ranges):
                    if (mr.min_row >= foot_src_start
                            and mr.max_row <= foot_src_start + n_footer - 1
                            and mr.min_col <= tbl_n_cols):
                        try:
                            ws_out.merge_cells(
                                start_row=mr.min_row + foot_offset,
                                start_column=mr.min_col,
                                end_row=mr.max_row + foot_offset,
                                end_column=min(mr.max_col, tbl_n_cols),
                            )
                        except Exception:
                            pass

            # ── Saut de page après ce tableau (sauf le dernier) ────────
            if ti < n_tables - 1:
                ws_out.row_breaks.append(Break(id=end_row - 1))

            out_row = end_row

            _log(f"  ✓ Tableau {ti + 1}/{n_tables} "
                 f"({n_main} données + {n_padding} rembourrage + {n_footer} pied)")

        # Zone d'impression
        ws_out.print_area = f"A1:{get_column_letter(tbl_n_cols)}{out_row - 1}"

    try:
        wb_out.save(str(output_path))
    finally:
        wb_in.close()   # ferme le verrou Windows sur le fichier source
    _log(f"\n  ✓ Fichier reformaté : {output_path.name}  ({total_tables} tableau(x))")
    return total_tables


# ──────────────────────────────────────────────────────────────────────
# Mise à jour des espacements depuis un PDF source
# ──────────────────────────────────────────────────────────────────────

def appliquer_espacements_pdf(
    excel_path: Path,
    pdf_path: Path,
    output_path: Path,
    template=None,
    on_log=None,
    on_progress=None,
) -> int:
    """
    Lit les espacements proportionnels depuis le PDF source et les applique
    dans un Excel existant sans modifier les valeurs texte des cellules.

    Principe :
    1. Extraire les cellules du PDF avec OCR_PRESERVE_INTRA_CELL_SPACING=True
       → les positions PDF donnent les écarts réels entre blocs de mots.
    2. Construire un index normalisé : texte_sans_espaces → texte_espacé.
    3. Pour chaque cellule Excel dont la version normalisée est dans l'index,
       remplacer le contenu par la version avec espacements proportionnels.
       Les cellules sans correspondance ne sont pas touchées.

    Retourne le nombre de cellules modifiées.
    """
    from openpyxl import load_workbook
    from pdf_extractor import PdfTableExtractor, is_pymupdf_available
    from template import DEFAULT_TEMPLATE

    def _log(msg: str) -> None:
        if on_log:
            on_log(msg)

    if not is_pymupdf_available():
        raise RuntimeError(
            "PyMuPDF (fitz) requis.\n"
            "Installez-le avec : pip install pymupdf"
        )

    tpl = template or DEFAULT_TEMPLATE

    # ── Étape 1 : extraire les cellules avec espacements depuis le PDF ──
    _log(f"  Lecture du PDF : {pdf_path.name}...")
    if on_progress:
        on_progress(0, 3)

    pdf_ext = PdfTableExtractor(template=tpl)
    results, _ = pdf_ext.extract_all(pdf_path)

    # Index normalisé → version espacée (uniquement les cellules multi-espaces)
    # La clé supprime tous les espaces et met en majuscules pour la comparaison.
    spacing_map: Dict[str, str] = {}
    pages_ok = sum(1 for r in results if r.get('success'))

    for result in results:
        if not result.get('success'):
            continue
        for row in result.get('rows', []):
            if row.get('type') != 'data':
                continue
            for cell_val in row.get('cells', []):
                if not cell_val or '  ' not in cell_val:
                    continue  # pas d'espacement multiple → rien à apporter
                key = re.sub(r'\s+', '', cell_val.upper())
                if key and key not in spacing_map:
                    spacing_map[key] = cell_val

    _log(
        f"  → {pages_ok} pages PDF lues, "
        f"{len(spacing_map)} motif(s) d'espacement détecté(s)."
    )
    if on_progress:
        on_progress(1, 3)

    if not spacing_map:
        _log(
            "  Aucun espacement multiple trouvé dans le PDF.\n"
            "  Conseil : vérifiez que le PDF contient une couche texte\n"
            "  avec des positions de caractères précises (PDF natif ou\n"
            "  exporté depuis logiciel, pas un scan simple)."
        )
        if on_progress:
            on_progress(3, 3)
        return 0

    # ── Étape 2 : appliquer dans l'Excel ───────────────────────────────
    _log(f"  Application dans : {excel_path.name}...")
    wb = load_workbook(str(excel_path))
    updated = 0

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                val = cell.value
                if not isinstance(val, str) or ' ' not in val:
                    continue
                key = re.sub(r'\s+', '', val.upper())
                if not key:
                    continue
                spaced = spacing_map.get(key)
                # Appliquer uniquement si la version espacée DIFFÈRE
                # et contient bien les mêmes caractères (hors espaces)
                if spaced and spaced != val:
                    cell.value = spaced
                    updated += 1

    if on_progress:
        on_progress(2, 3)

    wb.save(str(output_path))
    if on_progress:
        on_progress(3, 3)

    _log(f"  → {updated} cellule(s) mise(s) à jour.")
    _log(f"  → Enregistré : {output_path.name}")
    return updated


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

    duree = time.time() - t0
    print('=' * 62)
    print(f'  TERMINÉ en {duree:.0f} s')
    print()
    print('  Fichier créé :')
    print('    → tous_les_borniers.xlsx')
    print('=' * 62)
    print()


if __name__ == '__main__':
    main()
