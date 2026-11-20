"""File des fichiers déposés (QAbstractListModel) et lanceur d'analyse dans un fil à part."""
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QObject, QRunnable,
                            Qt, QThreadPool, Signal)

from trios_qt import analyse

ROLE_LIGNE = Qt.UserRole + 1


class LigneFichier:
    """Une entrée de la file : identité stable, chemin, nom affiché, résultat d'analyse."""

    def __init__(self, ident, chemin):
        self.ident = ident
        self.chemin = Path(chemin)
        self.nom = self.chemin.name
        self.resultat = analyse.ResultatAnalyse(etat=analyse.ANALYSE)
        self.profil_cle = "precis"   # profil de lecture choisi (ligne dépliée)
        self.lot = None              # None = pas encore initialisé (défaut : lot_propose)
        self.dossier_sortie = None   # surcharge par fichier ; sinon le dossier commun


class ModeleFichiers(QAbstractListModel):
    """Modèle de la liste des fichiers ; l'identité (ident) suit un fichier malgré les glissers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lignes = []
        self._prochain_ident = 0

    # ── API Qt ────────────────────────────────────────────────────────
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._lignes)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._lignes)):
            return None
        ligne = self._lignes[index.row()]
        if role == Qt.DisplayRole:
            return ligne.nom
        if role == ROLE_LIGNE:
            return ligne
        return None

    # ── API métier ────────────────────────────────────────────────────
    def ligne(self, rang):
        return self._lignes[rang]

    def ajouter(self, chemin):
        """Ajoute un fichier en état « analyse… » et rend son identité stable."""
        ident = self._prochain_ident
        self._prochain_ident += 1
        rang = len(self._lignes)
        self.beginInsertRows(QModelIndex(), rang, rang)
        self._lignes.append(LigneFichier(ident, chemin))
        self.endInsertRows()
        return ident

    def appliquer_resultat(self, ident, resultat):
        """Complète la ligne d'identité `ident` (retrouvée où qu'elle soit) avec son analyse."""
        for rang, ligne in enumerate(self._lignes):
            if ligne.ident == ident:
                ligne.resultat = resultat
                idx = self.index(rang)
                self.dataChanged.emit(idx, idx)
                return True
        return False

    def retirer(self, rang):
        self.beginRemoveRows(QModelIndex(), rang, rang)
        del self._lignes[rang]
        self.endRemoveRows()

    def deplacer(self, source, destination):
        """Déplace la ligne `source` à l'index `destination` (réordonnancement par glisser)."""
        if source == destination:
            return
        # beginMoveRows attend l'index d'insertion AVANT retrait quand on descend (+1).
        cible_qt = destination + 1 if destination > source else destination
        self.beginMoveRows(QModelIndex(), source, source, QModelIndex(), cible_qt)
        ligne = self._lignes.pop(source)
        self._lignes.insert(destination, ligne)
        self.endMoveRows()


class _Signaux(QObject):
    fini = Signal(int, object)


class _Tache(QRunnable):
    """Exécute l'analyse d'un fichier dans un fil du pool, puis émet (ident, résultat)."""

    def __init__(self, ident, chemin, analyser, options, signaux):
        super().__init__()
        self._ident = ident
        self._chemin = chemin
        self._analyser = analyser
        self._options = options
        self._signaux = signaux

    def run(self):
        resultat = self._analyser(self._chemin, **self._options)
        self._signaux.fini.emit(self._ident, resultat)


class LanceurAnalyse(QObject):
    """Lance l'analyse (detecter_type + estimer) hors du fil de l'interface ; `fini` la ramène."""

    fini = Signal(int, object)

    def __init__(self, analyser=None, pool=None, parent=None):
        super().__init__(parent)
        self._analyser = analyser or analyse.analyser
        self._pool = pool or QThreadPool.globalInstance()
        self._signaux = _Signaux()
        # File d'attente Qt : le résultat revient dans le fil de l'interface, pas depuis la tâche.
        self._signaux.fini.connect(self.fini, Qt.QueuedConnection)

    def lancer(self, ident, chemin, dossier_sortie=None, lot=False, profil=None):
        options = {'dossier_sortie': dossier_sortie, 'lot': lot, 'profil': profil}
        self._pool.start(_Tache(ident, chemin, self._analyser, options, self._signaux))
