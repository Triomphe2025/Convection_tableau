"""Étape 2 — zone de dépôt : filtrage des formats, dépôt glisser, bouton Choisir, Ctrl+O."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent, QKeySequence  # noqa: E402

from trios_qt.application import creer_application  # noqa: E402
from trios_qt.zone_depot import ZoneDepot, filtrer_sources  # noqa: E402


class TestFiltrerSources:

    def test_garde_les_extensions_connues(self, tmp_path):
        a = tmp_path / "doc.pdf"
        a.write_text("x", encoding="utf-8")
        b = tmp_path / "feuille.xlsx"
        b.write_text("x", encoding="utf-8")
        c = tmp_path / "note.txt"
        c.write_text("x", encoding="utf-8")
        gardes = filtrer_sources([str(a), str(b), str(c)])
        assert str(a) in gardes
        assert str(b) in gardes
        assert str(c) not in gardes

    def test_accepte_un_dossier(self, tmp_path):
        dossier = tmp_path / "images_scan"
        dossier.mkdir()
        assert filtrer_sources([str(dossier)]) == [str(dossier)]

    def test_insensible_a_la_casse(self, tmp_path):
        a = tmp_path / "DOC.PDF"
        a.write_text("x", encoding="utf-8")
        assert filtrer_sources([str(a)]) == [str(a)]

    def test_ignore_un_format_inconnu(self, tmp_path):
        a = tmp_path / "texte.odt"
        a.write_text("x", encoding="utf-8")
        assert filtrer_sources([str(a)]) == []


@pytest.fixture
def zone(qtbot):
    creer_application([])
    z = ZoneDepot()
    qtbot.addWidget(z)
    return z


class TestZoneDepot:

    def test_depot_emet_les_sources_acceptees(self, zone, qtbot, tmp_path):
        pdf = tmp_path / "bornier.pdf"
        pdf.write_text("x", encoding="utf-8")
        txt = tmp_path / "ignore.txt"
        txt.write_text("x", encoding="utf-8")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(pdf)), QUrl.fromLocalFile(str(txt))])
        event = QDropEvent(QPoint(5, 5), Qt.CopyAction, mime,
                           Qt.LeftButton, Qt.NoModifier)
        with qtbot.waitSignal(zone.sources_deposees, timeout=1000) as bloc:
            zone.dropEvent(event)
        assert bloc.args[0] == [str(pdf)]

    def test_ctrl_o_est_le_raccourci_du_choix(self, zone):
        sequences = [rc.key().toString() for rc in zone.raccourcis()]
        assert QKeySequence("Ctrl+O").toString() in sequences

    def test_bouton_choisir_appelle_le_dialogue(self, zone, monkeypatch):
        appels = {}
        monkeypatch.setattr(zone, "choisir_fichiers", lambda: appels.setdefault("ok", True))
        zone.bouton_choisir.click()
        assert appels.get("ok") is True
