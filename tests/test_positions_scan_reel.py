"""
Commit A sur pages réelles : réponses de Claude enregistrées (positions_reponses_claude.jsonl,
texte seul) et Tesseract en local, sans appel API. Positions d'origine contre la vérité :
223111PE011 p. 52, 6A23111PE133 p. 15, 223111PE012 p. 39 (section comprise) ; aucun mot
déplacé à tort (223111PE011 p. 1 : QTEL2 09 reste dans TENANT).

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_positions_scan_reel.py -v
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import fitz

from claude_ocr import _parse_pipe_response
from config import Config
from generer_classeur import generer_excel
from mesure_precision import mesurer
from mesurer_precision import lire_verite_excel, lire_xlsx
from pdf_extractor import PdfTableExtractor
from positions_scan import lire_page, placer_page
from template import TemplateManager

FIX = Path(__file__).parent / 'fixtures'
REPONSES = {(e['document'], e['page']): e['raw'] for e in map(
    json.loads, (FIX / 'positions_reponses_claude.jsonl').read_text('utf-8').splitlines())}
TESSERACT = Path(Config.TESSERACT_PATH).exists()


def _placer(document, page, gabarit):
    tpl = TemplateManager().get(gabarit)
    rows, meta, _ = _parse_pipe_response(REPONSES[(document, page)], tpl)
    with fitz.open(str(FIX / document)) as doc:
        lecture = lire_page(doc[page - 1])
    places, bilan = placer_page(rows, list(tpl.columns), lecture)
    resultat = {'success': True, 'headers': list(tpl.columns), 'metadata': meta,
                'rows': places, 'image_path': f'page_{page:03d}.png',
                'detection_method': 'claude-vision'}
    return tpl, rows, resultat, bilan


def _mesure(tpl, resultat, verite, index):
    with tempfile.TemporaryDirectory() as tmp:
        sortie = Path(tmp) / 's.xlsx'
        with contextlib.redirect_stdout(io.StringIO()):
            generer_excel([resultat], PdfTableExtractor(tpl), sortie, on_log=lambda m: None)
        converti = lire_xlsx(sortie)
    pages, colonnes = lire_verite_excel(FIX / verite)
    return mesurer(pages[index:index + 1], converti, colonnes)


def _debut_2e_mot(row, k):
    return row['debuts'][k][1]


@unittest.skipUnless(TESSERACT, "Tesseract absent")
class TestPE011Page52(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tpl, cls.lus, cls.resultat, cls.bilan = _placer(
            '223111PE011_extrait_10pages.pdf', 5, 'REPARTITEUR 2')

    # Lignes 18 et 32 : Tesseract n'y lit aucun mot (rien entre les lignes voisines) ;
    # sans boîte, aucune position n'est inventée, la cellule garde les espaces lus.
    LIGNES_SANS_LECTURE = (18, 32)

    def test_tenant_et_aboutissant_en_colonnes_0_6_16(self):
        donnees = [r for r in self.resultat['rows'] if r['type'] == 'data']
        self.assertEqual([n for n, r in enumerate(donnees, start=1) if 'debuts' not in r],
                         list(self.LIGNES_SANS_LECTURE))
        for n, row in enumerate(donnees, start=1):
            for k in (1, 3):
                if 'debuts' in row and len(row['cells'][k].split()) == 3:
                    self.assertEqual(row['debuts'][k], [0, 6, 16], (n, row['cells']))

    def test_seules_les_lignes_non_lues_par_tesseract_restent_fausses(self):
        rapport = _mesure(self.tpl, self.resultat, '223111PE011_extrait_verite.xlsx', 4)
        self.assertEqual(sorted((e.ligne_ref + 1, e.colonne, e.decalages_conv)
                                for e in rapport.ecarts_positions),
                         [(18, 'ABOUTISSANT', (0, 3, 9)), (18, 'TENANT', (0, 3, 8)),
                          (32, 'ABOUTISSANT', (0, 3, 9)), (32, 'TENANT', (0, 3, 8))])
        self.assertEqual(rapport.ecarts_cellules, [])


@unittest.skipUnless(TESSERACT, "Tesseract absent")
class TestPE133Page15(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tpl, cls.lus, cls.resultat, cls.bilan = _placer(
            '6A23111PE133_extrait_8pages.pdf', 6, 'REPARTITEUR')
        cls.donnees = [r for r in cls.resultat['rows'] if r['type'] == 'data']

    def test_2e_mot_de_tenant(self):
        for n, row in enumerate(self.donnees, start=1):
            if len(row['cells'][0].split()) == 2:
                self.assertEqual(_debut_2e_mot(row, 0), 11 if 33 <= n <= 40 else 10,
                                 f"ligne {n} {row['cells'][0]!r}")

    def test_2e_mot_d_aboutissant_lignes_31_32(self):
        self.assertEqual([_debut_2e_mot(self.donnees[n - 1], 2) for n in (31, 32)], [11, 11])

    def test_aucune_position_fausse_contre_la_verite(self):
        rapport = _mesure(self.tpl, self.resultat, '6A23111PE133_extrait_verite.xlsx', 2)
        self.assertEqual(rapport.ecarts_positions, [])
        # Seul écart de contenu : « TRANS. » lu sur une tache (RC 20), compté.
        self.assertEqual([(e.valeur_ref, e.valeur_conv) for e in rapport.ecarts_cellules],
                         [('TRANS C200 STM/PCC SECOURS', 'TRANS. C200 STM/PCC SECOURS')])


@unittest.skipUnless(TESSERACT, "Tesseract absent")
class TestPE012Page39(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tpl, cls.lus, cls.resultat, cls.bilan = _placer(
            '223111PE012_extrait_10pages.pdf', 8, 'Bornier standard')

    def test_section_comme_la_verite(self):
        section = next(r for r in self.resultat['rows'] if r['type'] == 'section')
        self.assertEqual(section['debuts'], {0: [0, 4, 7, 13, 18]})

    def test_aucune_position_fausse_contre_la_verite(self):
        rapport = _mesure(self.tpl, self.resultat, '223111PE012_extrait_verite.xlsx', 4)
        self.assertEqual(rapport.ecarts_positions, [])
        self.assertEqual(rapport.ecarts_cellules, [])


@unittest.skipUnless(TESSERACT, "Tesseract absent")
class TestPE011Page123CadreOuvertADroite(unittest.TestCase):
    """Page sans bord droit de cadre : les positions sont posées (avant : non recalculées)."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, cls.lus, cls.resultat, cls.bilan = _placer(
            '223111PE011_extrait_10pages.pdf', 10, 'REPARTITEUR 2')

    def test_positions_posees(self):
        self.assertIsNone(self.bilan['raison'])
        self.assertEqual(self.bilan['deplaces'], [])

    def test_tenant_et_aboutissant_comme_les_autres_pages(self):
        premiere = next(r for r in self.resultat['rows'] if r['type'] == 'data')
        self.assertEqual(premiere['cells'][1], 'PH PG 01')
        self.assertEqual(premiere['debuts'][1], [0, 6, 16])
        self.assertEqual(premiere['debuts'][3][:3], [0, 6, 16])


