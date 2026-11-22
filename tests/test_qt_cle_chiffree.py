"""Point 2 : la clé API n'est jamais stockée en clair (DPAPI, compte Windows courant).

Tests d'abord : avec le stub (proteger = identité), `test_proteger_ne_rend_pas_le_clair` et
`test_valeur_enregistree_jamais_en_clair` échouent sur le comportement visé. L'implémentation
DPAPI réelle les fait passer ; casser `proteger` (retour du clair) les repasse au rouge.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

pytest.importorskip("PySide6")  # sans Qt, QSettings indisponible

import chiffrement_dpapi  # noqa: E402
from trios_qt import reglages  # noqa: E402

_CLE = "sk-ant-api03-SECRET-abcdef0123456789"


class TestChiffrementDpapi:
    def test_rond_trip(self):
        assert chiffrement_dpapi.deproteger(chiffrement_dpapi.proteger(_CLE)) == _CLE

    def test_proteger_ne_rend_pas_le_clair(self):
        protege = chiffrement_dpapi.proteger(_CLE)
        assert _CLE not in protege

    def test_vide_reste_vide(self):
        assert chiffrement_dpapi.proteger("") == ""
        assert chiffrement_dpapi.deproteger("") == ""

    def test_deproteger_blob_invalide_rend_vide(self):
        # Une valeur enregistrée corrompue (ou issue d'un autre compte) ne doit pas faire planter.
        assert chiffrement_dpapi.deproteger("pas-un-blob-base64-valide!!") == ""


class TestReglagesCleChiffree:
    def test_ecrire_puis_lire(self, tmp_path):
        reglages.configurer_pour_tests(tmp_path)
        reglages.ecrire_cle_api(_CLE)
        assert reglages.lire_cle_api() == _CLE

    def test_valeur_enregistree_jamais_en_clair(self, tmp_path):
        reglages.configurer_pour_tests(tmp_path)
        reglages.ecrire_cle_api(_CLE)
        # La valeur réellement stockée (QSettings/.ini) ne doit jamais contenir la clé en clair.
        brute = reglages._settings().value(reglages._CLE_API_PROTEGEE, "", type=str)
        assert brute != ""
        assert _CLE not in brute
        contenu_ini = Path(reglages._fichier_test).read_text(encoding="utf-8", errors="ignore")
        assert _CLE not in contenu_ini

    def test_cle_vide_efface(self, tmp_path):
        reglages.configurer_pour_tests(tmp_path)
        reglages.ecrire_cle_api(_CLE)
        reglages.ecrire_cle_api("")
        assert reglages.lire_cle_api() == ""
