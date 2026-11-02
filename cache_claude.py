"""
Cache des lectures Claude Vision reussies : un fichier JSON par cle dans CLAUDE_CACHE_DOSSIER
(dossier de l'utilisateur, jamais a cote de ses documents). Permet de relancer un document
(test d'un correctif, reprise apres coupure) sans relire ni repayer les pages deja lues.

Cle = SHA-256 de tout ce qui determine la reponse : les octets de l'image reellement envoyee
(base64 apres preparation), le prompt complet, le modele, ses parametres et max_tokens. Une
difference quelconque (modele, effort, prompt, image) donne une autre cle, donc un nouvel appel.

Ne garde QUE des reponses reussies et completes (y compris « non-listing ») : jamais une erreur,
un refus, une reponse coupee, ni la cle API. Ecriture atomique (fichier temporaire puis
renommage) pour qu'une coupure ne laisse jamais un JSON a moitie ecrit. Module pur (config +
bibliotheque standard).
"""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

from config import Config


def cle(image_data: str, media_type: str, prompt: str, model: str,
        parametres: dict, max_tokens: int) -> str:
    """Empreinte SHA-256 de la demande exacte envoyee a Claude."""
    h = hashlib.sha256()
    h.update(image_data.encode('utf-8'))
    for part in (media_type, prompt, model,
                 json.dumps(parametres, sort_keys=True, ensure_ascii=False),
                 str(max_tokens)):
        h.update(b'\x00')
        h.update(part.encode('utf-8'))
    return h.hexdigest()


def _chemin(cle_hex: str) -> Path:
    return Path(Config.CLAUDE_CACHE_DOSSIER) / f"{cle_hex}.json"


def existe(cle_hex: str) -> bool:
    """Vrai si une lecture lisible est deja gardee pour cette cle."""
    return lire(cle_hex) is not None


def lire(cle_hex: str) -> Optional[Dict]:
    """Lecture gardee pour cette cle, ou None (absente ou JSON illisible — la page sera relue)."""
    try:
        entree = json.loads(_chemin(cle_hex).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(entree, dict) or 'raw' not in entree:
        return None
    return entree


def ecrire(cle_hex: str, entree: Dict) -> None:
    """Garde la lecture de maniere atomique (temporaire puis renommage), puis purge le dossier.

    Jamais d'erreur bloquante : un probleme d'ecriture laisse simplement la page hors cache.
    """
    chemin = _chemin(cle_hex)
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(chemin.parent), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(entree, f, ensure_ascii=False)
            os.replace(tmp, chemin)   # atomique sur le meme volume
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except OSError:
        return
    purger(Config.CLAUDE_CACHE_AGE_MAX_JOURS,
           Config.CLAUDE_CACHE_TAILLE_MAX_MO * 1024 * 1024)


def purger(age_max_jours: float, taille_max_octets: int) -> int:
    """Supprime les lectures trop vieilles, puis les plus anciennes au-dela de la taille."""
    dossier = Path(Config.CLAUDE_CACHE_DOSSIER)
    if not dossier.is_dir():
        return 0
    fichiers = sorted(((f.stat().st_mtime, f.stat().st_size, f) for f in dossier.glob('*.json')),
                      key=lambda t: t[0])
    limite = time.time() - age_max_jours * 86400
    supprimes = 0
    gardes = []
    for date, taille, f in fichiers:
        if date < limite:
            f.unlink(missing_ok=True)
            supprimes += 1
        else:
            gardes.append((taille, f))
    total = sum(taille for taille, _ in gardes)
    for taille, f in gardes:
        if total <= taille_max_octets:
            break
        f.unlink(missing_ok=True)
        total -= taille
        supprimes += 1
    return supprimes
