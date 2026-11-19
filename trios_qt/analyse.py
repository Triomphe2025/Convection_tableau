"""Analyse d'un fichier déposé : type détecté + estimation, hors du fil de l'interface."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import estimation
import types_documents

# États d'une ligne après l'analyse (la prise en compte du dossier de sortie vient au bas de page).
ANALYSE = "analyse"
INCONNU = "inconnu"
A_PRECISER = "a_preciser"
PRET = "pret"
ERREUR = "erreur"


@dataclass
class ResultatAnalyse:
    """Résultat de l'analyse d'un fichier : état, type proposé, preuves, estimation."""
    etat: str = ANALYSE
    type: Optional[object] = None
    confiance: float = 0.0
    preuves: list = field(default_factory=list)
    estimation: Optional[dict] = None
    erreur: Optional[str] = None


def analyser(chemin, dossier_sortie=None, lot=False, profil=None,
             detecter=None, estimer=None, preciser=None):
    """Détecte le type puis estime le coût ; fonctions injectables pour les tests."""
    detecter = detecter or types_documents.detecter_type
    estimer = estimer or estimation.estimer
    preciser = preciser or types_documents.a_preciser
    chemin = Path(chemin)
    try:
        type_, confiance, preuves = detecter(chemin)
        if type_ is None:
            return ResultatAnalyse(INCONNU, None, confiance, list(preuves))
        incertain = preciser(confiance, preuves)
        modele = getattr(type_, 'modele', '') or None
        devis = estimer(chemin, type=type_, profil=profil, lot=lot,
                        modele=modele, dossier_sortie=dossier_sortie)
        etat = A_PRECISER if incertain else PRET
        return ResultatAnalyse(etat, type_, confiance, list(preuves), devis)
    except Exception as erreur:  # une analyse ratée ne bloque jamais les autres fichiers
        return ResultatAnalyse(ERREUR, erreur=str(erreur))
