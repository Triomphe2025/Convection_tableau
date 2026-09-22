"""
Pipeline de vectorisation raster avancé TIF→DXF avec suivi par étape.

Ce module expose une fonction vectorize() qui orchestre les 7 étapes
nommées du pipeline, en appelant les callbacks on_step_start/on_step_done
à chaque transition. Il réutilise les fonctions bas niveau de
raster_tif_extractor sans les réécrire.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .models import CadDocument, CadEntity, CadPage, EntityKind

# ─── Seuils par défaut ───────────────────────────────────────────────────────
_TEXT_THRESH_PX = 60
_MAX_SAMPLES    = 180
_SPUR_LEN_PX    = 8.0
_CORNER_WINDOW  = 5
_CORNER_DEG     = 22.0
_MIN_CURVE_PTS  = 6
_POINT_TOL_MM       = 0.15
_MIN_ENTITY_LEN_MM  = 2.0   # longueur min d'une chaîne en mm (filtre micro-entités)

try:
    from config import Config as _C
    _TEXT_THRESH_PX    = getattr(_C, 'CAD_TEXT_THRESH_PX',     _TEXT_THRESH_PX)
    _MAX_SAMPLES       = getattr(_C, 'CAD_MAX_SAMPLES',         _MAX_SAMPLES)
    _SPUR_LEN_PX       = getattr(_C, 'CAD_SPUR_LEN_PX',        _SPUR_LEN_PX)
    _CORNER_WINDOW     = getattr(_C, 'CAD_CORNER_WINDOW',       _CORNER_WINDOW)
    _CORNER_DEG        = getattr(_C, 'CAD_CORNER_ANGLE_DEG',    _CORNER_DEG)
    _MIN_CURVE_PTS     = getattr(_C, 'CAD_MIN_CURVE_PTS',       _MIN_CURVE_PTS)
    _POINT_TOL_MM      = getattr(_C, 'CAD_POINT_TOL_MM',        _POINT_TOL_MM)
    _MIN_ENTITY_LEN_MM = getattr(_C, 'CAD_MIN_ENTITY_LEN_MM',   _MIN_ENTITY_LEN_MM)
except (ImportError, AttributeError):
    pass

# ─── Paramètres pré-lissage et fusion de coins ───────────────────────────────
_PRESMOOTH_SIGMA_PX = 2.5    # sigma du filtre gaussien avant détection de coin
_MIN_CORNER_SEP_PX  = 15.0   # distance min entre 2 coins consécutifs (en mm)

try:
    from config import Config as _C2
    _PRESMOOTH_SIGMA_PX = getattr(_C2, 'CAD_PRESMOOTH_SIGMA_PX', _PRESMOOTH_SIGMA_PX)
    _MIN_CORNER_SEP_PX  = getattr(_C2, 'CAD_MIN_CORNER_SEP_PX',  _MIN_CORNER_SEP_PX)
except (ImportError, AttributeError):
    pass

# Paramètres nettoyage boucles + assemblage chaînes (pipeline de référence v3)
_ANOMALY_RATIO        = 2.5    # ratio arc/corde — au-delà c'est une boucle locale parasite
_ANOMALY_MAX_CHORD_PX = 40.0   # corde max (px) — au-delà c'est de la vraie géométrie
_TANGENT_SAMPLE_PX    = 6      # nb de points pour estimer la tangente aux jonctions

# Détection sknw au chargement du module
try:
    import sknw as _sknw          # noqa: F401 (import de détection uniquement)
    _USE_SKNW = True
except ImportError:
    _USE_SKNW = False

# Noms des étapes exposées aux callbacks
ETAPES = [
    "chargement",
    "pretraitement",
    "separation",
    "squelettisation",
    "graphe",
    "vectorisation",
    "export",
]


def snap_lineweight(width_mm: float) -> float:
    """
    Retourne l'épaisseur en mm (CadEntity.lineweight est en mm).
    Le DXF writer multiplie par 100 pour obtenir les centièmes de mm ezdxf.
    """
    if width_mm < 0.40:
        return 0.09   # fin — dessin technique électrique
    if width_mm < 0.95:
        return 0.18   # normal
    return 0.25       # gras (cadres)


def detect_corners(
    pts_mm: np.ndarray,
    window: int = _CORNER_WINDOW,
    angle_deg: float = _CORNER_DEG,
) -> np.ndarray:
    """
    Détecte les coins sur le tracé DENSE (pas simplifié).
    Retourne un tableau bool True aux positions de coin.
    """
    n = len(pts_mm)
    corners = np.zeros(n, dtype=bool)
    if n < 2 * window + 1:
        corners[0] = corners[-1] = True
        return corners
    corners[0] = corners[-1] = True
    for i in range(window, n - window):
        v_in  = pts_mm[i] - pts_mm[i - window]
        v_out = pts_mm[i + window] - pts_mm[i]
        n_in  = np.linalg.norm(v_in)
        n_out = np.linalg.norm(v_out)
        if n_in < 1e-9 or n_out < 1e-9:
            continue
        cos_a = np.clip(np.dot(v_in, v_out) / (n_in * n_out), -1.0, 1.0)
        angle = math.degrees(math.acos(cos_a))
        if angle > angle_deg:
            corners[i] = True
    return corners


def fit_spline(
    pts_mm: np.ndarray,
    point_tol_mm: float = _POINT_TOL_MM,
    max_samples: int = _MAX_SAMPLES,
) -> Optional[tuple]:
    """
    Ajuste une B-spline de lissage par moindres carrés (scipy splprep, s>0).
    Retourne (degree, control_points, knots) ou None si scipy absent ou échec.
    """
    try:
        from scipy.interpolate import splprep
    except ImportError:
        return None

    # Rééchantillonnage régulier sur l'abscisse curviligne
    dists = np.cumsum(np.r_[0.0, np.linalg.norm(np.diff(pts_mm, axis=0), axis=1)])
    total = dists[-1]
    if total < 1e-9:
        return None
    n = min(max_samples, max(4, len(pts_mm)))
    u_uni = np.linspace(0.0, total, n)
    x_s = np.interp(u_uni, dists, pts_mm[:, 0])
    y_s = np.interp(u_uni, dists, pts_mm[:, 1])

    s = n * (point_tol_mm ** 2)
    try:
        tck, _ = splprep([x_s, y_s], k=3, s=s)
    except Exception:
        return None

    t, c, k = tck
    ctrl = list(zip(c[0], c[1]))
    if any(math.isnan(x) or math.isnan(y) for x, y in ctrl):
        return None
    return k, ctrl, list(t)


def presmooth_edge(chain_mm: np.ndarray, sigma: float = _PRESMOOTH_SIGMA_PX) -> np.ndarray:
    """
    Lisse le tracé dense par filtre gaussien 1D en fixant les extrémités.
    Les extrémités sont des nœuds du graphe topologique : elles doivent rester
    exactes pour maintenir la connectivité lors du découpage en tronçons.
    """
    from scipy.ndimage import gaussian_filter1d
    if len(chain_mm) <= int(2 * sigma) + 1:
        return chain_mm
    smoothed = chain_mm.copy().astype(float)
    smoothed[:, 0] = gaussian_filter1d(chain_mm[:, 0], sigma=sigma, mode='nearest')
    smoothed[:, 1] = gaussian_filter1d(chain_mm[:, 1], sigma=sigma, mode='nearest')
    smoothed[0]  = chain_mm[0]   # extrémité figée (nœud graphe)
    smoothed[-1] = chain_mm[-1]  # extrémité figée (nœud graphe)
    return smoothed


def merge_close_corners(
    corner_idxs: list,
    pts_mm: np.ndarray,
    min_sep_px: float = _MIN_CORNER_SEP_PX,
) -> list:
    """
    Fusionne les coins trop rapprochés (< min_sep_px mm) en gardant le premier.
    Deux détections à quelques pixels d'écart signalent un seul artefact de bruit.
    Les extrémités (premier et dernier index) sont toujours conservées.
    """
    if len(corner_idxs) <= 2:
        return corner_idxs
    kept = [corner_idxs[0]]
    for idx in corner_idxs[1:-1]:
        if np.linalg.norm(pts_mm[idx] - pts_mm[kept[-1]]) >= min_sep_px:
            kept.append(idx)
    kept.append(corner_idxs[-1])
    return kept


def _build_entities_from_paths(
    paths_with_widths: list,
    scale: float,
    max_samples: int,
) -> list:
    """
    Construit les CadEntity depuis une liste de (path_xy, width_mm).
    path_xy est une liste de tuples (x, y) en pixels.
    """
    entities = []
    for path_xy, width_mm in paths_with_widths:
        if len(path_xy) < 2:
            continue
        pts_arr = np.array(path_xy, dtype=float)  # shape (N, 2) — (x, y)
        pts_mm  = pts_arr * scale                  # passage en mm

        lw = snap_lineweight(width_mm)

        # Détection de coins + découpage en tronçons
        # Pré-lissage sur copie lissée ; découpage sur pts_mm original (connectivité)
        pts_mm_smooth = presmooth_edge(pts_mm)
        corners_mask  = detect_corners(pts_mm_smooth)
        corner_idxs   = merge_close_corners(
            np.where(corners_mask)[0].tolist(), pts_mm, _MIN_CORNER_SEP_PX
        )

        for seg_start, seg_end in zip(corner_idxs[:-1], corner_idxs[1:]):
            seg = pts_mm[seg_start:seg_end + 1]
            if len(seg) < 2:
                continue

            spline = None
            if len(seg) >= _MIN_CURVE_PTS:
                spline = fit_spline(seg, max_samples=max_samples)

            if spline is not None:
                degree, ctrl, knots = spline
                ent = CadEntity(
                    kind=EntityKind.SPLINE,
                    geometry={
                        'control_points': ctrl,
                        'knots': knots,
                        'degree': degree,
                        'closed': False,
                    },
                    layer='GEOMETRIE',
                    color=(0, 0, 0),
                )
            else:
                ent = CadEntity(
                    kind=EntityKind.POLYLINE,
                    geometry={
                        'points': [(float(p[0]), float(p[1])) for p in seg],
                        'closed': False,
                    },
                    layer='GEOMETRIE',
                    color=(0, 0, 0),
                )
            ent.lineweight = lw
            entities.append(ent)

    return entities


def _assemble_chains(graph, angle_max_deg: float = 45.0) -> list:
    """
    §2.6ter — Assemble les arêtes sknw en chaînes par continuité tangentielle.

    Améliorations vs version précédente (pipeline de référence v3) :
    - Normalisation pts[0]→u via graph.nodes[u]["o"] (si disponible)
    - Marche bidirectionnelle (avant + arrière) depuis chaque arête de départ
    - _dep_dir() traite correctement les deux sens d'entrée dans une arête

    §2.6quater — 'visited' GLOBAL : n'est jamais réinitialisé entre les chaînes.
    """

    def _fwd_u(pts: np.ndarray, n: int) -> np.ndarray:
        """Tangente de départ depuis u (pts[0] → pts[n])."""
        k = min(n, len(pts) - 1)
        dv = pts[k] - pts[0]
        nm = float(np.linalg.norm(dv))
        return dv / nm if nm > 1e-9 else np.array([1.0, 0.0])

    def _fwd_v(pts: np.ndarray, n: int) -> np.ndarray:
        """Tangente d'arrivée en v (pts[-n] → pts[-1])."""
        k = min(n, len(pts) - 1)
        dv = pts[-1] - pts[-1 - k]
        nm = float(np.linalg.norm(dv))
        return dv / nm if nm > 1e-9 else np.array([1.0, 0.0])

    def _dep_dir(pts: np.ndarray, entry_end: str) -> np.ndarray:
        """Direction en quittant entry_end ('u' ou 'v') vers l'autre extrémité."""
        if entry_end == 'u':
            return _fwd_u(pts, _TANGENT_SAMPLE_PX)
        return _fwd_v(pts[::-1], _TANGENT_SAMPLE_PX)

    def _ang(a: np.ndarray, b: np.ndarray) -> float:
        c = float(np.clip(
            np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12), -1.0, 1.0
        ))
        return math.degrees(math.acos(c))

    # ── Indexation des arêtes ─────────────────────────────────────────────────
    edge_records: dict = {}   # eid → {'u': int, 'v': int, 'pts': ndarray (float)}
    adjacency:   dict = {}    # node → list[(eid, end_label)]
    eid = 0
    for u, v, k, data in graph.edges(keys=True, data=True):
        pts = data.get('pts', np.array([])).astype(float)
        if len(pts) < 2:
            continue
        # Normaliser : pts[0] doit être proche du nœud u (si attribut 'o' disponible)
        try:
            ou = graph.nodes[u]['o'].astype(float)
            ov = graph.nodes[v]['o'].astype(float)
            if np.linalg.norm(pts[0] - ou) > np.linalg.norm(pts[0] - ov):
                pts = pts[::-1].copy()
        except (KeyError, AttributeError, TypeError):
            pass  # graphe sans attribut 'o' (tests) → direction supposée correcte
        edge_records[eid] = {'u': u, 'v': v, 'pts': pts}
        adjacency.setdefault(u, []).append((eid, 'u'))
        adjacency.setdefault(v, []).append((eid, 'v'))
        eid += 1

    def _walk(start_key: int, from_end: str, vis: set) -> list:
        """
        Marche depuis start_key en entrant par from_end ('u' ou 'v').
        Retourne une liste de segments (np.ndarray de forme (N, 2)).
        """
        rec = edge_records[start_key]
        pts = rec['pts'] if from_end == 'u' else rec['pts'][::-1]
        vis.add(start_key)
        cur_node = rec['v'] if from_end == 'u' else rec['u']
        seg_list: list = [pts]
        arr_dir = _fwd_v(pts, _TANGENT_SAMPLE_PX)   # direction d'arrivée au cur_node

        while True:
            cands = [(ek, ee) for ek, ee in adjacency.get(cur_node, []) if ek not in vis]
            if not cands:
                break
            bk, be, ba = None, None, None
            for ek, ee in cands:
                dep = _dep_dir(edge_records[ek]['pts'], ee)
                ang = _ang(arr_dir, dep)
                if ba is None or ang < ba:
                    bk, be, ba = ek, ee, ang
            if bk is None or ba > angle_max_deg:
                break
            raw = edge_records[bk]['pts']
            ordered = raw if be == 'u' else raw[::-1]
            seg_list.append(ordered)
            vis.add(bk)
            cur_node = edge_records[bk]['v'] if be == 'u' else edge_records[bk]['u']
            arr_dir = _fwd_v(ordered, _TANGENT_SAMPLE_PX)
        return seg_list

    visited: set = set()   # §2.6quater : GLOBAL
    chains = []

    for start_key in edge_records:
        if start_key in visited:
            continue

        # Double marche : avant (depuis u) + arrière (depuis v)
        vis_here = set(visited)
        fwd = _walk(start_key, 'u', vis_here)
        vis_here.discard(start_key)         # autorise la marche arrière à passer par start_key
        bwd = _walk(start_key, 'v', vis_here)

        # Assembler : backward renversé + forward (skip le 1er pt de chaque segment suivant)
        bwd_segs = [s[::-1] for s in reversed(bwd)]
        full_segs = bwd_segs[:-1] + fwd if bwd_segs else fwd
        assembled = [full_segs[0]]
        for seg in full_segs[1:]:
            assembled.append(seg[1:])   # skip pts[0] = nœud de jonction déjà présent
        chain = np.concatenate(assembled, axis=0)

        if len(chain) >= 2:
            chains.append(chain.astype(np.int32))
        visited |= vis_here

    return chains


