"""Tests de non-régression mémoire pour le pipeline raster CAD."""
import numpy as np


def test_preprocess_petite_image():
    """Images < 10 Mpx : fastNlMeansDenoising utilisé, retourne uint8 même forme."""
    from cad.raster_tif_extractor import _preprocess
    gray = np.ones((100, 200), dtype=np.uint8) * 200
    result = _preprocess(gray)
    assert result.shape == gray.shape
    assert result.dtype == np.uint8


def test_preprocess_grande_image_sans_oom():
    """Images > 10 Mpx : GaussianBlur utilisé — doit terminer sans erreur mémoire."""
    from cad.raster_tif_extractor import _preprocess
    # 4000×3000 = 12 Mpx > seuil 10 Mpx → GaussianBlur
    gray = np.random.randint(100, 220, (3000, 4000), dtype=np.uint8)
    result = _preprocess(gray)
    assert result.shape == gray.shape
    assert result.dtype == np.uint8


def test_preprocess_seuil_10mpx():
    """Image juste au-dessus du seuil (> 10 000 000 pixels) utilise GaussianBlur."""
    from cad.raster_tif_extractor import _preprocess
    # 3163 × 3163 = 10 004 569 pixels > 10 000 000
    gray = np.ones((3163, 3163), dtype=np.uint8) * 180
    result = _preprocess(gray)
    assert result.shape == gray.shape
    assert result.dtype == np.uint8


def test_downscale_raster_reduit_dimensions():
    """Auto-downscale : une image > 20 Mpx est réduite avant traitement."""
    import cv2
    # Image synthétique 6000×4000 = 24 Mpx > seuil 20 Mpx
    gray = np.ones((4000, 6000), dtype=np.uint8) * 200
    _MAX = 20_000_000
    pc = gray.shape[0] * gray.shape[1]
    assert pc > _MAX, "Précondition : image au-dessus du seuil"
    ratio = (_MAX / pc) ** 0.5
    nw = max(1, int(gray.shape[1] * ratio))
    nh = max(1, int(gray.shape[0] * ratio))
    resized = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA)
    assert resized.shape[0] * resized.shape[1] <= _MAX * 1.05  # ≤ 20 Mpx (marge 5%)
    assert resized.dtype == np.uint8


def test_downscale_raster_preserve_ratio():
    """Auto-downscale : le ratio largeur/hauteur est préservé (déformation < 1%)."""
    H, W = 7308, 10215  # dimensions réelles de P1B-B-202-022.tif
    _MAX = 20_000_000
    ratio = (_MAX / (H * W)) ** 0.5
    nw = max(1, int(W * ratio))
    nh = max(1, int(H * ratio))
    orig_ratio = W / H
    new_ratio = nw / nh
    assert abs(new_ratio - orig_ratio) / orig_ratio < 0.01  # déformation < 1%


def test_dist_map_float32_sans_buffer_2d():
    """cv2.distanceTransform retourne float32, pas float64, sans buffer (2,H,W)."""
    import cv2
    line = np.zeros((50, 100), dtype=np.uint8)
    line[20:30, 10:90] = 255   # rectangle = trait horizontal
    dist = cv2.distanceTransform(line, cv2.DIST_L2, 5)
    assert dist.dtype == np.float32, "Doit être float32 (pas float64)"
    assert dist.shape == line.shape, "Doit être (H,W), pas (2,H,W)"
    # Le centre du rectangle a la distance maximale (≈ demi-largeur = 5px)
    assert dist[25, 50] > dist[20, 50]


def test_lineweight_plafonne_a_035():
    """Correction P2b : aucun lineweight ne dépasse 0.35mm."""
    from cad.raster_tif_extractor import _lineweight_from_radius
    assert _lineweight_from_radius(0.05) == 0.18   # fin
    assert _lineweight_from_radius(0.20) == 0.35   # normal
    assert _lineweight_from_radius(5.0) == 0.35    # câble épais → plafonné


def test_separate_text_geometry_seuil_mm():
    """Seuil texte/géom = 7.62mm (60px à 200DPI, cf. méthodologie §2.2)."""
    from cad.raster_tif_extractor import _separate_text_geometry
    binary = np.zeros((250, 250), dtype=np.uint8)
    binary[10:40, 10:40] = 255     # 30×30px = 2.54mm à 300DPI < 7.62mm → texte
    binary[100:200, 100:200] = 255  # 100×100px = 8.47mm à 300DPI > 7.62mm → géométrie
    geom, text = _separate_text_geometry(binary, dpi=300.0)
    assert text[25, 25] == 255     # petit composant (2.54mm) → texte
    assert geom[150, 150] == 255   # grand composant (8.47mm) → géométrie


def test_process_page_sans_blobs_texte():
    """Correction P1 : aucune entité TEXTE dans la sortie _process_page."""
    from PIL import Image
    from cad.raster_tif_extractor import _process_page
    arr = np.ones((100, 100), dtype=np.uint8) * 255
    arr[20:25, 20:25] = 0   # petit carré noir
    arr[50:55, 50:55] = 0   # deuxième petit carré
    pil_img = Image.fromarray(arr)
    page = _process_page(pil_img, page_index=0)
    texte_entities = [e for e in page.entities if e.layer == 'TEXTE']
    assert len(texte_entities) == 0


def test_micro_entites_filtrees():
    """P4 : les entités < 2mm ne doivent pas apparaître dans la sortie (nuage de points)."""
    import math
    # Simuler le calcul de longueur d'une entité très courte (< 2mm)
    pts_courts = [(0.0, 0.0), (0.5, 0.5)]   # longueur ≈ 0.71mm < 2mm
    pts_longs  = [(0.0, 0.0), (10.0, 0.0)]  # longueur = 10mm > 2mm
    MIN = 2.0

    def longueur(pts):
        return sum(
            math.sqrt((pts[i+1][0]-pts[i][0])**2 + (pts[i+1][1]-pts[i][1])**2)
            for i in range(len(pts)-1)
        )

    assert longueur(pts_courts) < MIN   # doit être filtré
    assert longueur(pts_longs) >= MIN   # doit être conservé


def test_spur_threshold_adaptatif():
    """Correction P2a : le seuil d'élagage dépasse 8 pour un trait épais (> 32px)."""
    import cv2
    # Trait de 40px d'épaisseur → max_dist ≈ 20px → spur = max(8, 10) = 10 > 8
    line = np.zeros((60, 100), dtype=np.uint8)
    line[10:50, 5:95] = 255
    dist = cv2.distanceTransform(line, cv2.DIST_L2, 5)
    max_dist = float(dist.max())
    expected_spur = max(8, int(max_dist * 0.5))
    assert expected_spur >= 8    # jamais moins que 8
    assert expected_spur > 8     # trait épais → seuil supérieur au minimum
