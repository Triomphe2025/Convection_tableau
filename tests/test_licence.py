"""
Licence de l'exe (licence.py) : signature, lien au poste, échéance, préavis, garde d'horloge,
messages clairs. La vérification cryptographique est simulée ici (testée à part sur les
vecteurs RFC dans test_ed25519_verif) ; on teste la logique de décision et les messages.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_licence.py -v
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
import licence

MARQUEUR = licence._MARQUEUR
POSTE = '11B0-9E38-9601-2DB7'


def _texte(poste=POSTE, echeance='2027-04-14', contact='Triomphe'):
    entete = f"poste: {poste}\necheance: {echeance}\ncontact: {contact}\n"
    return entete + MARQUEUR + '\n' + '00' * 64 + '\n'


class _Base(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self._tmp.name)
        self._patches = [
            patch.object(licence, 'identifiant_poste', lambda: POSTE),
            patch.object(Config, 'DOSSIER_UTILISATEUR', self.dossier),
            patch.object(Config, 'LICENCE_CONTACT', 'Triomphe (01 23 45 67 89)'),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()


class TestLicenceValide(_Base):

    def _vrai(self, *a, **k):
        return True

    def _faux(self, *a, **k):
        return False

    def test_licence_du_poste_valable(self):
        with patch.object(licence, 'verifier', self._vrai):
            ok, infos, raison = licence.licence_valide(_texte(), dt.date(2026, 10, 14))
        self.assertTrue(ok)
        self.assertEqual(raison, 'ok')
        self.assertEqual(infos['echeance'], '2027-04-14')

    def test_signature_invalide(self):
        with patch.object(licence, 'verifier', self._faux):
            self.assertEqual(licence.licence_valide(_texte())[2], 'signature')

    def test_autre_poste(self):
        with patch.object(licence, 'verifier', self._vrai):
            self.assertEqual(licence.licence_valide(_texte(poste='X-0000'))[2], 'poste')

    def test_expiree(self):
        with patch.object(licence, 'verifier', self._vrai):
            self.assertEqual(licence.licence_valide(_texte(), dt.date(2027, 5, 1))[2], 'expiree')

    def test_forme_fausse(self):
        self.assertEqual(licence.licence_valide('nimporte quoi')[2], 'forme')

    def test_echeance_absente(self):
        with patch.object(licence, 'verifier', self._vrai):
            texte = f"poste: {POSTE}\ncontact: X\n" + MARQUEUR + '\n' + '00' * 64 + '\n'
            self.assertEqual(licence.licence_valide(texte)[2], 'forme')


class TestIdentifiantPoste(unittest.TestCase):

    def test_forme_stable(self):
        a, b = licence.identifiant_poste(), licence.identifiant_poste()
        self.assertEqual(a, b)
        self.assertRegex(a, r'^[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$')


class TestControlerHorloge(_Base):

    def _garde(self, date):
        (self.dossier / 'licence_horloge.json').write_text(
            json.dumps({'plus_recent': date}), encoding='utf-8')

    def test_premier_lancement_ecrit_la_date(self):
        licence.controler_horloge(dt.date(2026, 10, 14))
        vu = json.loads((self.dossier / 'licence_horloge.json').read_text('utf-8'))
        self.assertEqual(vu['plus_recent'], '2026-10-14')

    def test_avance_acceptee(self):
        self._garde('2026-10-10')
        licence.controler_horloge(dt.date(2026, 10, 14))
        vu = json.loads((self.dossier / 'licence_horloge.json').read_text('utf-8'))
        self.assertEqual(vu['plus_recent'], '2026-10-14')

    def test_recul_refuse(self):
        self._garde('2026-10-20')
        with self.assertRaises(licence.LicenceError) as cm:
            licence.controler_horloge(dt.date(2026, 10, 14))
        self.assertIn('horloge', str(cm.exception).lower())
        self.assertIn('Triomphe', str(cm.exception))

    def test_recul_dans_la_tolerance_accepte(self):
        self._garde('2026-10-15')
        licence.controler_horloge(dt.date(2026, 10, 14))  # 1 jour, tolérance 1


class TestMessagePreavis(_Base):

    def test_loin_pas_de_preavis(self):
        self.assertEqual(licence.message_preavis({'echeance': '2027-04-14'},
                                                 dt.date(2026, 10, 14)), '')

    def test_proche_preavis(self):
        msg = licence.message_preavis({'echeance': '2026-10-24'}, dt.date(2026, 10, 14))
        self.assertIn('expire le 24/10/2026', msg)
        self.assertIn('10 jour', msg)

    def test_echeance_fausse_pas_de_preavis(self):
        self.assertEqual(licence.message_preavis({}, dt.date(2026, 10, 14)), '')


class TestExiger(_Base):

    def test_hors_exe_aucun_controle(self):
        # sys.frozen absent en développement : exiger ne contrôle rien
        self.assertEqual(licence.exiger(), '')

    def test_exe_sans_licence_donne_l_identifiant(self):
        with patch.object(licence.sys, 'frozen', True, create=True), \
                patch.object(licence, '_dossier_exe', lambda: self.dossier):
            with self.assertRaises(licence.LicenceError) as cm:
                licence.exiger(dt.date(2026, 10, 14))
        self.assertIn(POSTE, str(cm.exception))

    def test_exe_licence_valable_rend_preavis(self):
        (self.dossier / Config.LICENCE_NOM).write_text(_texte(echeance='2026-10-24'), 'utf-8')
        with patch.object(licence.sys, 'frozen', True, create=True), \
                patch.object(licence, '_dossier_exe', lambda: self.dossier), \
                patch.object(licence, 'verifier', lambda *a: True):
            msg = licence.exiger(dt.date(2026, 10, 14))
        self.assertIn('expire le 24/10/2026', msg)

    def test_exe_licence_expiree_message_clair(self):
        (self.dossier / Config.LICENCE_NOM).write_text(_texte(echeance='2026-10-01'), 'utf-8')
        with patch.object(licence.sys, 'frozen', True, create=True), \
                patch.object(licence, '_dossier_exe', lambda: self.dossier), \
                patch.object(licence, 'verifier', lambda *a: True):
            with self.assertRaises(licence.LicenceError) as cm:
                licence.exiger(dt.date(2026, 10, 14))
        self.assertIn('expiré le 2026-10-01', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
