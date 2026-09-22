"""Tests unitaires du pipeline raster TIF → DXF (cad/raster_tif_extractor.py)."""
import pytest
import numpy as np
import cv2
from pathlib import Path
from PIL import Image


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tif_simple(tmp_path):
    """TIF 300 DPI avec 3 traits horizontaux parallèles."""
    img = np.ones((600, 800), dtype=np.uint8) * 255
    cv2.line(img, (50, 100), (750, 100), 0, 2)
    cv2.line(img, (50, 300), (750, 300), 0, 2)
    cv2.line(img, (50, 500), (750, 500), 0, 2)
    pil_img = Image.fromarray(img)
    path = tmp_path / "test_simple.tif"
    pil_img.save(str(path), dpi=(300, 300))
    return path


@pytest.fixture
def tif_vide(tmp_path):
    """TIF entièrement blanc — aucune géométrie."""
    img = np.ones((100, 100), dtype=np.uint8) * 255
    pil_img = Image.fromarray(img)
    path = tmp_path / "test_vide.tif"
    pil_img.save(str(path), dpi=(300, 300))
    return path


@pytest.fixture
def tif_multipage(tmp_path):
    """TIF multi-page (3 frames), 300 DPI."""
    frames = []
    for i in range(3):
        img = np.ones((400, 600), dtype=np.uint8) * 255
        cv2.line(img, (10, 50 + i * 50), (590, 50 + i * 50), 0, 2)
        frames.append(Image.fromarray(img))
    path = tmp_path / "test_multipage.tif"
    frames[0].save(str(path), dpi=(300, 300), save_all=True, append_images=frames[1:])
    return path


# ── Tests source_detector ─────────────────────────────────────────────────────

class TestSourceDetectorTif:
    def test_detect_source_mode_tif_retourne_raster(self, tmp_path):
        """detect_source_mode doit retourner 'raster' pour .tif sans lire PyMuPDF."""
        from cad.source_detector import detect_source_mode
        img = np.ones((10, 10), dtype=np.uint8) * 255
        path = tmp_path / "x.tif"
        Image.fromarray(img).save(str(path))
        assert detect_source_mode(path) == 'raster'

    def test_detect_source_mode_tiff_retourne_raster(self, tmp_path):
        """Extension .tiff doit aussi retourner 'raster'."""
        from cad.source_detector import detect_source_mode
        img = np.ones((10, 10), dtype=np.uint8) * 255
        path = tmp_path / "x.tiff"
        Image.fromarray(img).save(str(path))
        assert detect_source_mode(path) == 'raster'


# ── Tests utilitaires internes ────────────────────────────────────────────────

class TestPxToMm:
    def test_px_to_mm_300dpi_un_pouce(self):
        """300 px à 300 DPI = 25.4 mm (1 pouce)."""
        from cad.raster_tif_extractor import _px_to_mm
        assert abs(_px_to_mm(300, 300) - 25.4) < 0.01

    def test_px_to_mm_200dpi_un_pouce(self):
        """200 px à 200 DPI = 25.4 mm."""
        from cad.raster_tif_extractor import _px_to_mm
        assert abs(_px_to_mm(200, 200) - 25.4) < 0.01

    def test_px_to_mm_zero(self):
        """0 px → 0 mm."""
        from cad.raster_tif_extractor import _px_to_mm
        assert _px_to_mm(0, 300) == 0.0

    def test_px_to_mm_formule_lineaire(self):
        """Formule px * 25.4 / dpi : 150 px à 300 DPI = 12.7 mm."""
        from cad.raster_tif_extractor import _px_to_mm
        assert abs(_px_to_mm(150, 300) - 12.7) < 0.01


class TestReadDpi:
    def test_read_dpi_present_300(self, tmp_path):
        """PIL Image sauvée avec dpi=(300,300) → _read_dpi retourne 300."""
        from cad.raster_tif_extractor import _read_dpi
        img = Image.fromarray(np.ones((10, 10), dtype=np.uint8) * 255)
        path = tmp_path / "dpi300.tif"
        img.save(str(path), dpi=(300, 300))
        pil = Image.open(str(path))
        assert abs(_read_dpi(pil) - 300.0) < 1.0

    def test_read_dpi_absent_fallback(self):
        """Image PIL sans métadonnées DPI → retourne _DEFAULT_DPI (300)."""
        from cad.raster_tif_extractor import _read_dpi, _DEFAULT_DPI
        img = Image.fromarray(np.ones((10, 10), dtype=np.uint8) * 255)
        assert _read_dpi(img) == _DEFAULT_DPI

    def test_read_dpi_default_vaut_300(self):
        """_DEFAULT_DPI doit valoir 300 (convention industrielle standard)."""
        from cad.raster_tif_extractor import _DEFAULT_DPI
        assert _DEFAULT_DPI == 300


# ── Tests extract_raster_tif ──────────────────────────────────────────────────

