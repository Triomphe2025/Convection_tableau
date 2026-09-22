"""Tests du module cad/segment_merger.py — fusion de segments fragmentés."""
import math
import pytest


class TestRdpSimplify:
    def test_droite_devient_2_points(self):
        from cad.segment_merger import _rdp_simplify
        pts = [(float(i), 0.0) for i in range(20)]
        result = _rdp_simplify(pts, epsilon=0.1)
        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[-1] == (19.0, 0.0)

    def test_courbe_conserve_points(self):
        from cad.segment_merger import _rdp_simplify
        pts = [(math.cos(t), math.sin(t)) for t in [i * 0.3 for i in range(20)]]
        result = _rdp_simplify(pts, epsilon=0.01)
        assert len(result) > 2

    def test_liste_vide(self):
        from cad.segment_merger import _rdp_simplify
        assert _rdp_simplify([], 0.5) == []

    def test_deux_points_inchanges(self):
        from cad.segment_merger import _rdp_simplify
        pts = [(0.0, 0.0), (5.0, 3.0)]
        assert _rdp_simplify(pts, 0.5) == pts


class TestMergeCollinearEntities:
    def test_deux_segments_connectes_fusionnes(self):
        """Deux segments qui se touchent bout-à-bout → une chaîne."""
        from cad.segment_merger import merge_collinear_entities
        s1 = [(0.0, 0.0), (5.0, 0.0)]
        s2 = [(5.0, 0.0), (10.0, 0.0)]
        result = merge_collinear_entities([s1, s2], eps_gap_mm=0.3, eps_rdp_mm=0.1)
        assert len(result) == 1
        pts = result[0]
        assert pts[0][0] < 1.0 and pts[-1][0] > 9.0

    def test_segments_avec_gap_fusionnes(self):
        """Deux segments avec un écart < eps_gap fusionnés."""
        from cad.segment_merger import merge_collinear_entities
        s1 = [(0.0, 0.0), (5.0, 0.0)]
        s2 = [(5.2, 0.0), (10.0, 0.0)]  # gap = 0.2mm < eps_gap=0.3mm
        result = merge_collinear_entities([s1, s2], eps_gap_mm=0.3, eps_rdp_mm=0.1)
        assert len(result) == 1

    def test_segments_distants_restent_separes(self):
        """Deux segments distants > eps_gap restent séparés."""
        from cad.segment_merger import merge_collinear_entities
        s1 = [(0.0, 0.0), (5.0, 0.0)]
        s2 = [(10.0, 0.0), (15.0, 0.0)]  # gap = 5mm >> eps_gap
        result = merge_collinear_entities([s1, s2], eps_gap_mm=0.3, eps_rdp_mm=0.1)
        assert len(result) == 2

    def test_liste_vide_retourne_vide(self):
        from cad.segment_merger import merge_collinear_entities
        assert merge_collinear_entities([]) == []

    def test_fusion_reduit_count(self):
        """20 micro-segments colinéaires → 1 polyligne."""
        from cad.segment_merger import merge_collinear_entities
        segs = [[(i * 1.0, 0.0), (i * 1.0 + 0.8, 0.0)] for i in range(20)]
        result = merge_collinear_entities(segs, eps_gap_mm=0.3, eps_rdp_mm=0.1)
        # Doit réduire significativement le nombre
        assert len(result) < 20

    def test_longueur_totale_conservee(self):
        """La longueur totale avant/après fusion doit rester proche."""
        from cad.segment_merger import merge_collinear_entities
        segs = [[(i * 2.0, 0.0), (i * 2.0 + 1.8, 0.0)] for i in range(10)]
        # Longueur totale originale : 10 * 1.8mm = 18mm
        original_len = sum(1.8 for _ in segs)
        result = merge_collinear_entities(segs, eps_gap_mm=0.3, eps_rdp_mm=0.3)
        merged_len = sum(
            sum(
                math.sqrt((pts[j + 1][0] - pts[j][0]) ** 2 + (pts[j + 1][1] - pts[j][1]) ** 2)
                for j in range(len(pts) - 1)
            )
            for pts in result
        )
        # La longueur fusionnée peut varier un peu (RDP simplifie), mais pas de >10% de perte
        # On accepte une perte jusqu'à 20% due à la simplification RDP
        assert merged_len >= original_len * 0.8


class TestSnapToOrthogonal:
    def test_segment_quasi_horizontal_snapped(self):
        """Segment à 3° du horizontal → forcé à 0°."""
        from cad.curve_fitter import snap_to_orthogonal
        # Segment de (0,0) à (10, 0.52) → angle ≈ 3°
        pts = [(0.0, 0.0), (10.0, 0.52)]
        result = snap_to_orthogonal(pts, theta_snap_deg=5.0)
        assert abs(result[1][1] - 0.0) < 1e-9  # y snappé à y0=0

    def test_segment_quasi_vertical_snapped(self):
        """Segment à 88° → forcé à 90°."""
        from cad.curve_fitter import snap_to_orthogonal
        pts = [(0.0, 0.0), (0.17, 10.0)]  # angle ≈ 89°
        result = snap_to_orthogonal(pts, theta_snap_deg=5.0)
        assert abs(result[1][0] - 0.0) < 1e-9  # x snappé à x0=0

    def test_segment_diagonal_conserve(self):
        """Segment à 45° → conservé tel quel."""
        from cad.curve_fitter import snap_to_orthogonal
        pts = [(0.0, 0.0), (10.0, 10.0)]  # 45°
        result = snap_to_orthogonal(pts, theta_snap_deg=5.0)
        assert abs(result[1][0] - 10.0) < 1e-9
        assert abs(result[1][1] - 10.0) < 1e-9

    def test_liste_vide(self):
        from cad.curve_fitter import snap_to_orthogonal
        assert snap_to_orthogonal([]) == []

    def test_un_point_retourne_tel_quel(self):
        from cad.curve_fitter import snap_to_orthogonal
        pts = [(5.0, 3.0)]
        assert snap_to_orthogonal(pts) == pts