def _clean_loop_artifacts(
    graph,
    anomaly_ratio: float = _ANOMALY_RATIO,
    max_chord_px: float = _ANOMALY_MAX_CHORD_PX,
) -> int:
    """
    §2b — Remplace les boucles locales parasites du squelette par des segments droits.

    Signature : ratio arc/corde >> 1 (chemin tortueux) ET corde courte (nœuds proches).
    Au-delà de max_chord_px, c'est de la vraie géométrie et non un artefact.
    """
    n_cleaned = 0
    for u, v, k, data in graph.edges(keys=True, data=True):
        pts = data.get('pts', np.array([]))
        if len(pts) < 3:
            continue
        pts_f = pts.astype(float)
        arc   = float(np.linalg.norm(np.diff(pts_f, axis=0), axis=1).sum())
        chord = float(np.linalg.norm(pts_f[-1] - pts_f[0]))
        if chord > 1e-6 and chord < max_chord_px and (arc / chord) > anomaly_ratio:
            data['pts'] = np.array([pts_f[0], pts_f[-1]])
            n_cleaned += 1
    return n_cleaned


def _dedup_by_overlap(
    entities: list,
    buffer_mm: float = 0.35,
    overlap_frac: float = 0.6,
    min_len_mm: float = 0.3,
) -> list:
    """
    Garde-fou anti-doublons par comparaison spatiale Shapely (STRtree).

    Deux entités dont les buffers se chevauchent à > overlap_frac de la plus petite
    enveloppe sont dupliquées → la plus courte est supprimée. Sans shapely, retourne
    la liste d'entrée inchangée.
    """
    try:
        from shapely.geometry import LineString
        from shapely.strtree import STRtree
    except ImportError:
        return entities

    geom_list = []
    for ent in entities:
        pts = None
        if ent.kind == EntityKind.POLYLINE:
            pts = ent.geometry.get('points')
        elif ent.kind == EntityKind.SPLINE:
            pts = ent.geometry.get('control_points')
        if pts and len(pts) >= 2:
            try:
                g = LineString(pts)
                geom_list.append(g if g.length >= min_len_mm else None)
            except Exception:
                geom_list.append(None)
        else:
            geom_list.append(None)

    valid = [(i, g) for i, g in enumerate(geom_list) if g is not None]
    if len(valid) < 2:
        return entities

    valid_idxs = [i for i, _ in valid]
    valid_geoms = [g for _, g in valid]
    tree = STRtree(valid_geoms)
    to_remove: set = set()

    for local_i, (orig_i, geom_i) in enumerate(zip(valid_idxs, valid_geoms)):
        if orig_i in to_remove:
            continue
        buf_i = geom_i.buffer(buffer_mm)
        for local_j in tree.query(buf_i):
            if local_j <= local_i:
                continue
            orig_j = valid_idxs[local_j]
            if orig_j in to_remove:
                continue
            geom_j = valid_geoms[local_j]
            try:
                buf_j = geom_j.buffer(buffer_mm)
                inter_area = buf_i.intersection(buf_j).area
                min_area = min(buf_i.area, buf_j.area)
                if min_area > 0 and (inter_area / min_area) > overlap_frac:
                    to_remove.add(orig_j if geom_i.length >= geom_j.length else orig_i)
            except Exception:
                pass

    if not to_remove:
        return entities
    return [ent for i, ent in enumerate(entities) if i not in to_remove]


