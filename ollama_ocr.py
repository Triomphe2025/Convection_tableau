"""
Moteur OCR Ollama Vision — extraction de tableaux via un modèle local.

Activer avec Config.OCR_MODE = "ollama".
Retourne le même format que BornierTableExtractor.extract().

Prérequis :
  1. Ollama installé et démarré (https://ollama.com)
  2. Modèle téléchargé : ollama pull qwen2.5vl:7b
     ou pour PC limité : ollama pull qwen2.5vl:3b

Stratégie d'appel :
  Priorité 1 — librairie Python officielle `ollama` (pip install ollama)
               → plus simple, plus fiable, accepte les chemins d'images directement
  Priorité 2 — requête HTTP manuelle (fallback si la lib n'est pas installée)
               → endpoint /v1/chat/completions (format OpenAI-compatible)
"""

import datetime
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from claude_ocr import _detect_ambiguous_segments, _encode_image, _parse_pipe_response

logger = logging.getLogger(__name__)

# ── Détection SDK Ollama ──────────────────────────────────────────────
try:
    import ollama as _sdk
    _SDK_DISPONIBLE = True
except ImportError:
    _sdk = None
    _SDK_DISPONIBLE = False

# ── Journal JSONL ─────────────────────────────────────────────────────
_ollama_log_path: Optional[Path] = None


def set_ollama_log_path(path: Optional[Path]) -> None:
    """Définit le fichier JSONL de journal. None = désactive l'écriture."""
    global _ollama_log_path
    _ollama_log_path = path


def write_ollama_session(
    *,
    source_file: str = '',
    output_dir: str = '',
    ocr_mode: str = '',
    template_columns: List[str] = None,
) -> None:
    """
    Écrit l'en-tête de session au début du fichier log.
    Appelé une fois par conversion, juste après set_ollama_log_path().
    """
    from config import Config
    entry = {
        'type':             'session',
        'ts':               datetime.datetime.now().isoformat(timespec='seconds'),
        'model':            getattr(Config, 'OLLAMA_MODEL', 'qwen2.5vl:7b'),
        'url':              getattr(Config, 'OLLAMA_URL',
                                    'http://localhost:11434/v1/chat/completions'),
        'sdk':              _SDK_DISPONIBLE,
        'ocr_mode':         ocr_mode,
        'source_file':      source_file,
        'output_dir':       output_dir,
        'template_columns': template_columns or [],
        'prompt_version':   'v5-sdk',
    }
    _write_ollama_log(entry)


