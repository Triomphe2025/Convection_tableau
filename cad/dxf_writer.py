"""Génération de fichiers DXF depuis un CadDocument via ezdxf."""
import logging
from pathlib import Path
from .models import CadDocument, CadPage, CadEntity, EntityKind

# $INTERFEREOBJVS / $INTERFEREVPVS sont des variables 3D non utilisées en 2D —
# ezdxf les saute avec un message INFO parasite → on les filtre au niveau WARNING.
logging.getLogger('ezdxf').setLevel(logging.WARNING)

_PAGE_GAP_MM = 50.0     # espace entre les folios en mm


def write_dxf(doc_cad: CadDocument, output_path: Path,
              version: str = "R2013", existing_doc=None) -> Path:
    """
    Génère un fichier DXF.

    Toutes les pages sont placées dans le modelspace, décalées horizontalement :
      - Folio 1 à x=0
      - Folio 2 à x=largeur_folio1 + 50 mm
      - Folio 3 à x=largeur_folio1 + largeur_folio2 + 100 mm
      - etc.

    Chaque folio est encadré d'un rectangle de bord et d'un calque dédié
    "FOLIO_N" pour pouvoir les isoler dans AutoCAD.
    """
    import ezdxf

    output_path = Path(output_path)
    if existing_doc is not None:
        dxf = existing_doc
        if '$INSUNITS' not in dxf.header:
            dxf.header['$INSUNITS'] = 4
        dxf.header['$LWDISPLAY'] = 1    # Affiche les épaisseurs de ligne à l'ouverture AutoCAD
        dxf.header['$MEASUREMENT'] = 1  # système métrique
    else:
        dxf = ezdxf.new(version)
        dxf.header['$INSUNITS'] = 4     # 4 = millimètres
        dxf.header['$LWDISPLAY'] = 1   # Affiche les épaisseurs de ligne à l'ouverture AutoCAD
        dxf.header['$MEASUREMENT'] = 1  # système métrique
    msp = dxf.modelspace()

    # Charger les linetypes standard si absents
    try:
        if 'DASHED' not in dxf.linetypes:
            dxf.linetypes.add('DASHED', pattern='A, 12.7, -6.35',
                              description='Dashed ____ ____ ____')
        if 'DASHED2' not in dxf.linetypes:
            dxf.linetypes.add('DASHED2', pattern='A, 6.35, -3.175',
                              description='Dashed2 _ _ _ _ _ _ _')
    except Exception:
        pass  # si ezdxf ne supporte pas cette syntaxe, les linetypes resteront au défaut

    # Calcul des offsets X cumulatifs
    x_offsets = _compute_offsets(doc_cad.pages)

    for page, x_off in zip(doc_cad.pages, x_offsets):
        folio_layer = f"FOLIO_{page.page_index + 1}"
        _ensure_layers(dxf, page, extra_layers=[folio_layer, 'CADRES'])

        # Cadre du folio (rectangle de bord visible dans AutoCAD)
        _draw_frame(msp, page, x_off, folio_layer)

        # Entités du folio avec décalage X
        for ent in page.entities:
            try:
                _write_entity(msp, ent, x_off)
            except Exception:
                pass

    dxf.saveas(str(output_path))
    return output_path


def _compute_offsets(pages: list) -> list:
    """Calcule l'offset X de chaque page pour les disposer côte à côte."""
    offsets = []
    cumul = 0.0
    for page in pages:
        offsets.append(cumul)
        cumul += page.width + _PAGE_GAP_MM
    return offsets


def _draw_frame(msp, page: CadPage, x_off: float, layer: str):
    """Trace un rectangle de bord autour du folio dans AutoCAD."""
    w, h = page.width, page.height
    pts = [
        (x_off,     0),
        (x_off + w, 0),
        (x_off + w, h),
        (x_off,     h),
    ]
    msp.add_lwpolyline(
        pts,
        dxfattribs={'layer': 'CADRES', 'closed': True},
    )
    # Étiquette du folio
    msp.add_text(
        f"Folio {layer}",
        dxfattribs={
            'layer': 'CADRES',
            'height': max(h * 0.015, 2.0),
            'insert': (x_off + 2, h + 3),
        },
    )


def _ensure_layers(dxf, page: CadPage, extra_layers: list = None):
    """Crée les calques nécessaires s'ils n'existent pas encore."""
    names = {ent.layer or '0' for ent in page.entities}
    if extra_layers:
        names.update(extra_layers)
    for name in names:
        if name not in dxf.layers:
            layer = dxf.layers.new(name)
            layer.color = 7     # ACI 7 = blanc/noir selon fond


def _write_entity(msp, ent: CadEntity, x_off: float = 0.0):
    """Écrit une entité dans le modelspace avec décalage X."""
    layer = ent.layer or '0'

    if ent.kind == EntityKind.LINE:
        g = ent.geometry
        msp.add_line(
            (g['x1'] + x_off, g['y1'], 0),
            (g['x2'] + x_off, g['y2'], 0),
            dxfattribs={'layer': layer, 'lineweight': int(round(ent.lineweight * 100))},
        )

    elif ent.kind in (EntityKind.POLYLINE, EntityKind.RECT):
        pts = ent.geometry.get('points', [])
        if len(pts) < 2:
            return
        # Lire closed depuis la géométrie ; RECT est toujours fermé par défaut
        closed = ent.geometry.get('closed', ent.kind == EntityKind.RECT)
        lw_int = int(round(ent.lineweight * 100))
        # Linetype depuis l'entité (DASHED possible pour les tiretés)
        linetype = getattr(ent, 'linetype', 'CONTINUOUS')
        ltscale = getattr(ent, 'ltscale', 1.0)
        dxfattribs = {'layer': layer, 'closed': closed}
        if linetype != 'CONTINUOUS':
            dxfattribs['linetype'] = linetype
            dxfattribs['ltscale'] = ltscale
        lwpoly = msp.add_lwpolyline(
            [(x + x_off, y) for x, y in pts],
            dxfattribs=dxfattribs,
        )
        lwpoly.dxf.lineweight = lw_int

    elif ent.kind == EntityKind.SPLINE:
        # 'control_points' (vectorizer.py) ou 'points' (vector_pdf_extractor.py)
        pts = ent.geometry.get('control_points') or ent.geometry.get('points', [])
        if len(pts) < 2:
            return
        lw_int = int(round(ent.lineweight * 100))
        if len(pts) < 4:
            # Pas assez de points pour degree=3 : fallback en LWPOLYLINE
            lwpoly = msp.add_lwpolyline(
                [(x + x_off, y) for x, y in pts],
                dxfattribs={'layer': layer},
            )
            lwpoly.dxf.lineweight = lw_int
        else:
            msp.add_open_spline(
                control_points=[(x + x_off, y, 0) for x, y in pts],
                degree=3,
                dxfattribs={'layer': layer, 'lineweight': lw_int},
            )

    elif ent.kind == EntityKind.CIRCLE:
        g = ent.geometry
        msp.add_circle(
            center=(g['cx'] + x_off, g['cy'], 0),
            radius=g['r'],
            dxfattribs={'layer': layer},
        )

    elif ent.kind == EntityKind.TEXT:
        g = ent.geometry
        txt = g.get('text', '')
        if not txt:
            return
        h = max(g.get('size', 3.0), 0.5)
        msp.add_text(
            txt,
            dxfattribs={
                'layer': layer,
                'height': h,
                'insert': (g['x'] + x_off, g['y']),
                'rotation': g.get('angle', 0.0),
            },
        )
