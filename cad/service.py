"""Façade du pipeline CAD — appelée par interface.py."""
from pathlib import Path
from typing import Callable, Optional

from .source_detector import detect_source_mode, count_pages
from .vector_pdf_extractor import extract_vector_pdf
from .dxf_writer import write_dxf


def _compute_dxf_stats(doc_cad) -> dict:
    """Compte les entités par calque pour le résumé post-conversion."""
    stats = {'CABLES': 0, 'CABLES_EXISTANTS': 0, 'GEOMETRIE': 0, 'TEXTE': 0, 'total': 0}
    for page in doc_cad.pages:
        for ent in page.entities:
            layer = ent.layer
            if layer in stats:
                stats[layer] += 1
            stats['total'] += 1
    return stats


def convert_to_dxf(
    source_path: Path,
    output_dir: Path,
    page_indices: Optional[list] = None,
    on_log: Optional[Callable] = None,
    on_progress: Optional[Callable] = None,
    on_step_start: Optional[Callable] = None,
    on_step_done: Optional[Callable] = None,
    params: Optional[dict] = None,
) -> Path:
    """
    Convertit un PDF vectoriel en DXF.
    Détecte automatiquement les tableaux de légende et crée des blocs AutoCAD.

    Args:
        source_path  : chemin du PDF ou image source
        output_dir   : dossier de destination
        page_indices : liste des pages à traiter (None = toutes)
        on_log       : callback(message: str)
        on_progress  : callback(pct: float, message: str)

    Returns:
        Chemin du fichier DXF généré.
    """
    def _log(msg: str):
        if on_log:
            on_log(msg)

    def _progress(pct: float, msg: str = ""):
        if on_progress:
            on_progress(pct, msg)

    source_path = Path(source_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _log(f"━━ Analyse source : {source_path.name}")
    n_pages = count_pages(source_path)
    _log(f"  Pages disponibles : {n_pages}")
    _progress(0.05, "Détection du mode…")

    mode = detect_source_mode(source_path, page_index=0)
    _log(f"  Mode détecté : {mode}")

    if mode == 'vector':
        import ezdxf
        import fitz

        _log("━━ Pipeline vectoriel (PyMuPDF)")
        _progress(0.15, "Extraction géométrie vectorielle…")

        doc_cad = extract_vector_pdf(source_path, page_indices)

        n_pages_ok = len(doc_cad.pages)
        n_entities = sum(len(p.entities) for p in doc_cad.pages)
        _log(f"  ✓ {n_pages_ok} page(s) traitée(s)")
        _log(f"  ✓ {n_entities} entités extraites")
        for p in doc_cad.pages:
            _log(f"    Page {p.page_index + 1} : {len(p.entities)} entités"
                 f" ({p.width:.1f}×{p.height:.1f} mm)")
        _progress(0.65, f"{n_entities} entités extraites")

        # ── Détection des tableaux de légende et création de blocs ──────
        _log("━━ Détection des tableaux de légende…")
        _progress(0.70, "Recherche de tableaux de légende…")

        try:
            from .block_builder import detect_legend_pages, extract_table_rows, create_dxf_blocks

            pdf = fitz.open(str(source_path))
            legend_pages = detect_legend_pages(pdf)

            if legend_pages:
                _log(f"  ✓ {len(legend_pages)} page(s) de légende détectée(s) : "
                     f"{[p + 1 for p in legend_pages]}")
                all_rows = []
                for idx in legend_pages:
                    rows = extract_table_rows(pdf[idx])
                    all_rows.extend(rows)
                    _log(f"    Page {idx + 1} : {len(rows)} ligne(s) extraite(s)")

                if all_rows:
                    _log(f"━━ Création de {len(all_rows)} bloc(s) AutoCAD…")
                    _progress(0.78, f"Création de {len(all_rows)} blocs AutoCAD…")

                    # Pré-créer le document DXF pour y injecter les blocs
                    dxf_doc = ezdxf.new("R2010")
                    dxf_doc.header['$INSUNITS'] = 4
                    n_blocks = create_dxf_blocks(dxf_doc, all_rows, on_log=_log)
                    _log(f"  ✓ {n_blocks} bloc(s) AutoCAD créé(s)")
                    _progress(0.85, f"{n_blocks} blocs créés")

                    # Écrire le DXF avec les blocs pré-créés
                    output_path = output_dir / (source_path.stem + ".dxf")
                    _log(f"━━ Écriture DXF : {output_path.name}")
                    write_dxf(doc_cad, output_path, existing_doc=dxf_doc)
                    pdf.close()
                    _dxf_stats = _compute_dxf_stats(doc_cad)
                    _log(f"  Calques : CABLES={_dxf_stats['CABLES']} | "
                         f"TIRETÉS={_dxf_stats['CABLES_EXISTANTS']} | "
                         f"GÉOM={_dxf_stats['GEOMETRIE']} | "
                         f"TEXTE={_dxf_stats['TEXTE']} | "
                         f"Total={_dxf_stats['total']} entités")
                    size_ko = output_path.stat().st_size // 1024
                    _log(f"  ✓ {output_path.name}  ({size_ko} Ko)")
                    _log("━━ Conversion terminée")
                    _progress(1.0, "Terminé")
                    return output_path
                else:
                    _log("  ℹ Aucune ligne de bloc extraite des tableaux")
            else:
                _log("  ℹ Aucun tableau de légende détecté")
            pdf.close()
        except Exception as e:
            _log(f"  ⚠ Détection blocs ignorée : {e}")

    elif mode == 'raster':
        _log("━━ Pipeline raster (OpenCV)")
        _progress(0.15, "Prétraitement image…")

        def _raster_progress(frac: float):
            # Rescale 0.0→1.0 vers la plage 0.15→0.70 allouée au raster
            _progress(0.15 + frac * 0.55, f"Vectorisation page {int(frac * n_pages)}/{n_pages}…")

        # Tenter le pipeline vectorizer avancé (spline + graphe topologique)
        try:
            from .vectorizer import vectorize as _vectorize
            doc_cad = _vectorize(
                source_path,
                page_indices=page_indices,
                on_log=_log,
                on_step_start=on_step_start,
                on_step_done=on_step_done,
                params=params,
            )
        except Exception as _vec_err:
            _log(f"⚠ Vectorizer échoué ({type(_vec_err).__name__}: {_vec_err})")
            _log("  ⚠ Pipeline de secours activé — résultat potentiellement moins précis")
            from .raster_tif_extractor import extract_raster_tif
            doc_cad = extract_raster_tif(
                source_path, page_indices,
                on_progress=_raster_progress,
                on_log=_log,
            )

        n_pages_ok = len(doc_cad.pages)
        n_entities = sum(len(p.entities) for p in doc_cad.pages)
        _log(f"  ✓ {n_pages_ok} page(s) traitée(s)")
        _log(f"  ✓ {n_entities} entités extraites (lignes + textes)")
        for p in doc_cad.pages:
            _log(f"    Page {p.page_index + 1} : {len(p.entities)} entités"
                 f" ({p.width:.1f}×{p.height:.1f} mm)")
            for w in getattr(p, 'warnings', []):
                _log(f"    ⚠ {w}")
        _progress(0.70, f"{n_entities} entités extraites")
    else:
        raise ValueError(
            f"Format non reconnu : {source_path.suffix}\n"
            "Formats acceptés : PDF vectoriel, TIF, TIFF, PNG, JPG, BMP"
        )

    output_path = output_dir / (source_path.stem + ".dxf")
    _log(f"━━ Écriture DXF : {output_path.name}")
    _progress(0.85, "Génération DXF…")

    try:
        write_dxf(doc_cad, output_path)
    except PermissionError:
        import tempfile
        _tmp = Path(tempfile.gettempdir()) / output_path.name
        write_dxf(doc_cad, _tmp)
        _log(f"  ⚠ Accès refusé sur le dossier cible — fichier écrit dans : {_tmp}")
        output_path = _tmp

    _dxf_stats = _compute_dxf_stats(doc_cad)
    _log(f"  Calques : CABLES={_dxf_stats['CABLES']} | "
         f"TIRETÉS={_dxf_stats['CABLES_EXISTANTS']} | "
         f"GÉOM={_dxf_stats['GEOMETRIE']} | "
         f"TEXTE={_dxf_stats['TEXTE']} | "
         f"Total={_dxf_stats['total']} entités")

    size_ko = output_path.stat().st_size // 1024
    _log(f"  ✓ {output_path.name}  ({size_ko} Ko)")
    _log("━━ Conversion terminée")
    _progress(1.0, "Terminé")

    return output_path
