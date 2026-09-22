"""
Moteur OCR Claude Vision — extraction de tableaux via l'API Anthropic.

Activer avec Config.OCR_MODE = "claude".
Retourne le même format que BornierTableExtractor.extract().
"""

import base64
import datetime
import json
import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_api_log_path: Optional[Path] = None


def set_api_log_path(path: Optional[Path]) -> None:
    """Définit le fichier JSONL où les réponses brutes Claude seront consignées."""
    global _api_log_path
    _api_log_path = path


def _write_api_log(entry: dict) -> None:
    if _api_log_path is None:
        return
    try:
        with open(_api_log_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


_MEDIA_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png',  '.gif':  'image/gif',
    '.webp': 'image/webp',
}


def _encode_image(image_path: Path):
    """Retourne (base64_data, media_type) pour l'image."""
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower(), 'image/png')
    with open(image_path, 'rb') as f:
        return base64.standard_b64encode(f.read()).decode('utf-8'), media_type


def _build_prompt(template) -> str:
    """
    Construit le prompt pipe-séparé pour tous les templates.

    Format de sortie attendu de Claude :
      val1 | val2 | val3 | val4
      META: {"PAGE": "", "BORNIER": "", ...}

    L'assignation est PUREMENT POSITIONNELLE :
    - avant la 1ère barre  → colonne 1
    - entre barre 1 et 2   → colonne 2
    - ...
    - après la dernière    → colonne N
    Aucune interprétation sémantique, aucune correction post-API.
    """
    columns = template.columns
    n_cols = len(columns)

    footer_fields = getattr(template, 'footer_extract_fields', [])
    footer_keys = [fd.get('key', '') for fd in footer_fields if fd.get('key')]
    base_meta = ['PAGE', 'BORNIER', 'PET', 'NO_PLAN', 'INDICE']
    all_meta_keys = base_meta + [k for k in footer_keys if k not in base_meta]
    meta_json = ', '.join(f'"{k}": ""' for k in all_meta_keys)

    section_kw = getattr(template, 'section_keyword', 'NOM DU CABLE')
    footer_kws_str = "SIEMENS, ALSTOM, MTI, CABLE, N° PLAN, NO PLAN, INDICE, PAGE, P.E.T, BORNIER"
    footer_detect = getattr(template, 'footer_detect_keywords', [])
    if footer_detect:
        footer_kws_str += ', ' + ', '.join(footer_detect[:6])

    col_zones = ' | '.join(columns)
    example_line = ' | '.join('valeur_' + c for c in columns)

    # Règles positionnelles explicites selon le nombre de colonnes du template
    rules = []
    for i, col in enumerate(columns):
        if i == 0:
            rules.append(f"  • AVANT la 1ère barre verticale            → colonne 1 : {col}")
        elif i == n_cols - 1:
            rules.append(f"  • APRÈS la {i}{'ère' if i == 1 else 'ème'} barre verticale"
                         f"             → colonne {i+1} : {col}")
        else:
            rules.append(f"  • Entre la {i}ère et {i+1}ème barre verticale"
                         f"       → colonne {i+1} : {col}")
    rules_str = '\n'.join(rules)

    return (
        "Tu analyses une image issue d'un document électrique industriel.\n\n"
        "ÉTAPE 1 — TYPE DE PAGE (première ligne obligatoire) :\n"
        "  TYPE_PAGE: listing      ← la page contient un tableau de câblage /\n"
        "                             bornier avec des colonnes de données électriques\n"
        "  TYPE_PAGE: non-listing  ← page de garde, feuille de modifications /\n"
        "                             révisions, table des matières, schéma,\n"
        "                             texte descriptif sans tableau de données\n"
        "En cas de doute, choisis listing.\n"
        "Si non-listing : écris uniquement la ligne META ci-dessous,"
        " sans aucune ligne de données.\n\n"
        "ÉTAPE 2 — EXTRACTION (seulement si TYPE_PAGE: listing) :\n"
        f"Colonnes dans l'ordre visuel (de gauche à droite) : {col_zones}\n\n"
        "RÈGLE FONDAMENTALE — INSERTION PAR POSITION :\n"
        "Les colonnes sont délimitées par les barres verticales visibles dans l'image. et non les trop rand espace visible \n"
        "Recopie EXACTEMENT ce que tu lis dans chaque colonne, sans interpréter ni corriger :\n"
        f"{rules_str}\n\n"
        f"Pour chaque ligne de données visible, écris sur une seule ligne :\n"
        f"  {example_line}\n\n"
        "Règles :\n"
        "- Une ligne visuelle = une ligne de sortie\n"
        "- Cellule vide = rien entre les pipes (ex : \"val1 | | val3 | val4\")\n"
        "- Si une cellule contient plusieurs sous-parties visuelles,"
        " concatène-les avec un espace\n"
        f"- Ne pas inclure l'en-tête ni les lignes de pied de page ({footer_kws_str})\n"
        f"- Ne pas inclure les lignes de séparation '{section_kw}'\n\n"
        f"Après TOUTES les lignes de données, ajoute une ligne :\n"
        f"META: {{{meta_json}}}\n"
        "avec les valeurs trouvées dans le pied de page.\n"
    )


