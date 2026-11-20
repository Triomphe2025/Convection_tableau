"""Message 2 — préchauffage des modules lourds : « Lancer » ne doit plus geler l'UI ~5 s."""
import importlib

import pytest

pytest.importorskip("PySide6")

from trios_qt import application  # noqa: E402


class TestPrechauffer:

    def test_importe_les_modules_lourds_hors_du_fil_ui(self, monkeypatch):
        vus = []
        vrai = importlib.import_module
        monkeypatch.setattr(importlib, "import_module",
                            lambda nom: vus.append(nom) or vrai(nom))
        fil = application.prechauffer()
        fil.join(timeout=30)
        assert not fil.is_alive()
        # Les modules dont l'import gelait l'UI au premier « Lancer » sont bien préchargés.
        assert set(application._MODULES_LOURDS) <= set(vus)
        assert "converter" in vus and "service_conversion" in vus

    def test_rend_un_fil_demon(self):
        fil = application.prechauffer()
        assert fil.daemon
        fil.join(timeout=30)
