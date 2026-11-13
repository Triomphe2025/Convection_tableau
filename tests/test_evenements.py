"""
evenements.py — dataclass Evenement (phase 1a, étape 2). Module pur, sans moteur ni Tkinter.
Les zones par ligne sont produites par positions_scan.zones_par_ligne (testé là-bas).

    env\\Scripts\\python.exe -m pytest tests/test_evenements.py -v
"""
import dataclasses
import unittest

import evenements as ev


class TestEvenement(unittest.TestCase):

    def test_type_seul_les_autres_champs_none(self):
        e = ev.Evenement(type=ev.PAGE_DEBUT)
        self.assertEqual(e.type, ev.PAGE_DEBUT)
        for champ in ('page', 'rang', 'total', 'page_imprimee', 'nature', 'etat', 'bornier',
                      'lignes', 'zones', 'alertes', 'cout', 'lot', 'compteurs', 'message',
                      'points'):
            self.assertIsNone(getattr(e, champ), champ)

    def test_horodatage_rempli_automatiquement(self):
        e = ev.Evenement(type=ev.FIN)
        self.assertIsInstance(e.horodatage, float)
        self.assertGreater(e.horodatage, 0.0)

    def test_champs_portes(self):
        e = ev.Evenement(type=ev.PAGE_LUE, page=3, rang=2, total=10, page_imprimee='122a',
                         lignes=12, bornier='PA',
                         zones=[{'ligne': 0, 'boite': (0.1, 0.2, 0.3, 0.4)}])
        self.assertEqual((e.page, e.rang, e.total, e.page_imprimee, e.lignes, e.bornier),
                         (3, 2, 10, '122a', 12, 'PA'))
        self.assertEqual(e.zones, [{'ligne': 0, 'boite': (0.1, 0.2, 0.3, 0.4)}])

    def test_compteurs_porte_le_detail_du_lot(self):
        e = ev.Evenement(type=ev.LOT_ETAT, lot='batch_x',
                         compteurs={'lues': 2, 'en_attente': 1, 'a_reprendre': 0, 'total': 3})
        self.assertEqual(e.compteurs['lues'], 2)

    def test_message_porte_le_texte_libre(self):
        e = ev.Evenement(type=ev.ERREUR, message="réseau coupé")
        self.assertEqual(e.message, "réseau coupé")

    def test_fin_porte_le_chemin_des_points(self):
        e = ev.Evenement(type=ev.FIN, etat='terminee', points=r'C:\x\doc_points.json')
        self.assertEqual(e.points, r'C:\x\doc_points.json')

    def test_fige_pas_de_mutation(self):
        e = ev.Evenement(type=ev.PHASE, etat='lecture')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.etat = 'excel'


if __name__ == '__main__':
    unittest.main()
