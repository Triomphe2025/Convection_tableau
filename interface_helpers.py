"""Fonctions pures de présentation pour interface.py (aucun import tkinter) — testables seules.

interface.py se contente d'appeler ces fonctions ; la logique testable vit ici (règle 01 :
« pas de logique métier dans interface.py »). Ces fonctions ne touchent ni au disque, ni à la
conversion, ni à aucune ressource : elles transforment des valeurs en valeurs.
"""

import re

# Identifiant technique du modèle Claude → nom lisible affiché à l'utilisateur.
_NOMS_MODELES = {
    "claude-sonnet-5-5": "Sonnet 5.5 — recommandé",
    "claude-opus-5-5": "Opus 5.5 — documents difficiles",
    "claude-haiku-5-5": "Haiku 5.5 — le moins cher",
    "claude-sonnet-5": "Sonnet 5",
    "claude-opus-5": "Opus 5",
    "claude-haiku-4-5-20251001": "Haiku 4.5 — rapide",
    "claude-fable-5-1": "Fable 5.1 — le plus capable",
}

# Moteurs OCR du parcours : socle toujours visible, expérimentaux réservés au mode Dev.
_MOTEURS_SOCLE = ("tesseract", "claude")
_MOTEURS_EXPERIMENTAUX = ("docling", "ollama", "hybrid", "agent")

# Pages réservées au mode Dev (quittées vers l'Accueil quand Dev est décoché).
_PAGES_DEV = ("params", "ocr", "options")

# Seul le message on_progress « Page n/total [moteur] … » compte : crochet obligatoire, ce qui
# écarte la ligne de _log « Page 12/720 : scannée … » (deux-points, pas de crochet).
_PAGE_PROGRES = re.compile(r"^Page (\d+)/(\d+) \[")


def nom_modele_lisible(identifiant):
    """Nom lisible d'un modèle Claude ; identifiant inconnu rendu tel quel."""
    if not identifiant:
        return ""
    cle = identifiant.strip()
    return _NOMS_MODELES.get(cle, cle)


def moteurs_visibles(dev_actif, moteur_choisi=None):
    """Moteurs OCR affichés : socle (+ expérimentaux si Dev) ; le moteur choisi reste visible.

    Hors Dev, un moteur expérimental déjà sélectionné (ex. « hybrid ») reste à l'écran : il ne
    doit pas disparaître en restant pourtant actif.
    """
    if dev_actif:
        return _MOTEURS_SOCLE + _MOTEURS_EXPERIMENTAUX
    visibles = list(_MOTEURS_SOCLE)
    if moteur_choisi in _MOTEURS_EXPERIMENTAUX and moteur_choisi not in visibles:
        visibles.append(moteur_choisi)
    return tuple(visibles)


def page_apres_bascule_dev(page_affichee, dev_actif):
    """Page à afficher après (dé)cochage de Dev : retour à l'Accueil si on quitte une page Dev."""
    if not dev_actif and page_affichee in _PAGES_DEV:
        return "accueil"
    return page_affichee


def etat_lancement(source, destination):
    """(actif, message) du bouton de lancement : source puis destination obligatoires."""
    if not (source and str(source).strip()):
        return (False, "Choisissez d'abord un fichier source.")
    if not (destination and str(destination).strip()):
        return (False, "Choisissez un dossier de destination.")
    return (True, "")


def numero_page_validation(meta_page, page_done):
    """Numéro affiché à la validation : le PAGE lu s'il existe, sinon le rang traité."""
    meta = (meta_page or "").strip()
    if meta:
        return meta
    return str(page_done)


def dpi_a_activer(plateforme, reglage):
    """Vrai seulement si le réglage est actif ET la plateforme est Windows."""
    return bool(reglage) and str(plateforme).startswith("win")


def analyser_progres_page(message):
    """(done, total) d'un message on_progress « Page n/total [moteur] … » ; None sinon."""
    if not message:
        return None
    correspondance = _PAGE_PROGRES.match(message.strip())
    if not correspondance:
        return None
    done, total = int(correspondance.group(1)), int(correspondance.group(2))
    if total <= 0 or done < 0:
        return None
    return (done, total)


def estimer_temps_restant(ecoule_depuis_1re_page_s, done, total, mode_lot=False):
    """Secondes restantes mesurées depuis la 1re page ; None si done = 0 ou en mode lot.

    En mode lot, les pages reviennent toutes d'un coup après l'attente : une estimation serait
    absurde (des heures), donc jamais d'estimation. L'horloge part de la 1re page, pas du
    lancement : le temps d'analyse ne gonfle pas le temps par page (le jalon vient de
    `jalon_premiere_page`).
    """
    if mode_lot:
        return None
    if done <= 0 or total <= 0 or done > total:
        return None
    if done == total:
        return 0.0
    return ecoule_depuis_1re_page_s / done * (total - done)


def jalon_premiere_page(evenements):
    """Horodatage du 1er message « Page n/total » réel (l'analyse ne compte pas) ; None sinon.

    `evenements` : suite de (horodatage, message). Les lignes d'analyse, pour lesquelles
    `analyser_progres_page` rend None, ne déclenchent pas le jalon — le temps d'analyse est
    exclu de l'estimation.
    """
    for horodatage, message in evenements:
        if analyser_progres_page(message) is not None:
            return horodatage
    return None


def format_duree(secondes):
    """Durée « m:ss » ; None rend « — »."""
    if secondes is None:
        return "—"
    s = max(0, int(round(secondes)))
    return f"{s // 60}:{s % 60:02d}"


def ratio_contraste(couleur1, couleur2):
    """Rapport de contraste WCAG entre deux couleurs « #rrggbb » (≥ 1.0)."""
    l1, l2 = _luminance(couleur1), _luminance(couleur2)
    clair, sombre = max(l1, l2), min(l1, l2)
    return (clair + 0.05) / (sombre + 0.05)


def _luminance(couleur):
    """Luminance relative WCAG (0.0–1.0) d'une couleur « #rrggbb »."""
    canaux = []
    for composante in _composantes(couleur):
        x = composante / 255.0
        canaux.append(x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canaux[0] + 0.7152 * canaux[1] + 0.0722 * canaux[2]


def _composantes(couleur):
    """(r, g, b) d'une couleur « #rrggbb » ; ValueError si la forme n'est pas 6 chiffres hexa."""
    hexa = str(couleur).lstrip("#")
    if len(hexa) != 6:
        raise ValueError(f"couleur hexadécimale invalide : {couleur!r}")
    return int(hexa[0:2], 16), int(hexa[2:4], 16), int(hexa[4:6], 16)