def _write_ollama_log(entry: dict) -> None:
    """
    Écrit une entrée JSONL dans le fichier de journal.
    Les erreurs d'écriture sont loguées (jamais ignorées silencieusement).
    """
    if _ollama_log_path is None:
        return
    try:
        with open(_ollama_log_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(
            f"⚠ Écriture journal Ollama impossible "
            f"({_ollama_log_path}) : {e}"
        )


# ── Diagnostic de connexion ───────────────────────────────────────────

def test_ollama_connection(model: str = None) -> dict:
    """
    Test complet de la connexion et de la configuration Ollama.

    Vérifie dans l'ordre :
      1. Le serveur Ollama répond-il ?
      2. Quels modèles sont installés ?
      3. Le modèle configuré est-il présent ?
      4. Le modèle est-il compatible vision ?

    Retourne un dict :
      server_running  : bool
      models          : list[str] — noms des modèles installés
      model_found     : bool
      model_vision    : bool
      sdk             : bool — True si la librairie `ollama` est utilisée
      erreur          : str — message si server_running=False
      ok              : bool — True si tout est prêt
    """
    from config import Config
    model = model or getattr(Config, 'OLLAMA_MODEL', 'qwen2.5vl:7b')

    result = {
        'server_running': False,
        'models':         [],
        'model_found':    False,
        'model_vision':   False,
        'sdk':            _SDK_DISPONIBLE,
        'erreur':         '',
        'ok':             False,
    }

    # ── Étape 1 : serveur en ligne ────────────────────────────────────
    if _SDK_DISPONIBLE:
        try:
            host = _host_from_config()
            client = _sdk.Client(host=host)
            liste = client.list()
            result['server_running'] = True
            result['models'] = [
                m.get('model', m.get('name', ''))
                for m in (liste.get('models') or [])
            ]
        except Exception as e:
            result['erreur'] = (
                f"Ollama ne répond pas ({e}).\n"
                "Lancez Ollama (icône dans la barre des tâches) ou tapez :\n"
                "  ollama serve"
            )
            return result
    else:
        # Fallback HTTP pour tester le serveur
        try:
            url_tags = 'http://localhost:11434/api/tags'
            req = urllib.request.Request(url_tags)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            result['server_running'] = True
            result['models'] = [
                m.get('model', m.get('name', ''))
                for m in data.get('models', [])
            ]
        except Exception as e:
            result['erreur'] = (
                f"Ollama ne répond pas ({e}).\n"
                "Lancez Ollama (icône dans la barre des tâches) ou tapez :\n"
                "  ollama serve\n\n"
                "La librairie Python `ollama` n'est pas installée.\n"
                "Installez-la : pip install ollama"
            )
            return result

    # ── Étape 2 : modèle présent ──────────────────────────────────────
    model_base = model.split(':')[0].lower()
    result['model_found'] = any(
        model_base in m.lower() for m in result['models']
    )

    if not result['model_found']:
        installed = ', '.join(result['models']) if result['models'] else '(aucun)'
        result['erreur'] = (
            f"Modèle « {model} » non trouvé.\n"
            f"Modèles installés : {installed}\n\n"
            f"Téléchargez-le avec :\n  ollama pull {model}"
        )
        return result

    # ── Étape 3 : modèle vision ───────────────────────────────────────
    _VISION_KEYWORDS = (
        'vl', 'vision', 'llava', 'minicpm', 'bakllava',
        'cogvlm', 'moondream', 'internvl', 'pixtral', 'qwen2.5vl',
    )
    result['model_vision'] = any(kw in model.lower() for kw in _VISION_KEYWORDS)

    if not result['model_vision']:
        result['erreur'] = (
            f"Attention : « {model} » ne semble pas être un modèle vision.\n"
            "Les modèles vision reconnus : llava, qwen2.5vl, moondream…\n"
            "Si votre modèle supporte les images malgré tout, ignorez ce message."
        )
        # Ce n'est qu'un avertissement — on retourne quand même ok=True
        result['ok'] = True
        return result

    result['ok'] = True
    return result


def _host_from_config() -> str:
    """Extrait le host Ollama depuis la config (sans le chemin d'endpoint)."""
    from config import Config
    url = getattr(Config, 'OLLAMA_URL',
                  'http://localhost:11434/v1/chat/completions')
    # Garder uniquement scheme://host:port
    from urllib.parse import urlparse
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


# ── Appel au modèle : SDK ou HTTP ─────────────────────────────────────

def _appeler_ollama(
    model: str,
    prompt: str,
    image_path: Path,
    url: str,
    timeout: int,
) -> str:
    """
    Envoie le prompt + l'image à Ollama.
    Utilise le SDK officiel si disponible, sinon requête HTTP manuelle.
    Retourne la réponse brute (str) ou lève une exception.
    """
    if _SDK_DISPONIBLE:
        return _appeler_sdk(model, prompt, image_path, timeout)
    return _appeler_http(model, prompt, image_path, url, timeout)


def _appeler_sdk(
    model: str,
    prompt: str,
    image_path: Path,
    timeout: int,
) -> str:
    """Appel via la librairie officielle `ollama`."""
    host = _host_from_config()
    client = _sdk.Client(host=host, timeout=timeout)
    response = client.chat(
        model=model,
        messages=[{
            'role':    'user',
            'content': prompt,
            'images':  [str(image_path)],   # SDK accepte les chemins fichiers
        }],
    )
    # response.message.content (objet) ou response['message']['content'] (dict)
    msg = response.message if hasattr(response, 'message') else response.get('message', {})
    if hasattr(msg, 'content'):
        return msg.content
    return msg.get('content', '')


def _appeler_http(
    model: str,
    prompt: str,
    image_path: Path,
    url: str,
    timeout: int,
) -> str:
    """Fallback : requête HTTP manuelle — endpoint /v1/chat/completions."""
    image_data, media_type = _encode_image(image_path)

    payload = json.dumps({
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{image_data}",
                    },
                },
            ],
        }],
        "stream": False,
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode('utf-8'))

    # Format OpenAI (/v1/chat/completions) ou format natif (/api/chat)
    choices = body.get('choices')
    if choices:
        return choices[0].get('message', {}).get('content', '')
    return body.get('message', {}).get('content', '')


