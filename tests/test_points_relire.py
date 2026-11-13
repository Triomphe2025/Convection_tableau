"""
points_relire.py (phase 1B, étape 4, commit 2) : construction pure des points à relire.

Invariant sur un cas fabriqué portant les SIX sortes de cellule : chaque cellule de Borniers qui
porte un fond de la légende a son point, et chaque point à cellule_excel désigne une cellule qui
porte le fond ET le commentaire de sa sorte. (L'invariant sur les 4 cas du filet, de bout en
bout, est au commit 3, une fois le Converter câblé.)
"""
import json
import tempfile
import unittest
from pathlib import Path

import openpyxl

import pdf_extractor as pe
import points_relire as pr
from config import Config
from generer_classeur import OMISSION, generer_excel
from template import TemplateManager

_COULEUR_DE_SORTE = {
    'confiance_basse': Config.COULEUR_CONFIANCE_BASSE.upper(),
    'illisible': Config.COULEUR_ILLISIBLE.upper(),
    'corrige': Config.COULEUR_CORRIGE.upper(),
    'conservation': Config.COULEUR_CONSERVATION.upper(),
    'qualite': Config.COULEUR_QUALITE.upper(),
    'deduit': Config.COULEUR_DEDUIT.upper(),
}


def _rgb(cellule):
    return str(cellule.fill.fgColor.rgb)[-6:].upper() if cellule.fill.fill_type == 'solid' else ''


def _page(page, pet, data_colors=False, **extra):
    pied = [f"P.E.T. : {pet or ''}      JARRETIERAGE",
            f"N° PLAN  : 223400PE137     |  INDICE : R  |   PAGE : {page}"]
    meta = {'PAGE': str(page), 'NO_PLAN': '223400PE137', 'INDICE': 'R', 'PIED_BRUT': pied,
            'BORNIER': 'B702A'}
    if pet:
        meta['PET'] = pet
    base = {'success': True, 'headers': ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL'],
            'image_path': f'page_{page}', 'detection_method': 'pdf-grille', 'metadata': meta,
            '_page_pdf': page}
    if data_colors:
        base['rows'] = [
            {'type': 'data', 'cells': ['01', 'J', 'PF', 'TC1'], 'confidence': [50, 100, 100, 100]},
            {'type': 'data', 'cells': ['02', '??', 'PF', 'TC2'], 'confidence': [100] * 4},
            {'type': 'data', 'cells': ['03A', 'J', 'PF', 'TC3'], 'confidence': [100] * 4,
             'corrections_o': {0: 'O3A'}},
        ]
        base['a_verifier'] = [
            {'ligne': 0, 'colonne': 3, 'type': OMISSION,
             'message': 'élément peut-être omis', 'lecture': 'TC1X'},
            {'ligne': 1, 'colonne': 2, 'type': 'cohérence',
             'message': 'lu « PF », peut-être « PE » (lexique de référence)'},
        ]
    else:
        base['rows'] = [{'type': 'data', 'cells': ['PH', 'J', 'PF', 'X'], 'confidence': [100] * 4}]
    base.update(extra)
    return base


def _classeur(pages):
    tpl = TemplateManager().get('REPARTITEUR')
    extractor = pe.PdfTableExtractor(tpl)
    d = tempfile.mkdtemp()
    sortie = Path(d) / 's.xlsx'
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        generer_excel(pages, extractor, sortie)
    ws = openpyxl.load_workbook(sortie)['Borniers']
    return ws


