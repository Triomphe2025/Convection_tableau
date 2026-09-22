"""
Moteur OCR via Managed Agents Anthropic — Image Data Extractor.

Activer avec Config.OCR_MODE = "agent".
Envoie les images à une session d'agent persistante via l'API Sessions
(client.beta.sessions.events.send/stream) au lieu de client.messages.create.
La réponse est parsée avec le même parseur pipe que claude_ocr.
"""

import base64
import datetime
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Noms d'événements qui signalent la FIN du tour de l'agent.
# Le SDK envoie l'un de ces types quand la réponse est complète.
_TERMINAL_EVENT_TYPES = frozenset({
    'done', 'end', 'stop', 'finish',
    'turn.end', 'turn.stop',
    'agent.turn.end', 'agent.turn.stop',
    'agent.message.stop',
    'message_stop', 'message.stop',
    'session.turn.end', 'session.turn.stop',
    'response.done', 'response.stop',
    'stream.end',
})

# Délai maximum en secondes pour obtenir la réponse d'une page.
_STREAM_TIMEOUT_SEC = 300  # 5 min — largement suffisant pour un LLM


def _event_type(event) -> str:
    """Extrait le type d'un événement SDK (objet ou dict)."""
    if hasattr(event, 'type'):
        return str(event.type).lower()
    if isinstance(event, dict):
        return str(event.get('type', '')).lower()
    return ''


def _is_terminal(event) -> bool:
    """Retourne True si l'événement marque la fin de la réponse agent."""
    t = _event_type(event)
    return t in _TERMINAL_EVENT_TYPES or t.endswith('.stop') or t.endswith('.end')


def _collect_event_text(event) -> str:
    """Extrait le texte brut d'un événement de session Managed Agents."""
    if hasattr(event, 'model_dump'):
        d = event.model_dump()
    elif isinstance(event, dict):
        d = event
    elif hasattr(event, '__dict__'):
        d = vars(event)
    else:
        return ''

    event_type = str(d.get('type', ''))

    # --- Événements delta (streaming progressif) ---
    if 'delta' in event_type:
        delta = d.get('delta', {})
        if isinstance(delta, dict):
            # content_block_delta : delta = {"type": "text_delta", "text": "..."}
            if delta.get('type') == 'text_delta':
                return delta.get('text', '')
            # Forme simple : delta = {"text": "..."}
            return delta.get('text', '')
        if hasattr(delta, 'text') and isinstance(getattr(delta, 'text', None), str):
            return delta.text

    # --- Message complet avec blocs de contenu ---
    content = d.get('content', [])
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text':
                parts.append(block.get('text', ''))
            elif hasattr(block, 'text') and isinstance(getattr(block, 'text', None), str):
                parts.append(block.text)
        return ''.join(parts)

    # --- Champ texte direct (certains SDKs exposent event.text) ---
    if 'text' in d and isinstance(d['text'], str):
        return d['text']

    return ''


def _stream_response(client, session_id: str) -> tuple:
    """
    Lit la réponse de la session dans un thread avec timeout.

    Retourne (raw_text, error_message).
    error_message est None si tout s'est bien passé.
    """
    raw_parts: List[str] = []
    error_holder = [None]
    finished = threading.Event()

    def _worker():
        try:
            with client.beta.sessions.events.stream(session_id) as stream:
                for event in stream:
                    etype = _event_type(event)
                    logger.debug(f"Agent event type : {etype!r}")

                    # Collecter le texte AVANT de tester le terminal
                    text = _collect_event_text(event)
                    if text:
                        raw_parts.append(text)

                    # Sortir dès que l'agent signale la fin de son tour
                    if _is_terminal(event):
                        logger.debug("Événement terminal reçu — fin du streaming.")
                        break
        except Exception as exc:
            error_holder[0] = exc
        finally:
            finished.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    finished.wait(timeout=_STREAM_TIMEOUT_SEC)

    if not finished.is_set():
        # Timeout : le stream n'a pas répondu à temps
        return '', f"Délai dépassé ({_STREAM_TIMEOUT_SEC}s) — l'agent n'a pas répondu."

    if error_holder[0] and not raw_parts:
        return '', f"Erreur streaming : {error_holder[0]}"

    raw = ''.join(raw_parts)
    if error_holder[0]:
        logger.warning(f"Stream terminé avec erreur après contenu partiel : {error_holder[0]}")

    return raw, None