def _prechauffer_modele(model: str, url: str, timeout: int = 30) -> Tuple[bool, str]:
    """
    Envoie une requête texte simple (sans image) pour charger le modèle en RAM.
    Retourne (True, '') si réussi, (False, message_erreur) sinon.

    La première requête peut prendre 30-120 s selon la RAM/GPU disponible.
    Les appels suivants sont quasi-instantanés tant que le modèle reste en mémoire.
    """
    prompt_warmup = "Réponds uniquement avec le mot : OK"
    try:
        if _SDK_DISPONIBLE:
            host = _host_from_config()
            client = _sdk.Client(host=host, timeout=timeout)
            client.chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt_warmup}],
            )
            return True, ''
        else:
            # Fallback HTTP — /api/generate (texte seul, plus léger que /api/chat)
            host = _host_from_config()
            payload = json.dumps({
                'model':  model,
                'prompt': prompt_warmup,
                'stream': False,
            }).encode('utf-8')
            req = urllib.request.Request(
                f"{host}/api/generate",
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=timeout):
                pass
            return True, ''
    except Exception as e:
        return False, str(e)


# ── Construction du prompt structuré v5 ──────────────────────────────

def _construire_prompt_ollama(tpl, feedback: str = None) -> str:
    """
    Prompt Ollama v5 — analyse de structure visuelle + extraction pipe.

    Le modèle est guidé pour :
      1. détecter le type de page (listing / non-listing)
      2. analyser visuellement colonnes et fusions (ANALYSE_JSON)
      3. produire les lignes finales en respectant EXACTEMENT les colonnes
    """
    col_names_list = tpl.columns
    n_cols = len(col_names_list)
    col_enum = '\n'.join(f"  {i + 1}. {c}" for i, c in enumerate(col_names_list))
    col_example = ' | '.join(col_names_list)
    n_pipes = n_cols - 1

    footer_fields = [
        f['key']
        for f in getattr(tpl, 'footer_extract_fields', [])
    ] or ['PAGE', 'BORNIER', 'PET']
    meta_fields = ', '.join(footer_fields)

    base = (
        f"Tu analyses une image de tableau technique électrique.\n\n"
        f"Colonnes attendues ({n_cols} colonnes, dans cet ordre) :\n"
        f"{col_enum}\n\n"
        "Travail demandé :\n\n"
        "1. Détermine si la page contient un vrai tableau listing exploitable.\n"
        "   Réponds exactement sur une ligne :\n"
        "     TYPE_PAGE: listing\n"
        "   ou\n"
        "     TYPE_PAGE: non-listing\n\n"
        "2. Analyse visuellement la structure du tableau et réponds sur UNE SEULE LIGNE :\n"
        "   ANALYSE_JSON: {\"colonnes_visuelles\": N, \"fusions\": [], "
        "\"confiance\": \"haute|moyenne|faible\"}\n"
        "   • colonnes_visuelles : nombre de colonnes visibles dans l'image\n"
        "   • fusions : regroupements si le visuel dépasse le nombre attendu\n"
        "   • confiance : ta confiance dans la classification des colonnes\n\n"
        f"3. Si le tableau visuel contient plus de {n_cols} colonnes, détermine\n"
        "   quelles colonnes visuelles appartiennent à la même colonne du template\n"
        "   et fusionne leur contenu avec un espace dans la cellule cible.\n"
        "   Exemple :\n"
        "     AP | 23 | 0113R | AB | 27 | BFSHT 44 +\n"
        "   doit devenir :\n"
        "     AP 23 | 0113R | AB 27 | BFSHT 44 +\n\n"
        f"4. Produis UNIQUEMENT les lignes de données dans ce format strict :\n"
        f"   {col_example}\n"
        f"   Chaque ligne doit contenir EXACTEMENT {n_pipes} barre(s) verticale(s) '|'.\n"
        "   Ne produis AUCUN en-tête, AUCUNE ligne de séparateur (---), AUCUNE explication.\n"
        "   Saute les lignes qui répètent les noms de colonnes.\n\n"
        "5. Règles absolues :\n"
        "   • Ne supprime aucune donnée visible dans le tableau.\n"
        "   • Si une donnée ne peut pas être classée avec certitude, place-la dans\n"
        "     la cellule la plus probable et ajoute [A_VERIFIER] à la fin.\n"
        "   • Ne produis jamais plus de colonnes que la liste attendue.\n"
        "   • Ne donne aucune explication après les lignes de données.\n\n"
        f"6. Après les lignes de données, ajoute une ligne META :\n"
        f"   META: {{{meta_fields}}}\n"
        "   (valeurs extraites du bas de page de l'image)\n"
    )

    if feedback:
        return (
            "⚠ CORRECTION REQUISE — À LIRE EN PRIORITÉ ABSOLUE :\n"
            f"{feedback}\n"
            "Applique cette correction sur l'image avant toute autre règle.\n\n"
            + base
        )
    return base


