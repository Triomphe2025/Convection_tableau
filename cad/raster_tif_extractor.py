"""Extraction géométrie et textes d'une image raster (TIF/PNG/JPG) via OpenCV."""
import math
from pathlib import Path

from config import Config
from .models import CadDocument, CadPage, CadEntity, EntityKind


_DEFAULT_DPI = 300


def _read_dpi(pil_image) -> float:
    """Lit le DPI depuis les métadonnées TIFF/EXIF ; retourne _DEFAULT_DPI si absent."""
    info = getattr(pil_image, 'info', {})
    dpi_val = info.get('dpi')
    if dpi_val:
        try:
            return float(dpi_val[0]) if hasattr(dpi_val, '__iter__') else float(dpi_val)
        except (TypeError, ValueError):
            pass
    return _DEFAULT_DPI


def _px_to_mm(px: float, dpi: float) -> float:
    """Convertit des pixels en millimètres selon le DPI de l'image."""
    return px * 25.4 / dpi


def _preprocess(gray):
    """
    Débruitage puis seuillage adaptatif avec fermeture morphologique.
    Pour images > 10 Mpx : GaussianBlur (linéaire) au lieu de fastNlMeansDenoising
    qui alloue des images intégrales internes ~4× la taille de l'image (300+ Mo OOM).
    """
    import cv2
    pixel_count = gray.shape[0] * gray.shape[1]
    if pixel_count > 10_000_000:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    else:
        blurred = cv2.fastNlMeansDenoising(gray, h=15)
    binary = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=15, C=4,
    )
    del blurred
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)


def _separate_text_geometry(binary, dpi: float, text_max_dim_mm: float = 7.62):
    """
    Sépare texte/symboles (petites composantes) de la géométrie (grandes composantes).
    Le seuil est exprimé en mm physiques — reste correct après auto-downscale.
    """
    import cv2
    import numpy as np
    text_max_dim_px = int(text_max_dim_mm * dpi / 25.4)   # DPI-agnostique
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    geom = np.zeros_like(binary)
    text = np.zeros_like(binary)
    for lbl in range(1, n_labels):
        w = stats[lbl, cv2.CC_STAT_WIDTH]
        h = stats[lbl, cv2.CC_STAT_HEIGHT]
        mask = (labels == lbl).astype(np.uint8) * 255
        if max(w, h) < text_max_dim_px:
            text = cv2.bitwise_or(text, mask)
        else:
            geom = cv2.bitwise_or(geom, mask)
    return geom, text


def _skeletonize(binary) -> object:
    """Zhang-Suen via skimage si disponible, boucle cv2 en fallback."""
    import cv2
    import numpy as np
    if cv2.countNonZero(binary) == 0:
        return binary
    try:
        from skimage.morphology import skeletonize as _ski_skel
        skel_bool = _ski_skel(binary > 0)
        return skel_bool.astype(np.uint8) * 255
    except ImportError:
        skel = np.zeros_like(binary)
        img = binary.copy()
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        while True:
            eroded = cv2.erode(img, element)
            temp = cv2.dilate(eroded, element)
            temp = cv2.subtract(img, temp)
            skel = cv2.bitwise_or(skel, temp)
            img = eroded.copy()
            if cv2.countNonZero(img) == 0:
                break
        return skel


def _prune_spurs(skel, min_px: int = 8):
    """
    Supprime les micro-branches parasites (amorces de squelette aux croisements).
    Détecte les pixels terminaux (1 seul voisin 8-connexe) et les efface itérativement.
    """
    import cv2
    import numpy as np
    out = skel.copy()
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(min_px):
        neighbor_sum = cv2.filter2D(
            (out > 0).astype(np.uint8), -1, kernel
        ) * (out > 0).astype(np.uint8)
        tips = (neighbor_sum == 2).astype(np.uint8) * 255
        out = cv2.subtract(out, tips)
    return out


def _compute_distance_map(binary):
    """
    Carte de distance Euclidienne : valeur au squelette = demi-épaisseur du trait.
    Utilisée pour estimer l'épaisseur réelle de chaque tronçon détecté.
    """
    import cv2
    return cv2.distanceTransform(binary, cv2.DIST_L2, 5)


def _lineweight_from_radius(radius_mm: float) -> float:
    """
    Classe une demi-épaisseur en 2 paliers standards (diamètre du trait).
    Plafonné à 0.35mm — évite l'effet "région remplie" sur les câbles épais.
    """
    diam = radius_mm * 2.0
    if diam < 0.25:
        return 0.18    # fin : cotations, amorces
    else:
        return 0.35    # standard : géométrie principale (plafonné, jamais 0.60mm)


