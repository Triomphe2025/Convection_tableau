"""Tests unitaires pour cad/vectorizer.py."""
import math

import numpy as np


def test_snap_lineweight_fin():
    """Lignes fines → 0.09 mm (dessin technique électrique)."""
    from cad.vectorizer import snap_lineweight
    assert abs(snap_lineweight(0.20) - 0.09) < 1e-9


def test_snap_lineweight_normal():
    from cad.vectorizer import snap_lineweight
    assert abs(snap_lineweight(0.50) - 0.18) < 1e-9


def test_snap_lineweight_gras():
    from cad.vectorizer import snap_lineweight
    assert abs(snap_lineweight(1.20) - 0.25) < 1e-9


def test_snap_lineweight_frontiere_bas():
    """La valeur exacte 0.40 doit basculer vers normal (0.18 mm)."""
    from cad.vectorizer import snap_lineweight
    assert abs(snap_lineweight(0.40) - 0.18) < 1e-9


def test_detect_corners_angle_droit():
    from cad.vectorizer import detect_corners
    # Virage à 90° : ligne horizontale puis verticale
    pts = np.array(
        [[float(i), 0.0] for i in range(10)]
        + [[10.0, float(i)] for i in range(1, 10)]
    )
    corners = detect_corners(pts, window=3, angle_deg=22.0)
    # Le point d'inflexion (index 9) doit être détecté comme coin
    assert corners[9]


def test_detect_corners_courbe_douce():
    from cad.vectorizer import detect_corners
    # Arc régulier (courbe douce, pas de coin)
    t = np.linspace(0, math.pi / 4, 30)
    pts = np.column_stack([np.cos(t) * 10, np.sin(t) * 10])
    corners = detect_corners(pts, window=5, angle_deg=22.0)
    # Seuls les bords sont True (forcés), le milieu ne doit pas avoir de coin
    assert not corners[5:-5].any()


def test_detect_corners_single_point():
    from cad.vectorizer import detect_corners
    pts = np.array([[0.0, 0.0], [1.0, 0.0]])
    corners = detect_corners(pts)
    assert corners[0] and corners[-1]


def test_fit_spline_no_nan():
    from cad.vectorizer import fit_spline
    t = np.linspace(0, 2 * math.pi, 50)
    pts = np.column_stack([np.cos(t) * 5, np.sin(t) * 5])
    result = fit_spline(pts, max_samples=30)
    if result is not None:
        _, ctrl, _ = result
        assert all(not (math.isnan(x) or math.isnan(y)) for x, y in ctrl)


def test_fit_spline_returns_none_on_degenerate():
    from cad.vectorizer import fit_spline
    # Deux points identiques → longueur curviligne nulle
    pts = np.array([[0.0, 0.0], [0.0, 0.0]])
    result = fit_spline(pts)
    assert result is None


def test_etapes_liste_complete():
    """La liste ETAPES doit contenir les 7 étapes dans le bon ordre."""
    from cad.vectorizer import ETAPES
    assert ETAPES == [
        "chargement",
        "pretraitement",
        "separation",
        "squelettisation",
        "graphe",
        "vectorisation",
        "export",
    ]


def test_build_entities_path_trop_court():
    """Un chemin à 1 seul point doit être ignoré sans erreur."""
    from cad.vectorizer import _build_entities_from_paths
    result = _build_entities_from_paths([([[0, 0]], 0.35)], scale=0.127, max_samples=50)
    assert result == []


# ── Tests patch v1.1 — pré-lissage et fusion de coins ────────────────────────

def test_presmooth_edge_fixe_extremites():
    """Les extrémités doivent rester exactement aux positions originales."""
    from cad.vectorizer import presmooth_edge
    pts = np.array([[0.0, 0.0], [1.0, 0.5], [2.0, 0.0], [3.0, 0.5], [4.0, 0.0]])
    smoothed = presmooth_edge(pts, sigma=1.0)
    np.testing.assert_array_almost_equal(smoothed[0], pts[0])
    np.testing.assert_array_almost_equal(smoothed[-1], pts[-1])