# ── Analyse des lignes brutes ─────────────────────────────────────────

def _analyser_lignes_brutes(raw: str, n_cols: int) -> dict:
    """
    Analyse la réponse brute ligne par ligne AVANT le parsing.
    Filtre TYPE_PAGE:, META:, ANALYSE_JSON:.
    Classe chaque ligne de données en : acceptée / réparée / rejetée.
    """
    acceptees: List[str] = []
    reparees:  List[dict] = []
    rejetees:  List[dict] = []

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or '|' not in line:
            continue
        upper = line.upper()
        if upper.startswith(('TYPE_PAGE:', 'META:', 'ANALYSE_JSON:')):
            continue
        parts = [p.strip() for p in line.split('|')]
        found = len(parts)
        if found == n_cols:
            acceptees.append(line[:200])
        elif found > n_cols:
            reparees.append({
                'ligne':             line[:200],
                'segments_trouves':  found,
                'segments_attendus': n_cols,
            })
        else:
            rejetees.append({
                'ligne':             line[:200],
                'segments_trouves':  found,
                'segments_attendus': n_cols,
            })

    return {
        'total_lignes_data': len(acceptees) + len(reparees) + len(rejetees),
        'acceptees':         len(acceptees),
        'reparees':          len(reparees),
        'rejetees':          len(rejetees),
        'detail_reparees':   reparees,
        'detail_rejetees':   rejetees,
    }


# ── Extraction de la structure visuelle ──────────────────────────────

def _extraire_structure_ollama(raw: str) -> dict:
    """Parse la ligne ANALYSE_JSON: de la réponse Ollama."""
    default = {'colonnes_visuelles': 0, 'fusions': [], 'confiance': 'inconnue'}
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith('ANALYSE_JSON:'):
            json_part = stripped[len('ANALYSE_JSON:'):].strip()
            try:
                data = json.loads(json_part)
                if isinstance(data, dict):
                    return {
                        'colonnes_visuelles': int(data.get('colonnes_visuelles', 0)),
                        'fusions':            data.get('fusions', []),
                        'confiance':          str(data.get('confiance', 'inconnue')),
                    }
            except (json.JSONDecodeError, ValueError):
                logger.debug(f"ANALYSE_JSON non parsable : {json_part[:200]}")
    return default


