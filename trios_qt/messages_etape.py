"""Messages d'étape (étape 2C-4) : un message informatif à la fois, 3 s, en bas à droite.

File d'attente : chaque message (centaine de tableaux, « plus que 10 pages », fin) s'affiche
3 s (jeton message_etape_affiche) puis laisse la place au suivant. L'écran caché vide la file.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel

from trios_qt import theme


class MessagesEtape(QLabel):
    """Affiche des messages d'étape en file ; un seul visible à la fois, 3 s chacun."""

    def __init__(self, jetons: dict | None = None, parent=None):
        super().__init__(parent)
        self._jetons = jetons or theme.charger_jetons()
        self._duree = int(self._jetons["mouvement_ms"]["message_etape_affiche"])
        self._file: list[str] = []
        self._courant = ""
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._minuteur = QTimer(self)
        self._minuteur.setSingleShot(True)
        self._minuteur.setInterval(self._duree)
        self._minuteur.timeout.connect(self._afficher_suivant)

    def afficher(self, message: str) -> None:
        self._file.append(message)
        if not self._courant:
            self._prochain()

    def _prochain(self) -> None:
        if self._file:
            self._courant = self._file.pop(0)
            self.setText(self._courant)
            self._minuteur.start()
        else:
            self._courant = ""
            self.setText("")
            self._minuteur.stop()

    def _afficher_suivant(self) -> None:
        self._prochain()

    def message_courant(self) -> str:
        return self._courant

    def est_visible(self) -> bool:
        return bool(self._courant)

    def duree_ms(self) -> int:
        return self._duree

    def minuteur_actif(self) -> bool:
        return self._minuteur.isActive()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._file.clear()
        self._courant = ""
        self.setText("")
        self._minuteur.stop()