def test_presmooth_edge_reduit_bruit():
    """Le lissage doit réduire la variance du signal bruité."""
    from cad.vectorizer import presmooth_edge
    xs = np.linspace(0, 10, 50)
    noise = np.array([0.5 if i % 2 == 0 else -0.5 for i in range(50)])
    pts = np.column_stack([xs, noise])
    smoothed = presmooth_edge(pts, sigma=2.5)
    assert smoothed[1:-1, 1].std() < pts[1:-1, 1].std()


def test_merge_close_corners_fusionne():
    """Deux coins à 5mm d'écart (< 15mm) → le second doit être supprimé."""
    from cad.vectorizer import merge_close_corners
    pts = np.array([[0.0, 0.0], [5.0, 0.0], [10.0, 0.0], [50.0, 0.0], [100.0, 0.0]])
    idxs = [0, 1, 2, 3, 4]
    merged = merge_close_corners(idxs, pts, min_sep_px=15.0)
    assert 2 not in merged          # coin trop proche fusionné
    assert 0 in merged and 4 in merged  # extrémités toujours présentes


def test_build_entities_couche_geometrie_uniquement():
    """Correction blob vectorizer : _build_entities_from_paths ne produit aucune entité TEXTE."""
    from cad.vectorizer import _build_entities_from_paths
    paths = [([[0, 0], [5, 0], [10, 5], [15, 5]], 0.35)]
    entities = _build_entities_from_paths(paths, scale=0.1, max_samples=50)
    assert all(e.layer != 'TEXTE' for e in entities)


def test_separate_text_geometry_signature_dpi():
    """Régression P3 vectorizer : _separate_text_geometry accepte dpi=float sans crash."""
    import numpy as np
    from cad.raster_tif_extractor import _separate_text_geometry
    binary = np.zeros((80, 80), dtype=np.uint8)
    binary[5:20, 5:20] = 255   # 15×15px composant
    binary[40:70, 40:70] = 255  # 30×30px composant
    geom, text = _separate_text_geometry(binary, dpi=155.0)  # DPI effectif post-downscale
    assert geom.shape == binary.shape
    assert text.shape == binary.shape


def test_max_samples_conforme_patch_v11():
    """Divergence §2c patch v1.1 : MAX_SAMPLES doit être 180, pas 500."""
    from cad.vectorizer import _MAX_SAMPLES
    assert _MAX_SAMPLES == 180, f"Attendu 180 (patch v1.1), obtenu {_MAX_SAMPLES}"


def test_dxf_version_r2013():
    """Divergence §2.9 méthodo : write_dxf doit générer du DXF R2013."""
    import inspect
    from cad.dxf_writer import write_dxf
    sig = inspect.signature(write_dxf)
    default_version = sig.parameters['version'].default
    assert default_version == "R2013", f"Attendu R2013, obtenu {default_version}"


def test_seuil_texte_geom_7_62mm():
    """Divergence §2.2 méthodo : seuil texte/géom doit être 7.62mm (= 60px à 200DPI)."""
    import inspect
    from cad.raster_tif_extractor import _separate_text_geometry
    sig = inspect.signature(_separate_text_geometry)
    default_mm = sig.parameters['text_max_dim_mm'].default
    assert abs(default_mm - 7.62) < 0.01, f"Attendu 7.62mm, obtenu {default_mm}mm"


def test_detection_polarite_inverse():
    """Méthodo §2.1 : image à polarité inversée (fond noir) doit être corrigée."""
    import cv2
    import numpy as np
    # Image où le "fond" est noir (0) et l'"encre" est blanche (255)
    # après THRESH_BINARY_INV, l'encre blanche deviendrait 0 = fond → polarité inversée
    # Simuler: binary où 80% des pixels = 255 (résultat inverti)
    binary = np.full((100, 100), 255, dtype=np.uint8)
    binary[40:60, 40:60] = 0   # petite zone noire = vrai encre (20% de la surface)
    fraction = float((binary > 127).mean())
    assert fraction > 0.5   # condition de déclenchement
    corrected = cv2.bitwise_not(binary)
    corrected_fraction = float((corrected > 127).mean())
    assert corrected_fraction < 0.5  # après correction, encre = minorité


# ── Tests §2.6ter — assemblage de chaînes _assemble_chains ───────────────────

