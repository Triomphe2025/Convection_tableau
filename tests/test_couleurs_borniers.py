"""
Prérequis de l'étape 4 (points à relire) : filet qui garantit que les SIX couleurs de la
légende sont bien posées — et commentées — sur des cellules de la feuille « Borniers ».

conservation, qualite, corrige, illisible, confiance_basse (cellules de données) et deduit
(cellule de pied). Écrit avant de toucher aux alertes ; vert sur le code actuel. Les points de
l'étape 4 devront désigner exactement ces cellules.
"""
import tempfile
import unittest
from pathlib import Path

import openpyxl

import pdf_extractor as pe
from config import Config
from generer_classeur import OMISSION, generer_excel, ligne_excel
from template import TemplateManager


def _page_repartiteur(page, pet=None):
    """Page REPARTITEUR avec un pied brut où P.E.T. est lu ou laissé vide (déduction)."""
    pied = [f"P.E.T. : {pet or ''}      JARRETIERAGE",
            f"N° PLAN  : 223400PE137     |  INDICE : R  |   PAGE : {page}"]
    meta = {'PAGE': str(page), 'NO_PLAN': '223400PE137', 'INDICE': 'R', 'PIED_BRUT': pied}
    if pet:
        meta['PET'] = pet
    return {'success': True, 'headers': ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL'],
            'image_path': f'page_{page}', 'detection_method': 'pdf-grille', 'metadata': meta,
            'rows': [{'type': 'data', 'cells': ['PH 01', '0792N', 'PF 12', 'X'],
                      'confidence': [100] * 4}]}


def _resultat_cinq_couleurs():
    """Un bornier (Bornier standard) qui porte les 5 couleurs de cellule de données."""
    tpl = TemplateManager().get('Bornier standard')
    rows = [
        # ligne 0 : confiance basse sur BORNE (col 0) ; omission sur JARRETIERES (col 3).
        {'type': 'data', 'cells': ['01', 'ROUGE', 'TC1', 'J1'],
         'confidence': [50, 100, 100, 100]},
        # ligne 1 : illisible sur COULEUR (col 1) ; qualité sur SIGNAL (col 2).
        {'type': 'data', 'cells': ['02', '??', 'TC2', 'J2'],
         'confidence': [100, 100, 100, 100]},
        # ligne 2 : coquille O/0 corrigée sur JARRETIERES (col 3).
        {'type': 'data', 'cells': ['03', 'BLANC', 'TC3', 'J3'],
         'confidence': [100, 100, 100, 100], 'corrections_o': {3: 'O1A'}},
    ]
    a_verifier = [
        {'ligne': 0, 'colonne': 3, 'type': OMISSION,
         'message': 'élément peut-être omis', 'lecture': 'J1X'},
        {'ligne': 1, 'colonne': 2, 'type': 'cohérence',
         'message': 'lu « TC2 », peut-être « TG2 » (lexique de référence)'},
    ]
    result = {'success': True, 'headers': tpl.columns, 'rows': rows,
              'metadata': {'CABLE': 'ACC', 'TYPE': 'X', 'NO_PLAN': 'PE001',
                           'INDICE': 'R', 'PAGE': '7'},
              'a_verifier': a_verifier, 'detection_method': 'claude-vision', 'blur_pct': 0.0}
    return pe.PdfTableExtractor(tpl), result


def _rgb(cellule):
    return str(cellule.fill.fgColor.rgb)[-6:].upper()


class TestCouleursBorniers(unittest.TestCase):

    def _generer(self, pages, tpl_nom='Bornier standard', extractor=None):
        tpl = TemplateManager().get(tpl_nom)
        extractor = extractor or pe.PdfTableExtractor(tpl)
        with tempfile.TemporaryDirectory() as d:
            sortie = Path(d) / 'out.xlsx'
            generer_excel(pages, extractor, sortie)
            wb = openpyxl.load_workbook(sortie)
            return wb['Borniers']

    def test_cinq_couleurs_de_cellule_posees_et_commentees(self):
        extractor, result = _resultat_cinq_couleurs()
        ws = self._generer([result], extractor=extractor)
        debut = 1
        attendus = {
            (ligne_excel(debut, result, 0), 1): Config.COULEUR_CONFIANCE_BASSE,  # BORNE conf 50
            (ligne_excel(debut, result, 1), 2): Config.COULEUR_ILLISIBLE,        # « ?? »
            (ligne_excel(debut, result, 2), 4): Config.COULEUR_CORRIGE,          # coquille O/0
            (ligne_excel(debut, result, 0), 4): Config.COULEUR_CONSERVATION,     # omission
            (ligne_excel(debut, result, 1), 3): Config.COULEUR_QUALITE,          # cohérence
        }
        for (r, c), couleur in attendus.items():
            cellule = ws.cell(row=r, column=c)
            self.assertEqual(_rgb(cellule), couleur.upper(),
                             f"couleur {couleur} attendue en ({r},{c})")
            self.assertIsNotNone(cellule.comment, f"commentaire attendu en ({r},{c})")

    def test_deduit_sur_cellule_de_pied(self):
        # 2 pages : la P.E.T. est présente sur l'une, vide sur l'autre → déduite et colorée
        # (generer_excel fait la déduction en interne).
        pages = [_page_repartiteur(1, pet='EPEULE'), _page_repartiteur(2, pet=None)]
        ws = self._generer(pages, tpl_nom='REPARTITEUR')
        deduites = [c for ligne in ws.iter_rows() for c in ligne
                    if c.fill.fill_type == 'solid'
                    and _rgb(c) == Config.COULEUR_DEDUIT.upper()]
        self.assertTrue(deduites, "au moins une cellule de pied déduite colorée")
        self.assertTrue(all(c.comment is not None for c in deduites))


if __name__ == '__main__':
    unittest.main()
