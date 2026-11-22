"""Mode PDF/Tesseract : le converter émet page_debut / page_lue par page (phase 1A).

Sans ces événements, l'écran d'attente restait figé en mode Tesseract (aucune progression). On
vérifie sur un PDF vectoriel (rapide, sans OCR) : le routage par page passe par le même chemin
_extraire_depuis_pdf → extract_all → callbacks que les scans.
"""
from pathlib import Path

import evenements as ev
from config import Config
from converter import Converter

PDF = Path("tests/fixtures/223111PE022_extrait_surimpression.pdf")  # 2 pages


class TestEvenementsPageTesseract:

    def test_un_page_debut_et_un_page_lue_par_page(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Config, 'OCR_MODE', 'tesseract')
        evenements = []
        Converter(PDF, tmp_path, on_evenement=evenements.append,
                  on_log=lambda _m: None).run()
        debuts = [e for e in evenements if e.type == ev.PAGE_DEBUT]
        lues = [e for e in evenements if e.type == ev.PAGE_LUE]
        assert [e.rang for e in debuts] == [1, 2]
        assert [e.rang for e in lues] == [1, 2]
        assert all(e.total == 2 for e in lues)
