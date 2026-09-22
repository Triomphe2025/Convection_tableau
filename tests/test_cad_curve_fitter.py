"""Tests du module cad/curve_fitter.py — détection tiretés et reconstruction courbes."""
import math
import pytest


class TestPathLength:
    def test_segment_horizontal(self):
        from cad.curve_fitter import _path_length
        assert abs(_path_length([(0, 0), (10, 0)]) - 10.0) < 0.01

    def test_chemin_vide(self):
        from cad.curve_fitter import _path_length
        assert _path_length([]) == 0.0

    def test_un_point(self):
        from cad.curve_fitter import _path_length
        assert _path_length([(5, 5)]) == 0.0


class TestIsStaightLine:
    def test_deux_points_est_droite(self):
        from cad.curve_fitter import is_straight_line
        assert is_straight_line([(0, 0), (10, 0)]) is True

    def test_points_alignes_est_droite(self):
        from cad.curve_fitter import is_straight_line
        pts = [(float(i), 0.0) for i in range(20)]
        assert is_straight_line(pts, tol_mm=0.3) is True

    def test_courbe_sinusoidale_pas_droite(self):
        from cad.curve_fitter import is_straight_line
        pts = [(float(i), math.sin(i * 0.5) * 5.0) for i in range(20)]
        assert is_straight_line(pts, tol_mm=0.3) is False

    def test_tolerance_affecte_resultat(self):
        from cad.curve_fitter import is_straight_line
        # Point à 0.3mm de la droite
        pts = [(0.0, 0.0), (5.0, 0.3), (10.0, 0.0)]
        assert is_straight_line(pts, tol_mm=0.5) is True
        assert is_straight_line(pts, tol_mm=0.1) is False


class TestGroupCollinearFragments:
    def test_fragments_courts_et_long_separes(self):
        from cad.curve_fitter import group_collinear_fragments
        # Un fragment court (5mm) et un long (50mm)
        court = [(0.0, 0.0), (5.0, 0.0)]
        long = [(0.0, 10.0), (50.0, 10.0)]
        groupes, longs = group_collinear_fragments([court, long], dpi=200.0)
        assert len(longs) == 1
        assert any(court in g for g in groupes)

    def test_deux_fragments_meme_droite_groupes(self):
        from cad.curve_fitter import group_collinear_fragments
        f1 = [(0.0, 0.0), (10.0, 0.0)]
        f2 = [(15.0, 0.0), (25.0, 0.0)]  # même ligne horizontale y=0
        groupes, _ = group_collinear_fragments([f1, f2], dpi=200.0)
        assert any(len(g) == 2 for g in groupes)

    def test_fragments_paralleles_separes(self):
        from cad.curve_fitter import group_collinear_fragments
        f1 = [(0.0, 0.0), (10.0, 0.0)]   # y=0
        f2 = [(0.0, 5.0), (10.0, 5.0)]   # y=5mm — trop loin (> 1mm de tolérance)
        groupes, _ = group_collinear_fragments([f1, f2], dpi=200.0)
        # Les deux doivent être dans des groupes séparés
        assert not any(len(g) == 2 for g in groupes)


class TestDetectDashPattern:
    def test_tirets_reguliers_detectes(self):
        """3 fragments régulièrement espacés → is_dashed=True."""
        from cad.curve_fitter import detect_dash_pattern
        # 3 tirets de 5mm espacés de 3mm chacun
        group = [
            [(0.0, 0.0), (5.0, 0.0)],
            [(8.0, 0.0), (13.0, 0.0)],
            [(16.0, 0.0), (21.0, 0.0)],
        ]
        result = detect_dash_pattern(group, dpi=200.0)
        assert result['is_dashed'] is True
        assert abs(result['lt_mm'] - 5.0) < 0.5
        assert abs(result['le_mm'] - 3.0) < 0.5

    def test_fragments_irreguliers_non_detectes(self):
        """Espacements très irréguliers → is_dashed=False."""
        from cad.curve_fitter import detect_dash_pattern
        group = [
            [(0.0, 0.0), (5.0, 0.0)],
            [(6.0, 0.0), (11.0, 0.0)],   # gap=1mm
            [(25.0, 0.0), (30.0, 0.0)],  # gap=14mm (très irrégulier)
        ]
        result = detect_dash_pattern(group, dpi=200.0)
        assert result['is_dashed'] is False

    def test_moins_de_3_fragments_pas_detecte(self):
        """Moins de 3 fragments → impossible de valider la périodicité."""
        from cad.curve_fitter import detect_dash_pattern
        group = [[(0.0, 0.0), (5.0, 0.0)], [(8.0, 0.0), (13.0, 0.0)]]
        result = detect_dash_pattern(group, dpi=200.0)
        assert result['is_dashed'] is False

    def test_ltscale_calculee(self):
        """La LTSCALE AutoCAD doit être calculée depuis lt et le."""
        from cad.curve_fitter import detect_dash_pattern
        group = [
            [(0.0, 0.0), (12.7, 0.0)],   # tiret = 12.7mm (référence AutoCAD)
            [(19.05, 0.0), (31.75, 0.0)],
            [(38.1, 0.0), (50.8, 0.0)],
        ]
        result = detect_dash_pattern(group, dpi=200.0)
        if result['is_dashed']:
            assert result['ltscale'] > 0.5  # valeur positive


class TestMergeCollinearToOne:
    def test_deux_segments_proches_fusionnes(self):
        from cad.curve_fitter import merge_collinear_to_one
        s1 = [(0.0, 0.0), (10.0, 0.0)]
        s2 = [(11.0, 0.0), (20.0, 0.0)]  # gap = 1mm < 2mm
        result = merge_collinear_to_one([s1, s2])
        assert len(result) == 1

    def test_segments_eloignes_non_fusionnes(self):
        from cad.curve_fitter import merge_collinear_to_one
        s1 = [(0.0, 0.0), (10.0, 0.0)]
        s2 = [(50.0, 0.0), (60.0, 0.0)]  # gap = 40mm >> 2mm
        result = merge_collinear_to_one([s1, s2])
        assert len(result) == 2

    def test_liste_vide_retourne_vide(self):
        from cad.curve_fitter import merge_collinear_to_one
        assert merge_collinear_to_one([]) == []


class TestClassifyAndFit:
    def test_droite_retourne_line(self):
        from cad.curve_fitter import classify_and_fit
        pts = [(float(i), 0.0) for i in range(10)]
        result = classify_and_fit(pts)
        assert result.kind == 'LINE'
        assert len(result.points) == 2

    def test_polyligne_avec_coin_retourne_polyline(self):
        from cad.curve_fitter import classify_and_fit
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]  # angle 90°
        result = classify_and_fit(pts)
        assert result.kind == 'POLYLINE'

    def test_liste_vide_pas_exception(self):
        from cad.curve_fitter import classify_and_fit
        result = classify_and_fit([])
        assert result.kind == 'POLYLINE'

    def test_un_point_pas_exception(self):
        from cad.curve_fitter import classify_and_fit
        result = classify_and_fit([(0.0, 0.0)])
        assert result.kind == 'POLYLINE'
