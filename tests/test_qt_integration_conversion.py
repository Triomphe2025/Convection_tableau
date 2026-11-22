"""Message 2 — intégration : vrai Converter + ServiceConversion + pont Qt → écran Traitement.

Reproduit le « blocage » rapporté : en mode Tesseract l'écran restait figé sur « phase / — »
faute d'afficher les événements réellement émis (ANALYSE par page). Ici, sur un PDF vectoriel
rapide (pas d'OCR lent), la progression doit montrer « Lecture page n / total » et FIN arriver.

Avant le correctif de l'écran : ANALYSE n'était pas lu → aucune « Lecture page » → échec.
"""
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402

import evenements as ev  # noqa: E402
from config import Config  # noqa: E402
from converter import Converter  # noqa: E402
from service_conversion import ServiceConversion  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.page_traitement import PageTraitement  # noqa: E402

PDF = Path("tests/fixtures/223111PE022_extrait_surimpression.pdf")  # 2 pages vectorielles, rapide


class _Pont(QObject):
    recu = Signal(object)


class TestConversionReelle:

    def test_progression_lisible_et_fin_recue(self, qtbot, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, "OCR_MODE", "tesseract")
        creer_application([])
        page = PageTraitement()
        qtbot.addWidget(page)
        page.demarrer_fichier(PDF.name)

        pont = _Pont()
        etat = {'fin': False, 'progressions': []}

        def on_e(e):
            page.sur_evenement(e)
            etat['progressions'].append(page.journal_resume.text())
            if e.type == ev.FIN:
                etat['fin'] = True

        pont.recu.connect(on_e, Qt.ConnectionType.QueuedConnection)
        conv = Converter(PDF, tmp_path, on_log=lambda _m: None)
        service = ServiceConversion(conv, on_evenement=pont.recu.emit)
        service.demarrer()

        qtbot.waitUntil(lambda: etat['fin'], timeout=60000)
        assert any("Lecture page" in p for p in etat['progressions'])
        # Jamais le nom technique brut à l'écran.
        assert all(p != "phase" for p in etat['progressions'])
        assert service.resultat is not None and service.resultat.get('excel')
