"""
Cache des lectures Tesseract (cache_lectures.py) : dans un dossier de l'appli
(POSITIONS_CACHE_DOSSIER, %LOCALAPPDATA%\\TriosSeconverter\\cache), jamais à côté des
fichiers de l'utilisateur ; clé = empreinte du PDF + page + réglages de lecture ; purge
par âge et par taille.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_cache_lectures.py -v
"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cache_lectures as cl
from config import Config

LECTURE = {'mots': [[10, 20, 50, 40, 'PH', 90]], 'traits': [0.0, 300.0], 'dpi': 300,
           'taille': [2480, 3508]}


class _AvecDossier(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self._tmp.name) / 'cache'
        self._patch = patch.object(Config, 'POSITIONS_CACHE_DOSSIER', self.dossier)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()


class TestEmpreinte(_AvecDossier):

    def test_meme_contenu_meme_empreinte_quel_que_soit_le_nom(self):
        a, b = Path(self._tmp.name) / 'a.pdf', Path(self._tmp.name) / 'b.pdf'
        a.write_bytes(b'%PDF contenu')
        b.write_bytes(b'%PDF contenu')
        self.assertEqual(cl.empreinte_fichier(a), cl.empreinte_fichier(b))

    def test_contenu_different(self):
        a, b = Path(self._tmp.name) / 'a.pdf', Path(self._tmp.name) / 'b.pdf'
        a.write_bytes(b'%PDF 1')
        b.write_bytes(b'%PDF 2')
        self.assertNotEqual(cl.empreinte_fichier(a), cl.empreinte_fichier(b))


class TestLireEcrire(_AvecDossier):

    def test_aller_retour(self):
        cl.ecrire('abc', 4, LECTURE)
        self.assertEqual(cl.lire('abc', 4), LECTURE)
        self.assertEqual([p.parent for p in self.dossier.glob('*.json')], [self.dossier])

    def test_absent(self):
        self.assertIsNone(cl.lire('abc', 4))
        cl.ecrire('abc', 4, LECTURE)
        self.assertIsNone(cl.lire('abc', 5))
        self.assertIsNone(cl.lire('abd', 4))

    def test_reglage_de_lecture_change_la_cle(self):
        cl.ecrire('abc', 4, LECTURE)
        with patch.object(Config, 'POSITIONS_DPI', 200):
            self.assertIsNone(cl.lire('abc', 4))
        with patch.object(Config, 'POSITIONS_PSM', '4'):
            self.assertIsNone(cl.lire('abc', 4))

    def test_fichier_illisible_ignore(self):
        cl.ecrire('abc', 4, LECTURE)
        next(self.dossier.glob('*.json')).write_text('{tronqué', encoding='utf-8')
        self.assertIsNone(cl.lire('abc', 4))

    def test_nom_de_fichier_court(self):
        # Dossier de l'appli + nom court : loin des 260 caractères de Windows.
        cl.ecrire('a' * 64, 123, LECTURE)
        self.assertLess(len(next(self.dossier.glob('*.json')).name), 50)


class TestPurger(_AvecDossier):

    def _fichiers(self, n, age_jours=0):
        """n lectures écrites, puis vieillies de age_jours (chacune d'une seconde d'écart)."""
        avant = set(self.dossier.glob('*.json'))
        for i in range(n):
            cl.ecrire(f'doc{i}', 1, LECTURE)
        maintenant = time.time()
        nouveaux = sorted(set(self.dossier.glob('*.json')) - avant)
        for i, f in enumerate(nouveaux):
            t = maintenant - age_jours * 86400 - i
            os.utime(f, (t, t))

    def test_trop_vieux_supprimes(self):
        cl.ecrire('recent', 1, LECTURE)
        self._fichiers(3, age_jours=40)
        supprimes = cl.purger(age_max_jours=30, taille_max_octets=10 ** 9)
        self.assertEqual(supprimes, 3)
        self.assertEqual(cl.lire('recent', 1), LECTURE)

    def test_taille_depassee_plus_anciens_d_abord(self):
        self._fichiers(5)
        taille = sum(f.stat().st_size for f in self.dossier.glob('*.json'))
        le_plus_recent = max(self.dossier.glob('*.json'), key=lambda f: f.stat().st_mtime)
        cl.purger(age_max_jours=30, taille_max_octets=taille // 5)
        restants = list(self.dossier.glob('*.json'))
        self.assertEqual(restants, [le_plus_recent])

    def test_dossier_absent(self):
        self.assertEqual(cl.purger(age_max_jours=30, taille_max_octets=10), 0)


class TestDossierParDefaut(unittest.TestCase):

    def test_sous_localappdata(self):
        # conftest.py redirige le cache des tests : la valeur par défaut est relue dans un
        # module config neuf.
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'config_par_defaut', Path(__file__).parent.parent / 'config.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        dossier = Path(module.Config.POSITIONS_CACHE_DOSSIER)
        self.assertEqual(dossier.parts[-2:], ('TriosSeconverter', 'cache'))
        if os.environ.get('LOCALAPPDATA'):
            self.assertEqual(dossier.parent.parent, Path(os.environ['LOCALAPPDATA']))


if __name__ == '__main__':
    unittest.main()
