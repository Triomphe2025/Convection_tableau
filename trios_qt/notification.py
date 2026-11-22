"""Notification de fin (étape 2C-5) : bulle de la zone de notification + clignotement de la barre
des tâches, et progression dans le bouton de la barre (ITaskbarList3, optionnelle).

La décision « signaler seulement hors focus, sous Windows » réutilise interface_helpers (pas de
seconde règle). Les appels système sont enveloppés : indisponibles, ils rendent False sans planter
— la mini-fenêtre et l'écran de fin marchent même sans barre des tâches Windows.
"""
import sys

import interface_helpers

_FLASHW_ALL = 0x00000003
_FLASHW_TIMERNOFG = 0x0000000C


def flash_barre_taches(hwnd) -> bool:
    """Fait clignoter le bouton de la fenêtre dans la barre des tâches. False si indisponible."""
    if not sys.platform.startswith("win") or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class _FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND),
                        ("dwFlags", wintypes.DWORD), ("uCount", wintypes.UINT),
                        ("dwTimeout", wintypes.DWORD)]

        info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), int(hwnd),
                           _FLASHW_ALL | _FLASHW_TIMERNOFG, 0, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        return True
    except Exception:
        return False


def definir_progression_barre(hwnd, fraction) -> bool:
    """Pose la progression (0–1) dans le bouton de la barre des tâches (ITaskbarList3). Optionnel :
    False si la fenêtre manque, hors Windows, ou si comtypes n'est pas là — jamais d'erreur."""
    if not sys.platform.startswith("win") or not hwnd:
        return False
    try:
        import comtypes.client
        from comtypes.gen import TaskbarLib  # noqa: F401 (déclenche la génération du type)

        barre = comtypes.client.CreateObject(
            "{56FDF344-FD6D-11d0-958A-006097C9A090}", interface=None)
        barre.HrInit()
        maxi = 1000
        barre.SetProgressValue(int(hwnd), int(max(0.0, min(1.0, fraction)) * maxi), maxi)
        return True
    except Exception:
        return False


def notifier(tray, titre: str, message: str) -> bool:
    """Affiche une bulle via le QSystemTrayIcon fourni ; False si absent ou refusé."""
    if tray is None:
        return False
    try:
        tray.showMessage(titre, message)
        return True
    except Exception:
        return False


def signaler_fin(hwnd, tray, titre: str, message: str, a_le_focus: bool,
                 plateforme=None) -> bool:
    """Bulle + clignotement si la fenêtre n'a pas le focus, sous Windows. True si signalé."""
    plateforme = plateforme or sys.platform
    if not interface_helpers.doit_signaler_fin(plateforme, a_le_focus):
        return False
    notifier(tray, titre, message)
    flash_barre_taches(hwnd)
    return True