_FOOTER_MARKERS = frozenset([
    'SIEMENS', 'ALSTOM', 'SCHNEIDER', 'ABB', 'LEGRAND', 'MTI',
    'CABLE :', 'CABLE:', 'N° PLAN', 'NO PLAN', 'NO.PLAN',
    'INDICE :', 'INDICE:', 'PAGE :', 'PAGE:',
    'P.E.T', 'PET :', 'BORNIER :',
])


def _is_footer_row(cells: List[str]) -> bool:
    """Retourne True si la ligne ressemble à un pied de page plutôt qu'à une donnée."""
    joined = ' '.join(cells).upper()
    # Une ligne pied de page a typiquement beaucoup de colonnes vides
    non_empty = [c for c in cells if c.strip()]
    if len(non_empty) == 1 and len(cells) >= 3:
        val = non_empty[0].upper()
        # Valeur unique qui contient un marqueur de pied
        if any(m in val for m in _FOOTER_MARKERS):
            return True
    # Deux valeurs dont l'une contient "CABLE :" ou "N° PLAN"
    if any(m in joined for m in _FOOTER_MARKERS):
        return True
    return False


def _detect_ambiguous_segments(raw: str, n_cols: int) -> Optional[List[str]]:
    """Retourne les segments de la 1ère ligne de données avec plus de
    segments pipe que de colonnes template, ou None si aucune ambiguïté."""
    for line in raw.splitlines():
        line = line.strip()
        if not line or '|' not in line:
            continue
        if line.upper().startswith(('TYPE_PAGE:', 'META:')):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) > n_cols:
            return parts
    return None


def _parse_pipe_response(raw: str, template, column_mapping: dict = None) -> tuple:
    """
    Parse une réponse Claude au format pipe-separated.

    Format attendu :
      TYPE_PAGE: listing
      val1 | val2 | val3 | val4
      ...
      META: {"PAGE": "77", "BORNIER": "...", ...}

    Retourne (rows, metadata, page_type).
    page_type vaut 'listing' (défaut) ou 'non-listing'.
    """
    col_names = template.columns
    n_cols = len(col_names)
    rows: List[Dict] = []
    metadata: Dict = {}
    page_type = 'listing'  # défaut : on extrait

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ligne de classification de page (étape 1 du prompt)
        if line.upper().startswith('TYPE_PAGE:'):
            val = line[10:].strip().lower()
            if 'non' in val or 'autre' in val or 'cover' in val or 'modif' in val:
                page_type = 'non-listing'
            continue
        # Ligne métadonnées
        if line.upper().startswith('META:'):
            meta_str = line[5:].strip()
            try:
                parsed_meta = json.loads(meta_str)
                metadata = {k: str(v).strip() for k, v in parsed_meta.items() if v}
            except Exception:
                # Tentative de parse partiel si JSON invalide
                try:
                    # Chercher un objet JSON dans la ligne
                    m = re.search(r'\{.*\}', meta_str, re.DOTALL)
                    if m:
                        parsed_meta = json.loads(m.group(0))
                        metadata = {k: str(v).strip() for k, v in parsed_meta.items() if v}
                except Exception:
                    pass
            continue
        # Ligne de données : doit contenir au moins un |
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < n_cols:
            # Trop peu de segments : compléter avec des vides
            while len(parts) < n_cols:
                parts.append('')
            cells = parts[:n_cols]
        elif len(parts) == n_cols:
            cells = parts
        elif column_mapping:
            # Mapping validé par l'utilisateur (segment→colonne) — remplace
            # l'heuristique de fusion automatique ci-dessous.
            cells = [
                ' '.join(
                    parts[i] for i in column_mapping.get(col, [])
                    if 0 <= i < len(parts)
                ).strip()
                for col in col_names
            ]
        else:
            # Plus de segments que de colonnes : surplus dans l'avant-dernière colonne.
            # Règle physique : col[0..n-3] mapping direct,
            #                  col[n-2] (SIGNAL) absorbe tous les segments intermédiaires,
            #                  col[n-1] (JARRETIERES) reçoit le dernier segment.
            # Exemple 5 segs / 4 cols :
            #   B16T 01A | 0057R | B702A | 01H | FSa22-38
            #   → BORNE='B16T 01A' COULEUR='0057R'
            #     SIGNAL='B702A 01H'  JARRETIERES='FSa22-38'
            cells = list(parts[:n_cols - 2])
            mid = parts[n_cols - 2:-1]
            cells.append(' '.join(p for p in mid if p))
            cells.append(parts[-1])
        if not any(cells):
            continue
        if _is_footer_row(cells):
            continue
        rows.append({
            'type': 'data',
            'cells': cells,
            'confidence': [100] * n_cols,
            'raw': line,  # segments originaux conservés pour le mode hybride
        })

    return rows, metadata, page_type


