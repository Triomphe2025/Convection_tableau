"""
Détection des tableaux de légende dans un PDF et création de blocs
AutoCAD réutilisables (BLOCK definitions) dans le DXF via ezdxf.

Pipeline :
  pdf page → detect_legend_pages() → extract_table_rows() → create_dxf_blocks()
"""
from __future__ import annotations
import re
from typing import Callable, Optional


# Seuils pour identifier une page de tableau de légende
_MIN_TABLE_ROWS = 4        # nb min de lignes cohérentes
_MIN_TABLE_COLS = 2        # nb min de colonnes détectées


# ── Détection de pages de légende ────────────────────────────────────────────

def detect_legend_pages(pdf) -> list[int]:
    """
    Retourne les indices des pages PDF contenant un tableau de légende.
    Critère : structure tabulaire avec ≥ _MIN_TABLE_ROWS lignes alignées.
    """
    legend_pages = []
    for page_idx in range(len(pdf)):
        page = pdf[page_idx]
        if _page_has_table(page):
            legend_pages.append(page_idx)
    return legend_pages


def _page_has_table(page) -> bool:
    """Vérifie si une page contient une structure tabulaire."""
    try:
        # PyMuPDF 1.23+ : détection native des tableaux
        tabs = page.find_tables()
        if tabs and len(tabs.tables) >= 1:
            for t in tabs.tables:
                if t.row_count >= _MIN_TABLE_ROWS and t.col_count >= _MIN_TABLE_COLS:
                    return True
    except AttributeError:
        pass

    # Fallback : analyse des blocs de texte alignés verticalement
    blocks = page.get_text('dict').get('blocks', [])
    text_blocks = [b for b in blocks if b.get('type') == 0]
    if len(text_blocks) < _MIN_TABLE_ROWS:
        return False

    # Détecter des colonnes : regrouper les blocs par position X similaire
    x_positions = [round(b['bbox'][0], -1) for b in text_blocks]  # arrondi à 10px
    x_counts = {}
    for x in x_positions:
        x_counts[x] = x_counts.get(x, 0) + 1
    dominant_columns = [x for x, cnt in x_counts.items() if cnt >= _MIN_TABLE_ROWS]
    return len(dominant_columns) >= _MIN_TABLE_COLS


# ── Extraction des lignes de tableau ─────────────────────────────────────────

def extract_table_rows(page) -> list[dict]:
    """
    Extrait les lignes d'un tableau de légende depuis une page PDF.
    Retourne une liste de dicts :
      {code, libelle, description, bbox}
    """
    rows = []

    # Essai 1 : API native find_tables (PyMuPDF 1.23+)
    try:
        tabs = page.find_tables()
        if tabs and tabs.tables:
            for table in tabs.tables:
                extracted = table.extract()
                for row in extracted:
                    row_clean = [_clean_cell(c) for c in row]
                    row_clean = [c for c in row_clean if c]  # supprimer les vides
                    if len(row_clean) >= 2:
                        rows.append(_row_to_dict(row_clean))
            if rows:
                return _deduplicate(rows)
    except (AttributeError, Exception):
        pass

    # Essai 2 : extraction textuelle structurée par colonnes
    rows = _extract_rows_by_columns(page)
    return _deduplicate(rows)


def _clean_cell(value) -> str:
    """Nettoie une cellule de tableau (None, espaces, retours chariot)."""
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()


def _row_to_dict(cells: list[str]) -> dict:
    """Convertit une liste de cellules en dict code/libellé/description."""
    code = cells[0] if len(cells) > 0 else ''
    libelle = cells[1] if len(cells) > 1 else ''
    description = ' — '.join(cells[2:]) if len(cells) > 2 else ''
    return {
        'code': code,
        'libelle': libelle,
        'description': description,
    }


