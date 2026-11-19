"""Point d'entrée de la nouvelle interface Qt (aperçu, construite à côté de l'actuelle).

Lancer : env\\Scripts\\python.exe run_qt.py
La licence (même fichier, mêmes messages que l'exe actuel) est contrôlée avant d'ouvrir la
fenêtre : hors exe (développement) licence.exiger() ne contrôle rien et rend ''.
"""
import sys

from PySide6.QtWidgets import QMessageBox

from trios_qt.application import creer_application, creer_fenetre
from trios_qt.theme import appliquer_theme

TITRE_LICENCE = "TriosSeconverter — licence"


def verifier_licence(sur_erreur):
    """Contrôle la licence ; rend le préavis. LicenceError -> sur_erreur puis arrêt."""
    import licence
    try:
        return licence.exiger()
    except licence.LicenceError as erreur:
        sur_erreur(str(erreur))
        raise SystemExit(3)


def _afficher_erreur(message: str) -> None:
    QMessageBox.critical(None, TITRE_LICENCE, message)


def _afficher_preavis(message: str) -> None:
    QMessageBox.warning(None, TITRE_LICENCE, message)


def main(argv=None) -> int:
    app = creer_application(argv if argv is not None else sys.argv)
    appliquer_theme(app)
    preavis = verifier_licence(_afficher_erreur)
    fenetre = creer_fenetre()
    fenetre.show()
    if preavis:
        _afficher_preavis(preavis)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