def _vectorize_pdf_raster(
    pdf_path: Path,
    page_indices: Optional[list],
    on_log: Optional[Callable],
    on_step_start: Optional[Callable],
    on_step_done: Optional[Callable],
    params: Optional[dict],
) -> CadDocument:
    """
    Vectorise un PDF raster (scanné, non-vectorisé) page par page.
    Chaque page est rendue à 200 DPI en niveaux de gris, puis traitée
    par le pipeline vectorize() standard — identique aux fichiers TIF.
    """
    import fitz
    import tempfile
    from PIL import Image as _PILImage

    def _log(msg: str) -> None:
        if on_log:
            on_log(msg)

    try:
        pdf_doc = fitz.open(str(pdf_path))
    except Exception as e:
        raise ValueError(f"Impossible d'ouvrir le PDF raster : {e}")

    n_total   = len(pdf_doc)
    indices   = page_indices if page_indices is not None else list(range(n_total))
    _log(f"  PDF raster : {n_total} page(s) détectées, {len(indices)} à vectoriser")

    _cfg = __import__('config', fromlist=['Config']).Config
    TARGET_DPI = getattr(_cfg, 'CAD_PDF_RASTER_DPI', 150.0)
    MAX_MPX    = getattr(_cfg, 'CAD_PDF_MAX_MPX',    25.0)

    all_cad_pages = []

    for seq, page_idx in enumerate(indices):
        if page_idx >= n_total:
            _log(f"  ⚠ Page {page_idx + 1} hors limites — ignorée")
            continue

        pdf_page = pdf_doc[page_idx]

        # DPI adaptatif : réduire automatiquement si la page dépasse MAX_MPX
        # Les pages panoramiques (ex: 2100×900mm) atteignent 117 Mpx à 200 DPI
        # → on plafonne à MAX_MPX pour garder un temps de squelettisation raisonnable
        r = pdf_page.rect
        w_at_target = r.width  * TARGET_DPI / 72.0
        h_at_target = r.height * TARGET_DPI / 72.0
        mpx_at_target = w_at_target * h_at_target / 1_000_000
        if mpx_at_target > MAX_MPX:
            dpi = TARGET_DPI * (MAX_MPX / mpx_at_target) ** 0.5
        else:
            dpi = TARGET_DPI
        dpi = max(dpi, 60.0)   # jamais en dessous de 60 DPI (lisibilité minimale)

        w_px = int(r.width  * dpi / 72.0)
        h_px = int(r.height * dpi / 72.0)
        mpx  = w_px * h_px / 1_000_000
        if dpi < TARGET_DPI - 1:
            _log(
                f"━━ Page {page_idx + 1}/{n_total} : "
                f"{r.width*25.4/72:.0f}×{r.height*25.4/72:.0f}mm"
                f" — DPI {TARGET_DPI:.0f}→{dpi:.0f}"
                f" ({mpx_at_target:.0f}Mpx→{mpx:.0f}Mpx)"
            )
        else:
            _log(
                f"━━ Page {page_idx + 1}/{n_total} :"
                f" rendu à {dpi:.0f} DPI ({mpx:.1f} Mpx)…"
            )

        mat     = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix     = pdf_page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
        pil_img = _PILImage.frombytes('L', (pix.w, pix.h), pix.samples)

        # Fichier temporaire avec métadonnées DPI — vectorize() lira le bon DPI
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
            tmp_path = Path(tf.name)
        pil_img.save(str(tmp_path), dpi=(dpi, dpi))

        try:
            page_doc = vectorize(
                tmp_path,
                page_indices=None,
                on_log=on_log,
                on_step_start=on_step_start,
                on_step_done=on_step_done,
                params=params,
            )
            for cad_page in page_doc.pages:
                cad_page.page_index = page_idx
                all_cad_pages.append(cad_page)
        except Exception as e:
            _log(f"  ⚠ Page {page_idx + 1} échouée : {e}")
        finally:
            tmp_path.unlink(missing_ok=True)

    pdf_doc.close()

    if not all_cad_pages:
        _log("  ⚠ Aucune page vectorisée — document vide")

    return CadDocument(source_path=pdf_path, pages=all_cad_pages)


