"""
Compteur de lignes dans le convertisseur : fil à part sur un PDF fabriqué, mode 'ombre'
(journal et fichier de mesure, rien dans l'Excel ni dans l'ordre de validation), mode True
(alerte de page dans A VERIFIER, comptage incertain en information, synthèse), page relue.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_lignes_converter.py -v
"""
import contextlib
import io
import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import fitz
import openpyxl

from config import Config
from converter import Converter
from generer_classeur import entrees_cellules, entrees_syntheses_qualite, generer_excel
from pdf_extractor import PdfTableExtractor
from template import TemplateManager

TPL = TemplateManager().get('REPARTITEUR 2')


def _pdf_vectoriel(chemin: Path, lignes: int):
    """Page A4 vectorielle : cadre, trait sous l'en-tête, lignes à 12 pt, bas du tableau."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x in (30, 150, 300, 450, 565):
        page.draw_line((x, 40), (x, 760), width=0.8)
    for y in (40, 62, 760):
        page.draw_line((30, y), (565, y), width=0.8)
    page.insert_text((40, 56), "FIL   TENANT   SIGNAL   ABOUTISSANT", fontname='cour', fontsize=9)
    for k in range(lignes):
        page.insert_text((40, 80 + 12 * k), f"{k:02d} BC   PH A104 {k:02d}   RESERVE CABLEE",
                         fontname='cour', fontsize=9)
    page.insert_text((40, 790), "N° PLAN : 223111PE021   INDICE : R   PAGE : 1",
                     fontname='cour', fontsize=9)
    doc.save(str(chemin))


def _resultat(page_pdf, lues, numero=None):
    return {'success': True, 'headers': list(TPL.columns), '_page_pdf': page_pdf,
            'detection_method': 'claude-vision', 'metadata': {'PAGE': numero or str(page_pdf)},
            'rows': [{'type': 'data', 'cells': [str(k), 'PH A104 01', 'SIG', 'RA B1 17'],
                      'confidence': [100] * 4} for k in range(lues)]}


def _converter(journal):
    return Converter(word_file=Path('doc.pdf'), output_dir=Path(tempfile.gettempdir()),
                     template=TPL, on_log=journal.append)


def _future(comptes):
    future = Future()
    future.set_result(comptes)
    return future


def _compte(visibles, raison=None):
    return {'visibles': visibles, 'raison': raison, 'pas': 47.0, 'nature': 'scan',
            'duree': 0.4}


class TestCompterLignesPdf(unittest.TestCase):

    def test_pdf_vectoriel_compte_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'tableau.pdf'
            _pdf_vectoriel(pdf, 23)
            conv = Converter(word_file=pdf, output_dir=Path(tmp), template=TPL,
                             on_log=lambda m: None)
            comptes = conv._compter_lignes_pdf()
        self.assertEqual(comptes[1]['visibles'], 23)
        self.assertIsNone(comptes[1]['raison'])

    def test_fil_a_part_rend_un_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 'tableau.pdf'
            _pdf_vectoriel(pdf, 5)
            conv = Converter(word_file=pdf, output_dir=Path(tmp), template=TPL,
                             on_log=lambda m: None)
            self.assertEqual(conv._lancer_compte_lignes().result()[1]['visibles'], 5)


class TestModeOmbre(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = patch.object(Config, 'LIGNES_OMBRE_DOSSIER', Path(self._tmp.name))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _controler(self, mode, comptes, resultats):
        journal = []
        conv = _converter(journal)
        conv._compte_lignes = _future(comptes)
        with patch.object(Config, 'CONTROLE_LIGNES', mode):
            conv._controle_lignes(resultats)
        return conv, journal

    def _documents(self):
        # 20 pages : 2 écarts sur 19 comptées, sous le garde-fou des 20 %.
        comptes = {k: _compte(10) for k in range(1, 21)}
        comptes[2] = _compte(47)
        comptes[3] = _compte(13)
        comptes[4] = _compte(None, "trait sous l'en-tête non trouvé dans le haut du cadre")
        resultats = [_resultat(k, 10) for k in range(1, 21)]
        resultats[1] = _resultat(2, 46)
        return comptes, resultats

    def test_ombre_rien_dans_les_resultats_tout_au_journal(self):
        comptes, resultats = self._documents()
        _, journal = self._controler('ombre', comptes, resultats)
        self.assertFalse(any(r.get('a_verifier') for r in resultats))
        prefixe = "  ℹ nombre de lignes, scans (mode ombre)"
        self.assertIn(f"{prefixe} p. 2 : 47 lignes visibles, 46 lues", journal)
        self.assertIn(f"{prefixe} p. 3 : comptage incertain (écart de 3 lignes : 13 visibles, "
                      "10 lues)", journal)
        self.assertTrue(any('p. 4 : comptage impossible' in m for m in journal))

    def test_ombre_fichier_de_mesure(self):
        comptes, resultats = self._documents()
        self._controler('ombre', comptes, resultats)
        fichier = next(Path(self._tmp.name).glob('doc_*.jsonl'))
        mesures = [json.loads(lg) for lg in fichier.read_text('utf-8').splitlines()]
        self.assertEqual(len(mesures), 20)
        self.assertEqual({k: mesures[1][k] for k in ('page_pdf', 'visibles', 'lues', 'decision')},
                         {'page_pdf': 2, 'visibles': 47, 'lues': 46, 'decision': 'alerte'})

    def test_true_alerte_de_page_dans_a_verifier(self):
        comptes, resultats = self._documents()
        _, journal = self._controler(True, comptes, resultats)
        self.assertEqual(resultats[1]['a_verifier'], [{
            'ligne': None, 'colonne': None, 'type': 'nombre de lignes',
            'message': '47 lignes visibles, 46 lues', 'lecture': None, 'lignes': True}])
        self.assertFalse(resultats[2].get('a_verifier'))      # incertain : information seule
        self.assertIn("  ⚠ p. 2 : 47 lignes visibles, 46 lues", journal)
        entree = entrees_cellules([resultats[1]])[0]
        self.assertEqual((entree['ligne'], entree['colonne'], entree['type']),
                         (None, None, 'nombre de lignes'))

    def test_true_synthese_si_plus_de_20_pour_cent(self):
        comptes = {k: _compte(11) for k in range(1, 5)}
        resultats = [_resultat(k, 10) for k in range(1, 5)]
        self._controler(True, comptes, resultats)
        self.assertFalse(any(r.get('a_verifier') for r in resultats))
        syntheses = entrees_syntheses_qualite(resultats)
        self.assertEqual([s['type'] for s in syntheses], ['nombre de lignes'])
        self.assertIn('écart sur 4 pages sur 4', syntheses[0]['message'])

    def test_true_page_relue_alerte_refaite(self):
        comptes, resultats = self._documents()
        conv, _ = self._controler(True, comptes, resultats)
        with patch.object(Config, 'CONTROLE_LIGNES', True):
            relue = _resultat(2, 47)
            conv._alerte_lignes_relue(relue)
            self.assertFalse(relue.get('a_verifier'))
            relue = _resultat(2, 45)
            conv._alerte_lignes_relue(relue)
        self.assertEqual(relue['a_verifier'][0]['message'], '47 lignes visibles, 45 lues')

    def test_true_excel_ligne_de_page_sans_colonne(self):
        comptes, resultats = self._documents()
        self._controler(True, comptes, resultats)
        sortie = Path(self._tmp.name) / 's.xlsx'
        with contextlib.redirect_stdout(io.StringIO()):
            generer_excel(resultats, PdfTableExtractor(TPL), sortie, on_log=lambda m: None)
        lignes = [[c.value for c in r] for r in openpyxl.load_workbook(sortie)['A VERIFIER']
                  .iter_rows()]
        self.assertIn(['2', None, None, 'nombre de lignes', '47 lignes visibles, 46 lues',
                       None], [r[:6] for r in lignes])

    def test_valeur_par_defaut_ombre(self):
        self.assertEqual(Config.CONTROLE_LIGNES, 'ombre')


if __name__ == '__main__':
    unittest.main()


class TestPagesVectoriellesEtPagesPerdues(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = patch.object(Config, 'LIGNES_OMBRE_DOSSIER', Path(self._tmp.name))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _controler(self, comptes, resultats, scans='ombre', vect=True):
        journal = []
        conv = _converter(journal)
        conv._compte_lignes = _future(comptes)
        with patch.object(Config, 'CONTROLE_LIGNES', scans), \
                patch.object(Config, 'CONTROLE_LIGNES_VECTORIEL', vect):
            conv._controle_lignes(resultats)
        return journal

    @staticmethod
    def _vect(visibles):
        return dict(_compte(visibles), nature='vectoriel')

    def test_vectoriel_tout_ecart_est_une_alerte_sans_garde_fou(self):
        comptes = {1: self._vect(30), 2: self._vect(35), 3: self._vect(10)}
        resultats = [_resultat(1, 0), _resultat(2, 30), _resultat(3, 10)]
        self._controler(comptes, resultats)
        self.assertEqual(resultats[0]['a_verifier'][0]['message'], '30 lignes visibles, 0 lues')
        self.assertEqual(resultats[1]['a_verifier'][0]['message'], '35 lignes visibles, 30 lues')
        self.assertFalse(resultats[2].get('a_verifier'))
        self.assertFalse(any(r.get('syntheses_lignes') for r in resultats))

    def test_scan_page_perdue_alerte_meme_en_ombre(self):
        comptes = {k: _compte(10) for k in range(1, 6)}
        comptes[3] = _compte(28)
        resultats = [_resultat(k, 10) for k in range(1, 6)]
        resultats[2] = _resultat(3, 0)
        journal = self._controler(comptes, resultats, scans='ombre')
        self.assertEqual(resultats[2]['a_verifier'][0]['message'],
                         '28 lignes visibles, aucune lue')
        self.assertIn('  ⚠ p. 3 : 28 lignes visibles, aucune lue', journal)

    def test_scan_ombre_ecart_ordinaire_rien_dans_les_resultats(self):
        comptes = {k: _compte(10) for k in range(1, 11)}
        comptes[2] = _compte(11)
        resultats = [_resultat(k, 10) for k in range(1, 11)]
        self._controler(comptes, resultats, scans='ombre')
        self.assertFalse(any(r.get('a_verifier') for r in resultats))

    def test_vectoriel_coupe(self):
        comptes = {1: self._vect(30)}
        resultats = [_resultat(1, 0)]
        self._controler(comptes, resultats, vect=False)
        self.assertFalse(resultats[0].get('a_verifier'))

    def test_information_pas_une_alerte_dans_l_ordre(self):
        from converter import nombre_alertes
        r = _resultat(1, 3)
        r['a_verifier'] = [{'ligne': None, 'type': 'information'}]
        self.assertEqual(nombre_alertes(r), 0)
        r['a_verifier'].append({'ligne': None, 'type': 'nombre de lignes'})
        self.assertEqual(nombre_alertes(r), 1)

    def test_defauts(self):
        self.assertEqual((Config.CONTROLE_LIGNES, Config.CONTROLE_LIGNES_VECTORIEL),
                         ('ombre', True))