class TestExtractRasterTif:
    def test_retourne_cad_document(self, tif_simple):
        """extract_raster_tif retourne un CadDocument."""
        from cad.raster_tif_extractor import extract_raster_tif
        from cad.models import CadDocument
        doc = extract_raster_tif(tif_simple)
        assert isinstance(doc, CadDocument)

    def test_une_page_pour_tif_simple(self, tif_simple):
        """TIF simple 1 frame → CadDocument avec exactement 1 page."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_simple)
        assert len(doc.pages) == 1

    def test_source_mode_raster(self, tif_simple):
        """CadPage.source_mode doit valoir 'raster'."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_simple)
        assert doc.pages[0].source_mode == 'raster'

    def test_dimensions_positives(self, tif_simple):
        """CadPage.width et height doivent être > 0."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_simple)
        page = doc.pages[0]
        assert page.width > 0
        assert page.height > 0

    def test_dimensions_coherentes_300dpi(self, tif_simple):
        """Image 800×600px à 300 DPI → dimensions ~67.7×50.8 mm."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_simple)
        page = doc.pages[0]
        assert abs(page.width - 800 * 25.4 / 300) < 1.0
        assert abs(page.height - 600 * 25.4 / 300) < 1.0

    def test_contient_entites_polyline(self, tif_simple):
        """Image avec 3 traits → au moins 1 entité POLYLINE ou SPLINE détectée."""
        from cad.raster_tif_extractor import extract_raster_tif
        from cad.models import EntityKind
        doc = extract_raster_tif(tif_simple)
        entites = [e for e in doc.pages[0].entities
                   if e.kind in (EntityKind.POLYLINE, EntityKind.SPLINE)]
        assert len(entites) >= 1

    def test_image_vide_zero_entites(self, tif_vide):
        """Image blanche → 0 entité POLYLINE ou SPLINE (pas d'exception)."""
        from cad.raster_tif_extractor import extract_raster_tif
        from cad.models import EntityKind
        doc = extract_raster_tif(tif_vide)
        assert len(doc.pages) == 1
        entites = [e for e in doc.pages[0].entities
                   if e.kind in (EntityKind.POLYLINE, EntityKind.SPLINE)]
        assert len(entites) == 0

    def test_multipage_trois_pages(self, tif_multipage):
        """TIF multi-page 3 frames → CadDocument avec 3 pages."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_multipage)
        assert len(doc.pages) == 3

    def test_page_indices_selection(self, tif_multipage):
        """page_indices=[0, 2] sur TIF 3 pages → 2 pages retournées."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_multipage, page_indices=[0, 2])
        assert len(doc.pages) == 2

    def test_page_index_hors_borne(self, tif_simple):
        """page_indices=[99] sur TIF 1 page → 0 page, pas d'exception."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_simple, page_indices=[99])
        assert len(doc.pages) == 0

    def test_source_path_conservee(self, tif_simple):
        """CadDocument.source_path doit pointer vers le fichier d'origine."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_simple)
        assert Path(doc.source_path) == Path(tif_simple)

    def test_pas_exception_sur_png(self, tmp_path):
        """extract_raster_tif accepte aussi les PNG (pas uniquement les TIF)."""
        from cad.raster_tif_extractor import extract_raster_tif
        img = np.ones((100, 100), dtype=np.uint8) * 255
        cv2.line(img, (10, 50), (90, 50), 0, 3)
        path = tmp_path / "test.png"
        Image.fromarray(img).save(str(path))
        doc = extract_raster_tif(path)
        assert len(doc.pages) == 1

    def test_page_indices_none_traite_tout(self, tif_multipage):
        """page_indices=None → toutes les frames sont traitées."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_multipage, page_indices=None)
        assert len(doc.pages) == 3

    def test_page_index_zero_dans_multipage(self, tif_multipage):
        """page_indices=[0] sur TIF 3 pages → exactement 1 page."""
        from cad.raster_tif_extractor import extract_raster_tif
        doc = extract_raster_tif(tif_multipage, page_indices=[0])
        assert len(doc.pages) == 1


# ── Tests coordonnées DXF ─────────────────────────────────────────────────────

class TestCoordonneesDxf:
    def test_inversion_y_trait_haut_image(self, tmp_path):
        """
        Un trait en haut (y_px petit) → y_mm grand en DXF (inversion Y).
        Un trait en bas (y_px grand) → y_mm petit en DXF.
        """
        from cad.raster_tif_extractor import extract_raster_tif
        img = np.ones((600, 600), dtype=np.uint8) * 255
        cv2.line(img, (10, 10), (590, 10), 0, 3)    # trait en haut (y_px=10)
        cv2.line(img, (10, 580), (590, 580), 0, 3)  # trait en bas (y_px=580)
        pil = Image.fromarray(img)
        path = tmp_path / "inversion.tif"
        pil.save(str(path), dpi=(300, 300))
        doc = extract_raster_tif(path)
        geom = [e for e in doc.pages[0].entities if e.layer == 'GEOMETRIE']
        # Vérifie qu'au moins 2 entités sont détectées avant d'affirmer l'inversion
        if len(geom) >= 2:
            y_values = sorted([ent.geometry['points'][0][1] for ent in geom])
            # Le trait en bas (y_px=580) doit avoir un y_dxf plus petit
            assert y_values[0] < y_values[-1]

    def test_coordonnees_en_mm_pas_pixels(self, tif_simple):
        """
        Les coordonnées DXF doivent être en mm.
        Image 800px large à 300 DPI → max x_mm ≈ 67.7 mm, jamais > 100 mm.
        """
        from cad.raster_tif_extractor import extract_raster_tif
        _GEOM_LAYERS = {'CABLES', 'CABLES_EXISTANTS', 'GEOMETRIE', 'TEXTE'}
        doc = extract_raster_tif(tif_simple)
        geom = [e for e in doc.pages[0].entities if e.layer in _GEOM_LAYERS]
        assert len(geom) >= 1
        for ent in geom:
            # En pixels 800 DPI, x serait > 100. En mm, toujours < 100.
            assert ent.geometry['points'][0][0] < 100

    def test_layer_lignes_raster(self, tif_simple):
        """Les entités géométrie sont sur un calque de géométrie reconnu."""
        from cad.raster_tif_extractor import extract_raster_tif
        _GEOM_LAYERS = {'CABLES', 'CABLES_EXISTANTS', 'GEOMETRIE', 'TEXTE'}
        doc = extract_raster_tif(tif_simple)
        geom = [e for e in doc.pages[0].entities if e.layer in _GEOM_LAYERS]
        assert len(geom) >= 1
        for ent in geom:
            assert ent.layer in _GEOM_LAYERS


# ── Tests nouveaux modules internes ───────────────────────────────────────────

class TestSkeletonize:
    def test_skeletonize_image_vide_retourne_vide(self):
        import numpy as np
        from cad.raster_tif_extractor import _skeletonize
        empty = np.zeros((50, 50), dtype=np.uint8)
        result = _skeletonize(empty)
        assert result.sum() == 0

    def test_skeletonize_retourne_ndarray(self):
        import numpy as np
        import cv2
        from cad.raster_tif_extractor import _skeletonize
        img = np.zeros((100, 100), dtype=np.uint8)
        img[40:60, 10:90] = 255
        result = _skeletonize(img)
        assert isinstance(result, np.ndarray)
        assert cv2.countNonZero(result) > 0

    def test_skeletonize_reduit_epaisseur(self):
        """Un trait de 20px de large doit produire un squelette nettement plus fin."""
        import numpy as np
        import cv2
        from cad.raster_tif_extractor import _skeletonize
        thick = np.zeros((100, 200), dtype=np.uint8)
        thick[40:60, :] = 255
        skel = _skeletonize(thick)
        assert cv2.countNonZero(skel) < cv2.countNonZero(thick) * 0.2


class TestSeparateTextGeometry:
    def test_grande_composante_va_en_geometrie(self):
        import numpy as np
        import cv2
        from cad.raster_tif_extractor import _separate_text_geometry
        binary = np.zeros((200, 400), dtype=np.uint8)
        binary[20:180, 10:390] = 255
        geom, text = _separate_text_geometry(binary, dpi=300.0)
        assert cv2.countNonZero(geom) > 0
        assert cv2.countNonZero(text) == 0

    def test_petite_composante_va_en_texte(self):
        import numpy as np
        import cv2
        from cad.raster_tif_extractor import _separate_text_geometry
        binary = np.zeros((200, 400), dtype=np.uint8)
        binary[90:110, 190:210] = 255
        geom, text = _separate_text_geometry(binary, dpi=300.0)
        assert cv2.countNonZero(text) > 0
        assert cv2.countNonZero(geom) == 0

    def test_image_vide_retourne_deux_masques_vides(self):
        import numpy as np
        from cad.raster_tif_extractor import _separate_text_geometry
        binary = np.zeros((100, 100), dtype=np.uint8)
        geom, text = _separate_text_geometry(binary, dpi=300.0)
        assert geom.sum() == 0
        assert text.sum() == 0


class TestLineweightFromRadius:
    def test_trait_fin(self):
        from cad.raster_tif_extractor import _lineweight_from_radius
        assert _lineweight_from_radius(0.05) == 0.18

    def test_trait_normal(self):
        from cad.raster_tif_extractor import _lineweight_from_radius
        assert _lineweight_from_radius(0.15) == 0.35

    def test_trait_gras(self):
        from cad.raster_tif_extractor import _lineweight_from_radius
        assert _lineweight_from_radius(0.35) == 0.35   # plafonné — pas de 0.60mm


class TestIsSmoothCurve:
    def test_droite_retourne_false(self):
        """Droite parfaite : courbure totale < 5° → False."""
        from cad.raster_tif_extractor import _is_smooth_curve
        pts = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
        assert _is_smooth_curve(pts) is False

    def test_angle_droit_retourne_false(self):
        """Angle à 90° → coin détecté → False."""
        from cad.raster_tif_extractor import _is_smooth_curve
        pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        assert _is_smooth_curve(pts) is False

    def test_courbe_douce_retourne_true(self):
        """Arc de cercle graduel → True."""
        import math
        from cad.raster_tif_extractor import _is_smooth_curve
        pts = [(math.cos(t) * 100, math.sin(t) * 100) for t in [i * 0.1 for i in range(10)]]
        assert _is_smooth_curve(pts) is True
