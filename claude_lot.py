"""Lecture d'un lot de pages par la Message Batches API d'Anthropic (mode claude seul).

Facturation à moitié prix par rapport à un appel par page. Chaque page réussie passe par le
chemin unique ClaudeVisionExtractor._traiter_reponse : même journal, même cache, même retour
qu'une lecture normale. Les pages en erreur / expirées / annulées sont rendues avec
`repli_normal=True` pour relecture en appel normal — la relecture n'entre jamais dans un lot.
Ne lève jamais : une page non lue est rendue, elle n'interrompt pas le document.

Module appelé par converter.py (jamais par interface.py). Réutilise les aides de claude_ocr
(une seule façon de construire la requête, de lire la réponse et de l'écrire en cache).
"""

import datetime
import json
import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config import Config
import claude_ocr

logger = logging.getLogger(__name__)


def _custom_id(index: int) -> str:
    """Identifiant de requête unique et conforme (^[a-zA-Z0-9_-]{1,64}$) : le rang de la page."""
    return f"p{index:05d}"


def _enregistrer_lot(dossier_sortie, batch_id: str, table: Dict, modele: str) -> None:
    """Écrit l'id du lot et la table custom_id → page dans le dossier de sortie (reprise possible).

    Jamais bloquant : un échec d'écriture laisse le lot se dérouler normalement.
    """
    try:
        dossier = Path(dossier_sortie)
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / f'lot_{batch_id}.json').write_text(
            json.dumps({
                'id': batch_id,
                'modele': modele,
                'date': datetime.datetime.now().isoformat(timespec='seconds'),
                'pages': {cid: str(info['image']) for cid, info in table.items()},
            }, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
    except Exception as exc:
        logger.warning(f"Lot : table de correspondance non enregistrée ({exc})")


class LecteurLot:
    """Lit une liste de pages en un seul lot et rend {chemin_image: resultat}.

    Une page non lue (préparation impossible, erreur / expiration / annulation, arrêt demandé,
    lot indisponible) est rendue avec `repli_normal=True` : converter la relira en appel normal.
    """

    def __init__(self, extractor, on_log: Optional[Callable] = None,
                 doit_arreter: Optional[Callable] = None, poll_secondes=None):
        self._ex = extractor
        self._on_log = on_log or (lambda *a, **k: None)
        self._doit_arreter = doit_arreter or (lambda: False)
        self._poll = poll_secondes if poll_secondes is not None else \
            getattr(Config, 'CLAUDE_LOT_POLL_SECONDES', 30)

    def lire(self, image_paths: List[Path], dossier_sortie) -> Dict[str, dict]:
        """Lit toutes les pages par lot. Ne lève jamais."""
        resultats: Dict[str, dict] = {}
        image_paths = list(image_paths)
        if not image_paths:
            return resultats

        api_key = getattr(Config, 'CLAUDE_API_KEY', '').strip()
        if not api_key:
            return {str(p): self._repli(p, "clé API absente") for p in image_paths}
        try:
            import anthropic
        except ImportError:
            return {str(p): self._repli(p, "package anthropic absent") for p in image_paths}

        cache_actif = (getattr(Config, 'CLAUDE_CACHE_LECTURES', False)
                       and not getattr(Config, 'CLAUDE_FORCER_RELECTURE', False))
        modele = getattr(Config, 'CLAUDE_OCR_MODEL', 'claude-opus-5')

        requetes: List[dict] = []
        table: Dict[str, dict] = {}
        for index, image_path in enumerate(image_paths):
            try:
                prepa = self._preparer(image_path, cache_actif)
            except Exception as exc:
                # Page non préparable (image illisible, modèle refusé) : repli en appel normal.
                resultats[str(image_path)] = self._repli(image_path, str(exc))
                continue
            cid = _custom_id(index)
            requetes.append({'custom_id': cid, 'params': prepa['requete']})
            table[cid] = dict(prepa, image=image_path)

        if not requetes:
            return resultats

        client = anthropic.Anthropic(api_key=api_key)
        batch = self._creer(client, requetes)
        if batch is None:
            for info in table.values():
                resultats.setdefault(str(info['image']),
                                     self._repli(info['image'], "lot indisponible"))
            return resultats

        _enregistrer_lot(dossier_sortie, batch.id, table, modele)
        self._on_log(f"  Lot envoyé : {len(requetes)} page(s) (id {batch.id})", 'info')

        statut = self._attendre(client, batch)
        if statut == 'arret':
            self._annuler(client, batch.id)
        elif statut == 'fini':
            self._recuperer(client, batch.id, table, cache_actif, resultats)

        # Toute page sans réponse (arrêt, lot interrompu, absente des résultats) : repli normal.
        for info in table.values():
            resultats.setdefault(str(info['image']),
                                 self._repli(info['image'], "page non rendue par le lot"))
        return resultats

    def _preparer(self, image_path, cache_actif: bool) -> dict:
        """Construit la requête standard d'une page (consigne en cache) + sa clé de cache."""
        model = getattr(Config, 'CLAUDE_OCR_MODEL', 'claude-opus-5')
        parametres = claude_ocr._parametres_modele(model)       # ValueError si modèle inconnu
        image_data, media_type = claude_ocr._preparer_image_claude(
            image_path, getattr(Config, 'CLAUDE_IMAGE_MAX_PX', 2576))
        prompt = self._ex._prompt_page(None, None)              # lot : pages standard uniquement
        requete, max_tokens = self._ex._construire_requete(
            model, parametres, image_data, media_type, prompt)
        cle_cache = None
        if cache_actif:
            import cache_claude
            cle_cache = cache_claude.cle(image_data, media_type, prompt, model,
                                         parametres, max_tokens)
        return {'requete': requete, 'model': model, 'max_tokens': max_tokens,
                'cle_cache': cle_cache}

    def _creer(self, client, requetes):
        """Crée le lot ; retries sur coupure réseau, None si création impossible."""
        delais = list(getattr(Config, 'CLAUDE_RETRY_DELAIS', ()))
        for tentative in range(len(delais) + 1):
            try:
                return client.messages.batches.create(requests=requetes)
            except Exception as exc:
                if claude_ocr._erreur_reseau(exc) and tentative < len(delais):
                    self._on_log(
                        f"  Lot indisponible — nouvelle tentative dans {delais[tentative]} s",
                        'warn')
                    time.sleep(delais[tentative])
                    continue
                logger.warning(f"Lot : création impossible ({exc})")
                return None

    def _attendre(self, client, batch) -> str:
        """Interroge l'état jusqu'à 'ended'. Rend 'fini', 'arret' ou 'indisponible'."""
        statut = getattr(batch, 'processing_status', 'in_progress')
        while statut != 'ended':
            if self._doit_arreter():
                return 'arret'
            maj = self._etat(client, batch.id)
            if maj is None:
                return 'indisponible'
            statut = maj.processing_status
            if statut == 'ended':
                break
            rc = maj.request_counts
            a_reprendre = rc.errored + rc.expired + rc.canceled
            self._on_log(
                f"  Lot en cours : {rc.succeeded} lue(s), {rc.processing} en attente"
                + (f", {a_reprendre} à reprendre" if a_reprendre else ''), 'info')
            if self._dormir() == 'arret':
                return 'arret'
        return 'fini'

    def _dormir(self) -> str:
        """Attend l'intervalle d'interrogation en coupant tôt si un arrêt est demandé."""
        reste = self._poll
        while reste > 0:
            if self._doit_arreter():
                return 'arret'
            time.sleep(min(1, reste))
            reste -= 1
        return 'ok'

    def _etat(self, client, batch_id):
        """Lit l'état du lot ; retries sur coupure réseau, None si indisponible."""
        delais = list(getattr(Config, 'CLAUDE_RETRY_DELAIS', ()))
        for tentative in range(len(delais) + 1):
            try:
                return client.messages.batches.retrieve(batch_id)
            except Exception as exc:
                if claude_ocr._erreur_reseau(exc) and tentative < len(delais):
                    time.sleep(delais[tentative])
                    continue
                logger.warning(f"Lot : état indisponible ({exc})")
                return None

    def _annuler(self, client, batch_id) -> None:
        """Demande l'annulation du lot (arrêt utilisateur)."""
        try:
            client.messages.batches.cancel(batch_id)
            self._on_log("  Lot annulé (arrêt demandé)", 'warn')
        except Exception as exc:
            logger.warning(f"Lot : annulation impossible ({exc})")

    def _recuperer(self, client, batch_id, table: Dict, cache_actif: bool,
                   resultats: Dict) -> None:
        """Parcourt les réponses du lot et route chacune par le chemin de lecture unique."""
        try:
            individuels = client.messages.batches.results(batch_id)
        except Exception as exc:
            logger.warning(f"Lot : résultats illisibles ({exc})")
            return
        for reponse in individuels:
            info = table.get(getattr(reponse, 'custom_id', None))
            if info is None:
                continue
            resultats[str(info['image'])] = self._traiter(reponse, info, cache_actif)

    def _traiter(self, reponse, info: dict, cache_actif: bool) -> dict:
        """Une réponse de lot → résultat, par le MÊME chemin qu'une réponse normale."""
        resultat = reponse.result
        if getattr(resultat, 'type', '') != 'succeeded':
            # errored / expired / canceled → repli en appel normal.
            return self._repli(info['image'], f"lot : {getattr(resultat, 'type', 'inconnu')}")
        message = resultat.message
        raw = claude_ocr._texte_reponse(message)
        usage = claude_ocr._consommation(message)
        modele_servi = getattr(message, 'model', info['model'])
        id_reponse = getattr(message, 'id', '') or ''
        stop_reason = message.stop_reason
        return self._ex._traiter_reponse(
            info['image'], raw, usage, modele_servi, id_reponse, stop_reason,
            'api', '', cache_actif, info['cle_cache'], info['max_tokens'], message)

    @staticmethod
    def _repli(image_path, raison: str) -> dict:
        """Résultat d'une page à relire en appel normal (hors lot)."""
        return {
            'success': False,
            'repli_normal': True,
            'error': f"Page non lue par le lot ({raison}) — relecture en appel normal",
            'image_path': str(image_path),
        }