def vectorize(
    source_path: Path,
    page_indices: Optional[list] = None,
    on_log: Optional[Callable] = None,
    on_step_start: Optional[Callable[[str], None]] = None,
    on_step_done: Optional[Callable[[str, dict], None]] = None,
    params: Optional[dict] = None,
) -> CadDocument:
    """
    Vectorise un fichier image (TIF/PNG/JPG/BMP) ou un PDF raster en CadDocument.

    Étapes nommées déclarées dans ETAPES :
      chargement → pretraitement → separation → squelettisation
      → graphe → vectorisation → export
    """
    import cv2
    from .raster_tif_extractor import (
        _preprocess,
        _prune_spurs,
        _skeletonize,
        _trace_paths_from_skeleton,
    )

    try:
        from .raster_tif_extractor import _separate_text_geometry
        _has_sep = True
    except ImportError:
        _has_sep = False

    import gc

    source_path = Path(source_path)

    # PDF raster → rendu image page par page via _vectorize_pdf_raster()
    if source_path.suffix.lower() == '.pdf':
        return _vectorize_pdf_raster(
            source_path, page_indices, on_log, on_step_start, on_step_done, params
        )

    p = params or {}
    max_samples = int(p.get('max_samples', _MAX_SAMPLES))

    def _log(msg: str) -> None:
        if on_log:
            on_log(msg)

    def _step_start(name: str) -> None:
        if on_step_start:
            on_step_start(name)

    def _step_done(name: str, info: dict = None) -> None:
        if on_step_done:
            on_step_done(name, info or {})

    # ── Étape 1 : chargement ──────────────────────────────────────────────────
    _step_start("chargement")
    _log(f"  Chargement : {source_path.name}")
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None   # plans TIF haute résolution dépassent le seuil par défaut
    try:
        pil_img  = Image.open(source_path)
        dpi_info = pil_img.info.get('dpi', (200, 200))
        dpi      = float(dpi_info[0]) if dpi_info[0] > 0 else 200.0
    except Exception:
        dpi = 200.0
    scale  = 25.4 / dpi   # mm/px
    img_cv = cv2.imread(str(source_path), cv2.IMREAD_GRAYSCALE)
    if img_cv is None:
        raise ValueError(f"Impossible de lire l'image : {source_path}")
    _log(
        f"  DPI={dpi:.0f}, scale={scale:.4f} mm/px, "
        f"taille={img_cv.shape[1]}×{img_cv.shape[0]} px"
    )
    _step_done("chargement", {'dpi': dpi, 'scale': scale})

    # Pleine résolution — OOM résolu par cv2.distanceTransform (float32, pas de buffer (2,H,W))
    # Le downscale silencieux (52%) rendait le texte < seuil Potrace et dégradait la qualité.
    if img_cv.shape[0] * img_cv.shape[1] > 20_000_000:
        _log(
            f"  Image {img_cv.shape[1]}×{img_cv.shape[0]} px"
            f" ({img_cv.shape[0] * img_cv.shape[1] / 1_000_000:.0f} Mpx)"
            f" — traitement pleine résolution"
        )

    # ── Étape 2 : prétraitement ───────────────────────────────────────────────
    _step_start("pretraitement")
    _log("  Prétraitement (binarisation, correction de perspective)...")
    try:
        binary = _preprocess(img_cv)
    except Exception as e:
        _log(f"  ⚠ _preprocess échoué ({e}), binarisation simple")
        _, binary = cv2.threshold(img_cv, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _h_px, _w_px = img_cv.shape   # dimensions pour l'étape 7
    del img_cv
    gc.collect()

    # Détection de polarité : si > 50% des pixels sont "encre" après binarisation,
    # la photo est inversée (blanc = encre) — on la retourne
    if float((binary > 127).mean()) > 0.5:
        binary = cv2.bitwise_not(binary)
        _log("  ⚠ Polarité inversée détectée — image corrigée (blanc↔noir)")

    _step_done("pretraitement")

    # ── Étape 3 : séparation texte / géométrie ────────────────────────────────
    # _separate_text_geometry retourne (geom_mask, text_mask)
    _step_start("separation")
    _text_thresh_mm = 7.62   # 60px à 200DPI — seuil physique conforme à la méthodologie
    _log(f"  Séparation texte/géométrie (seuil {_text_thresh_mm}mm physiques)...")
    fg = (binary > 127).astype(np.uint8)
    if _has_sep:
        try:
            line_mask, text_mask = _separate_text_geometry(binary, dpi=25.4 / scale)
            line_mask = (line_mask > 0).astype(np.uint8)
            text_mask = (text_mask > 0).astype(np.uint8)
        except Exception as e:
            _log(f"  ⚠ _separate_text_geometry échoué ({e}), masques unifiés")
            text_mask = np.zeros_like(fg)
            line_mask = fg
    else:
        # Fallback manuel : seuil converti en pixels effectifs via scale (mm/px)
        _text_thresh_px_eff = max(3, int(_text_thresh_mm / scale))
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
        text_mask = np.zeros_like(fg)
        line_mask = np.zeros_like(fg)
        for lbl in range(1, num_labels):
            w_comp = stats[lbl, cv2.CC_STAT_WIDTH]
            h_comp = stats[lbl, cv2.CC_STAT_HEIGHT]
            if max(w_comp, h_comp) < _text_thresh_px_eff:
                text_mask[labels == lbl] = 1
            else:
                line_mask[labels == lbl] = 1
    n_text = int(text_mask.sum())
    n_geom = int(line_mask.sum())
    _log(f"  Texte : {n_text} px | Géométrie : {n_geom} px")
    del binary, fg   # libère 2 × 75 Mo — plus utilisés après la séparation
    gc.collect()
    _step_done("separation", {'text_px': n_text, 'geom_px': n_geom})

    # ── Étape 4 : squelettisation ─────────────────────────────────────────────
    _step_start("squelettisation")
    _log("  Squelettisation (Zhang-Suen)...")
    geom_uint8 = (line_mask * 255).astype(np.uint8)
    skel = _skeletonize(geom_uint8)
    skel = _prune_spurs(skel, min_px=int(_SPUR_LEN_PX))
    del geom_uint8   # libère 75 Mo — squelette extrait
    gc.collect()
    n_skel = int((skel > 0).sum())
    _log(f"  Squelette : {n_skel} pixels actifs")

    # cv2.distanceTransform retourne float32 natif, sans buffer intermédiaire (2,H,W)
    # scipy.ndimage.distance_transform_edt alloue internement (2,H,W) float64 → 1.19 Go OOM
    _line_u8 = (line_mask * 255).astype(np.uint8)
    dist_map  = cv2.distanceTransform(_line_u8, cv2.DIST_L2, 5)
    del _line_u8

    _step_done("squelettisation", {'skel_px': n_skel})

    # ── Étape 5 : graphe topologique ─────────────────────────────────────────
    _step_start("graphe")
    # Format unifié : list of (path_xy, width_mm) — path_xy contient des (x, y) pixels
    paths_with_widths = []
    _use_sknw_local   = False

    if _USE_SKNW:
        _log("  Construction du graphe topologique (sknw)...")
        try:
            import networkx as nx
            import sknw
            skel_bool = (skel > 0)
            graph = sknw.build_sknw(skel_bool.astype(np.uint8), multi=True)
            # Élagage des amorces parasites — 1 passe sans cascade
            # La boucle while détruisait le graphe entier par effet domino sur les
            # plans denses : chaque arête supprimée créait un nouveau degré-1 qui
            # déclenchait la suppression suivante, éliminant 99% de la géométrie.
            deg = dict(graph.degree())
            to_rm = []
            for u, v, k_edge, data in graph.edges(keys=True, data=True):
                pts   = data.get('pts', np.array([]))
                arc_L = float(
                    np.linalg.norm(np.diff(pts.astype(float), axis=0), axis=1).sum()
                ) if len(pts) >= 2 else 0.0
                if (deg.get(u, 0) == 1 or deg.get(v, 0) == 1) and arc_L < _SPUR_LEN_PX:
                    to_rm.append((u, v, k_edge))
            if to_rm:
                graph.remove_edges_from(to_rm)
                graph.remove_nodes_from(list(nx.isolates(graph)))
            # §2b — Nettoyage des boucles locales parasites (référence pipeline v3)
            n_anomalies = _clean_loop_artifacts(graph, _ANOMALY_RATIO, _ANOMALY_MAX_CHORD_PX)
            if n_anomalies:
                _log(f"  {n_anomalies} artefact(s) de boucle locale nettoyé(s)")
            # §2.6ter — Assemblage en chaînes par continuité tangentielle + normalisation
            # pts de sknw sont (row, col) = (y, x)
            chains = _assemble_chains(graph)
            n_micro = 0
            for chain_pts in chains:
                # Filtre longueur min — élimine les micro-chaînes entre jonctions serrées
                c_arr    = chain_pts.astype(float)
                arc_L_mm = float(np.linalg.norm(np.diff(c_arr, axis=0), axis=1).sum()) * scale
                if arc_L_mm < _MIN_ENTITY_LEN_MM:
                    n_micro += 1
                    continue
                path_xy = [(int(p[1]), int(p[0])) for p in chain_pts]  # (y,x) → (x,y)
                ys_all  = np.clip([int(p[0]) for p in chain_pts], 0, dist_map.shape[0] - 1)
                xs_all  = np.clip([int(p[1]) for p in chain_pts], 0, dist_map.shape[1] - 1)
                trim    = max(1, int(len(ys_all) * 0.2))
                ys_c, xs_c = ys_all[trim:-trim], xs_all[trim:-trim]
                if len(ys_c) > 0:
                    width_mm = 2.0 * float(np.percentile(dist_map[ys_c, xs_c], 15)) * scale
                else:
                    width_mm = 0.35
                paths_with_widths.append((path_xy, width_mm))
            if n_micro:
                _log(f"  {n_micro} micro-chaînes < {_MIN_ENTITY_LEN_MM}mm filtrées")
            _log(
                f"  Graphe sknw : {graph.number_of_edges()} arêtes"
                f" → {len(chains)} chaînes → {len(paths_with_widths)} retenues"
            )
            _use_sknw_local = True
        except Exception as e:
            _log(f"  ⚠ sknw échoué ({e}), fallback BFS")
            _use_sknw_local = False

    if not _use_sknw_local:
        _log("  Extraction de chemins BFS (fallback)...")
        try:
            # _trace_paths_from_skeleton retourne list[(path_xy, median_r_mm)]
            # path_xy contient des (x, y) ; median_r_mm est le rayon en mm
            raw_paths = _trace_paths_from_skeleton(skel, dist_map, dpi)
            for path_xy, median_r_mm in raw_paths:
                # width = diamètre = 2 * rayon
                paths_with_widths.append((path_xy, 2.0 * median_r_mm))
        except Exception as e:
            _log(f"  ⚠ BFS échoué ({e})")
            paths_with_widths = []

    _log(f"  {len(paths_with_widths)} chemins extraits")
    _step_done("graphe", {'paths': len(paths_with_widths)})

    # ── Étape 6 : vectorisation ───────────────────────────────────────────────
    _step_start("vectorisation")
    _log(f"  Vectorisation : {len(paths_with_widths)} chemins → entités DXF...")
    entities = _build_entities_from_paths(paths_with_widths, scale, max_samples)

    # Garde-fou anti-doublons via Shapely (safety net post-assemblage)
    n_ent_before = len(entities)
    entities = _dedup_by_overlap(entities)
    n_removed = n_ent_before - len(entities)
    if n_removed:
        _log(f"  Déduplication Shapely : {n_removed} entités dupliquées supprimées")

    # Diagnostic Preuve n°1 : texte segmenté mais pipeline Potrace non implémenté
    n_text_px = int(text_mask.sum())
    del text_mask
    if n_text_px > 0:
        _log(f"  ℹ {n_text_px} px texte isolés — non exportés (pipeline Potrace non disponible)")

    n_geom_ent = sum(1 for e in entities if e.layer == 'GEOMETRIE')
    n_text_ent = sum(1 for e in entities if e.layer == 'TEXTE')
    _log(f"  {n_geom_ent} entités GEOMETRIE | {n_text_ent} entités TEXTE")
    _step_done("vectorisation", {'geom': n_geom_ent, 'texte': n_text_ent})

    # ── Étape 7 : export CadDocument ─────────────────────────────────────────
    _step_start("export")
    _log("  Construction du document CAD...")
    page = CadPage(
        width=_w_px * scale,
        height=_h_px * scale,
        source_mode='raster',
        entities=entities,
    )
    doc = CadDocument(source_path=source_path, pages=[page])
    _log(
        f"  Document CAD : {len(entities)} entités"
        f" sur {page.width:.0f}×{page.height:.0f} mm"
    )
    _step_done("export", {'total': len(entities)})

    return doc