class ClaudeVisionExtractor:
    """Extracteur de tableaux via Claude Vision API (Anthropic)."""

    def __init__(self, template, on_column_mapping: Optional[Callable] = None):
        self._tpl = template
        # Mapping manuel segment→colonne — demandé quand Claude renvoie plus
        # de segments pipe que de colonnes template. Mis en cache par run
        # (même clé de segments) pour ne pas resolliciter à chaque page.
        self._on_column_mapping = on_column_mapping
        self._cached_column_mapping: Optional[dict] = None
        self._cached_mapping_key = None

    def _resoudre_mapping_segments(self, raw: str, image_path) -> Optional[dict]:
        """Déclenche (ou réutilise depuis le cache) le mapping manuel
        segment→colonne quand la réponse a plus de segments que de colonnes."""
        n_cols = len(self._tpl.columns)
        ambiguous = _detect_ambiguous_segments(raw, n_cols)
        if not ambiguous or self._on_column_mapping is None:
            return None
        cache_key = (tuple(self._tpl.columns), len(ambiguous))
        if cache_key == self._cached_mapping_key:
            return self._cached_column_mapping
        candidate_blocks = [
            {'text': seg, 'x': i, 'x2': i + 1} for i, seg in enumerate(ambiguous)
        ]
        mapping = self._on_column_mapping(
            candidate_blocks, list(self._tpl.columns), image_path
        )
        self._cached_column_mapping = mapping
        self._cached_mapping_key = cache_key
        return mapping

    def extract(
        self,
        image_path: Path,
        feedback: str = None,
        context_data: str = None,
    ) -> Dict:
        """
        Envoie l'image à Claude Vision et retourne le dict structuré.

        Même format de retour que BornierTableExtractor.extract() :
          success, headers, rows, metadata, image_path, detection_method

        feedback     : commentaire de l'utilisateur, ajouté en tête de prompt.
        context_data : données Ollama déjà classées en colonnes (mode hybride v4).
                       Claude corrige uniquement les erreurs de caractères —
                       il ne reclassifie pas les colonnes.
        """
        from config import Config

        try:
            import anthropic
        except ImportError:
            return {
                'success': False,
                'error': (
                    "Package 'anthropic' non installé.\n"
                    "Lancez : pip install anthropic"
                ),
            }

        api_key = getattr(Config, 'CLAUDE_API_KEY', '').strip()
        if not api_key:
            return {
                'success': False,
                'error': (
                    "Clé API Claude manquante.\n"
                    "Renseignez votre clé dans l'interface ou dans config.py"
                    " (CLAUDE_API_KEY)."
                ),
            }

        try:
            image_data, media_type = _encode_image(image_path)
        except Exception as e:
            return {'success': False, 'error': f"Lecture image impossible : {e}"}

        model = getattr(Config, 'CLAUDE_OCR_MODEL', 'claude-haiku-4-5-20251001')

        if context_data:
            # Mode hybride v4 : Ollama a déjà classé les colonnes.
            # Claude corrige uniquement les caractères mal lus.
            col_names = ' | '.join(self._tpl.columns)
            n_cols = len(self._tpl.columns)
            all_meta = ['PAGE', 'BORNIER', 'PET', 'NO_PLAN', 'INDICE']
            footer_fields = getattr(self._tpl, 'footer_extract_fields', [])
            for fd in footer_fields:
                k = fd.get('key', '')
                if k and k not in all_meta:
                    all_meta.append(k)
            meta_json = ', '.join(f'"{k}": ""' for k in all_meta)
            prompt = (
                "TYPE_PAGE: listing\n\n"
                "DONNÉES EXTRAITES PAR OLLAMA "
                "(classification visuelle des colonnes déjà réalisée) :\n"
                "──────────────────────────────────────────────────────────\n"
                f"{context_data}\n"
                "──────────────────────────────────────────────────────────\n\n"
                "TON RÔLE UNIQUE — CORRECTION DES CARACTÈRES :\n"
                "La classification des colonnes d'Ollama est DÉJÀ CORRECTE.\n"
                "Ne change ni l'ordre ni l'attribution des colonnes.\n\n"
                "Pour chaque ligne, regarde l'image et corrige uniquement les\n"
                "erreurs de lecture OCR :\n"
                "  • confusion de caractères (O↔0, l↔1, S↔5, B↔8, rn↔m…)\n"
                "  • caractères manquants ou en trop\n"
                "  • casse si clairement visible\n\n"
                "Règles de sortie OBLIGATOIRES :\n"
                f"1. Il y a exactement {n_cols} colonnes : {col_names}\n"
                "2. UNE ligne de sortie par ligne de données, dans le MÊME ORDRE.\n"
                "3. Format pipe strict :  val1 | val2 | val3 | val4\n"
                "4. Si Ollama a omis une ligne visible dans l'image, ajoute-la.\n"
                "5. Après TOUTES les lignes de données, ajoute :\n"
                f"   META: {{{meta_json}}}\n"
                "   avec les valeurs lues dans le pied de page de l'image.\n"
            )
            logger.info(
                f"Claude Vision — mode correction Ollama "
                f"({len(context_data.splitlines())} lignes) : {image_path.name}"
            )
        elif feedback:
            # Le feedback est placé EN TÊTE du prompt : Claude lit de haut en bas
            # et donne plus de poids aux instructions placées en premier.
            prompt = (
                "⚠ CORRECTION REQUISE — À LIRE EN PRIORITÉ ABSOLUE :\n"
                f"{feedback}\n"
                "Applique cette correction sur l'image avant toute autre règle.\n\n"
                + _build_prompt(self._tpl)
            )
            logger.info(
                f"Claude Vision — feedback inclus "
                f"({len(feedback)} car.) : {image_path.name}"
            )
        else:
            prompt = _build_prompt(self._tpl)

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image',
                            'source': {
                                'type':       'base64',
                                'media_type': media_type,
                                'data':       image_data,
                            },
                        },
                        {'type': 'text', 'text': prompt},
                    ],
                }],
            )
        except Exception as e:
            _write_api_log({
                'ts':      datetime.datetime.now().isoformat(timespec='seconds'),
                'image':   image_path.name,
                'model':   getattr(Config, 'CLAUDE_OCR_MODEL', '?'),
                'error':   str(e),
                'success': False,
            })
            return {'success': False, 'error': f"Appel API Claude échoué : {e}"}

        raw = response.content[0].text
        # Parseur pipe-séparé unique — insertion positionnelle pour tous les templates
        try:
            column_mapping = self._resoudre_mapping_segments(raw, image_path)
            rows, metadata, page_type = _parse_pipe_response(
                raw, self._tpl, column_mapping=column_mapping
            )
        except ValueError as e:
            _write_api_log({
                'ts':      datetime.datetime.now().isoformat(timespec='seconds'),
                'image':   image_path.name,
                'model':   model,
                'error':   str(e),
                'success': False,
            })
            return {'success': False, 'error': str(e)}

        # Page de garde / modifications / sommaire → ignorer proprement
        if page_type == 'non-listing':
            logger.info(
                f"⊘ Page non-listing ignorée : {image_path.name}"
            )
            _write_api_log({
                'ts':       datetime.datetime.now().isoformat(timespec='seconds'),
                'image':    image_path.name,
                'model':    model,
                'raw':      raw,
                'rows':     0,
                'metadata': metadata,
                'success':  False,
                'error':    'non-listing',
            })
            return {
                'success': False,
                'error':   'Page ignorée (page de garde / modifications / sommaire)',
                'image_path': str(image_path),
                'detection_method': 'claude-vision',
            }

        logger.info(
            f"✓ Claude Vision : {len(rows)} lignes depuis {image_path.name} "
            f"(modèle {model})"
        )
        _write_api_log({
            'ts':        datetime.datetime.now().isoformat(timespec='seconds'),
            'image':     image_path.name,
            'model':     model,
            'raw':       raw,
            'rows':      len(rows),
            'rows_data': rows,      # données déjà parsées — utilisées par LogReplayer
            'metadata':  metadata,
            'success':   True,
        })
        return {
            'success':          True,
            'headers':          self._tpl.columns,
            'rows':             rows,
            'metadata':         metadata,
            'image_path':       str(image_path),
            'blur_pct':         0.0,
            'detection_method': 'claude-vision',
        }