@unittest.skipUnless(TESSERACT, "Tesseract absent")
class TestPE011Page52LigneRetiree(unittest.TestCase):
    """Lignes presque identiques : une ligne retirée ne fait plus glisser l'appariement."""

    def test_ligne_de_tesseract_du_trou_reste_libre(self):
        from positions_scan import apparier_rangs, lignes_page
        tpl = TemplateManager().get('REPARTITEUR 2')
        rows, _, _ = _parse_pipe_response(
            REPONSES[('223111PE011_extrait_10pages.pdf', 5)], tpl)
        with fitz.open(str(FIX / '223111PE011_extrait_10pages.pdf')) as doc:
            lignes = lignes_page(lire_page(doc[4]), list(tpl.columns))['lignes']
        _, avant = apparier_rangs(rows, lignes)
        retiree = next(i for i, r in enumerate(rows) if r.get('cells', [''])[0] == '15B/M')
        _, apres = apparier_rangs(rows[:retiree] + rows[retiree + 1:], lignes)
        self.assertNotIn(avant[retiree], apres.values())
        for i, li in avant.items():
            if i > retiree:
                self.assertEqual(apres.get(i - 1), li, rows[i]['cells'])


@unittest.skipUnless(TESSERACT, "Tesseract absent")
class TestPE011Page1AucunDeplacementATort(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tpl, cls.lus, cls.resultat, cls.bilan = _placer(
            '223111PE011_extrait_10pages.pdf', 1, 'REPARTITEUR 2')

    def test_qtel2_09_reste_dans_tenant(self):
        row = next(r for r in self.resultat['rows']
                   if r['type'] == 'data' and 'QTEL2' in ' '.join(r['cells']))
        self.assertIn('QTEL2 09', ' '.join(row['cells'][1].split()))
        self.assertEqual(' '.join(row['cells'][2].split()), 'TEL PMS Q1')

    def test_contenu_et_cellules_identiques_a_la_lecture(self):
        self.assertEqual(self.bilan['deplaces'], [])
        for avant, apres in zip(self.lus, self.resultat['rows']):
            self.assertEqual(avant.get('cells'), apres.get('cells'))


if __name__ == '__main__':
    unittest.main()