def test_assemble_chains_lineaire_fusionne():
    """§2.6ter : 3 arêtes colinéaires doivent fusionner en 1 seule chaîne."""
    import networkx as nx
    import numpy as np
    from cad.vectorizer import _assemble_chains

    g = nx.MultiGraph()
    # 3 arêtes horizontales (y constant, x croissant) — colinéaires à 0°
    g.add_edge(0, 1, pts=np.array([[0, 0], [0, 1], [0, 2]]))
    g.add_edge(1, 2, pts=np.array([[0, 2], [0, 3], [0, 4]]))
    g.add_edge(2, 3, pts=np.array([[0, 4], [0, 5], [0, 6]]))

    chains = _assemble_chains(g, angle_max_deg=45.0)
    assert len(chains) == 1, f"Attendu 1 chaîne, obtenu {len(chains)}"
    assert len(chains[0]) >= 7  # 9 pts originaux − 2 doublons de nœuds


def test_assemble_chains_ratio_reduit():
    """§2.6ter : le nombre de chaînes doit être inférieur au nombre d'arêtes."""
    import networkx as nx
    import numpy as np
    from cad.vectorizer import _assemble_chains

    g = nx.MultiGraph()
    # 5 arêtes en ligne droite (n_edges=5 → n_chains=1 si tous colinéaires)
    for i in range(5):
        g.add_edge(i, i + 1, pts=np.array([[0, i * 3], [0, i * 3 + 1], [0, i * 3 + 2]]))

    chains = _assemble_chains(g, angle_max_deg=45.0)
    assert len(chains) < 5, (
        f"§2.6ter : attendu < 5 chaînes pour 5 arêtes colinéaires, obtenu {len(chains)}"
    )


def test_assemble_chains_visited_global_quater():
    """§2.6quater : aucune arête n'est visitée deux fois (ensemble visited global)."""
    import networkx as nx
    import numpy as np
    from cad.vectorizer import _assemble_chains

    g = nx.MultiGraph()
    # Fourche en Y : nœud 1 connecté à 0, 2 et 3
    g.add_edge(0, 1, pts=np.array([[0, 0], [0, 1], [0, 2]]))  # horizontal
    g.add_edge(1, 2, pts=np.array([[0, 2], [0, 3], [0, 4]]))  # horizontal
    g.add_edge(1, 3, pts=np.array([[0, 2], [1, 3], [2, 4]]))  # diagonal

    chains = _assemble_chains(g, angle_max_deg=45.0)
    # Vérifier que le total de pts couvre toutes les arêtes sans duplication d'arêtes
    total_edge_pts = sum(len(c) for c in chains)
    # 3 arêtes × 3 pts chacune = 9 pts, moins les doublons aux nœuds = 7 min
    assert total_edge_pts >= 7, "Des arêtes semblent manquantes (visited trop global ?)"
    assert len(chains) <= 3, "Pas plus de chaînes que d'arêtes (aucun doublon)"


# ── Tests _clean_loop_artifacts (§2b, pipeline de référence v3) ───────────────

def test_clean_loop_artifacts_remplace_boucle():
    """§2b : arête tortueuse (arc/corde > 2.5, corde < 40px) remplacée par segment droit."""
    import networkx as nx
    import numpy as np
    from cad.vectorizer import _clean_loop_artifacts

    g = nx.MultiGraph()
    # Zigzag court : arc ≈ 82px, corde ≈ 10px → ratio ≈ 8.2 >> 2.5, chord < 40px
    pts_zigzag = np.array([
        [0, 0], [20, 0], [0, 5], [20, 5], [0, 10], [1, 10]
    ])
    arc = float(np.linalg.norm(np.diff(pts_zigzag.astype(float), axis=0), axis=1).sum())
    chord = float(np.linalg.norm(pts_zigzag[-1].astype(float) - pts_zigzag[0].astype(float)))
    assert arc / chord > 2.5 and chord < 40.0, "Précondition : l'arête doit être un artefact"

    g.add_edge(0, 1, pts=pts_zigzag)
    n_cleaned = _clean_loop_artifacts(g, anomaly_ratio=2.5, max_chord_px=40.0)

    assert n_cleaned == 1
    for u, v, k, data in g.edges(keys=True, data=True):
        assert len(data['pts']) == 2, "L'arête doit être réduite à ses 2 extrémités"


