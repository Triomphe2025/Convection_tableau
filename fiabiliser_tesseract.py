"""Fiabilise l'appel à tesseract.exe depuis un exe SANS console (interface Qt windowed).

tesseract.exe est une application console. Lancé par pytesseract depuis un process sans console
et sans CREATE_NO_WINDOW, Windows alloue une console au sous-processus : combiné à OpenMP et au
fil Tesseract concurrent (compte de lignes), le sous-processus se bloquait et ne rendait jamais la
main (pytesseract.communicate figé) → la lecture de la 1re page scannée ne finissait pas.

On ajoute CREATE_NO_WINDOW aux arguments de subprocess de pytesseract (aucune console allouée).
Module pur, idempotent ; ne lève jamais (sans pytesseract, il ne fait rien).
"""


def appliquer():
    """Ajoute CREATE_NO_WINDOW au Popen de pytesseract. Idempotent, sûr à rappeler."""
    try:
        import subprocess

        from pytesseract import pytesseract as _pt
    except Exception:
        return False
    if getattr(_pt, '_trios_no_window', False):
        return True
    drapeau = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    if not drapeau:
        return False
    _vrai = _pt.subprocess_args

    def _args(include_stdout=True):
        kwargs = _vrai(include_stdout)
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | drapeau
        return kwargs

    _pt.subprocess_args = _args
    _pt._trios_no_window = True
    return True
