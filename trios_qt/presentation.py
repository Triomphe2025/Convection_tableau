"""Présentation d'une ligne (pur, sans Qt) : sigle, libellé de type, estimation, couleur d'état."""
from dataclasses import dataclass
from typing import Optional

from trios_qt import analyse


@dataclass(frozen=True)
class Profil:
    """Un profil de lecture proposé dans la ligne dépliée (tableau)."""
    cle: str
    titre: str
    moteur: str
    profil: str
    modele: Optional[str]


# Les trois profils d'un tableau (Rapide local, Précis/Difficile via Claude).
PROFILS_TABLEAU = (
    Profil("rapide", "Rapide", "Tesseract · sur ce PC", "tesseract", None),
    Profil("precis", "Précis", "Claude Sonnet 5.5", "claude", "claude-sonnet-5-5"),
    Profil("difficile", "Difficile", "Claude Opus 5.5", "claude", "claude-opus-5-5"),
)

# Finesses d'un plan (sans coût API, réglage de rendu).
FINESSES_PLAN = ("Rapide", "Standard", "Précis")

_SIGLES = {
    "tableau": "TAB",
    "plan": "DXF",
    "excel": "XLS",
    "journal": "JRN",
    "mixte": "MIX",
}

_NOMS_FAMILLE = {
    "tableau": "Tableau",
    "plan": "Plan",
    "excel": "Excel",
    "journal": "Journal",
    "mixte": "Mixte",
}

# Famille → nom du jeton de couleur du carré (atténué en QSS).
_COULEUR_FAMILLE = {
    "tableau": "rose_trios",
    "plan": "texte_natif",
    "excel": "succes",
    "journal": "texte_discret",
    "mixte": "page_scannee",
}

_LIBELLES_GROUPE = {
    "tableau": "Tableaux → Excel",
    "plan": "Plans → DXF",
    "mixte": "Mixtes → Excel + DXF",
    "excel": "Classeurs Excel",
    "journal": "Journal .jsonl",
}

_ORDRE_GROUPES = ("tableau", "plan", "mixte", "excel", "journal")

# Descriptions des groupes à type unique ; les tableaux listent plutôt leurs modèles.
_DESCRIPTIONS_GROUPE = {
    "plan": "Plans scannés en PDF ou TIFF",
    "mixte": "Chaque page classée : tableau, plan ou légende",
    "excel": "Mise en forme des classeurs produits par l'appli",
    "journal": "Rejouer une conversion sans appel à Claude",
}

_NOMS_SORTIE = {"excel": "Excel", "dxf": "DXF"}

