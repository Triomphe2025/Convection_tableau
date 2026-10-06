"""
Configuration pytest — ajoute le répertoire racine du projet au sys.path.
Ce fichier est chargé automatiquement par pytest avant tout test.
Les fichiers de tests n'ont donc plus besoin de sys.path.insert().
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config  # noqa: E402

# Les conversions lancées par les tests ne remplissent pas le cache de l'appli de la machine
# (%LOCALAPPDATA%\TriosSeconverter\cache) : dossier temporaire propre à la session de tests.
_CACHE_TESTS = tempfile.TemporaryDirectory(prefix='triosseconverter_cache_tests_')
Config.POSITIONS_CACHE_DOSSIER = Path(_CACHE_TESTS.name)
