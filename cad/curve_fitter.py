"""
Classification et reconstruction des entités géométriques d'un plan TIF.
Spécialisé pour les plans à dominante orthogonale avec détection de lignes tiretées.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

# ─── Constantes de détection (valeurs par défaut) ────────────────────────────

_L_MAX_TIRET_MM   = 40.0   # fragment court → candidat tiret
_L_MIN_TIRET_MM   = 1.0    # bruit (trop court)
_D_PERP_MAX_MM    = 1.0    # tolérance de colinéarité (même droite support)
_ANGLE_TOL_DEG    = 5.0    # tolérance angulaire pour le regroupement
_N_MIN_TIRETS     = 3      # minimum de fragments pour valider un pattern périodique
_S_MAX_GAP_MM     = 50.0   # espacement max entre deux tirets d'un même groupe
_CV_SEUIL         = 0.20   # seuil coefficient de variation (σ/μ < 0.20 → périodique)
_D_GAP_FUSION_MM  = 2.0    # lacune max pour fusionner deux segments colinéaires
_D_PERP_FUSION_MM = 0.5    # désalignement max pour la fusion
_DELTA_THETA_FUSE = 3.0    # tolérance angulaire pour la fusion (degrés)
_LTSCALE_REF_MM   = 12.7   # longueur tiret dans DASHED LTSCALE=1 (standard AutoCAD)

# Écrasement depuis config.py si disponible (les defaults ci-dessus servent de fallback)
try:
    from config import Config as _Cfg
    _L_MAX_TIRET_MM   = _Cfg.CAD_L_MAX_TIRET_MM
    _L_MIN_TIRET_MM   = _Cfg.CAD_L_MIN_TIRET_MM
    _CV_SEUIL         = _Cfg.CAD_CV_SEUIL
    _D_GAP_FUSION_MM  = _Cfg.CAD_D_GAP_FUSION_MM
except (ImportError, AttributeError):
    pass  # valeurs par défaut conservées si Config absent


@dataclass
class FittedCurve:
    """Résultat de classification d'un chemin géométrique."""
    kind: Literal['LINE', 'DASHED', 'POLYLINE', 'ARC', 'SPLINE']
    points: list
    lineweight: float = 0.35
    layer: str = 'GEOMETRIE'
    lt_mm: float = 0.0      # longueur d'un tiret en mm (si DASHED)
    le_mm: float = 0.0      # espacement entre tirets en mm (si DASHED)
    ltscale: float = 1.0    # LTSCALE AutoCAD recommandée (si DASHED)
    confidence: float = 1.0


def _path_length(pts_mm: list) -> float:
    """Longueur curviligne d'un chemin en mm."""
    if len(pts_mm) < 2:
        return 0.0
    pts = np.array(pts_mm)
    return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))


def _path_angle_deg(pts_mm: list) -> float:
    """Angle de la droite extrémité-à-extrémité en degrés dans [0, 180[."""
    if len(pts_mm) < 2:
        return 0.0
    dx = pts_mm[-1][0] - pts_mm[0][0]
    dy = pts_mm[-1][1] - pts_mm[0][1]
    return math.degrees(math.atan2(dy, dx)) % 180.0


def _quantize_angle(angle_deg: float) -> float:
    """Quantifie l'angle sur les 4 axes principaux : 0, 45, 90, 135."""
    candidates = [0.0, 45.0, 90.0, 135.0]
    # Gérer le repliement autour de 180°
    dists = [min(abs(angle_deg - c), abs(angle_deg - c - 180), abs(angle_deg - c + 180))
             for c in candidates]
    return candidates[int(np.argmin(dists))]


def _dist_point_to_line(pt, line_start, line_end) -> float:
    """Distance perpendiculaire d'un point à une droite définie par deux points (en mm)."""
    p = np.array(pt, dtype=float)
    a = np.array(line_start, dtype=float)
    b = np.array(line_end, dtype=float)
    ab = b - a
    norm_ab = np.linalg.norm(ab)
    if norm_ab < 1e-9:
        return float(np.linalg.norm(p - a))
    # Produit vectoriel 2D scalaire : évite le warning NumPy 2.0 sur np.cross 2D
    ap = a - p
    cross_z = float(ab[0] * ap[1] - ab[1] * ap[0])
    return abs(cross_z) / norm_ab


