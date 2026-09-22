"""Extraction de la géométrie d'un PDF vectoriel via PyMuPDF."""
import math
from pathlib import Path
from .models import CadDocument, CadPage, CadEntity, EntityKind

PT_TO_MM = 25.4 / 72.0     # 1 point PDF = 25.4/72 mm


def _pt(v: float) -> float:
    return v * PT_TO_MM


def _color_to_rgb(col) -> tuple:
    """Normalise une couleur PyMuPDF (None, float, tuple) en (r,g,b) 0-255."""
    if col is None:
        return (0, 0, 0)
    if isinstance(col, (int, float)):
        v = int(col * 255)
        return (v, v, v)
    if hasattr(col, '__iter__'):
        vals = list(col)
        if len(vals) >= 3:
            return tuple(int(c * 255) for c in vals[:3])
        if len(vals) == 1:
            v = int(vals[0] * 255)
            return (v, v, v)
    return (0, 0, 0)


def _dedup_texts(entities: list, tol_mm: float = 1.0) -> list:
    """
    Supprime les entités TEXT dupliquées.
    Deux textes sont considérés doublons si même contenu ET position ≤ tol_mm.
    Conserve le premier occurrence (content stream avant annotations).
    """
    kept = []
    for ent in entities:
        g = ent.geometry
        x, y, txt = g['x'], g['y'], g['text']
        is_dup = False
        for prev in kept:
            pg = prev.geometry
            if (pg['text'] == txt
                    and abs(pg['x'] - x) <= tol_mm
                    and abs(pg['y'] - y) <= tol_mm):
                is_dup = True
                break
        if not is_dup:
            kept.append(ent)
    return kept


def _remove_text_overlaps(entities: list, char_width_factor: float = 0.55) -> list:
    """
    Supprime les entités TEXT qui se chevauchent physiquement.

    Deux textes se chevauchent si, sur la même ligne (même Y ± 1 hauteur),
    la largeur estimée du premier dépasse le début du second.
    Dans ce cas, le texte le plus court (ou le second) est supprimé.

    char_width_factor : facteur largeur/hauteur par caractère (0.55 pour police prop.)
    """
    texts = [e for e in entities if e.kind == EntityKind.TEXT]
    other = [e for e in entities if e.kind != EntityKind.TEXT]

    if not texts:
        return entities

    # Trier par Y puis X pour traitement ligne par ligne
    texts.sort(key=lambda e: (round(e.geometry['y'] * 2), e.geometry['x']))

    kept = []
    removed = set()

    for i, e1 in enumerate(texts):
        if i in removed:
            continue
        g1 = e1.geometry
        x1, y1, h1 = g1['x'], g1['y'], g1['size']
        w1 = len(g1['text']) * h1 * char_width_factor   # largeur estimée

        for j, e2 in enumerate(texts):
            if j <= i or j in removed:
                continue
            g2 = e2.geometry
            x2, y2, h2 = g2['x'], g2['y'], g2['size']

            # Vérifier si sur la même ligne (Y proche)
            if abs(y1 - y2) > max(h1, h2) * 1.1:
                continue

            # Chevauchement horizontal réel : fin de e1 > début de e2 (si e1 à gauche)
            if x1 <= x2:
                overlap = (x1 + w1) - x2
            else:
                w2 = len(g2['text']) * h2 * char_width_factor
                overlap = (x2 + w2) - x1

            if overlap > h1 * 0.5:   # chevauchement > 50% d'une hauteur
                # Garder le plus long (plus d'information) ou le premier
                if len(g2['text']) > len(g1['text']):
                    removed.add(i)
                    break
                else:
                    removed.add(j)

    for i, ent in enumerate(texts):
        if i not in removed:
            kept.append(ent)

    return other + kept


def _dedup_lines(entities: list, tol_mm: float = 0.2) -> list:
    """
    Supprime les entités LINE dupliquées (même paire de points ± tol_mm).
    Fréquent dans les PDFs AutoCAD : traits dessinés deux fois sur des calques différents.
    """
    kept = []
    for ent in entities:
        if ent.kind != EntityKind.LINE:
            kept.append(ent)
            continue
        g = ent.geometry
        is_dup = False
        for prev in kept:
            if prev.kind != EntityKind.LINE:
                continue
            pg = prev.geometry
            # Même direction ou direction inversée
            same = (abs(pg['x1'] - g['x1']) <= tol_mm
                    and abs(pg['y1'] - g['y1']) <= tol_mm
                    and abs(pg['x2'] - g['x2']) <= tol_mm
                    and abs(pg['y2'] - g['y2']) <= tol_mm)
            rev  = (abs(pg['x1'] - g['x2']) <= tol_mm
                    and abs(pg['y1'] - g['y2']) <= tol_mm
                    and abs(pg['x2'] - g['x1']) <= tol_mm
                    and abs(pg['y2'] - g['y1']) <= tol_mm)
            if same or rev:
                is_dup = True
                break
        if not is_dup:
            kept.append(ent)
    return kept


