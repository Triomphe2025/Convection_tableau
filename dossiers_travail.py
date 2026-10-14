"""
Dossiers des images de travail d'une conversion (pages rendues, prétraitées, relues).

Ce sont des images de documents clients : elles vont dans TRAVAIL_DOSSIER (dossier de
l'application), jamais à côté du document source ni dans le dossier de sortie choisi par
l'utilisateur. Un dossier par document (nom + empreinte de son chemin : deux PDF de même
nom dans deux dossiers ne se mélangent pas). À chaque ouverture, les dossiers des autres
documents sont purgés : trop vieux d'abord, puis les plus anciens au-delà de la taille.
Module pur (config + bibliothèque standard).
"""
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from config import Config


def _dossier_document(document: Path) -> Path:
    chemin = str(Path(document).resolve()).lower()
    empreinte = hashlib.sha256(chemin.encode('utf-8')).hexdigest()[:10]
    return Path(Config.TRAVAIL_DOSSIER) / f"{Path(document).stem[:60]}_{empreinte}"


def dossier_travail(document: Path, sorte: str = '') -> Path:
    """Dossier de travail (créé) de ce document pour cette sorte d'images ; purge les autres."""
    racine = _dossier_document(document)
    dossier = racine / sorte if sorte else racine
    dossier.mkdir(parents=True, exist_ok=True)
    # La date du dossier du document dit son dernier usage : la purge garde les récents.
    os.utime(racine)
    purger(Config.TRAVAIL_AGE_MAX_JOURS, Config.TRAVAIL_TAILLE_MAX_MO * 1024 * 1024,
           garder=racine)
    return dossier


def _taille(dossier: Path) -> int:
    return sum(f.stat().st_size for f in dossier.rglob('*') if f.is_file())


def purger(age_max_jours: float, taille_max_octets: int,
           garder: Optional[Path] = None) -> int:
    """Supprime les dossiers de documents trop vieux, puis les plus anciens au-delà de la taille."""
    racine = Path(Config.TRAVAIL_DOSSIER)
    if not racine.is_dir():
        return 0
    dossiers = sorted(((d.stat().st_mtime, _taille(d), d) for d in racine.iterdir()
                       if d.is_dir() and d != garder), key=lambda t: t[0])
    total = sum(t for _, t, _ in dossiers) + (_taille(garder) if garder and garder.is_dir()
                                              else 0)
    limite = time.time() - age_max_jours * 86400
    supprimes = 0
    for date, taille, dossier in dossiers:
        if date >= limite and total <= taille_max_octets:
            continue
        shutil.rmtree(dossier, ignore_errors=True)
        total -= taille
        supprimes += 1
    return supprimes