class LogReplayer:
    """
    Rejoue un fichier claude_api_log.jsonl sans appeler l'API Claude.

    Lit les réponses brutes enregistrées lors d'une conversion précédente,
    les re-parse avec _parse_pipe_response() et retourne des résultats
    dans le même format que ClaudeVisionExtractor.extract().
    Permet de régénérer l'Excel sans dépenser de tokens.
    """

    def __init__(self, log_path: Path, template):
        self._log_path = Path(log_path)
        self._tpl = template

    def load_entries(self) -> List[Dict]:
        """Lit toutes les entrées JSONL (succès et erreurs)."""
        entries = []
        try:
            with open(self._log_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as exc:
            logger.error(f"Impossible de lire le log : {exc}")
        return entries

    def replay_all(self) -> List[Dict]:
        """Retourne la liste de résultats depuis le log, sans appeler l'API.

        Déduplication par image : si une page a fait l'objet de N retries,
        le log contient N entrées pour le même fichier image. On conserve
        uniquement la DERNIÈRE entrée réussie par image — c'est celle que
        l'utilisateur a validée (le retry final).

        Priorité des sources de données (de la plus fidèle à la moins fidèle) :
          1. rows_data  — données déjà parsées lors de l'extraction originale.
                          Résultat IDENTIQUE à l'Excel d'origine garanti.
          2. raw        — réponse brute re-parsée (fallback pour anciens logs
                          qui ne contiennent pas rows_data).
        """
        # Grouper par image : clé = nom du fichier image.
        # On parcourt le log dans l'ordre chronologique. Pour chaque image,
        # on écrase l'entrée précédente dès qu'une nouvelle entrée réussie
        # apparaît → à la fin, chaque clé pointe vers la dernière tentative
        # réussie (= le résultat accepté par l'utilisateur).
        seen: Dict[str, dict] = {}     # image_name → dernière entrée success
        seen_fail: Dict[str, dict] = {}  # image_name → dernière entrée failed
        _idx = [0]

        for entry in self.load_entries():
            # Clé unique : nom du fichier image, ou indice séquentiel si absent
            img_key = entry.get('image') or f'__seq_{_idx[0]}'
            _idx[0] += 1
            if entry.get('success'):
                seen[img_key] = entry
            else:
                # Garder l'échec seulement s'il n'y a pas d'entrée réussie
                if img_key not in seen:
                    seen_fail[img_key] = entry

        # Reconstruire une liste ordonnée : toutes les clés dans l'ordre
        # d'apparition (première occurrence), en privilégiant le succès
        ordered_keys: list = []
        key_order: dict = {}
        for i, entry in enumerate(self.load_entries()):
            img_key = entry.get('image') or f'__seq_{i}'
            if img_key not in key_order:
                key_order[img_key] = i
                ordered_keys.append(img_key)

        results = []
        for img_key in ordered_keys:
            entry = seen.get(img_key) or seen_fail.get(img_key)
            if entry is None:
                continue

            if not entry.get('success'):
                results.append({
                    'success':          False,
                    'error':            entry.get('error', 'Erreur inconnue'),
                    'image_path':       entry.get('image', ''),
                    'detection_method': 'log-replay',
                })
                continue

            metadata = entry.get('metadata', {})

            # ── Chemin 1 : données traitées stockées directement ──────
            rows_data = entry.get('rows_data')
            if rows_data:
                results.append({
                    'success':          True,
                    'headers':          self._tpl.columns,
                    'rows':             rows_data,
                    'metadata':         metadata,
                    'image_path':       entry.get('image', ''),
                    'blur_pct':         0.0,
                    'detection_method': 'log-replay',
                })
                continue

            # ── Chemin 2 : re-parsing de la réponse brute (anciens logs) ─
            raw = entry.get('raw', '')
            if not raw:
                continue
            try:
                rows, metadata, page_type = _parse_pipe_response(raw, self._tpl)
                if page_type == 'non-listing':
                    results.append({
                        'success': False,
                        'error':   'Page ignorée (page de garde / modifications / sommaire)',
                        'image_path': entry.get('image', ''),
                        'detection_method': 'log-replay',
                    })
                    continue
                results.append({
                    'success':          True,
                    'headers':          self._tpl.columns,
                    'rows':             rows,
                    'metadata':         metadata,
                    'image_path':       entry.get('image', ''),
                    'blur_pct':         0.0,
                    'detection_method': 'log-replay',
                })
            except Exception as exc:
                results.append({
                    'success':          False,
                    'error':            str(exc),
                    'image_path':       entry.get('image', ''),
                    'detection_method': 'log-replay',
                })
        return results
