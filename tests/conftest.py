"""
Configuration pytest — ajoute le répertoire racine du projet au sys.path.
Ce fichier est chargé automatiquement par pytest avant tout test.
Les fichiers de tests n'ont donc plus besoin de sys.path.insert().
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
