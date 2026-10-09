"""
Commit B — indicateur de page et contrôle de conservation (controle_conservation.py),
sur des lectures Tesseract fabriquées puis sur pages réelles (réponses enregistrées).

Taux de divergence = mots Claude appariés (alignement du commit A) à un mot Tesseract de
texte différent / mots appariés ; page dégradée au-dessus de PAGE_DEGRADEE.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_controle_conservation.py -v
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from claude_ocr import _parse_pipe_response
from config import Config
from controle_conservation import analyser_page
from positions_scan import LecturePage, lire_page
from template import TemplateManager

PAS, PHASE = 10.0, 5.0
COLONNES = ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT']
TRAITS = [0.0, 300.0, 600.0, 900.0, 1200.0]
FIX = Path(__file__).parent / 'fixtures'


def _mot(col, ligne, texte, conf=90):
    x0 = PHASE + PAS * col
    return (x0, 100 * ligne, x0 + PAS * len(texte), 100 * ligne + 30, texte, conf)


def _lecture(*mots):
    return LecturePage(mots=list(mots), traits=list(TRAITS), dpi=300, taille=(1200, 2000))


def _ligne(*cellules):
    return {'type': 'data', 'cells': list(cellules), 'confidence': [100] * len(cellules)}


def _page(n_lignes, differents=()):
    """n lignes « A<i> | PH A104 <i> | SIG | PH TA106 <i> » ; Tesseract lit « FH » sur les
    lignes de `differents` (TENANT, 1er mot)."""
    rows, mots = [], []
    for i in range(1, n_lignes + 1):
        rows.append(_ligne(f'A{i}', f'PH A104 {i:02d}', 'SIG', f'PH TA106 {i:02d}'))
        mots += [_mot(1, i, f'A{i}'), _mot(31, i, 'FH' if i in differents else 'PH'),
                 _mot(37, i, 'A104'), _mot(47, i, f'{i:02d}'), _mot(61, i, 'SIG'),
                 _mot(91, i, 'PH'), _mot(97, i, 'TA106'), _mot(107, i, f'{i:02d}')]
    return rows, _lecture(*mots)


class TestTauxDeDivergence(unittest.TestCase):

    def test_lecture_identique(self):
        rows, lecture = _page(5)
        analyse = analyser_page(rows, COLONNES, lecture)
        self.assertEqual((analyse['divergences'], analyse['mots_apparies']), (0, 40))
        self.assertEqual(analyse['taux'], 0.0)
        self.assertFalse(analyse['degradee'])

    def test_mot_lu_autrement(self):
        rows, lecture = _page(5, differents=(2, 4))
        analyse = analyser_page(rows, COLONNES, lecture)
        self.assertEqual((analyse['divergences'], analyse['mots_apparies']), (2, 40))
        self.assertAlmostEqual(analyse['taux'], 0.05)

    def test_confusion_o_0_comptee(self):
        # Même définition que la mesure B0 : texte brut, sans repli O/0.
        rows, lecture = _page(1)
        rows[0]['cells'][1] = 'PH A104 O1'
        analyse = analyser_page(rows, COLONNES, lecture)
        self.assertEqual(analyse['divergences'], 1)

    def test_page_degradee_au_dessus_du_seuil(self):
        rows, lecture = _page(4, differents=(1, 2, 3, 4))       # 4 / 32 = 12,5 %
        self.assertTrue(analyser_page(rows, COLONNES, lecture)['degradee'])
        with patch.object(Config, 'PAGE_DEGRADEE', 0.125):
            self.assertFalse(analyser_page(rows, COLONNES, lecture)['degradee'])

    def test_sans_cadre_non_mesurable(self):
        rows, lecture = _page(2)
        lecture.traits = None
        analyse = analyser_page(rows, COLONNES, lecture)
        self.assertIsNone(analyse['taux'])
        self.assertFalse(analyse['degradee'])
        self.assertEqual(analyse['raison'], 'colonnes du cadre non trouvées')


@unittest.skipUnless(Path(Config.TESSERACT_PATH).exists(), "Tesseract absent")
class TestPagesReelles(unittest.TestCase):
    """Taux de la mesure B0 : PE011 p. 52 ≈ 29 %, PE133 p. 15 ≈ 5 %, PE012 p. 39 ≈ 1 %."""

    REPONSES = {(e['document'], e['page']): e['raw'] for e in map(
        json.loads, (FIX / 'positions_reponses_claude.jsonl').read_text('utf-8').splitlines())}

    def _analyser(self, document, page, gabarit):
        tpl = TemplateManager().get(gabarit)
        rows, _, _ = _parse_pipe_response(self.REPONSES[(document, page)], tpl)
        with fitz.open(str(FIX / document)) as doc:
            return analyser_page(rows, list(tpl.columns), lire_page(doc[page - 1]))

    def test_pe011_p52_degradee(self):
        analyse = self._analyser('223111PE011_extrait_10pages.pdf', 5, 'REPARTITEUR 2')
        self.assertTrue(analyse['degradee'])
        self.assertGreater(analyse['taux'], 0.2)

    def test_pe133_p15_propre(self):
        analyse = self._analyser('6A23111PE133_extrait_8pages.pdf', 6, 'REPARTITEUR')
        self.assertFalse(analyse['degradee'])
        self.assertLess(analyse['taux'], 0.08)

    def test_pe012_p39_propre(self):
        analyse = self._analyser('223111PE012_extrait_10pages.pdf', 8, 'Bornier standard')
        self.assertFalse(analyse['degradee'])
        self.assertLess(analyse['taux'], 0.03)


if __name__ == '__main__':
    unittest.main()


class TestConservation(unittest.TestCase):
    """Page propre : mot Tesseract sans mot Claude en face, ligne Tesseract sans ligne Claude."""

    def _page_avec(self, *mots_en_plus, lignes=4):
        rows, lecture = _page(lignes)
        lecture.mots += list(mots_en_plus)
        return rows, lecture

    def test_mot_omis_dans_la_cellule(self):
        rows, lecture = _page(4)
        rows[1]['cells'][1] = 'PH A104'                      # « 02 » omis par Claude
        analyse = analyser_page(rows, COLONNES, lecture)
        self.assertEqual([(o['ligne'], o['colonne'], o['lecture']) for o in analyse['omissions']],
                         [(1, 1, '02')])
        self.assertEqual(rows[1]['cells'][1], 'PH A104')    # la valeur de Claude est gardée

    def test_confiance_sous_le_seuil_ignoree(self):
        rows, lecture = _page(4)
        rows[1]['cells'][1] = 'PH A104'
        lecture.mots = [m if m[4] != '02' else m[:5] + (40,) for m in lecture.mots]
        self.assertEqual(analyser_page(rows, COLONNES, lecture)['omissions'], [])

    def test_mots_recolles_pas_une_omission(self):
        # 223111PE012 : Claude « 1 B », Tesseract « 1B » ; rien ne manque.
        rows, lecture = _page(3)
        rows[1]['cells'][2] = 'S IG'
        self.assertEqual(analyser_page(rows, COLONNES, lecture)['omissions'], [])

    def test_ligne_manquante_entre_deux_lignes(self):
        rows, lecture = _page(5)
        del rows[2]                                          # ligne 3 absente de Claude
        analyse = analyser_page(rows, COLONNES, lecture)
        self.assertEqual([(m['avant'], m['apres']) for m in analyse['lignes_manquantes']],
                         [(1, 2)])
        self.assertIn('A3', analyse['lignes_manquantes'][0]['lecture'])

    def test_ligne_peu_sure_ignoree(self):
        rows, lecture = _page(5)
        del rows[2]
        lecture.mots = [m if m[1] != 300 else m[:5] + (30,) for m in lecture.mots]
        self.assertEqual(analyser_page(rows, COLONNES, lecture)['lignes_manquantes'], [])

    def test_page_degradee_controle_impossible(self):
        rows, lecture = _page(4, differents=(1, 2, 3, 4))
        rows[1]['cells'][1] = 'PH A104'
        analyse = analyser_page(rows, COLONNES, lecture)
        self.assertTrue(analyse['controle_impossible'])
        self.assertEqual((analyse['omissions'], analyse['lignes_manquantes']), ([], []))

    def test_controle_desactive(self):
        rows, lecture = _page(4)
        rows[1]['cells'][1] = 'PH A104'
        with patch.object(Config, 'CONTROLE_CONSERVATION', False):
            analyse = analyser_page(rows, COLONNES, lecture)
        self.assertEqual((analyse['omissions'], analyse['lignes_manquantes']), ([], []))
        self.assertFalse(analyse['controle_impossible'])


@unittest.skipUnless(Path(Config.TESSERACT_PATH).exists(), "Tesseract absent")
class TestConservationPagesReelles(TestPagesReelles):
    """Réponses non modifiées des pages propres : aucune alerte de conservation."""

    def test_pe133_p15_sans_alerte(self):
        analyse = self._analyser('6A23111PE133_extrait_8pages.pdf', 6, 'REPARTITEUR')
        self.assertEqual((analyse['omissions'], analyse['lignes_manquantes']), ([], []))

    def test_pe012_p39_sans_alerte(self):
        analyse = self._analyser('223111PE012_extrait_10pages.pdf', 8, 'Bornier standard')
        self.assertEqual((analyse['omissions'], analyse['lignes_manquantes']), ([], []))