# Libellé du type pour les familles à type unique (évite « Excel › Excel »).
_LIBELLE_TYPE_FAMILLE = {
    "excel": "Mise en forme",
    "journal": "Rejeu sans appel",
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


def nom_famille(famille):
    return _NOMS_FAMILLE.get(famille, "Inconnu")


def couleur_famille(famille, jetons):
    """Couleur (hex) du carré de famille, tirée des jetons ; orange si inconnue."""
    nom = _COULEUR_FAMILLE.get(famille, "a_relire")
    return jetons['couleurs'][nom]


def texte_pages(resultat):
    """« N pages · n scannées · n en texte natif » depuis l'estimation (parties nulles omises)."""
    devis = resultat.estimation
    if not devis:
        return ""
    pages = devis.get('pages') or {}
    total = pages.get('total', 0)
    parts = [f"{total} page{'s' if total > 1 else ''}"]
    scan = pages.get('scan', 0)
    if scan:
        parts.append(f"{scan} scannée{'s' if scan > 1 else ''}")
    natif = pages.get('vectoriel', 0)
    if natif:
        parts.append(f"{natif} en texte natif")
    return " · ".join(parts)


def texte_sortie(resultat):
    """« → Excel » / « → DXF » depuis les sorties du type ; vide sans type."""
    sorties = getattr(resultat.type, 'sorties', ()) or ()
    noms = [_NOMS_SORTIE.get(s, s.upper()) for s in sorties]
    return "→ " + " + ".join(noms) if noms else ""


def preuve_courte(resultat):
    """Preuve la plus parlante pour la sous-ligne ; « aucun type ne correspond » si inconnu."""
    if resultat.etat == analyse.INCONNU:
        return "aucun type ne correspond"
    return resultat.preuves[-1] if resultat.preuves else ""


def groupes_types(registre):
    """[(famille, [noms triés])] dans l'ordre d'affichage, familles présentes seulement."""
    par_famille = {}
    for type_ in registre.values():
        par_famille.setdefault(type_.famille, []).append(type_.nom)
    groupes = []
    for famille in _ORDRE_GROUPES:
        if famille in par_famille:
            groupes.append((famille, sorted(par_famille[famille])))
    return groupes


def libelle_groupe(famille):
    return _LIBELLES_GROUPE.get(famille, nom_famille(famille))


def description_groupe(famille, noms):
    """Sous-titre d'un groupe : liste des modèles pour les tableaux, phrase fixe sinon."""
    if famille == "tableau":
        return " · ".join(noms)
    return _DESCRIPTIONS_GROUPE.get(famille, " · ".join(noms))


def _libelle_plan(resultat):
    """« Plan vectoriel » si la couche texte domine, « Plan scanné » sinon."""
    pages = (resultat.estimation or {}).get('pages') or {}
    if pages.get('vectoriel', 0) > pages.get('scan', 0):
        return "Plan vectoriel"
    return "Plan scanné"


def texte_type(resultat):
    """Libellé du type pour la ligne, selon l'état de l'analyse (sans redondance de famille)."""
    if resultat.etat == analyse.ANALYSE:
        return "analyse…"
    if resultat.etat == analyse.ERREUR:
        return "erreur"
    if resultat.etat == analyse.INCONNU:
        return "à préciser"
    famille = getattr(resultat.type, 'famille', None)
    if famille == "plan":
        return _libelle_plan(resultat)
    base = _LIBELLE_TYPE_FAMILLE.get(famille) or getattr(resultat.type, 'nom', '') or "à préciser"
    if resultat.etat == analyse.A_PRECISER:
        return f"{base} ? (à préciser)"
    return base


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


def lot_propose(resultat):
    """Mode lot proposé d'office au-delà de 100 pages payantes (scan + couche OCR)."""
    devis = resultat.estimation or {}
    return devis.get('pages_payantes', 0) > 100


def lot_effectif(profil, lot):
    """Le lot (Message Batches) ne concerne que les profils Claude, jamais Tesseract."""
    return bool(lot) and profil.modele is not None


def texte_resume(total, prets, a_preciser, jetons):
    """Résumé du bas de page, compteurs colorés (prêts en succès, à préciser en orange)."""
    c = jetons['couleurs']
    morceaux = [f"{total} fichier{'s' if total > 1 else ''}",
                f"<span style='color:{c['succes']}'>{prets} prêts</span>"]
    if a_preciser:
        morceaux.append(
            f"<span style='color:{c['a_relire']}'>{a_preciser} à préciser</span>")
    return " · ".join(morceaux)


def _montant(cout):
    """« 0,18 » : deux décimales, virgule française."""
    return f"{cout:.2f}".replace('.', ',')


def texte_cout_total(entrees, jetons):
    """Coût Claude cumulé des fichiers prêts + part en différé ; « ~ » / « au plus » comme
    les lignes. Vide s'il n'y a aucun coût API (fichiers Tesseract, plans, Excel seuls).

    Chaque entrée : {'cout_usd', 'cache_connu', 'differe'}."""
    c = jetons['couleurs']
    total = sum(e.get('cout_usd', 0.0) for e in entrees)
    if total <= 0:
        return ""
    differe = sum(e.get('cout_usd', 0.0) for e in entrees if e.get('differe'))
    incertain = any(not e.get('cache_connu', True)
                    for e in entrees if e.get('cout_usd', 0.0) > 0)
    prefixe = "au plus ~" if incertain else "~"
    texte = (f"<span style='color:{c['texte_secondaire']}'>"
             f"{prefixe} {_montant(total)} $ Claude</span>")
    if differe > 0:
        texte += (f" · <span style='color:{c['texte_discret']}'>"
                  f"dont {_montant(differe)} $ en différé</span>")
    return texte


def couleur_etat(etat, jetons):
    """Couleur (hex) de l'état, tirée des jetons du thème."""
    nom = _COULEUR_PAR_ETAT.get(etat, "texte_secondaire")
    return jetons['couleurs'][nom]