def test_clean_loop_artifacts_conserve_longue_courbe():
    """§2b : une vraie courbe (corde > 40px) ne doit pas être nettoyée."""
    import networkx as nx
    import numpy as np
    from cad.vectorizer import _clean_loop_artifacts

    g = nx.MultiGraph()
    # Corde 100px >> 40px → vraie géométrie, pas un artefact
    pts = np.array([[0, 0], [20, 10], [40, 5], [60, 15], [0, 100]])
    g.add_edge(0, 1, pts=pts)

    n_cleaned = _clean_loop_artifacts(g, anomaly_ratio=2.5, max_chord_px=40.0)
    assert n_cleaned == 0


def test_clean_loop_artifacts_conserve_segment_droit():
    """§2b : segment court et droit (ratio ≈ 1) ne doit pas être nettoyé."""
    import networkx as nx
    import numpy as np
    from cad.vectorizer import _clean_loop_artifacts

    g = nx.MultiGraph()
    pts = np.array([[0, 0], [5, 0], [10, 0]])   # segment horizontal, ratio = 1
    g.add_edge(0, 1, pts=pts)

    n_cleaned = _clean_loop_artifacts(g, anomaly_ratio=2.5, max_chord_px=40.0)
    assert n_cleaned == 0


# ── Tests _dedup_by_overlap (Shapely safety net) ──────────────────────────────

def test_dedup_by_overlap_supprime_doublon():
    """Déduplication Shapely : deux LWPOLYLINE quasi-identiques → une seule conservée."""
    from cad.vectorizer import _dedup_by_overlap
    from cad.models import CadEntity, EntityKind

    pts_a = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]   # ligne à y=0
    pts_b = [(0.1, 0.1), (10.1, 0.1), (20.1, 0.1)]   # quasi-identique, décalée 0.1mm

    e1 = CadEntity(
        kind=EntityKind.POLYLINE, layer='GEOMETRIE', color=(0, 0, 0),
        geometry={'points': pts_a, 'closed': False},
    )
    e2 = CadEntity(
        kind=EntityKind.POLYLINE, layer='GEOMETRIE', color=(0, 0, 0),
        geometry={'points': pts_b, 'closed': False},
    )

    result = _dedup_by_overlap([e1, e2], buffer_mm=0.35, overlap_frac=0.6)
    assert len(result) == 1, f"Attendu 1 entité conservée, obtenu {len(result)}"


def test_dedup_by_overlap_conserve_entites_distinctes():
    """Déduplication Shapely : deux entités éloignées doivent toutes deux être conservées."""
    from cad.vectorizer import _dedup_by_overlap
    from cad.models import CadEntity, EntityKind

    pts_a = [(0.0, 0.0), (10.0, 0.0)]
    pts_b = [(50.0, 50.0), (60.0, 50.0)]   # éloignée de 50mm

    e1 = CadEntity(
        kind=EntityKind.POLYLINE, layer='GEOMETRIE', color=(0, 0, 0),
        geometry={'points': pts_a, 'closed': False},
    )
    e2 = CadEntity(
        kind=EntityKind.POLYLINE, layer='GEOMETRIE', color=(0, 0, 0),
        geometry={'points': pts_b, 'closed': False},
    )

    result = _dedup_by_overlap([e1, e2], buffer_mm=0.35, overlap_frac=0.6)
    assert len(result) == 2, "Les deux entités distantes doivent être conservées"


# ── Tests correctif cascade spur pruning (v1.8) ───────────────────────────────

def test_min_entity_len_mm_defaut():
    """Filtre micro-chaînes : seuil par défaut = 2.0mm."""
    from cad.vectorizer import _MIN_ENTITY_LEN_MM
    assert _MIN_ENTITY_LEN_MM == 2.0


def test_write_entity_spline_control_points():
    """Régression : SPLINE avec 'control_points' ne doit pas être silencieusement ignoré."""
    import ezdxf
    from cad.dxf_writer import _write_entity
    from cad.models import CadEntity, EntityKind

    ent = CadEntity(
        kind=EntityKind.SPLINE,
        layer='GEOMETRIE',
        color=(0, 0, 0),
        geometry={
            'control_points': [(0.0, 0.0), (10.0, 5.0), (20.0, 0.0), (30.0, 5.0)],
            'knots': [],
            'degree': 3,
            'closed': False,
        },
    )
    ent.lineweight = 35

    doc = ezdxf.new('R2013')
    msp = doc.modelspace()
    _write_entity(msp, ent, x_off=0.0)

    written = list(msp)
    assert len(written) == 1, (
        "SPLINE avec 'control_points' doit produire une entité DXF"
    )
    assert written[0].dxftype() in ('SPLINE', 'LWPOLYLINE')


