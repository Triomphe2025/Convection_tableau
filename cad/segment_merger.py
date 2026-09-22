"""
Fusion de segments colinéaires fragmentés par graphe de connectivité.
Transforme N micro-polylignes (<5mm) en M polylignes longues (20-100mm).
"""
from __future__ import annotations

import math


def _pt_dist(a: tuple, b: tuple) -> float:
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)


def _rdp_simplify(pts: list, epsilon: float) -> list:
    """Ramer-Douglas-Peucker : simplifie un chemin de points (x, y) en mm."""
    if len(pts) < 3:
        return pts

    def _dist_point_to_segment(p, a, b):
        ax, ay = a
        bx, by = b
        px, py = p
        dx, dy = bx - ax, by - ay
        norm = dx * dx + dy * dy
        if norm < 1e-12:
            return _pt_dist(p, a)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / norm))
        return _pt_dist(p, (ax + t * dx, ay + t * dy))

    def _rdp(points, eps, start, end):
        if end <= start + 1:
            return []
        dmax, idx = 0.0, start
        for i in range(start + 1, end):
            d = _dist_point_to_segment(points[i], points[start], points[end])
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps:
            return _rdp(points, eps, start, idx) + [idx] + _rdp(points, eps, idx, end)
        return []

    indices = [0] + _rdp(pts, epsilon, 0, len(pts) - 1) + [len(pts) - 1]
    return [pts[i] for i in sorted(set(indices))]


def merge_collinear_entities(
    polylines_pts: list,
    eps_gap_mm: float = 0.254,
    eps_rdp_mm: float = 0.5,
    angle_max_deg: float = 5.0,
) -> list:
    """
    Fusionne les polylignes fragmentées en chemins connectés simplifiés.

    Args:
        polylines_pts : liste de listes de points (x_mm, y_mm)
        eps_gap_mm    : distance max entre extrémités pour les relier (défaut 0.254mm = 2px@200DPI)
        eps_rdp_mm    : tolérance RDP pour simplification (défaut 0.5mm)
        angle_max_deg : angle max pour valider la colinéarité lors du suivi de chemin

    Returns:
        liste de listes de points — une par chemin fusionné
    """
    if not polylines_pts:
        return []

    # ── Construire les nœuds (extrémités) et le graphe de connectivité ──────
    nodes = []    # [(x, y), ...]
    edges = []    # [(poly_idx, node_start_idx, node_end_idx)]

    def _find_or_add(pt):
        for i, n in enumerate(nodes):
            if _pt_dist(pt, n) <= eps_gap_mm:
                return i
        nodes.append(pt)
        return len(nodes) - 1

    for i, poly in enumerate(polylines_pts):
        if len(poly) < 2:
            continue
        ni_start = _find_or_add(poly[0])
        ni_end = _find_or_add(poly[-1])
        edges.append((i, ni_start, ni_end))

    if not edges:
        return polylines_pts

    # ── Graphe d'adjacence : nœud → liste de (poly_idx, nœud_opposé) ─────────
    adjacency = {i: [] for i in range(len(nodes))}
    for poly_i, ni_s, ni_e in edges:
        if ni_s != ni_e:
            adjacency[ni_s].append((poly_i, ni_e))
            adjacency[ni_e].append((poly_i, ni_s))

    # ── Parcours BFS depuis les nœuds terminaux (degré 1) ou isolés ──────────
    visited_polys = set()
    result_chains = []

    def _build_chain(start_node, start_poly_i, next_node):
        """Suit le chemin depuis start_node en passant par start_poly_i."""
        chain_pts = list(polylines_pts[start_poly_i])
        # Orienter : start de chain_pts doit être au niveau de start_node
        if _pt_dist(chain_pts[-1], nodes[start_node]) < _pt_dist(chain_pts[0], nodes[start_node]):
            chain_pts = list(reversed(chain_pts))
        visited_polys.add(start_poly_i)
        cur_node = next_node

        while True:
            neighbors = [(pi, nn) for pi, nn in adjacency[cur_node]
                         if pi not in visited_polys]
            if len(neighbors) != 1:
                break  # croisement ou fin de chaîne
            pi, nn = neighbors[0]
            seg_pts = list(polylines_pts[pi])
            # Orienter pour connecter au bout actuel
            if _pt_dist(seg_pts[-1], nodes[cur_node]) < _pt_dist(seg_pts[0], nodes[cur_node]):
                seg_pts = list(reversed(seg_pts))
            # Vérifier colinéarité approximative (angle au joint)
            if len(chain_pts) >= 2 and len(seg_pts) >= 2:
                v1 = (chain_pts[-1][0] - chain_pts[-2][0], chain_pts[-1][1] - chain_pts[-2][1])
                v2 = (seg_pts[1][0] - seg_pts[0][0], seg_pts[1][1] - seg_pts[0][1])
                n1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
                n2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
                if n1 > 1e-9 and n2 > 1e-9:
                    cos_a = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
                    angle = math.degrees(math.acos(cos_a))
                    if angle > angle_max_deg:
                        break  # vraie courbure → ne pas fusionner au-delà
            chain_pts.extend(seg_pts[1:])  # éviter le doublon du nœud de jonction
            visited_polys.add(pi)
            cur_node = nn

        return chain_pts

    # Nœuds de départ : terminaux (degré 1) ou isolés (degré 0), puis le reste
    start_nodes = [n for n, adj in adjacency.items() if len(adj) <= 1]
    start_nodes += [n for n, adj in adjacency.items() if len(adj) > 1 and n not in start_nodes]

    for sn in start_nodes:
        for pi, nn in adjacency[sn]:
            if pi not in visited_polys:
                chain = _build_chain(sn, pi, nn)
                simplified = _rdp_simplify(chain, eps_rdp_mm)
                if len(simplified) >= 2:
                    result_chains.append(simplified)

    # Polys non visitées (isolées, degré 0 des deux côtés)
    for poly_i, poly in enumerate(polylines_pts):
        if poly_i not in visited_polys and len(poly) >= 2:
            simplified = _rdp_simplify(poly, eps_rdp_mm)
            if len(simplified) >= 2:
                result_chains.append(simplified)

    return result_chains
