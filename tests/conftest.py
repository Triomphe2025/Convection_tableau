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

import hashlib  # noqa: E402
import shutil  # noqa: E402

import pytest  # noqa: E402

import data_dictionary  # noqa: E402

FICHIERS_DICTIONNAIRE = (data_dictionary.DICT_FILE, data_dictionary.DICT_FILE_PENDING)


def empreinte_dictionnaires():
    """Empreinte des vrais fichiers du dictionnaire (absent = None)."""
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None
            for f in FICHIERS_DICTIONNAIRE}


EMPREINTE_AVANT_TESTS = empreinte_dictionnaires()


@pytest.fixture(scope='session', autouse=True)
def dictionnaire_temporaire(tmp_path_factory):
    """Les tests travaillent sur une copie du dictionnaire, jamais sur le vrai fichier.

    Une validation enrichit le dictionnaire (Converter._apprendre_corrections) : sans cette
    copie, une suite de tests écrivait ses valeurs fabriquées dans data_dictionary.json.
    """
    dossier = tmp_path_factory.mktemp('dictionnaire')
    copies = []
    for vrai in FICHIERS_DICTIONNAIRE:
        copie = dossier / vrai.name
        if vrai.exists():
            shutil.copyfile(vrai, copie)
        copies.append(copie)
    anciens = (data_dictionary.DataDictionary.__init__.__defaults__,
               data_dictionary.PendingDictionary.__init__.__defaults__)
    data_dictionary.DataDictionary.__init__.__defaults__ = (copies[0],)
    data_dictionary.PendingDictionary.__init__.__defaults__ = (copies[1],)
    data_dictionary._global_dict = None
    data_dictionary._global_pending = None
    yield dossier
    (data_dictionary.DataDictionary.__init__.__defaults__,
     data_dictionary.PendingDictionary.__init__.__defaults__) = anciens
    data_dictionary._global_dict = None
    data_dictionary._global_pending = None
    assert empreinte_dictionnaires() == EMPREINTE_AVANT_TESTS, \
        "la suite de tests a modifié le vrai data_dictionary.json"


@pytest.fixture
def empreintes_dictionnaire():
    """(empreinte avant la suite, fonction qui relit l'empreinte des vrais fichiers)."""
    return EMPREINTE_AVANT_TESTS, empreinte_dictionnaires