def is_straight_line(pts_mm: list, tol_mm: float = 0.5) -> bool:
    """
    Retourne True si tous les points sont à moins de tol_mm de la droite
    passant par les extrémités. Cas droit → LINE DXF (2 points uniquement).
    """
    if len(pts_mm) < 3:
        return True
    start, end = pts_mm[0], pts_mm[-1]
    if start == end:
        return True
    return all(_dist_point_to_line(p, start, end) <= tol_mm for p in pts_mm[1:-1])


def group_collinear_fragments(
    paths_mm: list,
    dpi: float,
    angle_tol_deg: float = _ANGLE_TOL_DEG,
    dist_perp_tol_mm: float = _D_PERP_MAX_MM,
    l_max_mm: float = _L_MAX_TIRET_MM,
    l_min_mm: float = _L_MIN_TIRET_MM,
) -> tuple:
    """
    Sépare les chemins courts (candidats tirets) des longs (câbles principaux),
    puis regroupe les courts par collinéarité (même direction + même droite support).

    Retourne : (groupes_candidats, segments_longs)
      groupes_candidats : list de list de chemins courts colinéaires
      segments_longs    : list de chemins longs
    """
    courts = []
    longs = []

    for path in paths_mm:
        L = _path_length(path)
        if L < l_min_mm:
            continue  # bruit
        if L <= l_max_mm:
            courts.append(path)
        else:
            longs.append(path)

    # Regrouper les courts par direction principale puis collinéarité
    # Clé de bucket : angle quantifié (0, 45, 90, 135)
    buckets: dict = {}
    for path in courts:
        theta = _quantize_angle(_path_angle_deg(path))
        if theta not in buckets:
            buckets[theta] = []
        buckets[theta].append(path)

    groupes = []
    for theta, paths_in_bucket in buckets.items():
        # Pour chaque chemin, tester si il appartient à un groupe existant
        angle_groups: list = []
        for path in paths_in_bucket:
            start = path[0]
            end = path[-1]
            mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
            assigned = False
            for grp in angle_groups:
                # Référence = axe du premier élément du groupe
                ref_start = grp[0][0]
                ref_end = grp[0][-1]
                d = _dist_point_to_line(mid, ref_start, ref_end)
                if d <= dist_perp_tol_mm:
                    grp.append(path)
                    assigned = True
                    break
            if not assigned:
                angle_groups.append([path])

        groupes.extend(angle_groups)

    return groupes, longs


