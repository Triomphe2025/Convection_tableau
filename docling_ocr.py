"""
Moteur OCR Docling (IBM Research) — extraction de tableaux par IA locale.

Activer avec Config.OCR_MODE = "docling".
Retourne le même format que BornierTableExtractor.extract().

Installation : pip install docling
Le modèle (~500 Mo) se télécharge automatiquement au premier lancement.
Fonctionne sans GPU, mais plus lent (CPU seul ~10-30 s/image).

Architecture Docling :
  document.tables  → tableau de données (lignes de borniers)
  document.texts   → blocs texte hors tableau (pied de page, titres, etc.)
Les métadonnées (CABLE, TYPE, NO_PLAN…) sont dans document.texts.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DoclingExtractor:
    """Extracteur de tableaux via Docling (IBM Research)."""

    # Convertisseur partagé entre toutes les instances — chargé une seule fois
    _converter = None

    def __init__(self, template):
        self._tpl = template

    @classmethod
    def _get_converter(cls):
        if cls._converter is None:
            try:
                from docling.document_converter import DocumentConverter
                cls._converter = DocumentConverter()
                logger.info("✓ Docling chargé (IBM Research)")
            except ImportError:
                raise RuntimeError(
                    "Package 'docling' non installé.\n"
                    "Lancez : pip install docling"
                )
        return cls._converter

    # ------------------------------------------------------------------
    # Extraction des métadonnées depuis les TextItem Docling
    # ------------------------------------------------------------------

    def _extract_footer_metadata(self, result) -> Dict[str, str]:
        """
        Parcourt les blocs texte hors tableau (document.texts) pour y trouver
        les champs de pied de page définis dans footer_extract_fields.

        Docling place le texte du pied (CABLE :, TYPE :, N° PLAN :…)
        dans des TextItem séparés du tableau principal.
        On collecte ces textes ligne par ligne et on applique les mêmes
        patterns regex que pdf_extractor._extract_meta().
        """
        meta: Dict[str, str] = {}

        # ── 1. Collecter le texte brut de tous les blocs hors tableau ──────
        raw_lines: List[str] = []

        try:
            for item in result.document.texts:
                text = getattr(item, 'text', '') or ''
                if text.strip():
                    raw_lines.append(text.strip().upper())
        except Exception:
            pass

        if not raw_lines:
            # Fallback : export markdown, garder uniquement les lignes sans |
            try:
                md = result.document.export_to_markdown()
                raw_lines = [
                    ln.upper() for ln in md.splitlines()
                    if ln.strip() and not ln.strip().startswith('|')
                ]
            except Exception:
                return meta

        if not raw_lines:
            return meta

        # ── 2. Repérer les lignes de pied (contiennent un mot-clé + ':') ──
        footer_kws = [
            kw.upper().rstrip(': ')
            for kw in getattr(self._tpl, 'footer_detect_keywords', [])
            if kw.strip()
        ]
        footer_left = re.sub(
            r'\s+', ' ',
            getattr(self._tpl, 'footer_left_label', '').upper()
        ).strip()

        footer_lines: List[str] = []
        collecting = False
        for lt in raw_lines:
            if collecting:
                footer_lines.append(lt)
                continue
            # Déclencheur : un mot-clé suivi de ':' OU l'étiquette gauche (ex: SIEMENS)
            triggered = False
            for kw in footer_kws:
                if re.search(rf'{re.escape(kw)}\s{{0,10}}[:\|]', lt):
                    triggered = True
                    break
            if not triggered and footer_left and footer_left in lt:
                triggered = True
            if triggered:
                collecting = True
                footer_lines.append(lt)

        # Si aucune ligne de pied détectée, tenter sur toutes les lignes
        if not footer_lines:
            footer_lines = raw_lines

        # ── 3. Extraire chaque champ défini dans footer_extract_fields ─────
        _standard = {'PET', 'BORNIER', 'NO_PLAN', 'INDICE', 'PAGE'}

        # Champs standards communs
        joined = ' '.join(footer_lines)

        _pat_no_plan = r'(?:NO\.?\s*PLAN|N°\s*PLAN)\s*[:\-]?\s*([A-Z0-9\s]{3,30}?)(?:\||INDICE|\Z)'
        m = re.search(_pat_no_plan, joined)
        if m:
            meta['NO_PLAN'] = m.group(1).strip()

        m = re.search(r'INDICE\s*[:\-]?\s*([0-9A-Z]{1,5})', joined)
        if m:
            meta['INDICE'] = m.group(1).strip().replace('O', '0')

        m = re.search(r'PAGE\s*[:\-]?\s*(\d+)', joined)
        if m:
            meta['PAGE'] = m.group(1).strip()

        _pat_pet = r'P\.?E\.?T\.?\s*[:\-]?\s*([A-Z][A-Z0-9\s\-]{1,30}?)(?:BORNIER|JARRET|\||\Z)'
        m = re.search(_pat_pet, joined)
        if m:
            meta['PET'] = m.group(1).strip()

        m = re.search(r'BORNIER\s*[:\-]?\s*([A-Z0-9\-]{2,20})', joined)
        if m:
            meta['BORNIER'] = m.group(1).strip()

        # Champs personnalisés du template (ex: CABLE, TYPE)
        for fdef in getattr(self._tpl, 'footer_extract_fields', []):
            key   = fdef.get('key', '').upper()
            label = fdef.get('label', '').upper()
            if not key or not label or key in _standard or key in meta:
                continue
            label_re = re.sub(r'\.', r'\\.?', re.escape(label))
            label_re = label_re.replace(r'\ ', r'\\s+')
            # Analyse ligne par ligne (évite l'interférence du compteur "10/10")
            for lt in footer_lines:
                m = re.search(
                    rf'{label_re}\s*[:\-]\s*([A-Z0-9/][A-Z0-9\s\-/]{{0,50}}?)'
                    rf'(?:\s+\d+/\d+)?$',
                    lt.strip()
                )
                if m:
                    meta[key] = m.group(1).strip()
                    break

        if meta:
            logger.debug(f"Docling pied de page extrait : {meta}")
        else:
            logger.debug("Docling : aucune métadonnée de pied trouvée dans document.texts")

        return meta

    # ------------------------------------------------------------------
    # Pipeline principal
    # ------------------------------------------------------------------

    def extract(self, image_path: Path, feedback: str = None) -> Dict:
        """
        Analyse l'image avec Docling et retourne le dict structuré.

        Même format de retour que BornierTableExtractor.extract() :
          success, headers, rows, metadata, image_path, detection_method

        feedback : ignoré pour Docling (interface commune avec Claude/Tesseract).

        Étapes :
          1. Conversion de l'image par Docling (IA locale)
          2. Extraction du tableau principal → rows
          3. Extraction du pied de page depuis document.texts → metadata
        """
        try:
            converter = self._get_converter()
        except RuntimeError as e:
            return {'success': False, 'error': str(e)}

        try:
            result = converter.convert(str(image_path))
        except Exception as e:
            return {'success': False, 'error': f"Docling : erreur de conversion — {e}"}

        col_names = self._tpl.columns
        tables = list(result.document.tables)
        if not tables:
            return {
                'success': False,
                'error': "Docling n'a détecté aucun tableau dans l'image.",
            }

        # Tableau avec le plus de lignes = tableau principal
        main_table = max(tables, key=lambda t: len(t.data.grid))

        try:
            df = main_table.export_to_dataframe()
        except Exception as e:
            return {'success': False, 'error': f"Docling : export DataFrame — {e}"}

        # Exclure la ligne d'en-tête si elle est incluse dans le DataFrame
        header_idx: Optional[int] = None
        for i in range(min(5, len(df))):
            row_text = ' '.join(str(v).upper() for v in df.iloc[i].values)
            hits = sum(1 for col in col_names if col.upper() in row_text)
            if hits >= max(2, len(col_names) // 2):
                header_idx = i
                break

        start = (header_idx + 1) if header_idx is not None else 0
        rows: List[Dict] = []
        for i in range(start, len(df)):
            vals = df.iloc[i]
            cells = []
            for j in range(len(col_names)):
                raw = str(vals.iloc[j]).strip() if j < len(vals) else ''
                cells.append('' if raw in ('nan', 'None', 'NaN', '-') else raw)
            if any(c for c in cells):
                rows.append({
                    'type':       'data',
                    'cells':      cells,
                    'confidence': [100] * len(cells),
                })

        # Extraction du pied de page depuis les blocs texte hors tableau
        metadata = self._extract_footer_metadata(result)

        logger.info(
            f"✓ Docling : {len(rows)} lignes, "
            f"métadonnées : {list(metadata.keys()) or 'aucune'} "
            f"depuis {image_path.name}"
        )
        return {
            'success':          True,
            'headers':          col_names,
            'rows':             rows,
            'metadata':         metadata,
            'image_path':       str(image_path),
            'blur_pct':         0.0,
            'detection_method': 'docling',
        }