def _trace_paths_from_skeleton(skel, dist_map, dpi: float) -> list:
    """
    Extrait des chemins ordonnés depuis le squelette par parcours BFS.
    Commence depuis les pixels terminaux (1 voisin 8-connexe) pour couvrir
    toutes les branches. Retourne une liste de (pixels_xy, épaisseur_mm).
    """
    import cv2
    import numpy as np

    h, w = skel.shape
    visited = np.zeros_like(skel, dtype=bool)
    kernel_count = np.ones((3, 3), np.uint8)

    neighbor_count = cv2.filter2D(
        (skel > 0).astype(np.uint8), -1, kernel_count
    ) * (skel > 0).astype(np.uint8)

    endpoints = np.argwhere(neighbor_count == 2)
    junctions = set(map(tuple, np.argwhere(neighbor_count >= 4)))

    def _follow(sy, sx):
        path_px = [(sx, sy)]
        visited[sy, sx] = True
        cy, cx = sy, sx
        while True:
            found = False
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = cy + dy, cx + dx
                    if (0 <= ny < h and 0 <= nx < w
                            and skel[ny, nx] > 0 and not visited[ny, nx]):
                        visited[ny, nx] = True
                        path_px.append((nx, ny))
                        cy, cx = ny, nx
                        found = True
                        break
                if found:
                    break
            if not found or (cy, cx) in junctions:
                break
        return path_px

    paths = []

    for ep in endpoints:
        sy, sx = int(ep[0]), int(ep[1])
        if visited[sy, sx]:
            continue
        path_px = _follow(sy, sx)
        if len(path_px) < 3:
            continue
        trim = max(1, len(path_px) // 5)
        radii = [dist_map[py, px] for px, py in path_px[trim:-trim]]
        median_r_px = float(np.median(radii)) if radii else 1.0
        paths.append((path_px, _px_to_mm(median_r_px, dpi)))

    remaining = np.argwhere((skel > 0) & ~visited)
    for pt in remaining:
        sy, sx = int(pt[0]), int(pt[1])
        if visited[sy, sx]:
            continue
        path_px = _follow(sy, sx)
        if len(path_px) >= 3:
            radii = [dist_map[py, px] for px, py in path_px]
            median_r_mm = _px_to_mm(float(np.median(radii)), dpi)
            paths.append((path_px, median_r_mm))

    return paths


def _is_smooth_curve(pts_mm: list, corner_angle_deg: float = 25.0) -> bool:
    """
    Retourne True si le chemin est une courbe douce sans coin vif.
    Une droite quasi-parfaite (courbure totale < 5°) retourne False
    pour éviter de générer des SPLINE inutiles sur des segments droits.
    """
    if len(pts_mm) < 3:
        return False
    angles = []
    for i in range(1, len(pts_mm) - 1):
        ax, ay = pts_mm[i - 1]
        bx, by = pts_mm[i]
        cx, cy = pts_mm[i + 1]
        v1x, v1y = bx - ax, by - ay
        v2x, v2y = cx - bx, cy - by
        norm1 = math.sqrt(v1x ** 2 + v1y ** 2)
        norm2 = math.sqrt(v2x ** 2 + v2y ** 2)
        if norm1 < 1e-9 or norm2 < 1e-9:
            continue
        cos_a = (v1x * v2x + v1y * v2y) / (norm1 * norm2)
        cos_a = max(-1.0, min(1.0, cos_a))
        angle = math.degrees(math.acos(cos_a))
        if angle > corner_angle_deg:
            return False    # coin vif → pas une courbe douce
        angles.append(angle)
    if not angles:
        return False
    # Droite pratiquement parfaite : courbure totale négligeable → POLYLINE
    if sum(angles) < 5.0:
        return False
    return True


def _extract_geometry_entities(
    geom_mask, dist_map, dpi: float, epsilon_mm: float = 0.5,
) -> list:
    """
    Pipeline géométrie : squelettisation → élagage → traçage → SPLINE ou LWPOLYLINE.
    Chaque entité porte son épaisseur réelle détectée par distance transform.
    """
    import cv2
    import numpy as np

    skeleton = _skeletonize(geom_mask)
    # Élagage adaptatif : proportionnel à l'épaisseur max des traits
    _spur_min = max(8, int(dist_map.max() * 0.5))
    skeleton = _prune_spurs(skeleton, min_px=_spur_min)

    if cv2.countNonZero(skeleton) == 0:
        return []

    h_img = geom_mask.shape[0]
    epsilon_px = epsilon_mm * dpi / 25.4
    paths_raw = _trace_paths_from_skeleton(skeleton, dist_map, dpi)

    from .curve_fitter import group_collinear_fragments, detect_dash_pattern, \
        merge_collinear_to_one

    # Convertir tous les chemins pixels → mm
    all_paths_mm = []
    lineweights = {}  # index → lineweight

    for i, (path_px, median_r_mm) in enumerate(paths_raw):
        pts_arr = np.array(path_px, dtype=np.float32).reshape(-1, 1, 2)
        approx = cv2.approxPolyDP(pts_arr, epsilon_px, closed=False)
        pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
        if len(pts) < 2:
            continue
        pts_mm = [(_px_to_mm(x, dpi), _px_to_mm(h_img - y, dpi)) for x, y in pts]
        all_paths_mm.append(pts_mm)
        lineweights[len(all_paths_mm) - 1] = _lineweight_from_radius(median_r_mm)

    if not all_paths_mm:
        return []

    entities = []

    # Séparer fragments courts (candidats tirets) et segments longs
    groupes_courts, segments_longs = group_collinear_fragments(all_paths_mm, dpi=dpi)

    # Traiter les groupes de fragments courts
    for groupe in groupes_courts:
        pattern = detect_dash_pattern(groupe, dpi=dpi)
        if pattern['is_dashed'] and pattern['pt_start'] and pattern['pt_end']:
            # Ligne tiretée reconstituée → une seule LWPOLYLINE DASHED
            ent = CadEntity(
                kind=EntityKind.POLYLINE,
                geometry={
                    'points': [pattern['pt_start'], pattern['pt_end']],
                    'closed': False,
                },
                layer='CABLES_EXISTANTS',
                color=(0, 0, 0),
            )
            ent.lineweight = 0.18
            ent.linetype = 'DASHED'
            ent.ltscale = pattern['ltscale']
            entities.append(ent)
        else:
            # Fragments indépendants → POLYLINE courtes individuelles
            for frag in groupe:
                if len(frag) < 2:
                    continue
                ent = CadEntity(
                    kind=EntityKind.POLYLINE,
                    geometry={'points': frag, 'closed': False},
                    layer='GEOMETRIE',
                    color=(0, 0, 0),
                )
                ent.lineweight = 0.18
                entities.append(ent)

    # Traiter les segments longs (câbles principaux) — fusion en un seul segment par droite
    fusionnes = merge_collinear_to_one(segments_longs)
    for pt_start, pt_end in fusionnes:
        ent = CadEntity(
            kind=EntityKind.POLYLINE,
            geometry={'points': [pt_start, pt_end], 'closed': False},
            layer='CABLES',
            color=(0, 0, 0),
        )
        ent.lineweight = 0.35
        entities.append(ent)

    # ── Post-traitement : fusion des micro-segments et snapping orthogonal ──
    from .segment_merger import merge_collinear_entities
    from .curve_fitter import snap_to_orthogonal

    # Séparer entités GEOMETRIE (à fusionner) des autres calques
    geom_entities = [e for e in entities if e.layer == 'GEOMETRIE']
    other_entities = [e for e in entities if e.layer != 'GEOMETRIE']

    if geom_entities:
        geom_pts = [e.geometry['points'] for e in geom_entities]
        # Fusion des micro-segments
        merged_pts = merge_collinear_entities(
            geom_pts,
            eps_gap_mm=Config.CAD_EPS_GAP_MM,
            eps_rdp_mm=0.5,
        )
        # Snapping orthogonal sur les chaînes fusionnées
        merged_entities = []
        for chain_pts in merged_pts:
            snapped = snap_to_orthogonal(chain_pts, theta_snap_deg=5.0)
            if len(snapped) >= 2:
                # Filtrer les micro-entités < 2mm — s'affichent comme des points dans AutoCAD
                _len = sum(
                    math.sqrt(
                        (snapped[i + 1][0] - snapped[i][0]) ** 2
                        + (snapped[i + 1][1] - snapped[i][1]) ** 2
                    )
                    for i in range(len(snapped) - 1)
                )
                if _len < 2.0:
                    continue
                ent = CadEntity(
                    kind=EntityKind.POLYLINE,
                    geometry={'points': snapped, 'closed': False},
                    layer='GEOMETRIE',
                    color=(0, 0, 0),
                )
                ent.lineweight = 0.25  # épaisseur standard trait géométrique
                merged_entities.append(ent)
        entities = other_entities + merged_entities
    # ── Fin post-traitement ──────────────────────────────────────────────────

    return entities


def _extract_text_entities(text_mask, dpi: float, min_area_mm2: float = 0.5) -> list:
    """
    Trace les contours des petites composantes (texte, symboles) en LWPOLYLINE.
    Préserve la forme des glyphes mieux que la squelettisation sur les petits traits.
    """
    import cv2
    min_area_px = min_area_mm2 * (dpi / 25.4) ** 2
    contours, _ = cv2.findContours(text_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h_img = text_mask.shape[0]
    entities = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area_px:
            continue
        eps = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, eps, True)
        if len(approx) < 2:
            continue
        pts_mm = [
            (_px_to_mm(int(p[0][0]), dpi), _px_to_mm(h_img - int(p[0][1]), dpi))
            for p in approx
        ]
        ent = CadEntity(
            kind=EntityKind.POLYLINE,
            geometry={'points': pts_mm, 'closed': True},
            layer='TEXTE',
            color=(0, 0, 0),
        )
        ent.lineweight = 0.18
        entities.append(ent)
    return entities


def _process_page(pil_image, page_index: int) -> CadPage:
    """
    Pipeline avancé : séparation texte/géométrie → centerlines (squelette) pour
    la géométrie + contours glyphes pour le texte + épaisseurs par distance transform.
    """
    import numpy as np
    dpi = _read_dpi(pil_image)
    w_mm = _px_to_mm(pil_image.width, dpi)
    h_mm = _px_to_mm(pil_image.height, dpi)

    cad_page = CadPage(
        width=w_mm,
        height=h_mm,
        source_mode='raster',
        page_index=page_index,
    )

    gray = np.array(pil_image.convert('L'))
    if gray.size == 0:
        cad_page.warnings.append(f"Page {page_index + 1} : image vide ignorée")
        return cad_page

    # Pleine résolution — OOM résolu par cv2.distanceTransform (float32)
    # Le downscale silencieux dégradait le texte en dessous du seuil de détection Potrace.
    if gray.shape[0] * gray.shape[1] > 20_000_000:
        cad_page.warnings.append(
            f"Image {gray.shape[1]}×{gray.shape[0]} px"
            f" — traitement pleine résolution (peut nécessiter > 2 Go RAM)"
        )

    try:
        import gc
        binary = _preprocess(gray)
        del gray
        gc.collect()

        dist_map = _compute_distance_map(binary)
        geom_mask, text_mask = _separate_text_geometry(binary, dpi=dpi)
        del binary
        gc.collect()

        geom_entities = _extract_geometry_entities(geom_mask, dist_map, dpi)
        del geom_mask, dist_map
        gc.collect()
        cad_page.entities.extend(geom_entities)

        del text_mask   # texte ignoré — blobs parasites dans AutoCAD
    except Exception as e:
        cad_page.warnings.append(f"Page {page_index + 1} : erreur vectorisation : {e}")

    return cad_page


def extract_raster_tif(
    path: Path,
    page_indices: list = None,
    on_progress=None,
    on_log=None,
) -> CadDocument:
    """
    Extrait lignes et textes d'une image raster (TIF multi-page, PNG, JPG, BMP).

    Returns:
        CadDocument avec une CadPage par frame traitée.
    """
    try:
        from PIL import Image
    except ImportError as e:
        raise ImportError("Pillow est requis pour traiter les fichiers TIF/PNG/JPG.") from e

    path = Path(path)
    doc_cad = CadDocument(source_path=path)

    pil_img = Image.open(str(path))

    # Collecte de toutes les frames (support TIF multi-page via PIL seek)
    frames = []
    try:
        while True:
            frames.append(pil_img.copy())
            pil_img.seek(pil_img.tell() + 1)
    except EOFError:
        pass

    if not frames:
        frames = [pil_img.copy()]

    if page_indices is None:
        page_indices = list(range(len(frames)))

    total = len(page_indices)
    for i, idx in enumerate(page_indices):
        if idx >= len(frames):
            continue
        if on_log:
            on_log(f"  Page {idx + 1}/{len(frames)} — vectorisation raster…")
        try:
            cad_page = _process_page(frames[idx], page_index=idx)
        except Exception as e:
            cad_page = CadPage(width=0, height=0, source_mode='raster', page_index=idx)
            cad_page.warnings.append(f"Page {idx + 1} ignorée : {e}")
        doc_cad.pages.append(cad_page)
        if on_progress:
            on_progress((i + 1) / total)

    return doc_cad