# ── Validation post-parsing ───────────────────────────────────────────

def _valider_lignes(
    rows: List[Dict],
    n_cols: int,
    structure: dict,
) -> Tuple[List[Dict], dict]:
    """
    Valide les lignes parsées et corrige les anomalies résiduelles.
    Surplus → fusion. Trop peu → [INCOMPLET]. [A_VERIFIER] → comptabilisé.
    """
    lignes_fusionnees = 0
    lignes_incompletes = 0
    lignes_a_verifier = 0
    details: List[dict] = []
    validated = []

    for i, row in enumerate(rows):
        if row.get('type') != 'data':
            validated.append(row)
            continue

        cells = list(row.get('cells', []))
        issues: List[str] = []

        if len(cells) > n_cols:
            surplus = cells[n_cols - 1:]
            cells = cells[:n_cols - 1] + [' '.join(str(s) for s in surplus)]
            lignes_fusionnees += 1
            issues.append(f"fusion_{len(row.get('cells', []))}→{n_cols}")

        while len(cells) < n_cols:
            cells.append('[INCOMPLET]')
            lignes_incompletes += 1
            issues.append('incomplet')

        for c in cells:
            if '[A_VERIFIER]' in str(c).upper():
                lignes_a_verifier += 1
                issues.append('a_verifier')
                break

        if issues:
            details.append({'ligne': i + 1, 'issues': issues})

        validated.append({
            'type':       row.get('type', 'data'),
            'cells':      cells,
            'confidence': row.get('confidence', [100] * n_cols),
        })

    rapport = {
        'lignes_total':                 len(rows),
        'lignes_fusionnees':            lignes_fusionnees,
        'lignes_incompletes':           lignes_incompletes,
        'lignes_a_verifier':            lignes_a_verifier,
        'score_confiance':              structure.get('confiance', 'inconnue'),
        'colonnes_visuelles_detectees': structure.get('colonnes_visuelles', 0),
        'details':                      details,
    }
    return validated, rapport


# ── Sauvegarde debug ──────────────────────────────────────────────────

def _sauvegarder_debug(
    img_name: str,
    raw: str,
    rows_valides: List[Dict],
    rapport: dict,
    structure: dict,
) -> None:
    """Sauvegarde les fichiers debug quand OLLAMA_DEBUG=True."""
    if _ollama_log_path is not None:
        debug_dir = Path(_ollama_log_path).parent / 'ollama_debug'
    else:
        debug_dir = Path.cwd() / 'ollama_debug'
    try:
        debug_dir.mkdir(exist_ok=True)
        stem = Path(img_name).stem
        (debug_dir / f"{stem}_raw.txt").write_text(raw, encoding='utf-8')
        lines_out = [
            ' | '.join(str(c) for c in row.get('cells', []))
            for row in rows_valides if row.get('type') == 'data'
        ]
        (debug_dir / f"{stem}_lignes.txt").write_text(
            '\n'.join(lines_out), encoding='utf-8'
        )
        (debug_dir / f"{stem}_decisions.json").write_text(
            json.dumps(
                {'image': img_name, 'structure': structure, 'rapport': rapport},
                ensure_ascii=False, indent=2,
            ),
            encoding='utf-8',
        )
    except Exception as e:
        logger.error(f"⚠ Sauvegarde debug Ollama impossible ({debug_dir}) : {e}")


# ── Extracteur principal ──────────────────────────────────────────────