def _span_angle(span: dict) -> float:
    """Calcule l'angle de rotation DXF (degrés) depuis le vecteur dir de PyMuPDF.
    PDF : Y vers le bas.  DXF : Y vers le haut → inverser le signe du sin.
    """
    direction = span.get('dir', (1.0, 0.0))
    dx, dy = direction[0], direction[1]
    return math.degrees(math.atan2(-dy, dx))


def _ocg_layer_map(pdf) -> dict:
    """Construit un mapping xref-OCG → nom de calque depuis le PDF."""
    mapping = {}
    try:
        for cfg in pdf.layer_ui_configs():
            num = cfg.get('number', -1)
            txt = cfg.get('text', '')
            if num >= 0 and txt:
                mapping[num] = txt
    except Exception:
        pass
    return mapping


def extract_vector_pdf(path: Path, page_indices: list = None) -> CadDocument:
    """Extrait lignes, polylignes, courbes et textes d'un PDF vectoriel."""
    import fitz

    path = Path(path)
    doc_cad = CadDocument(source_path=path)
    pdf = fitz.open(str(path))

    # Mapping des calques OCG (Optional Content Groups) du PDF
    ocg_map = _ocg_layer_map(pdf)

    if page_indices is None:
        page_indices = list(range(len(pdf)))

    for idx in page_indices:
        if idx >= len(pdf):
            continue
        page = pdf[idx]

        # get_drawings() retourne les coordonnées dans l'espace PHYSIQUE non-rotaté
        # (convention PyMuPDF : y pointant vers le bas depuis le haut).
        # page.rect donne les dimensions VISUELLES (après rotation) correctes pour le DXF.
        # La transformation_matrix est INCORRECTE pour les pages rotatées (voir tests) :
        # elle applique seulement un y-flip sans tenir compte de la rotation de page.
        # Formules correctes validées visuellement (comparaison PDF vs dessin généré) :
        #   rot=0  : x_dxf = raw_x*PT,       y_dxf = (mh - raw_y)*PT
        #   rot=90 : x_dxf = raw_y*PT,        y_dxf = raw_x*PT
        #   rot=180: x_dxf = (mw - raw_x)*PT, y_dxf = raw_y*PT
        #   rot=270: x_dxf = raw_y*PT,        y_dxf = (mw - raw_x)*PT  [testé ✓]

        rot = page.rotation
        mw_pts = page.mediabox.width   # largeur physique (avant rotation)
        mh_pts = page.mediabox.height  # hauteur physique

        # Dimensions visuelles (après rotation) pour le cadre DXF
        pw_mm = _pt(page.rect.width)
        ph_mm = _pt(page.rect.height)

        cad_page = CadPage(
            width=pw_mm,
            height=ph_mm,
            source_mode='vector',
            page_index=idx,
        )

        # Formules validées visuellement par comparaison avec le rendu PDF :
        #   rot=270 (cas PDF 717-6324-LL02) : x=raw_y*T, y=raw_x*T → CONFORME ✓
        #   Les autres rotations sont dérivées par symétrie et restent à valider.
        if rot == 90:
            def _vis(pt):
                # 90° CCW : symétrique de 270° → à valider si nécessaire
                return _pt(mh_pts - pt.y), _pt(mw_pts - pt.x)
        elif rot == 180:
            def _vis(pt):
                return _pt(mw_pts - pt.x), _pt(mh_pts - pt.y)
        elif rot == 270:
            def _vis(pt):
                # Validé visuellement sur 717-6324-LL02.pdf : x=raw_y, y=raw_x
                return _pt(pt.y), _pt(pt.x)
        else:   # rot == 0 ou inconnu
            def _vis(pt):
                return _pt(pt.x), _pt(mh_pts - pt.y)

        # ── Drawings (lignes, courbes, rectangles) ──────────────────
        for d in page.get_drawings():
            # Résoudre le nom de calque : OCG xref → nom lisible, sinon '0'
            raw_layer = d.get('layer')
            if isinstance(raw_layer, int) and raw_layer in ocg_map:
                layer = ocg_map[raw_layer]
            elif isinstance(raw_layer, str) and raw_layer:
                layer = raw_layer
            else:
                layer = '0'
            col_rgb = _color_to_rgb(d.get('color'))

            for item in d.get('items', []):
                if not item:
                    continue
                kind_code = item[0]

                if kind_code == 'l' and len(item) >= 3:
                    # Ligne simple — appliquer la matrice de rotation
                    x1, y1 = _vis(item[1])
                    x2, y2 = _vis(item[2])
                    cad_page.entities.append(CadEntity(
                        kind=EntityKind.LINE,
                        geometry={'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                        layer=layer, color=col_rgb,
                    ))

                elif kind_code == 're' and len(item) >= 2:
                    # Rectangle — transformer les 4 coins
                    r = item[1]
                    corners = [
                        fitz.Point(r.x0, r.y0), fitz.Point(r.x1, r.y0),
                        fitz.Point(r.x1, r.y1), fitz.Point(r.x0, r.y1),
                    ]
                    pts = [_vis(c) for c in corners]
                    cad_page.entities.append(CadEntity(
                        kind=EntityKind.RECT,
                        geometry={'points': pts},
                        layer=layer, color=col_rgb,
                    ))

                elif kind_code == 'c' and len(item) >= 2:
                    # Courbe Bézier → polyligne approchée
                    raw_pts = [item[i] for i in range(1, len(item))
                               if hasattr(item[i], 'x')]
                    if len(raw_pts) >= 2:
                        pts = [_vis(p) for p in raw_pts]
                        cad_page.entities.append(CadEntity(
                            kind=EntityKind.POLYLINE,
                            geometry={'points': pts},
                            layer=layer, color=col_rgb,
                        ))

                elif kind_code == 'qu' and len(item) >= 2:
                    # Quad → 4 coins
                    quad = item[1]
                    try:
                        pts = [_vis(quad.ul), _vis(quad.ur),
                               _vis(quad.lr), _vis(quad.ll)]
                        cad_page.entities.append(CadEntity(
                            kind=EntityKind.RECT,
                            geometry={'points': pts},
                            layer=layer, color=col_rgb,
                        ))
                    except AttributeError:
                        pass

        # ── Textes ──────────────────────────────────────────────────
        # Extraction par LIGNE (pas par span) pour éviter les interférences.
        # Plusieurs spans sur la même ligne logique PDF sont fusionnés en
        # une seule entité TEXT dans le DXF.
        try:
            text_dict = page.get_text('dict', sort=True,
                                      flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except TypeError:
            text_dict = page.get_text('dict')
        raw_texts = []
        for block in text_dict.get('blocks', []):
            if block.get('type') != 0:
                continue
            for line in block.get('lines', []):
                spans = [s for s in line.get('spans', [])
                         if s.get('text', '').strip()]
                if not spans:
                    continue

                # Fusionner tous les spans de la ligne en un seul texte
                # Utiliser l'origine du premier span (coin gauche de la ligne)
                first_span = spans[0]
                parts = []
                for s in spans:
                    t = s.get('text', '').strip()
                    if t:
                        parts.append(t)
                full_text = '  '.join(parts)   # double espace entre spans

                origin = first_span.get('origin', (0, 0))
                # Hauteur = max des spans de la ligne (évite les variations mineures)
                size_pt = max(s.get('size', 10) for s in spans)
                angle = _span_angle(first_span)

                tx, ty = _vis(fitz.Point(origin[0], origin[1]))
                raw_texts.append(CadEntity(
                    kind=EntityKind.TEXT,
                    geometry={
                        'x': tx,
                        'y': ty,
                        'text': full_text,
                        'size': max(_pt(size_pt), 1.0),
                        'angle': angle,
                    },
                    layer='TEXTES',
                    color=(0, 0, 0),
                ))

        # 1. Dédupliquer les textes identiques à proximité (tolérance 2mm)
        deduped = _dedup_texts(raw_texts, tol_mm=2.0)

        # 2. Supprimer les chevauchements physiques entre textes différents
        deduped = _remove_text_overlaps(deduped)

        for ent in deduped:
            cad_page.entities.append(ent)

        # 3. Dédupliquer les lignes géométriques (doublons fréquents AutoCAD)
        cad_page.entities = _dedup_lines(cad_page.entities, tol_mm=0.2)

        doc_cad.pages.append(cad_page)

    pdf.close()
    return doc_cad
