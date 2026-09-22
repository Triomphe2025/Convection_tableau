"""
Mode OCR hybride v4 — Ollama classe les colonnes, Claude corrige les caractères.

Activer avec Config.OCR_MODE = "hybrid".

Fonctionnement :
  1. Ollama Vision lit l'image et extrait les données en les classant visuellement
     dans les bonnes colonnes (structure fiable car il voit l'image entière).
  2. Les résultats Ollama (déjà structurés par colonne) sont envoyés à Claude
     avec l'image originale.
  3. Claude ne reclassifie PAS les colonnes — il corrige uniquement les erreurs
     de lecture de caractères (O↔0, l↔1, S↔5, rn↔m, etc.).
  4. Filet de sécurité : toute cellule vide chez Claude est comblée par
     la valeur Ollama correspondante.
  5. Métadonnées (PAGE, BORNIER, PET…) issues de Claude (plus fiable pour lire
     les pieds de page).

Pourquoi Ollama d'abord :
  Ollama voit l'image entière et comprend visuellement les frontières de colonnes
  sans qu'on lui donne de règle fixe. La structure (quelle valeur appartient à
  quelle colonne) est bien meilleure que la lecture fine des caractères.

Pourquoi Claude ensuite :
  Claude lit les caractères avec une précision bien supérieure à Ollama, mais
  a tendance à se tromper sur le nombre de colonnes quand il extrait seul.
  En lui fournissant la structure correcte d'Ollama, il se concentre uniquement
  sur la correction character-level.

Cas d'échec :
  Ollama échoue  → Claude seul (OCR classique complet).
  Claude échoue  → Ollama seul.
  Les deux échouent → erreur.
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _rows_to_pipe(rows: List[Dict], n_cols: int) -> str:
    """
    Formate les lignes Ollama en texte pipe-séparé pour Claude.

    Chaque ligne devient :  val_col1 | val_col2 | val_col3 | val_col4
    Claude reçoit cette structure et corrige uniquement les caractères.

    Exemple :
      Ligne Ollama : cells=['B16T 01A', '0057R', 'B702A', 'FSa22-38']
      Sortie       : "B16T 01A | 0057R | B702A | FSa22-38"
    """
    lines = []
    for row in rows:
        if row.get('type') != 'data':
            continue
        cells = list(row.get('cells', []))
        while len(cells) < n_cols:
            cells.append('')
        lines.append(' | '.join(cells[:n_cols]))
    return '\n'.join(lines)


def _safety_fill(
    claude_rows: List[Dict],
    ollama_rows: List[Dict],
    n_cols: int,
) -> List[Dict]:
    """
    Filet de sécurité : comble les cellules vides de Claude par les valeurs Ollama.

      Claude[i][j] non vide → Claude (lecture précise des caractères)
      Claude[i][j] vide     → Ollama (pas de perte de données)
    """
    n = max(len(claude_rows), len(ollama_rows))
    result = []

    for i in range(n):
        c_row = claude_rows[i] if i < len(claude_rows) else {
            'type': 'data', 'cells': [''] * n_cols,
        }
        o_row = ollama_rows[i] if i < len(ollama_rows) else {
            'type': 'data', 'cells': [''] * n_cols,
        }

        c_cells = list(c_row.get('cells', []))
        o_cells = list(o_row.get('cells', []))

        while len(c_cells) < n_cols:
            c_cells.append('')
        while len(o_cells) < n_cols:
            o_cells.append('')

        cells = [
            (c_cells[j].strip() if c_cells[j].strip() else o_cells[j].strip())
            for j in range(n_cols)
        ]

        result.append({
            'type':       c_row.get('type', 'data'),
            'cells':      cells,
            'confidence': [100] * n_cols,
        })

    return result


# ──────────────────────────────────────────────────────────────────────
# Extracteur principal
# ──────────────────────────────────────────────────────────────────────

class HybridVisionExtractor:
    """
    Extracteur hybride v4.

    Pipeline :
      Ollama + image → classification visuelle dans les colonnes
        ↓ données déjà structurées en pipe (val1 | val2 | ...)
      Claude + image + données Ollama → correction des caractères uniquement
        ↓ filet de sécurité (cellule Claude vide → Ollama)
      résultat final
    """

    def __init__(self, template, on_column_mapping: Optional[Callable] = None):
        self._tpl = template
        self._on_column_mapping = on_column_mapping

    def extract(self, image_path: Path, feedback: str = None) -> Dict:
        """
        Extrait le tableau en deux passes :
          Ollama pour la structure visuelle des colonnes,
          Claude pour corriger les erreurs de lecture de caractères.

        Même format de retour que ClaudeVisionExtractor.extract().
        feedback : correctif utilisateur transmis aux deux moteurs.
        """
        from ollama_ocr import OllamaVisionExtractor
        from claude_ocr import ClaudeVisionExtractor

        n_cols = len(self._tpl.columns)
        img_name = Path(image_path).name

        # ── Passe 1 : Ollama — classification visuelle des colonnes ──────
        logger.info(f"↔ Hybrid — passe 1 Ollama (structure) : {img_name}")
        ollama_result = OllamaVisionExtractor(
            self._tpl, on_column_mapping=self._on_column_mapping
        ).extract(image_path, feedback=feedback)

        if not ollama_result.get('success'):
            logger.info(
                f"  ↔ Ollama échoué — Claude seul (OCR complet) : {img_name}"
            )
            return ClaudeVisionExtractor(
                self._tpl, on_column_mapping=self._on_column_mapping
            ).extract(image_path, feedback=feedback)

        ollama_rows = ollama_result.get('rows', [])

        # Données Ollama en format pipe → Claude corrige les caractères
        pipe_data = _rows_to_pipe(ollama_rows, n_cols)

        logger.info(
            f"  ↔ Passe 1 OK : {len(ollama_rows)} lignes Ollama. "
            "Lancement passe 2 Claude (correction caractères)…"
        )

        # ── Passe 2 : Claude — correction des caractères ─────────────────
        claude_result = ClaudeVisionExtractor(
            self._tpl, on_column_mapping=self._on_column_mapping
        ).extract(
            image_path,
            feedback=feedback,
            context_data=pipe_data,
        )

        if not claude_result.get('success'):
            logger.info(
                f"  ↔ Claude échoué — Ollama seul utilisé : {img_name}"
            )
            return ollama_result

        claude_rows = claude_result.get('rows', [])
        claude_meta = claude_result.get('metadata', {})

        logger.info(
            f"  ↔ Passe 2 OK : {len(claude_rows)} lignes Claude corrigées. "
            "Application du filet de sécurité…"
        )

        # ── Filet de sécurité ──────────────────────────────────────────
        final_rows = _safety_fill(claude_rows, ollama_rows, n_cols)

        logger.info(
            f"  ↔ Hybride terminé : {len(final_rows)} lignes finales "
            f"({img_name})"
        )

        return {
            'success':          True,
            'headers':          self._tpl.columns,
            'rows':             final_rows,
            'metadata':         claude_meta or ollama_result.get('metadata') or {},
            'image_path':       str(image_path),
            'blur_pct':         0.0,
            'detection_method': 'hybrid',
        }