class OllamaVisionExtractor:
    """Extracteur de tableaux via Ollama Vision (modèle local)."""

    def __init__(self, template, on_column_mapping: Optional[Callable] = None):
        self._tpl = template
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
        Extrait le tableau via Ollama (SDK ou HTTP) et retourne le dict structuré.
        Une entrée de log est TOUJOURS écrite, quelle que soit l'issue.
        """
        ts_debut = time.monotonic()
        img_name = Path(image_path).name

        from config import Config
        url = getattr(Config, 'OLLAMA_URL',   'http://localhost:11434/v1/chat/completions')
        model = getattr(Config, 'OLLAMA_MODEL',  'qwen2.5vl:7b')
        timeout = getattr(Config, 'OLLAMA_TIMEOUT', 180)
        debug = getattr(Config, 'OLLAMA_DEBUG',   False)
        n_cols = len(self._tpl.columns)

        log: dict = {
            'type':                    'page',
            'ts':                      datetime.datetime.now().isoformat(timespec='seconds'),
            'image':                   img_name,
            'model':                   model,
            'sdk':                     _SDK_DISPONIBLE,
            'url':                     url if not _SDK_DISPONIBLE else _host_from_config(),
            'n_cols_attendu':          n_cols,
            'prompt':                  '',
            'raw':                     '',
            'analyse_lignes':          {},
            'n_cols_visuels_detectes': 0,
            'structure_detectee':      {},
            'rapport_validation':      {},
            'rows':                    0,
            'rows_data':               [],
            'metadata':                {},
            'success':                 False,
            'error_type':              '',
            'error_msg':               '',
            'duree_ms':                0,
        }

        def _fin(success: bool,
                 error_type: str = '',
                 error_msg:  str = '',
                 result:     dict = None) -> dict:
            log['success'] = success
            log['error_type'] = error_type
            log['error_msg'] = error_msg
            log['duree_ms'] = int((time.monotonic() - ts_debut) * 1000)
            _write_ollama_log(log)
            if success:
                return result
            logger.warning(
                f"✗ Ollama [{error_type}] {img_name} : {error_msg[:120]}"
            )
            return {
                'success':          False,
                'error':            error_msg,
                'image_path':       str(image_path),
                'detection_method': 'ollama-vision',
            }

        try:
            return self._extraire(
                image_path, feedback, img_name, model, url,
                timeout, n_cols, log, _fin, debug,
            )
        except Exception as exc:
            logger.error(
                f"Exception inattendue Ollama {img_name} : {exc}",
                exc_info=True,
            )
            return _fin(False, 'exception_inattendue', str(exc))

    # ── Logique d'extraction ──────────────────────────────────────────

    def _extraire(
        self, image_path, feedback, img_name, model, url,
        timeout, n_cols, log, _fin, debug,
    ) -> dict:
        col_names = ' | '.join(self._tpl.columns)

        # ── Étape 1 : prompt ──────────────────────────────────────────
        prompt = _construire_prompt_ollama(self._tpl, feedback=feedback)
        log['prompt'] = prompt if len(prompt) <= 1200 else prompt[:1200] + '…[tronqué]'

        # ── Étape 2 : appel (SDK ou HTTP) ─────────────────────────────
        methode = 'SDK' if _SDK_DISPONIBLE else 'HTTP'
        try:
            raw = _appeler_ollama(model, prompt, image_path, url, timeout)
        except Exception as e:
            msg = str(e)
            # Classer l'erreur pour un message utilisateur clair
            msg_lower = msg.lower()
            if any(k in msg_lower for k in ('connect', 'refused', 'timeout',
                                            'unavailable', 'unreachable')):
                return _fin(
                    False, 'connexion_echouee',
                    f"Ollama ne répond pas ({msg}).\n"
                    f"Lancez Ollama, puis : ollama pull {model}",
                )
            if 'not found' in msg_lower or '404' in msg:
                return _fin(
                    False, 'modele_absent',
                    f"Modèle « {model} » non installé.\n"
                    f"Téléchargez-le : ollama pull {model}",
                )
            if 'vision' in msg_lower or 'image' in msg_lower:
                return _fin(
                    False, 'modele_non_vision',
                    f"Le modèle « {model} » ne supporte pas les images.\n"
                    "Utilisez un modèle vision : qwen2.5vl:7b, llava, etc.",
                )
            return _fin(False, 'appel_echoue',
                        f"Appel Ollama [{methode}] échoué : {msg}")

        log['raw'] = raw

        if not raw or not raw.strip():
            return _fin(
                False, 'reponse_vide',
                f"Ollama [{methode}] : réponse vide.\n"
                "Vérifiez que le modèle vision est bien chargé.",
            )

        # ── Étape 3 : structure visuelle (ANALYSE_JSON) ───────────────
        structure = _extraire_structure_ollama(raw)
        log['structure_detectee'] = structure
        log['n_cols_visuels_detectes'] = structure.get('colonnes_visuelles', 0)

        if structure['colonnes_visuelles'] > 0:
            logger.info(
                f"  ↔ Structure {img_name} : "
                f"{structure['colonnes_visuelles']} cols visuelles, "
                f"confiance {structure['confiance']}"
            )

        # ── Étape 4 : analyse lignes brutes ───────────────────────────
        analyse = _analyser_lignes_brutes(raw, n_cols)
        log['analyse_lignes'] = analyse

        if analyse['reparees']:
            logger.warning(
                f"  ⚠ Ollama {img_name} : {analyse['reparees']} ligne(s) "
                "avec surplus (fusion automatique)"
            )
        if analyse['rejetees']:
            logger.warning(
                f"  ⚠ Ollama {img_name} : {analyse['rejetees']} ligne(s) "
                "incomplètes après parsing"
            )

        # ── Étape 5 : parsing ─────────────────────────────────────────
        try:
            column_mapping = self._resoudre_mapping_segments(raw, image_path)
            rows, metadata, page_type = _parse_pipe_response(
                raw, self._tpl, column_mapping=column_mapping
            )
        except Exception as e:
            return _fin(False, 'parsing_echoue', str(e))

        if page_type == 'non-listing':
            logger.info(f"⊘ Ollama — non-listing ignorée : {img_name}")
            return _fin(
                False, 'non_listing',
                'Page ignorée (page de garde / modifications / sommaire)',
            )

        # ── Étape 6 : validation ──────────────────────────────────────
        rows_valides, rapport = _valider_lignes(rows, n_cols, structure)
        log['rapport_validation'] = rapport

        if rapport['lignes_fusionnees']:
            logger.warning(
                f"  ⚠ Ollama {img_name} : {rapport['lignes_fusionnees']} "
                "ligne(s) avec surplus fusionné"
            )
        if rapport['lignes_incompletes']:
            logger.warning(
                f"  ⚠ Ollama {img_name} : {rapport['lignes_incompletes']} "
                "ligne(s) marquées [INCOMPLET]"
            )
        if rapport['lignes_a_verifier']:
            logger.warning(
                f"  ⚠ Ollama {img_name} : {rapport['lignes_a_verifier']} "
                "ligne(s) [A_VERIFIER] à contrôler"
            )

        log['rows'] = len(rows_valides)
        log['rows_data'] = rows_valides
        log['metadata'] = metadata

        if debug:
            _sauvegarder_debug(img_name, raw, rows_valides, rapport, structure)

        # ── Aperçu UI ─────────────────────────────────────────────────
        logger.info(f"✓ Ollama [{methode}] : {len(rows_valides)} lignes ← {img_name}")
        logger.info(f"  Colonnes : {col_names}")
        for idx, row in enumerate(rows_valides[:6], 1):
            cells = row.get('cells', [])
            logger.info(f"  L{idx:02d} : {' | '.join(str(c) for c in cells)}")
        if len(rows_valides) > 6:
            logger.info(f"  … ({len(rows_valides) - 6} lignes supplémentaires)")

        return _fin(True, result={
            'success':          True,
            'headers':          self._tpl.columns,
            'rows':             rows_valides,
            'metadata':         metadata,
            'image_path':       str(image_path),
            'blur_pct':         0.0,
            'detection_method': 'ollama-vision',
        })
