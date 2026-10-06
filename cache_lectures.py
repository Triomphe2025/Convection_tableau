"""
Cache des lectures Tesseract des pages scannées (positions d'origine, double lecture,
contrôle de conservation) : une lecture par fichier JSON dans POSITIONS_CACHE_DOSSIER.

Clé = empreinte du contenu du PDF (pas son nom ni son dossier) + page + réglages de
lecture (DPI, psm) : un même PDF déplacé ou renommé est retrouvé, un réglage changé
force une nouvelle lecture. Module pur (config + bibliothèque standard).
"""
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Optional

from config import Config


def empreinte_fichier(chemin: Path) -> str:
    """Empreinte SHA-256 du contenu du fichier."""
    h = hashlib.sha256()
    with open(chemin, 'rb') as f:
        for bloc in iter(lambda: f.read(1 << 20), b''):
            h.update(bloc)
    return h.hexdigest()


def _chemin(empreinte: str, page: int) -> Path:
    reglages = f"{Config.POSITIONS_DPI}-{Config.POSITIONS_PSM}"
    cle = hashlib.sha256(f"{empreinte}:{page}:{reglages}".encode('utf-8')).hexdigest()[:32]
    return Path(Config.POSITIONS_CACHE_DOSSIER) / f"{cle}.json"


def lire(empreinte: str, page: int) -> Optional[Dict]:
    """Lecture gardée pour cette page de ce PDF, ou None (absente ou illisible)."""
    chemin = _chemin(empreinte, page)
    try:
        return json.loads(chemin.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def ecrire(empreinte: str, page: int, lecture: Dict) -> None:
    """Garde la lecture de la page, puis purge le dossier (âge, taille)."""
    chemin = _chemin(empreinte, page)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(lecture), encoding='utf-8')
    purger(Config.POSITIONS_CACHE_AGE_MAX_JOURS,
           Config.POSITIONS_CACHE_TAILLE_MAX_MO * 1024 * 1024)


def purger(age_max_jours: float, taille_max_octets: int) -> int:
    """Supprime les lectures trop vieilles, puis les plus anciennes au-delà de la taille."""
    dossier = Path(Config.POSITIONS_CACHE_DOSSIER)
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