def detect_dash_pattern(
    group: list,
    dpi: float,
    n_min: int = _N_MIN_TIRETS,
    s_max_gap_mm: float = _S_MAX_GAP_MM,
    cv_seuil: float = _CV_SEUIL,
) -> dict:
    """
    Analyse un groupe de fragments colinéaires et détecte le pattern de tiretés.

    Trie les fragments par position sur l'axe directeur, calcule les espacements
    inter-fragments et teste la périodicité via le coefficient de variation (σ/μ).

    Retourne un dict avec : is_dashed, lt_mm, le_mm, sigma_ratio, ltscale,
    pt_start, pt_end, n_fragments.
    """
    _no_pattern = {
        'is_dashed': False, 'lt_mm': 0.0, 'le_mm': 0.0,
        'sigma_ratio': 1.0, 'ltscale': 1.0,
        'pt_start': None, 'pt_end': None, 'n_fragments': len(group),
    }

    if len(group) < n_min:
        return _no_pattern

    # Direction de référence du groupe
    ref_start = np.array(group[0][0])
    ref_end = np.array(group[0][-1])
    direction = ref_end - ref_start
    norm_dir = np.linalg.norm(direction)
    if norm_dir < 1e-9:
        return _no_pattern
    unit = direction / norm_dir

    # Trier les fragments par projection sur l'axe directeur
    def _proj(path):
        mid = np.array([(path[0][0] + path[-1][0]) / 2.0,
                        (path[0][1] + path[-1][1]) / 2.0])
        return float(np.dot(mid - ref_start, unit))

    sorted_group = sorted(group, key=_proj)

    # Mesurer les espacements inter-tirets (gap = espace entre fin d'un tiret et début du suivant)
    spacings = []
    lengths = []
    for path in sorted_group:
        L = _path_length(path)
        lengths.append(L)

    for i in range(len(sorted_group) - 1):
        end_i = np.array(sorted_group[i][-1])
        start_i1 = np.array(sorted_group[i + 1][0])
        # Distance entre extrémité du fragment i et début du fragment i+1
        gap = float(np.linalg.norm(start_i1 - end_i))
        if 0.0 < gap < s_max_gap_mm:
            spacings.append(gap)

    if len(spacings) < 2:
        return _no_pattern

    mu = float(np.mean(spacings))
    sigma = float(np.std(spacings))
    cv = sigma / mu if mu > 1e-9 else 1.0

    if cv >= cv_seuil:
        return {**_no_pattern, 'sigma_ratio': cv}

    # Pattern périodique confirmé
    lt = float(np.mean(lengths))
    le = mu

    # Câble fragmenté aux croisements : tirets très longs par rapport à l'espace → faux positif
    # (tirets réels : lt/le ≈ 1.5 à 3 ; câble fragmenté aux intersections : lt/le souvent > 4)
    if le > 1e-9 and lt / le > 4.0:
        return {**_no_pattern, 'sigma_ratio': cv}

    # LTSCALE AutoCAD = rapport entre l'espacement détecté et l'espacement de référence
    # AutoCAD DASHED (LTSCALE=1) : tiret=12.7mm, espace=6.35mm, total=19.05mm
    ltscale = (lt + le) / (_LTSCALE_REF_MM + _LTSCALE_REF_MM / 2.0)

    # Extrémités globales
    pt_start = sorted_group[0][0]
    pt_end = sorted_group[-1][-1]

    return {
        'is_dashed': True,
        'lt_mm': lt,
        'le_mm': le,
        'sigma_ratio': cv,
        'ltscale': round(ltscale, 2),
        'pt_start': pt_start,
        'pt_end': pt_end,
        'n_fragments': len(sorted_group),
    }


def merge_collinear_to_one(
    longs: list,
    d_gap_max_mm: float = _D_GAP_FUSION_MM,
    d_perp_max_mm: float = _D_PERP_FUSION_MM,
    delta_theta_deg: float = _DELTA_THETA_FUSE,
) -> list:
    """
    Fusionne les segments longs colinéaires fragmentés (par les intersections du squelette)
    en segments étendus (start_mm, end_mm).

    Retourne une liste de tuples (pt_start, pt_end) — un par segment fusionné.
    """
    if not longs:
        return []

    # Trier par direction principale, puis par position
    def _sort_key(path):
        theta = _path_angle_deg(path)
        q = _quantize_angle(theta)
        # Projection du milieu sur l'axe quantifié
        mid_x = (path[0][0] + path[-1][0]) / 2.0
        mid_y = (path[0][1] + path[-1][1]) / 2.0
        return (q, mid_x + mid_y)

    sorted_longs = sorted(longs, key=_sort_key)

    result = []
    stack = [sorted_longs[0]]

    for seg in sorted_longs[1:]:
        top = stack[-1]
        # Direction
        theta_top = _path_angle_deg(top)
        theta_seg = _path_angle_deg(seg)
        dtheta = abs(theta_top - theta_seg) % 180.0
        if dtheta > 90.0:
            dtheta = 180.0 - dtheta

        if dtheta > delta_theta_deg:
            result.append((top[0], top[-1]))
            stack.pop()
            stack.append(seg)
            continue

        # Distance entre extrémités
        end_top = np.array(top[-1])
        start_seg = np.array(seg[0])
        gap = float(np.linalg.norm(start_seg - end_top))

        # Distance perpendiculaire
        d_perp = _dist_point_to_line(seg[0], top[0], top[-1])

        if gap <= d_gap_max_mm and d_perp <= d_perp_max_mm:
            # Fusionner : créer un segment étendu
            merged = [top[0]] + seg
            stack[-1] = merged
        else:
            result.append((top[0], top[-1]))
            stack.pop()
            stack.append(seg)

    while stack:
        top = stack.pop()
        result.append((top[0], top[-1]))

    return result


