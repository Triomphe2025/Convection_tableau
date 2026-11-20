"""Message 1 — réglages Qt : chargement de la clé API (même source que l'appli) + isolation."""
import pytest

pytest.importorskip("PySide6")

from config import Config  # noqa: E402
from trios_qt import reglages  # noqa: E402
import interface_helpers  # noqa: E402


@pytest.fixture
def cle_vierge(monkeypatch):
    # La clé est globale : on repart d'un état propre et on le restaure après le test.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ancienne = Config.CLAUDE_API_KEY
    Config.CLAUDE_API_KEY = ""
    yield
    Config.CLAUDE_API_KEY = ancienne


class TestChargerCleApi:

    def test_env_du_vieux_mecanisme_rend_la_cle_configuree(self, cle_vierge, monkeypatch):
        # ANTHROPIC_API_KEY = exactement la source lue par l'appli actuelle.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123")
        reglages.charger_cle_api_demarrage()
        assert Config.CLAUDE_API_KEY == "sk-ant-test-123"
        assert interface_helpers.etat_cle_api(Config.CLAUDE_API_KEY) == "configurée"

    def test_sans_env_ni_cle_reste_absente(self, cle_vierge):
        reglages.charger_cle_api_demarrage()
        assert interface_helpers.etat_cle_api(Config.CLAUDE_API_KEY) == "absente"

    def test_ne_remplace_pas_une_cle_deja_posee(self, cle_vierge, monkeypatch):
        Config.CLAUDE_API_KEY = "sk-deja-la"
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-autre")
        reglages.charger_cle_api_demarrage()
        assert Config.CLAUDE_API_KEY == "sk-deja-la"


class TestIsolationReglages:

    def test_ecriture_va_dans_le_ini_isole_pas_le_vrai_store(self, tmp_path):
        # conftest a déjà appelé configurer_pour_tests : rien n'atteint TriosSeconverter/apercu.
        reglages.configurer_pour_tests(tmp_path)
        reglages.ecrire_dossier_sortie(r"C:\isole")
        assert reglages.lire_dossier_sortie() == r"C:\isole"
        assert (tmp_path / "apercu_tests.ini").exists()

    def test_defaut_vide(self, tmp_path):
        reglages.configurer_pour_tests(tmp_path)   # dossier neuf, aucune valeur
        assert reglages.lire_dossier_sortie() == ""