class AgentVisionExtractor:
    """Extracteur de tableaux via session Managed Agent Anthropic."""

    def __init__(self, template, on_column_mapping: Optional[Callable] = None):
        self._tpl = template
        self._on_column_mapping = on_column_mapping
        self._cached_column_mapping: Optional[dict] = None
        self._cached_mapping_key = None

    def _resoudre_mapping_segments(self, raw: str, image_path) -> Optional[dict]:
        """Déclenche (ou réutilise depuis le cache) le mapping manuel
        segment→colonne quand la réponse a plus de segments que de colonnes."""
        from claude_ocr import _detect_ambiguous_segments
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
        Envoie l'image à la session agent et retourne le dict structuré.
        Même format de retour que ClaudeVisionExtractor.extract().

        Flux :
          1. Upload image via Files API (repli base64 si non disponible)
          2. Envoyer user.message via events.send()
          3. Lire réponse via events.stream() dans un thread avec timeout
          4. Parser avec _parse_pipe_response() (identique à claude_ocr)
        """
        from config import Config
        from claude_ocr import (
            _build_prompt, _parse_pipe_response,
            _write_api_log, _encode_image,
        )

        try:
            import anthropic
        except ImportError:
            return {
                'success': False,
                'error': "Package 'anthropic' non installé. Lancez : pip install anthropic",
            }

        api_key = getattr(Config, 'CLAUDE_API_KEY', '').strip()
        if not api_key:
            return {
                'success': False,
                'error': "Clé API Claude manquante. Renseignez-la dans l'interface.",
            }

        session_id = getattr(Config, 'CLAUDE_AGENT_SESSION_ID', '').strip()
        if not session_id:
            return {
                'success': False,
                'error': (
                    "ID de session agent manquant.\n"
                    "Renseignez-le dans le champ 'ID de session agent' (page Mode OCR)."
                ),
            }

        try:
            image_data, media_type = _encode_image(image_path)
        except Exception as e:
            return {'success': False, 'error': f"Lecture image impossible : {e}"}

        if feedback:
            prompt = (
                "⚠ CORRECTION REQUISE — À LIRE EN PRIORITÉ ABSOLUE :\n"
                f"{feedback}\n"
                "Applique cette correction sur l'image avant toute autre règle.\n\n"
                + _build_prompt(self._tpl)
            )
            logger.info(
                f"Agent Vision — feedback inclus ({len(feedback)} car.) : {image_path.name}"
            )
        else:
            prompt = _build_prompt(self._tpl)

        client = anthropic.Anthropic(api_key=api_key)

        # --- Étape 1 : upload via Files API (repli base64 si indisponible) ---
        file_id = None
        try:
            image_bytes = base64.standard_b64decode(image_data)
            file_obj = client.beta.files.upload(
                file=(image_path.name, image_bytes, media_type),
            )
            file_id = file_obj.id
            logger.debug(f"Image uploadée via Files API : {file_id}")
        except Exception as e:
            logger.warning(f"Files API non disponible, repli base64 : {e}")

        if file_id:
            image_block = {
                "type": "image",
                "source": {"type": "file", "file_id": file_id},
            }
        else:
            image_block = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            }

        # --- Étape 2 : envoyer le message à la session agent ---
        try:
            client.beta.sessions.events.send(
                session_id,
                events=[{
                    "type": "user.message",
                    "content": [image_block, {"type": "text", "text": prompt}],
                }],
            )
        except Exception as e:
            if file_id:
                try:
                    client.beta.files.delete(file_id)
                except Exception:
                    pass
            return {'success': False, 'error': f"Envoi à la session agent échoué : {e}"}

        # --- Étape 3 : lire la réponse (thread + timeout) ---
        raw, stream_err = _stream_response(client, session_id)

        # Nettoyage du fichier uploadé
        if file_id:
            try:
                client.beta.files.delete(file_id)
            except Exception:
                pass

        if stream_err:
            return {'success': False, 'error': stream_err}

        if not raw.strip():
            return {
                'success': False,
                'error': (
                    "Réponse agent vide.\n"
                    "Vérifiez que l'ID de session est correct et que l'agent est actif.\n"
                    "Activez OCR_DEBUG_LOG=True pour voir les événements reçus."
                ),
            }

        logger.debug(f"Réponse agent brute ({len(raw)} car.) : {raw[:200]!r}…")

        # --- Étape 4 : parser la réponse (même parseur que claude_ocr) ---
        try:
            column_mapping = self._resoudre_mapping_segments(raw, image_path)
            rows, metadata, page_type = _parse_pipe_response(
                raw, self._tpl, column_mapping=column_mapping
            )
        except Exception as e:
            return {'success': False, 'error': f"Parsing réponse agent échoué : {e}"}

        session_tag = f"agent:{session_id[:16]}"

        if page_type == 'non-listing':
            logger.info(f"⊘ Page non-listing ignorée (agent) : {image_path.name}")
            _write_api_log({
                'ts': datetime.datetime.now().isoformat(timespec='seconds'),
                'image': image_path.name,
                'model': session_tag,
                'raw': raw,
                'rows': 0,
                'metadata': metadata,
                'success': False,
                'error': 'non-listing',
            })
            return {
                'success': False,
                'error': 'Page ignorée (page de garde / modifications / sommaire)',
                'image_path': str(image_path),
                'detection_method': 'agent-vision',
            }

        logger.info(
            f"✓ Agent Vision : {len(rows)} lignes depuis {image_path.name} "
            f"(session …{session_id[-8:]})"
        )
        _write_api_log({
            'ts': datetime.datetime.now().isoformat(timespec='seconds'),
            'image': image_path.name,
            'model': session_tag,
            'raw': raw,
            'rows': len(rows),
            'rows_data': rows,
            'metadata': metadata,
            'success': True,
        })
        return {
            'success': True,
            'headers': self._tpl.columns,
            'rows': rows,
            'metadata': metadata,
            'image_path': str(image_path),
            'blur_pct': 0.0,
            'detection_method': 'agent-vision',
        }