class TestInvariantToutesLesSortes(unittest.TestCase):

    def setUp(self):
        # Page 1 : les 5 couleurs de cellule ; page 2 : P.E.T. vide → deduit sur le pied.
        self.pages = [_page(1, pet='EPEULE', data_colors=True), _page(2, pet=None)]
        self.ws = _classeur(self.pages)
        self.obj = pr.construire(self.pages, self.ws, document='doc', modele='M')
        self.pts_cell = [p for p in self.obj['points'] if p['cellule_excel']]

    def _cellules_colorees(self):
        return {c.coordinate: _rgb(c) for ligne in self.ws.iter_rows() for c in ligne
                if _rgb(c) in _COULEUR_DE_SORTE.values()}

    def test_les_six_sortes_sont_presentes(self):
        sortes = {p['sorte'] for p in self.pts_cell}
        assert sortes == set(_COULEUR_DE_SORTE), sortes

    def test_chaque_cellule_coloree_a_un_point(self):
        colorees = set(self._cellules_colorees())
        assert {p['cellule_excel'] for p in self.pts_cell} == colorees

    def test_chaque_point_designe_une_cellule_au_bon_fond_et_commentee(self):
        for p in self.pts_cell:
            cellule = self.ws[p['cellule_excel']]
            assert _rgb(cellule) == _COULEUR_DE_SORTE[p['sorte']], p
            assert cellule.comment is not None, p

    def test_id_stable_unique_et_etat_a_voir(self):
        ids = [p['id'] for p in self.obj['points']]
        assert len(ids) == len(set(ids))
        assert all(p['etat'] == 'a_voir' for p in self.obj['points'])

    def test_enrichissement_suggestion_bornier_page(self):
        qualite = next(p for p in self.pts_cell if p['sorte'] == 'qualite')
        assert qualite['suggestion'] == 'PE'           # « peut-être « PE » »
        assert qualite['bornier'] == 'B702A'
        assert qualite['page_imprimee'] == '1'         # bloc qualité placé sur la page 1
        assert qualite['colonne'] == 'ABOUTISSANT'


class TestEnveloppeEtEcriture(unittest.TestCase):

    def test_objet_englobant_et_ecriture(self):
        pages = [_page(1, pet='EPEULE', data_colors=True), _page(2, pet=None)]
        ws = _classeur(pages)
        obj = pr.construire(pages, ws, document='223400PE137', empreinte='abc',
                            excel='s.xlsx', type_doc='Répartiteur', modele='claude-opus-5-5',
                            arrete=True)
        assert obj['version'] == 1
        assert obj['arrete'] is True
        assert obj['document'] == '223400PE137' and obj['empreinte'] == 'abc'
        with tempfile.TemporaryDirectory() as d:
            chemin = pr.ecrire(obj, Path(d) / '223400PE137_points.json')
            relu = json.loads(Path(chemin).read_text(encoding='utf-8'))
        assert relu['version'] == 1 and relu['points']
        assert relu['arrete'] is True


class TestZoneCellule(unittest.TestCase):

    def _point_confiance(self, result_extra):
        page = _page(1, pet='EPEULE', data_colors=True, **result_extra)
        ws = _classeur([page, _page(2, pet='EPEULE')])
        obj = pr.construire([page, _page(2, pet='EPEULE')], ws)
        return next(p for p in obj['points'] if p['sorte'] == 'confiance_basse')

    def test_zone_cellule_coupee_aux_bornes(self):
        p = self._point_confiance({'zones': [{'ligne': 0, 'boite': [0.1, 0.2, 0.9, 0.3]}],
                                   'bornes_colonnes': [0.0, 0.25, 0.5, 0.75, 1.0]})
        assert p['zone'] == {'niveau': 'cellule', 'boite': [0.0, 0.2, 0.25, 0.3]}  # colonne 0

    def test_zone_ligne_sans_bornes(self):
        p = self._point_confiance({'zones': [{'ligne': 0, 'boite': [0.1, 0.2, 0.9, 0.3]}]})
        assert p['zone'] == {'niveau': 'ligne', 'boite': [0.1, 0.2, 0.9, 0.3]}

    def test_zone_none_sans_positions(self):
        p = self._point_confiance({})
        assert p['zone'] is None


if __name__ == '__main__':
    unittest.main()
