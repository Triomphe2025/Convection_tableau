"""
Non-régression du classeur Excel produit par le pipeline.

L'instantané `fixtures/xlsx_baseline.json` a été pris AVANT l'ajout de la
fonctionnalité « vérification de conversion » : il prouve que celle-ci ne
change pas une seule cellule du .xlsx. Les données d'entrée sont fabriquées
et en mode `claude-vision`, donc indépendantes de Tesseract et du dictionnaire.

Régénérer volontairement l'instantané (changement voulu du format Excel) :
    env\\Scripts\\python.exe -m tests.test_non_regression_xlsx --regenerer
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

from generer_classeur import generer_excel
from ocr_processor import BornierTableExtractor
from template import DEFAULT_TEMPLATE

BASELINE = Path(__file__).parent / 'fixtures' / 'xlsx_baseline.json'


def _ligne(*cells):
    return {'type': 'data', 'cells': list(cells), 'confidence': [100] * len(cells)}


def _bornier(page, bornier, image, rows):
    return {
        'success': True,
        'headers': list(DEFAULT_TEMPLATE.columns),
        'rows': rows,
        'metadata': {
            'PAGE': page, 'BORNIER': bornier, 'PET': 'GARE TRAMWAY',
            'NO_PLAN': '6A 23111 PE 102', 'INDICE': 'R',
        },
        'image_path': image,
        'detection_method': 'claude-vision',
    }


def resultats_synthetiques():
    """Trois borniers fabriqués : section, lignes vides, colonnes vides."""
    b1 = _bornier('1', 'PA', 'page_001.png', [
        {'type': 'section', 'text': 'NOM DU CABLE : EPS/GAT'},
        _ligne('01', '1 G', 'COMMUN TS GR3 105TS', '0013B'),
        _ligne('02', '1 BC', 'EP. STAT/TS ENTRETIEN POMPE', '0017B'),
        _ligne('03', '1 I', 'EP.STAT/TS DISCORDANCE POMPE', '0033B'),
        {'type': 'blank', 'count': 1},
        _ligne('04', '2 J', 'RESERVE CABLEE', ''),
        _ligne('05', '', 'RESERVE CABLEE', ''),
    ])
    b2 = _bornier('2', 'PB', 'page_002.png', [
        _ligne('01A', 'BLANC', 'TC IDPO1', '0109R'),
        _ligne('01B', 'ROUGE', 'TC IDPO2', '0110W'),
        _ligne('02A', 'BLEU', 'FSI-31', '0111R'),
        _ligne('02B', 'NOIR', 'FSI-32', '0112W'),
    ])
    b3 = _bornier('3', 'PC', 'page_003.png', [
        _ligne('10', 'VERT', 'ALIM 24V', '0200B'),
        _ligne('11', 'JAUNE', 'ALIM 48V', '0201B'),
        _ligne('12', 'GRIS', 'RESERVE', '0202B'),
    ])
    return [b3, b1, b2]   # ordre volontairement mélangé : le tri par PAGE est testé


def dump_classeur(path):
    """Instantané JSON d'un classeur : valeurs, fusions, bordures, hauteurs."""
    wb = openpyxl.load_workbook(path)
    out = {}
    for ws in wb.worksheets:
        cells = {}
        for row in ws.iter_rows():
            for c in row:
                b = c.border
                info = {
                    'v': c.value,
                    'nf': c.number_format,
                    'bold': bool(c.font.b),
                    'sz': c.font.sz,
                    'fill': str(c.fill.fgColor.rgb) if c.fill.fill_type else None,
                    'al': [c.alignment.horizontal, c.alignment.vertical,
                           bool(c.alignment.wrap_text)],
                    'bd': [b.left.style, b.right.style, b.top.style, b.bottom.style],
                }
                if info['v'] is not None or any(info['bd']) or info['fill']:
                    cells[c.coordinate] = info
        out[ws.title] = {
            'cells': cells,
            'merged': sorted(str(r) for r in ws.merged_cells.ranges),
            'row_heights': {
                str(k): v.height for k, v in sorted(ws.row_dimensions.items()) if v.height
            },
            'col_widths': {
                k: v.width for k, v in sorted(ws.column_dimensions.items()) if v.width
            },
            'page_breaks': [brk.id for brk in ws.row_breaks.brk],
        }
    return json.loads(json.dumps(out, default=str))


def generer_instantane():
    extractor = BornierTableExtractor(template=DEFAULT_TEMPLATE)
    with tempfile.TemporaryDirectory() as tmp:
        cible = Path(tmp) / 'sortie.xlsx'
        generer_excel(resultats_synthetiques(), extractor, cible)
        return dump_classeur(cible)


class TestXlsxInchange(unittest.TestCase):

    def test_classeur_identique_a_l_instantane_d_avant_la_fonctionnalite(self):
        attendu = json.loads(BASELINE.read_text(encoding='utf-8'))
        obtenu = generer_instantane()
        self.assertEqual(sorted(obtenu), sorted(attendu), "feuilles différentes")
        for feuille, ref in attendu.items():
            cur = obtenu[feuille]
            self.assertEqual(cur['merged'], ref['merged'], f"{feuille} : fusions")
            self.assertEqual(cur['row_heights'], ref['row_heights'], f"{feuille} : hauteurs")
            self.assertEqual(cur['col_widths'], ref['col_widths'], f"{feuille} : largeurs")
            self.assertEqual(cur['page_breaks'], ref['page_breaks'], f"{feuille} : sauts")
            diff = [
                coord for coord in sorted(set(cur['cells']) | set(ref['cells']))
                if cur['cells'].get(coord) != ref['cells'].get(coord)
            ]
            self.assertEqual(diff, [], f"{feuille} : cellules différentes {diff[:10]}")

    def test_instantane_contient_du_contenu(self):
        attendu = json.loads(BASELINE.read_text(encoding='utf-8'))
        self.assertIn('Borniers', attendu)
        valeurs = [c['v'] for c in attendu['Borniers']['cells'].values()]
        self.assertIn('EP.STAT/TS DISCORDANCE POMPE', valeurs)


if __name__ == '__main__':
    if '--regenerer' in sys.argv:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(generer_instantane(), ensure_ascii=False, indent=1, sort_keys=True),
            encoding='utf-8',
        )
        print(f"Instantané écrit : {BASELINE}")
    else:
        unittest.main()
