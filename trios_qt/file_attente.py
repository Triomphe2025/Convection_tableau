"""File d'attente de conversion (module pur) : les fichiers prêts traités un à la fois."""
from collections import deque


class FileAttente:
    """Séquence des fichiers à convertir ; l'échec d'un fichier ne bloque pas les suivants."""

    def __init__(self, elements=()):
        self._reste = deque(elements)
        self._courant = None
        self._arrete = False
        self.faits = []
        self.echecs = []

    def demarrer(self):
        """Démarre la file et rend le premier fichier (ou None si vide)."""
        return self._avancer()

    def terminer(self, ok=True):
        """Marque le fichier courant fait (ou en échec) et rend le suivant (ou None)."""
        if self._courant is not None:
            (self.faits if ok else self.echecs).append(self._courant)
        return self._avancer()

    def _avancer(self):
        if self._arrete or not self._reste:
            self._courant = None
            return None
        self._courant = self._reste.popleft()
        return self._courant

    def arreter(self):
        self._arrete = True
        self._reste.clear()
        self._courant = None

    @property
    def courant(self):
        return self._courant

    @property
    def restants(self):
        return list(self._reste)

    @property
    def termine(self):
        return self._courant is None and not self._reste
