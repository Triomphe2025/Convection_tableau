"""
Licence de l'exe livré : clé signée (Ed25519) liée au poste et datée, vérifiée au démarrage.

L'exe ne contient que la clé publique (CLE_PUBLIQUE). La clé privée qui signe les licences
reste sur le poste de Triomphe (hors git, hors exe). Le fichier de licence (Config.LICENCE_NOM)
est posé à côté de l'exe ; le renouvellement consiste à en poser un nouveau, sans reconstruire.

Règles (mêmes que l'essai PyArmor) : refus sans clé (avec l'identifiant du poste à transmettre),
clé d'un autre poste refusée, préavis avant l'échéance, message clair à l'expiration, garde
contre le recul de l'horloge. En développement (hors exe), aucun contrôle : le logiciel tourne
normalement. Module pur (ed25519_verif, config, bibliothèque standard).
"""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from config import Config
from ed25519_verif import verifier

CLE_PUBLIQUE = 'fd86aec58b4f176e0ad2816416616a254d5a138c8d3c4ee57e641fbaef650e57'
_MARQUEUR = '--- signature ---'


class LicenceError(RuntimeError):
    """Licence absente, invalide, pour un autre poste, expirée, ou horloge reculée."""


def identifiant_poste() -> str:
    """Identifiant stable du poste (indépendant du réseau), à transmettre pour obtenir la clé."""
    graine = ''
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r'SOFTWARE\Microsoft\Cryptography') as k:
                graine = winreg.QueryValueEx(k, 'MachineGuid')[0]
        except OSError:
            graine = ''
    if not graine:
        import platform
        graine = platform.node()
    empreinte = hashlib.sha256(('TriosSeconverter:' + graine).encode('utf-8')).hexdigest()
    return '-'.join(empreinte[i:i + 4].upper() for i in range(0, 16, 4))


def _dossier_exe() -> Path:
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()


def analyser_licence(texte: str):
    """(infos, entete_bytes, signature) d'un contenu de licence, ou None si la forme est fausse."""
    if _MARQUEUR not in texte:
        return None
    entete, _, signature = texte.partition(_MARQUEUR)
    infos = {}
    for ligne in entete.splitlines():
        if ':' in ligne:
            cle, _, valeur = ligne.partition(':')
            infos[cle.strip().lower()] = valeur.strip()
    try:
        sig = bytes.fromhex(signature.strip())
    except ValueError:
        return None
    return infos, entete.encode('utf-8'), sig


def licence_valide(texte: str, aujourd_hui=None):
    """(ok, infos, raison) : vérifie signature, poste et échéance d'un contenu de licence."""
    aujourd_hui = aujourd_hui or dt.date.today()
    analyse = analyser_licence(texte)
    if analyse is None:
        return False, {}, 'forme'
    infos, entete, sig = analyse
    if not verifier(entete, sig, bytes.fromhex(CLE_PUBLIQUE)):
        return False, infos, 'signature'
    if infos.get('poste') != identifiant_poste():
        return False, infos, 'poste'
    try:
        echeance = dt.date.fromisoformat(infos['echeance'])
    except (KeyError, ValueError):
        return False, infos, 'forme'
    if aujourd_hui > echeance:
        return False, infos, 'expiree'
    return True, infos, 'ok'


def _fichier_garde() -> Path:
    return Path(Config.DOSSIER_UTILISATEUR) / 'licence_horloge.json'


def controler_horloge(aujourd_hui=None) -> None:
    """Refuse si l'horloge a reculé de plus de LICENCE_RECUL_MAX_JOURS sous la date déjà vue."""
    aujourd_hui = aujourd_hui or dt.date.today()
    fichier = _fichier_garde()
    try:
        vu = dt.date.fromisoformat(json.loads(fichier.read_text('utf-8'))['plus_recent'])
    except (OSError, ValueError, KeyError):
        vu = aujourd_hui
    if (vu - aujourd_hui).days > Config.LICENCE_RECUL_MAX_JOURS:
        raise LicenceError(
            f"L'horloge de ce poste indique le {aujourd_hui:%d/%m/%Y}, avant le "
            f"{vu:%d/%m/%Y} déjà vu. Remettez la date du jour. {_contact()}")
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps({'plus_recent': max(vu, aujourd_hui).isoformat()}), 'utf-8')
    except OSError:
        pass


def _contact() -> str:
    contact = getattr(Config, 'LICENCE_CONTACT', '').strip()
    return f"Contact : {contact}" if contact else "Contactez votre correspondant TriosSeconverter."


def message_preavis(infos: dict, aujourd_hui=None) -> str:
    """Avertissement si l'échéance est dans moins de LICENCE_PREAVIS_JOURS jours, sinon ''."""
    try:
        echeance = dt.date.fromisoformat(infos['echeance'])
    except (KeyError, ValueError):
        return ''
    reste = (echeance - (aujourd_hui or dt.date.today())).days
    if reste > Config.LICENCE_PREAVIS_JOURS:
        return ''
    return (f"Votre licence expire le {echeance:%d/%m/%Y} (dans {reste} jour(s)). "
            f"Pour la renouveler : {_contact()}")


def exiger(aujourd_hui=None) -> str:
    """Contrôle la licence au démarrage de l'exe. Rend le message de préavis (souvent '').

    Hors exe (développement), ne contrôle rien et rend ''. En cas de problème, lève
    LicenceError avec un message clair à montrer à l'utilisateur.
    """
    if not getattr(sys, 'frozen', False):
        return ''
    controler_horloge(aujourd_hui)
    fichier = _dossier_exe() / Config.LICENCE_NOM
    try:
        texte = fichier.read_text('utf-8')
    except OSError:
        raise LicenceError(
            "Aucune licence trouvée. Transmettez cet identifiant de poste pour obtenir "
            f"votre clé :\n\n    {identifiant_poste()}\n\n{_contact()}")
    ok, infos, raison = licence_valide(texte, aujourd_hui)
    if ok:
        return message_preavis(infos, aujourd_hui)
    if raison == 'poste':
        raise LicenceError(
            "Cette licence n'est pas celle de ce poste. Transmettez cet identifiant pour "
            f"obtenir la bonne clé :\n\n    {identifiant_poste()}\n\n{_contact()}")
    if raison == 'expiree':
        echeance = infos.get('echeance', '?')
        raise LicenceError(f"Votre licence a expiré le {echeance}. "
                           f"Pour la renouveler : {_contact()}")
    raise LicenceError("Fichier de licence illisible ou altéré. "
                       f"Demandez une nouvelle clé. {_contact()}")
