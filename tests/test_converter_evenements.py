"""
Événements structurés dans Converter (phase 1a, étape 2) : on_evenement émis EN PLUS de
on_progress / on_log. Réutilise le faux client du lot (tests/test_lot_converter) ; aucun réseau.

Un test par type d'événement + test d'équivalence (précision 4) : la même conversion avec
on_evenement=None puis avec un collecteur donne exactement le même instantané Excel.

    env\\Scripts\\python.exe -m pytest tests/test_converter_evenements.py -v
"""
import contextlib
import io
import logging
import tempfile
import unittest
from glob import glob
from pathlib import Path
from unittest.mock import patch

import evenements as ev
from config import Config
from converter import Converter
from template import TemplateManager
from tests.test_lot_converter import FauxUnifie, _Base
from tests.test_memes_cellules import FIXTURES, JOURNAUX
from tests.test_non_regression_xlsx import dump_classeur


class Collecteur:
    def __init__(self):
        self.evenements = []

    def __call__(self, e):
        self.evenements.append(e)

    def types(self):
        return [e.type for e in self.evenements]

    def du_type(self, type_):
        return [e for e in self.evenements if e.type == type_]


class TestEvenementsVision(_Base):

    def _lancer(self, images, mode_lot, etats=('ended',)):
        col = Collecteur()
        Config.CLAUDE_MODE_LOT = mode_lot
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / f'cache_{mode_lot}'
        FauxUnifie.etats = list(etats)
        self._raz_client()
        conv = Converter(word_file=images, output_dir=self.tmp / f'out_{mode_lot}',
                         template=self.template, on_log=lambda m: None, on_evenement=col)
        with patch('anthropic.Anthropic', FauxUnifie):
            conv._extraire_avec_progres(images, 0)
        return col

    def test_page_debut_et_page_lue_par_page(self):
        col = self._lancer(self._images(3), mode_lot=False)
        self.assertEqual([e.page for e in col.du_type(ev.PAGE_DEBUT)], [1, 2, 3])
        lues = col.du_type(ev.PAGE_LUE)
        self.assertEqual([e.page for e in lues], [1, 2, 3])
        self.assertTrue(all(isinstance(e.lignes, int) for e in lues))
        self.assertTrue(all(e.total == 3 for e in lues))

    def test_evenements_lot(self):
        col = self._lancer(self._images(3), mode_lot=True, etats=('in_progress', 'ended'))
        t = col.types()
        self.assertIn(ev.LOT_CREE, t)
        self.assertIn(ev.LOT_ETAT, t)
        self.assertIn(ev.LOT_RECUPERE, t)


class TestEvenementsUnitaires(_Base):

    def test_analyse_porte_nature_et_page(self):
        from pdf_extractor import VECTORIEL
        col = Collecteur()
        conv = Converter(word_file=self.tmp, output_dir=self.tmp / 'o',
                         template=self.template, on_log=lambda m: None, on_evenement=col)
        conv._journaliser_routage(2, 5, {'nature': VECTORIEL, 'couverture': 0.0,
                                         'illisibles': 0})
        analyses = col.du_type(ev.ANALYSE)
        self.assertEqual(len(analyses), 1)
        self.assertEqual((analyses[0].page, analyses[0].total), (2, 5))
        self.assertTrue(analyses[0].nature)

    def test_page_alerte_une_par_page_avec_messages(self):
        col = Collecteur()
        conv = Converter(word_file=self.tmp, output_dir=self.tmp / 'o',
                         template=self.template, on_log=lambda m: None, on_evenement=col)
        resultats = [
            {'success': True, 'metadata': {'PAGE': '7'},
             'a_verifier': [{'message': 'confusion O/0'}, {'message': 'colonne vide'}]},
            {'success': True, 'metadata': {'PAGE': '8'}, 'a_verifier': []},
        ]
        conv._emettre_alertes_pages(resultats)
        alertes = col.du_type(ev.PAGE_ALERTE)
        self.assertEqual(len(alertes), 1)
        self.assertEqual(alertes[0].alertes, ['confusion O/0', 'colonne vide'])


class TestRunPhasesEtFin(_Base):

    def test_phases_et_fin(self):
        col = Collecteur()
        Config.CLAUDE_MODE_LOT = False
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cache'
        self._raz_client()
        conv = Converter(word_file=self._images(2), output_dir=self.tmp / 'out',
                         template=self.template, on_log=lambda m: None, on_evenement=col)
        with patch('anthropic.Anthropic', FauxUnifie):
            conv.run()
        phases = [e.etat for e in col.du_type(ev.PHASE)]
        for attendu in ('lecture', 'controles', 'excel'):
            self.assertIn(attendu, phases)
        self.assertEqual(len(col.du_type(ev.FIN)), 1)

    def test_erreur_emise_puis_propagee(self):
        col = Collecteur()
        conv = Converter(word_file=self._images(1), output_dir=self.tmp / 'out',
                         template=self.template, on_log=lambda m: None, on_evenement=col)
        with patch.object(Converter, '_extraire_depuis_images',
                          side_effect=RuntimeError('boum')):
            with self.assertRaises(RuntimeError):
                conv.run()
        erreurs = col.du_type(ev.ERREUR)
        self.assertEqual(len(erreurs), 1)
        self.assertIn('boum', erreurs[0].message)


class TestEquivalenceLot(_Base):
    """Précision 4 : même conversion (lot, faux client) avec ou sans collecteur → même Excel."""

    def _run_snapshot(self, images, on_evenement):
        suff = 'avec' if on_evenement is not None else 'sans'
        Config.CLAUDE_MODE_LOT = True
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / f'cache_{suff}'
        FauxUnifie.etats = ['ended']
        self._raz_client()
        out = self.tmp / f'out_{suff}'
        conv = Converter(word_file=images, output_dir=out, template=self.template,
                         on_log=lambda m: None, on_evenement=on_evenement)
        with patch('anthropic.Anthropic', FauxUnifie):
            conv.run()
        return dump_classeur(glob(str(out / '*.xlsx'))[0])

    def test_meme_excel_avec_ou_sans_collecteur(self):
        images = self._images(3)
        sans = self._run_snapshot(images, None)
        avec = self._run_snapshot(images, Collecteur())
        self.assertEqual(sans, avec)


class TestEquivalenceRejeu(unittest.TestCase):
    """Précision 4 : même rejeu .jsonl avec ou sans collecteur → même Excel."""

    def _rejeu_snapshot(self, on_evenement):
        journal = FIXTURES / JOURNAUX['223111PE011']
        tpl = TemplateManager().get('Bornier standard')
        with tempfile.TemporaryDirectory() as sortie, tempfile.TemporaryDirectory() as lex:
            with patch.multiple(Config, QUALITE_LEXIQUE_DOSSIER=lex,
                                QUALITE_LEXIQUE_COMPILE=str(Path(lex) / 'absent.json')):
                niveau = logging.root.manager.disable
                logging.disable(logging.CRITICAL)
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        Converter(word_file=journal, output_dir=Path(sortie), template=tpl,
                                  on_log=lambda *a, **k: None,
                                  on_evenement=on_evenement).run()
                finally:
                    logging.disable(niveau)
            return dump_classeur(glob(str(Path(sortie) / '*.xlsx'))[0])

    def test_meme_excel_avec_ou_sans_collecteur(self):
        col = Collecteur()
        sans = self._rejeu_snapshot(None)
        avec = self._rejeu_snapshot(col)
        self.assertEqual(sans, avec)
        self.assertIn(ev.FIN, col.types())


if __name__ == '__main__':
    unittest.main()
