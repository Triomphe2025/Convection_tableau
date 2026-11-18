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

from PIL import Image

import evenements as ev
from config import Config
from converter import Converter
from template import TemplateManager
from tests.test_lot_converter import FauxUnifie, _Base, _texte
from tests.test_memes_cellules import FIXTURES, JOURNAUX
from tests.test_non_regression_xlsx import dump_classeur
from tests.test_positions_scan import _lecture, _mot


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

    def test_lot_compteurs(self):
        col = self._lancer(self._images(3), mode_lot=True, etats=('in_progress', 'ended'))
        cree = col.du_type(ev.LOT_CREE)[0]
        self.assertIn('requetes', cree.compteurs)
        self.assertIn('taille_mo', cree.compteurs)
        etat = col.du_type(ev.LOT_ETAT)[0]
        for cle in ('lues', 'en_attente', 'a_reprendre', 'total', 'delai'):
            self.assertIn(cle, etat.compteurs)

    def _images_nommees(self, numeros):
        d = self.tmp / 'nommees'
        d.mkdir(exist_ok=True)
        for n in numeros:
            Image.new('RGB', (200, 150), (n * 20, 0, 0)).save(d / f'page_{n}.png')
        return d

    def test_page_numero_pdf_et_rang(self):
        # Document mixte simulé : page 1 vectorielle (non rastérisée), pages 2 et 3 scannées.
        col = Collecteur()
        Config.CLAUDE_MODE_LOT = False
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cnum'
        FauxUnifie.etats = ['ended']
        self._raz_client()
        images = self._images_nommees([2, 3])
        conv = Converter(word_file=images, output_dir=self.tmp / 'onum', template=self.template,
                         on_log=lambda m: None, on_evenement=col)
        with patch('anthropic.Anthropic', FauxUnifie):
            conv._extraire_avec_progres(images, 0)
        lues = col.du_type(ev.PAGE_LUE)
        self.assertEqual([e.page for e in lues], [2, 3])        # numéro de page du PDF
        self.assertEqual([e.rang for e in lues], [1, 2])        # rang parmi les pages lues
        self.assertTrue(all(e.total == 2 for e in lues))
        self.assertEqual([e.page for e in col.du_type(ev.PAGE_DEBUT)], [2, 3])

    def test_zones_de_la_bonne_page_par_ligne(self):
        tpl = TemplateManager().get('Bornier standard')
        col = Collecteur()
        Config.CLAUDE_MODE_LOT = False
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cz'
        FauxUnifie.etats = ['ended']
        FauxUnifie.textes = [_texte(2), _texte(3)]   # page_2 lue en 1er → clé « A2 »
        self._raz_client()
        images = self._images_nommees([2, 3])
        conv = Converter(word_file=images, output_dir=self.tmp / 'oz', template=tpl,
                         on_log=lambda m: None, on_evenement=col)
        # Lectures Tesseract rangées par numéro de page du PDF (2 et 3), pas par rang.
        conv._lectures_tesseract = {
            2: _lecture(_mot(1, 1, 'A2'), _mot(31, 1, 'B2'),
                        _mot(61, 1, 'C2'), _mot(91, 1, 'D2')),
            3: _lecture(_mot(1, 1, 'A3'), _mot(31, 1, 'B3'),
                        _mot(61, 1, 'C3'), _mot(91, 1, 'D3')),
        }
        with patch('anthropic.Anthropic', FauxUnifie):
            conv._extraire_avec_progres(images, 0)
        lues = {e.page: e for e in col.du_type(ev.PAGE_LUE)}
        # Page 2 est au rang 1 : des zones non vides prouvent la clé par numéro PDF (une clé
        # par rang chercherait la lecture 1, absente → aucune zone).
        self.assertTrue(lues[2].zones)
        self.assertEqual(lues[2].zones[0]['ligne'], 0)
        self.assertTrue(lues[3].zones)


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
        self.assertEqual(alertes[0].page_imprimee, '7')

    def test_page_zones_emis_une_fois_apres_coup(self):
        tpl = TemplateManager().get('Bornier standard')
        col = Collecteur()
        conv = Converter(word_file=self.tmp, output_dir=self.tmp / 'o', template=tpl,
                         on_log=lambda m: None, on_evenement=col)
        lecture = _lecture(_mot(1, 1, 'A2'), _mot(31, 1, 'B2'),
                           _mot(61, 1, 'C2'), _mot(91, 1, 'D2'))
        resultat = {'success': True, 'metadata': {'PAGE': '2'},
                    'rows': [{'type': 'data', 'cells': ['A2', 'B2', 'C2', 'D2']}]}
        conv._emettre_page_zones(2, resultat, lecture)
        conv._emettre_page_zones(2, resultat, lecture)   # déjà émis → ignoré
        zones_ev = col.du_type(ev.PAGE_ZONES)
        self.assertEqual(len(zones_ev), 1)
        self.assertEqual(zones_ev[0].page, 2)
        self.assertEqual(zones_ev[0].zones[0]['ligne'], 0)


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
        fins = col.du_type(ev.FIN)
        self.assertEqual(len(fins), 1)
        self.assertEqual(fins[0].etat, 'terminee')

    def test_fin_etat_arretee_si_annule(self):
        # Annulation après la 1re page (une page lue, Excel partiel écrit) : fin = 'arretee'.
        class _AnnuleApresPremiere:
            def __init__(self):
                self._appels = 0

            def is_set(self):
                self._appels += 1
                return self._appels > 1

        col = Collecteur()
        Config.CLAUDE_MODE_LOT = False
        Config.CLAUDE_CACHE_DOSSIER = self.tmp / 'cann'
        self._raz_client()
        conv = Converter(word_file=self._images(2), output_dir=self.tmp / 'outann',
                         template=self.template, on_log=lambda m: None,
                         on_evenement=col, cancel_event=_AnnuleApresPremiere())
        with patch('anthropic.Anthropic', FauxUnifie):
            conv.run()
        self.assertEqual(col.du_type(ev.FIN)[0].etat, 'arretee')

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


class TestEcouteurRobuste(unittest.TestCase):
    """Correction 3 : un écouteur qui lève ne fait jamais échouer la conversion."""

    def _rejeu(self, on_evenement):
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

    def test_ecouteur_qui_leve_n_interrompt_pas_et_excel_identique(self):
        def leveur(_e):
            raise RuntimeError("écouteur cassé")
        sans = self._rejeu(None)
        avec = self._rejeu(leveur)          # ne doit pas lever
        self.assertEqual(sans, avec)


if __name__ == '__main__':
    unittest.main()