def classify_and_fit(
    pts_mm: list,
    lineweight: float = 0.35,
    dpi: float = 200.0,
    epsilon_mm: float = 0.5,
) -> FittedCurve:
    """
    Classifie un chemin géométrique et retourne la représentation DXF optimale.

    Pipeline de décision :
      1. < 2 points → POLYLINE vide
      2. Résidu de linéarité < epsilon_mm → LINE (droite)
      3. Coin vif (> 45°) entre segments → POLYLINE
      4. Courbe douce (courbure totale > 5°, pas de coin) → SPLINE si ≥ 4 pts
      5. Fallback → POLYLINE
    """
    if len(pts_mm) < 2:
        return FittedCurve('POLYLINE', pts_mm, lineweight)

    if is_straight_line(pts_mm, tol_mm=epsilon_mm):
        return FittedCurve('LINE', [pts_mm[0], pts_mm[-1]], lineweight)

    # Vérifier présence d'un coin vif
    has_corner = False
    total_angle = 0.0
    for i in range(1, len(pts_mm) - 1):
        ax, ay = pts_mm[i - 1]
        bx, by = pts_mm[i]
        cx, cy = pts_mm[i + 1]
        v1x, v1y = bx - ax, by - ay
        v2x, v2y = cx - bx, cy - by
        n1 = math.sqrt(v1x**2 + v1y**2)
        n2 = math.sqrt(v2x**2 + v2y**2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cos_a = max(-1.0, min(1.0, (v1x * v2x + v1y * v2y) / (n1 * n2)))
        angle = math.degrees(math.acos(cos_a))
        total_angle += angle
        if angle > 45.0:
            has_corner = True
            break

    if has_corner:
        return FittedCurve('POLYLINE', pts_mm, lineweight)

    # Courbe douce — B-spline si suffisamment de points et courbure notable
    if total_angle > 5.0 and len(pts_mm) >= 4:
        try:
            from scipy.interpolate import splprep, splev
            pts = np.array(pts_mm)
            k = min(3, len(pts) - 1)
            tck, u = splprep([pts[:, 0], pts[:, 1]], s=0.0, k=k)
            u_new = np.linspace(0, 1, min(len(pts_mm), 20))
            x_new, y_new = splev(u_new, tck)
            spline_pts = list(zip(x_new.tolist(), y_new.tolist()))
            return FittedCurve('SPLINE', spline_pts, lineweight)
        except Exception:
            pass

    return FittedCurve('POLYLINE', pts_mm, lineweight)


def snap_to_orthogonal(
    pts_mm: list,
    theta_snap_deg: float = 5.0,
) -> list:
    """
    Projette les segments quasi-horizontaux/verticaux sur les axes H/V exacts.
    Un plan électrique est quasi-exclusivement orthogonal — ce snapping
    élimine les angles parasites issus du bruit de numérisation.

    Ne modifie que les segments dont l'angle est à moins de theta_snap_deg
    d'un axe principal (0°, 90°, 180°, 270°).
    """
    if len(pts_mm) < 2:
        return pts_mm

    result = [pts_mm[0]]
    for i in range(1, len(pts_mm)):
        x0, y0 = result[-1]
        x1, y1 = pts_mm[i]
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            result.append((x1, y1))
            continue
        angle = math.degrees(math.atan2(abs(dy), abs(dx)))  # angle dans [0, 90]
        if angle <= theta_snap_deg:
            # Quasi-horizontal → forcer y = y0
            result.append((x1, y0))
        elif angle >= 90.0 - theta_snap_deg:
            # Quasi-vertical → forcer x = x0
            result.append((x0, y1))
        else:
            result.append((x1, y1))
    return result
