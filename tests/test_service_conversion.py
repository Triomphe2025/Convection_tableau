"""
service_conversion.py (phase 1a, étape 3) : Converter dans un fil, piloté par démarrer / pause /
reprendre / arrêter. La pause se fait entre deux pages (après page_lue), sans perte. Faux client
du lot, sans réseau.

    env\\Scripts\\python.exe -m pytest tests/test_service_conversion.py -v
"""
import threading
import unittest
from unittest.mock import patch

import evenements as ev
from config import Config
from converter import Converter
from service_conversion import ServiceConversion
from tests.test_lot_converter import FauxUnifie, _Base


class _BaseService(_Base):

    def _service(self, n_images, ecouteur):
        Config.CLAUDE_MODE_LOT = False
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache'
        FauxUnifie.etats = ['ended']
        self._raz_client()
        conv = Converter(word_file=self._images(n_images), output_dir=self.tmp / 'out',
                         template=self.template, on_log=lambda m: None)
        return ServiceConversion(conv, on_evenement=ecouteur)


class TestDemarrerAttendre(_BaseService):

    def test_termine_et_resultat_disponible(self):
        vus = []
        service = self._service(3, vus.append)
        with patch('anthropic.Anthropic', FauxUnifie):
            service.demarrer()
            self.assertTrue(service.attendre(10))
        self.assertEqual(sum(1 for e in vus if e.type == ev.PAGE_LUE), 3)
        self.assertIsNotNone(service.resultat)
        self.assertIsNone(service.erreur)
        self.assertEqual([e for e in vus if e.type == ev.FIN][0].etat, 'terminee')


class TestPause(_BaseService):

    def _ecouteur_pause_a_la_premiere(self, service, vus, pause_evt):
        def ecouteur(e):
            vus.append(e)
            if e.type == ev.PAGE_LUE and self._compter(vus, ev.PAGE_LUE) == 1:
                service.pause()
                pause_evt.set()
        return ecouteur

    @staticmethod
    def _compter(vus, type_):
        return sum(1 for e in vus if e.type == type_)

    def test_pause_entre_pages_puis_reprise(self):
        vus = []
        pause_evt = threading.Event()
        holder = {}
        service = self._service(3, lambda e: holder['ec'](e))
        holder['ec'] = self._ecouteur_pause_a_la_premiere(service, vus, pause_evt)
        with patch('anthropic.Anthropic', FauxUnifie):
            service.demarrer()
            self.assertTrue(pause_evt.wait(10))
            # Bloqué après la 1re page : la conversion ne se termine pas, aucune 2e page lue.
            self.assertFalse(service.attendre(0.4))
            self.assertTrue(service.en_pause())
            self.assertEqual(self._compter(vus, ev.PAGE_LUE), 1)
            service.reprendre()
            self.assertTrue(service.attendre(10))
        self.assertEqual(self._compter(vus, ev.PAGE_LUE), 3)

    def test_arreter_pendant_pause_libere_le_fil(self):
        vus = []
        pause_evt = threading.Event()
        holder = {}
        service = self._service(3, lambda e: holder['ec'](e))
        holder['ec'] = self._ecouteur_pause_a_la_premiere(service, vus, pause_evt)
        with patch('anthropic.Anthropic', FauxUnifie):
            service.demarrer()
            self.assertTrue(pause_evt.wait(10))
            service.arreter()
            self.assertTrue(service.attendre(10))
        # Arrêt pendant la pause : aucune page lue au-delà de la 1re, le fil se termine.
        self.assertEqual(self._compter(vus, ev.PAGE_LUE), 1)
        self.assertEqual([e for e in vus if e.type == ev.FIN][0].etat, 'arretee')


if __name__ == '__main__':
    unittest.main()
