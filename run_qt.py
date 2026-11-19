"""Point d'entrée de la nouvelle interface Qt (aperçu, construite à côté de l'actuelle).

Lancer : env\\Scripts\\python.exe run_qt.py
Le contrôle de licence (même fichier, mêmes messages que l'exe actuel) est branché à l'étape 4.
"""
import sys

from trios_qt.application import creer_application, creer_fenetre


def main(argv=None) -> int:
    app = creer_application(argv if argv is not None else sys.argv)
    fenetre = creer_fenetre()
    fenetre.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
