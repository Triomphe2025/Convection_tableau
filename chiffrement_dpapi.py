"""Protection des secrets au repos via DPAPI (CryptProtectData, compte Windows courant).

La clé API ne doit jamais être écrite en clair dans les réglages. DPAPI chiffre le texte avec une
clé liée au compte Windows de l'utilisateur : seul ce compte, sur ce poste, peut la déchiffrer.
Aucune dépendance (ctypes sur crypt32). Hors Windows ou en cas d'échec, `proteger` lève pour que
l'appelant n'enregistre rien plutôt que du clair ; `deproteger` d'un blob invalide rend ''.
"""
import base64
import ctypes
from ctypes import wintypes

_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _vers_blob(donnees):
    tampon = ctypes.create_string_buffer(donnees, len(donnees))
    blob = _DATA_BLOB(len(donnees), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char)))
    return blob, tampon   # le tampon est retourné pour rester vivant pendant l'appel


def _depuis_blob(blob):
    taille = int(blob.cbData)
    sortie = ctypes.create_string_buffer(taille)
    ctypes.memmove(sortie, blob.pbData, taille)
    return sortie.raw


def proteger(texte):
    """Chiffre `texte` (DPAPI) et rend le blob en base64 ; '' pour une entrée vide."""
    if not texte:
        return ''
    donnees = texte.encode('utf-8')
    blob_in, _tampon = _vers_blob(donnees)
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        raise OSError("CryptProtectData a échoué")
    try:
        chiffre = _depuis_blob(blob_out)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return base64.b64encode(chiffre).decode('ascii')


def deproteger(blob):
    """Déchiffre un blob base64 produit par `proteger` ; '' si absent, corrompu ou autre compte."""
    if not blob:
        return ''
    try:
        donnees = base64.b64decode(blob, validate=True)
    except Exception:
        return ''
    blob_in, _tampon = _vers_blob(donnees)
    blob_out = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out))
    if not ok:
        return ''
    try:
        clair = _depuis_blob(blob_out)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    try:
        return clair.decode('utf-8')
    except UnicodeDecodeError:
        return ''
