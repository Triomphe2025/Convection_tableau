"""
evenements.py — dataclass Evenement et zones_relatives (phase 1a, étape 2).

Module pur : aucun moteur, aucun Tkinter. zones_relatives est testée sur un objet
de lecture fabriqué (mots + taille), sans importer positions_scan (lourd, Tesseract).

    env\\Scripts\\python.exe -m pytest tests/test_evenements.py -v
"""
import dataclasses
import unittest
from types import SimpleNamespace

import evenements as ev


class TestEvenement(unittest.TestCase):

    def test_type_seul_les_autres_champs_none(self):
        e = ev.Evenement(type=ev.PAGE_DEBUT)
        self.assertEqual(e.type, ev.PAGE_DEBUT)
        for champ in ('page', 'total', 'nature', 'etat', 'bornier', 'lignes',
                      'zones', 'alertes', 'cout', 'lot', 'message'):
            self.assertIsNone(getattr(e, champ), champ)

    def test_horodatage_rempli_automatiquement(self):
        e = ev.Evenement(type=ev.FIN)
        self.assertIsInstance(e.horodatage, float)
        self.assertGreater(e.horodatage, 0.0)

    def test_champs_portes(self):
        e = ev.Evenement(type=ev.PAGE_LUE, page=3, total=10, lignes=12,
                         bornier='PA', zones=[(0.1, 0.2, 0.3, 0.4)])
        self.assertEqual((e.page, e.total, e.lignes, e.bornier), (3, 10, 12, 'PA'))
        self.assertEqual(e.zones, [(0.1, 0.2, 0.3, 0.4)])

    def test_message_porte_le_texte_libre(self):
        e = ev.Evenement(type=ev.ERREUR, message="réseau coupé")
        self.assertEqual(e.message, "réseau coupé")

    def test_fige_pas_de_mutation(self):
        e = ev.Evenement(type=ev.PHASE, etat='lecture')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.etat = 'excel'


class TestZonesRelatives(unittest.TestCase):

    def _lecture(self, mots, taille=(100, 200)):
        return SimpleNamespace(mots=mots, taille=taille)

    def test_mots_normalises_en_0_1(self):
        lecture = self._lecture([
            (10, 20, 30, 40, 'A1', 90),
            (0, 0, 100, 200, 'FULL', 80),
        ])
        self.assertEqual(ev.zones_relatives(lecture), [
            (0.1, 0.1, 0.3, 0.2),
            (0.0, 0.0, 1.0, 1.0),
        ])

    def test_traits_et_vides_ecartes(self):
        lecture = self._lecture([
            (10, 20, 30, 40, '|', 0),
            (50, 60, 70, 80, '   ', 10),
            (10, 20, 30, 40, 'B2', 85),
        ])
        self.assertEqual(ev.zones_relatives(lecture), [(0.1, 0.1, 0.3, 0.2)])

    def test_aucun_mot_rend_none(self):
        self.assertIsNone(ev.zones_relatives(self._lecture([])))

    def test_que_des_traits_rend_none(self):
        self.assertIsNone(ev.zones_relatives(self._lecture([(1, 1, 2, 2, '|', 0)])))

    def test_taille_nulle_rend_none(self):
        lecture = self._lecture([(10, 20, 30, 40, 'A1', 90)], taille=(0, 0))
        self.assertIsNone(ev.zones_relatives(lecture))

    def test_lecture_none_rend_none(self):
        self.assertIsNone(ev.zones_relatives(None))


if __name__ == '__main__':
    unittest.main()
