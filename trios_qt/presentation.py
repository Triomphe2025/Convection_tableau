"""Présentation d'une ligne (pur, sans Qt) : sigle, libellé de type, estimation, couleur d'état."""
from trios_qt import analyse

_SIGLES = {
    "tableau": "TAB",
    "plan": "PLN",
    "excel": "XLS",
    "journal": "JRN",
    "mixte": "MIX",
}

# État → nom du jeton de couleur (orange « à préciser », vert « prêt », rouge « erreur »).
_COULEUR_PAR_ETAT = {
    analyse.ANALYSE: "texte_discret",
    analyse.INCONNU: "a_relire",
    analyse.A_PRECISER: "a_relire",
    analyse.PRET: "succes",
    analyse.ERREUR: "erreur",
}


def sigle_famille(famille):
    return _SIGLES.get(famille, "?")


def texte_type(resultat):
    """Libellé du type pour la ligne, selon l'état de l'analyse."""
    if resultat.etat == analyse.ANALYSE:
        return "analyse…"
    if resultat.etat == analyse.ERREUR:
        return "erreur"
    if resultat.etat == analyse.INCONNU:
        return "à préciser"
    nom = getattr(resultat.type, 'nom', '') or "à préciser"
    if resultat.etat == analyse.A_PRECISER:
        return f"{nom} ? (à préciser)"
    return nom


def texte_estimation(resultat):
    """« ~ coût · durée » ; « au plus » si le cache est inconnu ; durée seule si coût nul."""
    devis = resultat.estimation
    if not devis:
        return ""
    duree = (devis.get('duree') or {}).get('texte', "")
    cout = devis.get('cout_usd', 0.0)
    if cout <= 0:
        return duree
    montant = f"{cout:.2f}".replace('.', ',')
    prefixe = "au plus ~" if not devis.get('cache_connu', False) else "~"
    morceau_cout = f"{prefixe} {montant} $"
    return f"{morceau_cout} · {duree}" if duree else morceau_cout


def couleur_etat(etat, jetons):
    """Couleur (hex) de l'état, tirée des jetons du thème."""
    nom = _COULEUR_PAR_ETAT.get(etat, "texte_secondaire")
    return jetons['couleurs'][nom]
