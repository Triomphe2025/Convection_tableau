"""Fiabilité de tesseract.exe dans un exe sans console : OMP_THREAD_LIMIT + CREATE_NO_WINDOW.

Sans ces réglages, le sous-processus tesseract.exe se bloquait (OpenMP / console allouée) et la
lecture de la 1re page scannée ne finissait pas (symptôme « conversion bloquée » de l'exe Qt).
"""
import os
import subprocess

import config
import fiabiliser_tesseract


class TestAppliquerEnvOcr:

    def test_pose_omp_thread_limit(self, monkeypatch):
        monkeypatch.delenv('OMP_THREAD_LIMIT', raising=False)
        config.appliquer_env_ocr()
        assert os.environ['OMP_THREAD_LIMIT'] == str(config.Config.TESSERACT_OMP_THREAD_LIMIT)

    def test_respecte_une_valeur_existante(self, monkeypatch):
        monkeypatch.setenv('OMP_THREAD_LIMIT', '4')   # réglage de l'utilisateur
        config.appliquer_env_ocr()
        assert os.environ['OMP_THREAD_LIMIT'] == '4'


class TestFiabiliserTesseract:

    def test_ajoute_create_no_window_au_subprocess(self, monkeypatch):
        from pytesseract import pytesseract as pt
        monkeypatch.setattr(pt, '_trios_no_window', False, raising=False)
        monkeypatch.setattr(pt, 'subprocess_args', pt.subprocess_args)   # restauré après le test
        assert fiabiliser_tesseract.appliquer() is True
        kwargs = pt.subprocess_args()
        assert kwargs.get('creationflags', 0) & subprocess.CREATE_NO_WINDOW

    def test_idempotent(self, monkeypatch):
        from pytesseract import pytesseract as pt
        monkeypatch.setattr(pt, '_trios_no_window', False, raising=False)
        monkeypatch.setattr(pt, 'subprocess_args', pt.subprocess_args)
        fiabiliser_tesseract.appliquer()
        premier = pt.subprocess_args
        fiabiliser_tesseract.appliquer()   # 2e appel : ne ré-enveloppe pas
        assert pt.subprocess_args is premier