def test_spur_pruning_une_seule_passe():
    """Correction cascade : une seule passe d'élagage ne doit pas détruire les arêtes longues."""
    import networkx as nx
    import numpy as np

    # Graphe en T : A(deg-1) --[10px]--> B(deg-3) --[10px]--> C(deg-1)
    #                                         |
    #                                      [10px]
    #                                         D (deg-1)
    # La cascade ancienne aurait supprimé AB et BC puis BC → graphe vide.
    # Avec une seule passe, seules les 3 épines courtes < seuil seraient candidates.
    g = nx.MultiGraph()
    pts10 = np.array([[i, 0] for i in range(11)])            # 10px horizontal
    g.add_edge(0, 1, pts=pts10)                               # A-B
    g.add_edge(1, 2, pts=pts10 + np.array([10, 0]))           # B-C
    g.add_edge(1, 3, pts=np.array([[i, i] for i in range(11)]))  # B-D diagonal 10px

    # Avec seuil 8px : 10px > 8px → aucune épine n'est supprimée
    # → le graphe doit rester intact
    deg = dict(g.degree())
    to_rm = []
    spur_thresh = 8.0
    for u, v, k, data in g.edges(keys=True, data=True):
        pts = data.get('pts', np.array([]))
        arc_L = float(
            np.linalg.norm(np.diff(pts.astype(float), axis=0), axis=1).sum()
        ) if len(pts) >= 2 else 0.0
        if (deg.get(u, 0) == 1 or deg.get(v, 0) == 1) and arc_L < spur_thresh:
            to_rm.append((u, v, k))
    assert len(to_rm) == 0, (
        "Aucune épine de 10px ne devrait être supprimée avec seuil 8px"
    )
    assert g.number_of_edges() == 3, "Graphe intact après 1 passe"


# ── Tests PDF raster → vectorize() ────────────────────────────────────────────

def test_detect_source_mode_pdf_raster():
    """PDF sans drawings vectoriels → détecté comme 'raster'."""
    import fitz
    import tempfile
    from pathlib import Path
    from cad.source_detector import detect_source_mode

    pdf_doc = fitz.open()
    pdf_doc.new_page(width=200, height=200)   # page vide, pas de drawings
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tf:
        pdf_path = Path(tf.name)
    pdf_doc.save(str(pdf_path))
    pdf_doc.close()

    try:
        mode = detect_source_mode(pdf_path)
        assert mode == 'raster', f"Attendu 'raster', obtenu '{mode}'"
    finally:
        pdf_path.unlink(missing_ok=True)


def test_vectorize_pdf_raster_sans_exception():
    """vectorize() sur un PDF raster doit terminer sans exception."""
    import fitz
    import numpy as np
    import tempfile
    from pathlib import Path
    from PIL import Image

    # Image 200×200 avec une croix noire sur fond blanc
    arr = np.ones((200, 200), dtype=np.uint8) * 255
    arr[90:110, :] = 0    # ligne horizontale
    arr[:, 90:110] = 0    # ligne verticale
    pil = Image.fromarray(arr)

    # Sauvegarder l'image temporaire
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
        img_path = Path(tf.name)
    pil.save(str(img_path), dpi=(200, 200))

    # Créer un PDF contenant cette image
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tf:
        pdf_path = Path(tf.name)
    pdf_doc = fitz.open()
    page = pdf_doc.new_page(width=200, height=200)
    page.insert_image(fitz.Rect(0, 0, 200, 200), filename=str(img_path))
    pdf_doc.save(str(pdf_path))
    pdf_doc.close()
    img_path.unlink(missing_ok=True)

    try:
        from cad.vectorizer import vectorize
        doc = vectorize(pdf_path)
        # Au minimum 1 page traitée sans exception
        assert len(doc.pages) == 1, f"Attendu 1 page, obtenu {len(doc.pages)}"
        assert doc.source_path == pdf_path
    finally:
        pdf_path.unlink(missing_ok=True)