def _extract_rows_by_columns(page) -> list[dict]:
    """Fallback : regroupe les spans texte par ligne Y pour simuler un tableau."""
    blocks = page.get_text('dict').get('blocks', [])
    all_spans = []
    for block in blocks:
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                txt = span.get('text', '').strip()
                if txt:
                    bbox = span.get('bbox', (0, 0, 0, 0))
                    all_spans.append({
                        'text': txt,
                        'x': bbox[0],
                        'y': round(bbox[1], -1),   # regroupement par Y à 10px
                    })

    if not all_spans:
        return []

    # Regrouper par Y (ligne)
    from collections import defaultdict
    by_y = defaultdict(list)
    for s in all_spans:
        by_y[s['y']].append(s)

    rows = []
    for y, spans in sorted(by_y.items()):
        spans_sorted = sorted(spans, key=lambda s: s['x'])
        cells = [s['text'] for s in spans_sorted]
        if len(cells) >= 2:
            rows.append(_row_to_dict(cells))

    return rows


def _deduplicate(rows: list[dict]) -> list[dict]:
    """Supprime les doublons (même code) et les lignes d'en-tête."""
    seen = set()
    result = []
    header_words = {'code', 'ref', 'désignation', 'libellé', 'description',
                    'symbole', 'nom', 'type', 'n°', 'repère'}
    for row in rows:
        code = row.get('code', '').strip()
        if not code:
            continue
        if code.lower() in header_words:
            continue
        if code in seen:
            continue
        seen.add(code)
        result.append(row)
    return result


# ── Création des blocs DXF ────────────────────────────────────────────────────

_BLOCK_SIZE_MM = 10.0      # emprise par défaut d'un bloc symbole (10×10 mm)


def create_dxf_blocks(dxf_doc, rows: list[dict],
                      on_log: Optional[Callable] = None) -> int:
    """
    Crée des définitions de BLOCK AutoCAD dans le document DXF.
    Chaque ligne du tableau → 1 BLOCK (rectangle + code + libellé).
    Retourne le nombre de blocs créés.
    """
    n_created = 0
    for row in rows:
        code = _sanitize_block_name(row.get('code', ''))
        if not code:
            continue
        libelle = row.get('libelle', '')
        desc = row.get('description', '')

        try:
            block = _create_one_block(dxf_doc, code, libelle, desc)
            n_created += 1
            if on_log:
                on_log(f"  ✓ BLOCK [{code}] — {libelle}")
        except Exception as e:
            if on_log:
                on_log(f"  ⚠ Bloc [{code}] ignoré : {e}")

    return n_created


def _sanitize_block_name(name: str) -> str:
    """Nettoie un nom de bloc pour le rendre valide en DXF (pas d'espaces, etc.)."""
    name = name.strip()
    # Remplacer les caractères non autorisés
    name = re.sub(r'[^\w\-.]', '_', name)
    name = name[:31]    # longueur max DXF
    return name


def _create_one_block(dxf_doc, code: str, libelle: str, desc: str):
    """
    Crée une définition de BLOCK dans le document DXF.

    Structure visuelle du bloc (10×10 mm) :
      ┌──────────┐
      │  CODE    │  ← texte code centré
      │  libellé │  ← texte libellé (petit)
      └──────────┘
    """
    s = _BLOCK_SIZE_MM

    # Vérifier si le bloc existe déjà
    if code in dxf_doc.blocks:
        return dxf_doc.blocks[code]

    block = dxf_doc.blocks.new(name=code)

    # Rectangle de contour
    block.add_lwpolyline(
        [(0, 0), (s, 0), (s, s), (0, s)],
        dxfattribs={'layer': '0', 'closed': True},
    )

    # Texte principal : code
    block.add_text(
        code,
        dxfattribs={
            'layer': '0',
            'height': s * 0.25,
            'insert': (s / 2, s * 0.55),
            'halign': 1,    # centré H
            'align_point': (s / 2, s * 0.55),
        },
    )

    # Texte secondaire : libellé (tronqué à 20 car)
    if libelle:
        block.add_text(
            libelle[:20],
            dxfattribs={
                'layer': '0',
                'height': s * 0.15,
                'insert': (s / 2, s * 0.25),
                'halign': 1,
                'align_point': (s / 2, s * 0.25),
            },
        )

    # Attribut dynamique ATT_DESC (description modifiable dans AutoCAD)
    if desc:
        block.add_attdef(
            tag='ATT_DESC',
            insert=(0, -s * 0.4),
            dxfattribs={
                'layer': '0',
                'height': s * 0.12,
                'prompt': 'Description :',
                'text': desc[:40],
            },
        )

    return block
