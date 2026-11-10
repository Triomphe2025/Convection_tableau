"""Service de conversion (phase 1a, étape 3).

Lance un Converter dans un fil et l'expose à une interface : démarrer, pause, reprendre,
arrêter, en relayant ses événements. La pause se fait entre deux pages (threading.Event),
sans perte : le fil de conversion se bloque juste après page_lue (la page lue est gardée),
avant la page suivante. L'interface actuelle peut toujours appeler Converter directement.
"""
import threading
from typing import Callable, Optional

import evenements as ev


class ServiceConversion:
    """Pilote un Converter dans un fil ; pause coopérative entre deux pages."""

    def __init__(self, converter, on_evenement: Optional[Callable] = None):
        self._converter = converter
        self._on_evenement = on_evenement or (lambda e: None)
        # SET = en marche ; CLEAR = en pause. Le fil de conversion attend sur cet Event
        # après chaque page_lue : il ne reprend qu'une fois remis en marche.
        self._pause = threading.Event()
        self._pause.set()
        self._arret = getattr(converter, '_cancel_event', None) or threading.Event()
        self._thread = None
        self._resultat = None
        self._erreur = None
        # Le service devient le puits d'événements et le signal d'arrêt du converter.
        converter._on_evenement = self._relayer
        converter._cancel_event = self._arret

    def _relayer(self, e) -> None:
        # Appelé dans le fil de conversion : on relaie, puis on se bloque si en pause. Bloquer
        # sur page_lue pause ENTRE deux pages (la page lue est gardée), jamais au milieu.
        self._on_evenement(e)
        if e.type == ev.PAGE_LUE:
            self._pause.wait()

    def demarrer(self) -> None:
        if self._thread is not None:
            raise RuntimeError("conversion déjà démarrée")
        self._thread = threading.Thread(target=self._executer, name='conversion', daemon=True)
        self._thread.start()

    def _executer(self) -> None:
        try:
            self._resultat = self._converter.run()
        except Exception as exc:
            # L'événement ERREUR a déjà été émis par le converter ; on garde l'exception.
            self._erreur = exc

    def pause(self) -> None:
        self._pause.clear()

    def reprendre(self) -> None:
        self._pause.set()

    def arreter(self) -> None:
        self._arret.set()
        self._pause.set()        # débloque une pause en cours pour que l'arrêt soit vu

    def en_pause(self) -> bool:
        return not self._pause.is_set()

    def est_en_cours(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def attendre(self, timeout=None) -> bool:
        """Attend la fin du fil ; rend True s'il est terminé, False si le délai expire."""
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def resultat(self):
        return self._resultat

    @property
    def erreur(self):
        return self._erreur
