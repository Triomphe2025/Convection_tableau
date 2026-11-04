"""Lecture d'un lot de pages par la Message Batches API d'Anthropic (mode claude seul).

Facturation à moitié prix par rapport à un appel par page. Chaque page réussie passe par le
chemin unique ClaudeVisionExtractor._traiter_reponse : même journal, même cache, même retour
qu'une lecture normale. Les pages en erreur / expirées / annulées sont rendues avec
`repli_normal=True` pour relecture en appel normal — la relecture n'entre jamais dans un lot.
Ne lève jamais : une page non lue est rendue, elle n'interrompt pas le document.

Un document est découpé en plusieurs lots sous CLAUDE_LOT_TAILLE_MAX_MO (la limite serveur est
de 256 Mo par lot) : un fichier lot_<id>.json par lot, `reprendre` accepte un dossier. Le client
du lot n'a aucune relance interne (max_retries=0) et un délai proportionnel à la taille ; nos
relances passent par CLAUDE_RETRY_DELAIS et respectent le bouton Arrêter. Après un délai dépassé,
un lot a pu aboutir côté serveur : on cherche un doublon récent avant d'en recréer un.

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


def _taille_octets(requete) -> int:
    """Taille approximative (octets) d'une requête préparée, dominée par l'image en base64."""
    try:
        return len(json.dumps(requete, ensure_ascii=False).encode('utf-8'))
    except Exception:
        return 0


def _format_taille(octets: int) -> str:
    """Taille lisible pour le journal (Mo au-delà de 1 Mo, sinon Ko)."""
    mo = octets / (1024 * 1024)
    if mo >= 1:
        return f"{mo:.0f} Mo"
    return f"{octets / 1024:.0f} Ko"


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
    """Lit une liste de pages par lot(s) et rend {chemin_image: resultat}.

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
        """Lit toutes les pages, découpées en lots sous le plafond de taille. Ne lève jamais.

        Tous les lots sont créés d'abord (un lot_<id>.json écrit dès chaque création), puis
        attendus dans une seule boucle de sondage, puis récupérés : un lot n'attend pas la fin
        du précédent pour partir.
        """
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

        infos: List[dict] = []
        for index, image_path in enumerate(image_paths):
            try:
                prepa = self._preparer(image_path, cache_actif)
            except Exception as exc:
                # Page non préparable (image illisible, modèle refusé) : repli en appel normal.
                resultats[str(image_path)] = self._repli(image_path, str(exc))
                continue
            infos.append(dict(prepa, image=image_path, cid=_custom_id(index),
                              taille=_taille_octets(prepa['requete'])))
        if not infos:
            return resultats

        lots = self._decouper(infos)
        client_base = anthropic.Anthropic(api_key=api_key, max_retries=0)
        # Un doublon côté serveur est un lot créé APRÈS le début de nos tentatives et dont l'id
        # n'est pas déjà connu (lot créé cette exécution, ou lot_*.json d'une exécution passée).
        heure_debut = datetime.datetime.now(datetime.timezone.utc)
        ids_connus = self._ids_lots_dossier(dossier_sortie)

        envois: List[tuple] = []          # (batch, table) des lots effectivement créés
        arret = False
        for i, lot in enumerate(lots, 1):
            batch, table, statut = self._creer_lot(
                anthropic, api_key, client_base, lot, i, len(lots),
                dossier_sortie, heure_debut, ids_connus, resultats)
            if batch is not None:
                envois.append((batch, table))
                ids_connus.add(batch.id)
            if statut == 'arret':
                arret = True
                break

        if envois and arret:
            # Arrêt pendant la création : on annule ce qui est parti, les pages repartent en repli.
            for batch, _ in envois:
                self._annuler(client_base, batch.id)
        elif envois:
            self._attendre_et_recuperer(client_base, envois, cache_actif, resultats)

        # Toute page sans réponse (arrêt, lot non envoyé, absente des résultats) : repli normal.
        for info in infos:
            resultats.setdefault(str(info['image']),
                                 self._repli(info['image'], "page non rendue par le lot"))
        return resultats

    def _ids_lots_dossier(self, dossier_sortie) -> set:
        """Ids des lot_*.json déjà présents (exécution passée) : jamais pris pour un doublon."""
        ids = set()
        try:
            for fichier in Path(dossier_sortie).glob('lot_*.json'):
                nom = fichier.stem                  # 'lot_<id>'
                if nom.startswith('lot_'):
                    ids.add(nom[4:])
        except Exception:
            pass
        return ids

    def _decouper(self, infos: List[dict]) -> List[List[dict]]:
        """Groupe les pages en lots sous CLAUDE_LOT_TAILLE_MAX_MO (limite serveur 256 Mo/lot)."""
        max_octets = getattr(Config, 'CLAUDE_LOT_TAILLE_MAX_MO', 50) * 1024 * 1024
        lots: List[List[dict]] = []
        courant: List[dict] = []
        taille = 0
        for info in infos:
            # Une page seule plus grosse que le plafond part quand même dans son propre lot.
            if courant and taille + info['taille'] > max_octets:
                lots.append(courant)
                courant, taille = [], 0
            courant.append(info)
            taille += info['taille']
        if courant:
            lots.append(courant)
        return lots

    def _creer_lot(self, anthropic_mod, api_key, client_base, infos, index, total,
                   dossier_sortie, heure_debut, ids_connus, resultats):
        """Crée un lot et écrit son lot_<id>.json. Rend (batch, table, statut).

        batch None avec statut 'arret' ou 'echec' : les pages du lot sont mises en repli.
        """
        requetes = [{'custom_id': info['cid'], 'params': info['requete']} for info in infos]
        table = {info['cid']: info for info in infos}
        octets = sum(info['taille'] for info in infos)
        self._on_log(
            f"  Lot {index}/{total} : {len(requetes)} page(s), {_format_taille(octets)} — envoi…",
            'info')

        batch, statut = self._creer(
            anthropic_mod, api_key, client_base, requetes, octets, heure_debut, ids_connus)
        if batch is None:
            for info in infos:
                resultats.setdefault(str(info['image']),
                                     self._repli(info['image'], "lot indisponible"))
            return None, table, statut          # 'arret' ou 'echec'

        _enregistrer_lot(dossier_sortie, batch.id, table, infos[0]['model'])
        self._on_log(f"  Lot {index}/{total} envoyé (id {batch.id})", 'info')
        return batch, table, 'ok'

    def _attendre_et_recuperer(self, client, envois, cache_actif, resultats) -> None:
        """Attend tous les lots dans une seule boucle de sondage, puis récupère chacun.

        Arrêt demandé : les lots encore en cours sont annulés, leurs pages repartent en repli.
        """
        etats = {b.id: getattr(b, 'processing_status', 'in_progress') for b, _ in envois}
        tables = {b.id: table for b, table in envois}
        while any(statut != 'ended' for statut in etats.values()):
            if self._doit_arreter():
                self._annuler_en_cours(client, etats)
                return
            lues = attente = a_reprendre = 0
            for bid, statut in list(etats.items()):
                if statut == 'ended':
                    continue
                maj = self._etat(client, bid)
                if maj is None:
                    etats[bid] = 'ended'            # état indisponible : on cesse d'attendre
                    continue
                etats[bid] = maj.processing_status
                rc = maj.request_counts
                lues += rc.succeeded
                attente += rc.processing
                a_reprendre += rc.errored + rc.expired + rc.canceled
            if all(statut == 'ended' for statut in etats.values()):
                break
            self._on_log(
                f"  Lots en cours : {lues} lue(s), {attente} en attente"
                + (f", {a_reprendre} à reprendre" if a_reprendre else ''), 'info')
            if self._dormir() == 'arret':
                self._annuler_en_cours(client, etats)
                return

        for bid, table in tables.items():
            self._recuperer(client, bid, table, cache_actif, resultats)

    def _annuler_en_cours(self, client, etats: Dict[str, str]) -> None:
        """Annule les lots pas encore terminés (arrêt utilisateur)."""
        for bid, statut in etats.items():
            if statut != 'ended':
                self._annuler(client, bid)

    def reprendre(self, lot_fichier) -> Dict[str, dict]:
        """Reprend un lot déjà envoyé depuis son lot_<id>.json (ou tous ceux d'un dossier).

        Un chemin de dossier reprend chaque lot_*.json qu'il contient (document découpé en
        plusieurs lots). Ne lève jamais.
        """
        chemin = Path(lot_fichier)
        if chemin.is_dir():
            resultats: Dict[str, dict] = {}
            for fichier in sorted(chemin.glob('lot_*.json')):
                resultats.update(self._reprendre_un(fichier))
            return resultats
        return self._reprendre_un(chemin)

    def _reprendre_un(self, lot_fichier) -> Dict[str, dict]:
        """Reprend un seul lot_<id>.json. Ne lève jamais.

        Lot terminé : récupère les résultats. Encore en cours : reprend l'attente. Expiré /
        annulé / introuvable : les pages manquantes sont rendues en `repli_normal` (converter
        les relit en appel normal) — même mécanisme qu'une page non lue d'un lot courant.
        """
        resultats: Dict[str, dict] = {}
        donnees = self._lire_fichier_lot(lot_fichier)
        if donnees is None:
            return resultats
        batch_id = donnees.get('id', '')
        pages = donnees.get('pages', {})
        if not batch_id or not pages:
            self._on_log("  Reprise : fichier de lot sans identifiant ni pages — ignoré", 'warn')
            return resultats

        api_key = getattr(Config, 'CLAUDE_API_KEY', '').strip()
        if not api_key:
            return {str(p): self._repli(p, "clé API absente") for p in pages.values()}
        try:
            import anthropic
        except ImportError:
            return {str(p): self._repli(p, "package anthropic absent") for p in pages.values()}

        cache_actif = (getattr(Config, 'CLAUDE_CACHE_LECTURES', False)
                       and not getattr(Config, 'CLAUDE_FORCER_RELECTURE', False))

        # La table (clé de cache, modèle, max_tokens) se reconstruit à l'identique depuis
        # l'image : _preparer est déterministe, le custom_id enregistré est conservé.
        table: Dict[str, dict] = {}
        for cid, image_brut in pages.items():
            image_path = Path(image_brut)
            try:
                prepa = self._preparer(image_path, cache_actif)
            except Exception as exc:
                resultats[str(image_path)] = self._repli(image_path, str(exc))
                continue
            table[cid] = dict(prepa, image=image_path)
        if not table:
            return resultats

        client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        etat = self._etat(client, batch_id)
        if etat is None:
            # Lot introuvable (expiré et purgé côté serveur, ou supprimé) : relecture normale.
            self._on_log(
                f"  Reprise : lot {batch_id} introuvable — pages relues en appel normal", 'warn')
            for info in table.values():
                resultats.setdefault(str(info['image']),
                                     self._repli(info['image'], "lot introuvable"))
            return resultats

        if getattr(etat, 'processing_status', 'ended') != 'ended':
            self._on_log(
                f"  Reprise : lot {batch_id} encore en cours — reprise de l'attente", 'info')
            statut = self._attendre(client, etat)
            if statut == 'arret':
                self._annuler(client, batch_id)
                for info in table.values():
                    resultats.setdefault(str(info['image']),
                                         self._repli(info['image'], "arrêt demandé"))
                return resultats
            if statut == 'indisponible':
                for info in table.values():
                    resultats.setdefault(str(info['image']),
                                         self._repli(info['image'], "lot indisponible"))
                return resultats
        else:
            self._on_log(
                f"  Reprise : lot {batch_id} terminé — récupération des résultats", 'info')

        # Terminé : pages réussies par le chemin de lecture unique, le reste (errored / expired /
        # canceled, ou absent des résultats) en repli pour relecture en appel normal.
        self._recuperer(client, batch_id, table, cache_actif, resultats)
        for info in table.values():
            resultats.setdefault(str(info['image']),
                                 self._repli(info['image'], "page non rendue par le lot"))
        return resultats

    def _lire_fichier_lot(self, lot_fichier) -> Optional[dict]:
        """Lit un fichier lot_<id>.json. None si absent ou illisible (jamais d'exception)."""
        try:
            return json.loads(Path(lot_fichier).read_text(encoding='utf-8'))
        except Exception as exc:
            self._on_log(f"  Reprise : fichier de lot illisible ({exc})", 'warn')
            return None

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

    def _creer(self, anthropic_mod, api_key, client_base, requetes, octets,
               heure_debut, ids_connus):
        """Crée un lot. Rend (batch, 'ok') ou (None, 'arret' | 'echec').

        Client dédié sans relance interne (max_retries=0) et délai proportionnel à la taille,
        pour que nos relances (CLAUDE_RETRY_DELAIS, qui respectent Arrêter via _dormir) ne
        s'ajoutent pas à celles du SDK. Après une erreur — l'envoi a pu aboutir malgré un délai
        dépassé — un lot récent du même nombre de requêtes, créé après le début de nos tentatives
        et encore inconnu, est repris plutôt que recréé (doublon facturé deux fois).
        """
        base = getattr(Config, 'CLAUDE_LOT_TIMEOUT_BASE_S', 60)
        par_mo = getattr(Config, 'CLAUDE_LOT_TIMEOUT_PAR_MO_S', 6)
        timeout = base + par_mo * (octets / (1024 * 1024))
        client = anthropic_mod.Anthropic(api_key=api_key, max_retries=0, timeout=timeout)
        delais = list(getattr(Config, 'CLAUDE_RETRY_DELAIS', ()))
        for tentative in range(len(delais) + 1):
            try:
                return client.messages.batches.create(requests=requetes), 'ok'
            except Exception as exc:
                doublon = self._chercher_doublon(
                    client_base, len(requetes), heure_debut, ids_connus)
                if doublon is not None:
                    self._on_log(
                        f"  Lot déjà créé côté serveur (id {doublon.id}) — repris, "
                        "pas de doublon", 'info')
                    return doublon, 'ok'
                if claude_ocr._erreur_reseau(exc) and tentative < len(delais):
                    self._on_log(
                        f"  Lot indisponible ({type(exc).__name__}) — nouvelle "
                        f"tentative dans {delais[tentative]} s", 'warn')
                    if self._dormir(delais[tentative]) == 'arret':
                        return None, 'arret'
                    continue
                logger.warning(f"Lot : création impossible ({exc})")
                return None, 'echec'

    def _chercher_doublon(self, client, nb_requetes: int, heure_debut, ids_connus):
        """Le lot que notre envoi a créé côté serveur malgré l'erreur — sinon None. Ne lève jamais.

        Un doublon est un lot du même nombre de requêtes, créé après le début de nos tentatives
        (marge d'une minute) et dont l'id est encore inconnu : ni un lot déjà créé cette exécution,
        ni un lot_*.json d'une exécution passée. Ces trois conditions évitent de reprendre par
        erreur un AUTRE lot du même document (même nombre de pages).
        """
        fenetre = getattr(Config, 'CLAUDE_LOT_FENETRE_DOUBLON_MIN', 10)
        maintenant = datetime.datetime.now(datetime.timezone.utc)
        seuil = heure_debut - datetime.timedelta(minutes=1)
        try:
            page = client.messages.batches.list(limit=20)
            lots = getattr(page, 'data', page)   # première page seule, pas tout l'historique
            for batch in lots:
                bid = getattr(batch, 'id', None)
                if not bid or bid in ids_connus:
                    continue
                cree = self._quand(getattr(batch, 'created_at', None))
                if cree is None or cree < seuil:
                    continue
                if (maintenant - cree) > datetime.timedelta(minutes=fenetre):
                    continue
                if self._nb_requetes(batch) == nb_requetes:
                    return batch
        except Exception as exc:
            logger.warning(f"Lot : recherche de doublon impossible ({exc})")
        return None

    @staticmethod
    def _nb_requetes(batch) -> int:
        """Nombre de requêtes d'un lot d'après ses compteurs (-1 si absents : jamais doublon)."""
        rc = getattr(batch, 'request_counts', None)
        if rc is None:
            return -1
        return (getattr(rc, 'processing', 0) + getattr(rc, 'succeeded', 0)
                + getattr(rc, 'errored', 0) + getattr(rc, 'canceled', 0)
                + getattr(rc, 'expired', 0))

    @staticmethod
    def _quand(cree):
        """Normalise created_at (datetime ou ISO) en datetime aware UTC, ou None."""
        if cree is None:
            return None
        if isinstance(cree, str):
            try:
                cree = datetime.datetime.fromisoformat(cree.replace('Z', '+00:00'))
            except ValueError:
                return None
        if cree.tzinfo is None:
            cree = cree.replace(tzinfo=datetime.timezone.utc)
        return cree

    @staticmethod
    def _recent(cree, maintenant, fenetre_min: int) -> bool:
        """Vrai si `cree` (datetime ou ISO) tombe dans les `fenetre_min` dernières minutes."""
        quand = LecteurLot._quand(cree)
        if quand is None:
            return False
        return (maintenant - quand) <= datetime.timedelta(minutes=fenetre_min)

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

    def _dormir(self, secondes=None) -> str:
        """Attend (intervalle d'interrogation ou `secondes`) en coupant tôt sur un arrêt."""
        reste = self._poll if secondes is None else secondes
        while reste > 0:
            if self._doit_arreter():
                return 'arret'
            time.sleep(min(1, reste))
            reste -= 1
        return 'ok'

    def _etat(self, client, batch_id):
        """Lit l'état du lot ; retries sur coupure réseau, None si indisponible ou arrêt."""
        delais = list(getattr(Config, 'CLAUDE_RETRY_DELAIS', ()))
        for tentative in range(len(delais) + 1):
            try:
                return client.messages.batches.retrieve(batch_id)
            except Exception as exc:
                if claude_ocr._erreur_reseau(exc) and tentative < len(delais):
                    if self._dormir(delais[tentative]) == 'arret':
                        return None
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
