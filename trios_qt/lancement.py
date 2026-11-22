"""Contrôleur de lancement (sans Qt) : enchaîne les fichiers prêts via une file et un service."""
import evenements as ev
from trios_qt.file_attente import FileAttente


class ControleurLancement:
    """Démarre chaque fichier à son tour ; avance sur FIN / ERREUR ; relaie les événements."""

    def __init__(self, fabrique_service, traitement_ou_selecteur):
        self._fabrique = fabrique_service
        # 2e argument : un écran fixe, ou un sélecteur chemin -> écran (routage lot/tableau par
        # fichier, étape 2C-10). Un widget n'est pas appelable, donc on l'enveloppe.
        self._selecteur = (traitement_ou_selecteur if callable(traitement_ou_selecteur)
                           else (lambda _chemin: traitement_ou_selecteur))
        self._traitement = None
        self._file = None
        self._service = None
        self._dossiers = {}
        self._dernier_excel = None
        self._dernier_dossier = None

    def lancer(self, fichiers, dossier_defaut=""):
        """fichiers = liste de chemins ou de couples (chemin, dossier)."""
        paires = [(f, dossier_defaut) if isinstance(f, str) else f for f in fichiers]
        self._dossiers = {chemin: dossier for chemin, dossier in paires}
        self._file = FileAttente([chemin for chemin, _ in paires])
        self._demarrer(self._file.demarrer())

    def _demarrer(self, chemin):
        if chemin is None:
            self._service = None
            if self._traitement is not None:
                self._traitement.terminer(self._dernier_excel, self._dernier_dossier)
            return
        self._dernier_dossier = self._dossiers.get(chemin) or None
        self._traitement = self._selecteur(chemin)
        self._traitement.demarrer_fichier(chemin)
        self._service = self._fabrique(chemin, self._dernier_dossier, self._sur_evenement)
        self._service.demarrer()

    def _sur_evenement(self, e):
        self._traitement.sur_evenement(e)
        if e.type == ev.FIN:
            self._dernier_excel = getattr(self._service, 'resultat', None)
            self._demarrer(self._file.terminer(ok=True))
        elif e.type == ev.ERREUR:
            self._demarrer(self._file.terminer(ok=False))

    def pause(self):
        if self._service is not None:
            self._service.pause()

    def reprendre(self):
        if self._service is not None:
            self._service.reprendre()

    def arreter(self):
        if self._service is not None:
            self._service.arreter()
        if self._file is not None:
            self._file.arreter()
        self._service = None

    def en_cours(self):
        return self._service is not None
