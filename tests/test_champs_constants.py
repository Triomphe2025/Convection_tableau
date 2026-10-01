"""
Champs constants d'un document (config.py, P.E.T. par défaut).

Une case vide est reprise des autres pages du MÊME document seulement si toutes
celles qui portent le champ donnent la même valeur (pas de vote majoritaire) ;
la cellule est colorée et commentée. Une valeur lue n'est jamais remplacée.
INDICE, PAGE, TYPE et CABLE ne sont jamais repris.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_champs_constants.py -v
"""
import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

import pdf_extractor as pe
from config import Config
from generer_classeur import (champs_constants, deduire_champs_constants, generer_excel,
                              marquer_deduits)
from pied_page import inserer_valeur, libelle_affiche
from template import TemplateManager

DEDUIT = "déduit des autres pages du document"


def _page(page, pet=None, **meta):
    """Page de tableau REPARTITEUR avec un pied brut où P.E.T. est lu ou laissé vide."""
    pied = [f"P.E.T. : {pet or ''}      JARRETIERAGE",
            f"N° PLAN  : 223400PE137     |  INDICE : R  |   PAGE : {page}"]
    meta = dict(meta, PAGE=str(page), NO_PLAN='223400PE137', INDICE='R', PIED_BRUT=pied)
    if pet:
        meta['PET'] = pet
    return {'success': True, 'headers': ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL'],
            'image_path': f'page_{page}', 'detection_method': 'pdf-grille',
            'metadata': meta,
            'rows': [{'type': 'data', 'cells': ['PH 01', '0792N', 'PF 12', 'X'],
                      'confidence': [100] * 4}]}


def _document(valeurs):
    return [_page(i + 1, v) for i, v in enumerate(valeurs)]


class _Classeur(unittest.TestCase):

    def _generer(self, pages):
        tpl = TemplateManager().get('REPARTITEUR')
        messages = []
        with tempfile.TemporaryDirectory() as tmp:
            sortie = Path(tmp) / 's.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                generer_excel(pages, pe.PdfTableExtractor(tpl), sortie,
                              on_log=messages.append)
            ws = openpyxl.load_workbook(sortie).worksheets[0]
            pieds = [ws.cell(row=c.row - 1, column=2) for c in ws['B']
                     if isinstance(c.value, str) and 'INDICE' in c.value]
        return [m.strip() for m in messages if '⚠' in m], pieds


class TestQuaranteSeptEpeuleEtUneVide(_Classeur):

    def test_remplie_coloree_commentee(self):
        alertes, pieds = self._generer(_document(['EPEULE'] * 47 + [None]))
        self.assertEqual(len(pieds), 48)
        self.assertIn('EPEULE', pieds[47].value)
        self.assertEqual(pieds[47].fill.fgColor.rgb, '00' + Config.COULEUR_DEDUIT)
        self.assertIn(DEDUIT, pieds[47].comment.text)
        self.assertTrue(all(c.comment is None and c.fill.fill_type is None
                            for c in pieds[:47]))
        self.assertFalse([a for a in alertes if 'P.E.T.' in a or 'PET' in a])


class TestAutresPagesPasUnanimes(_Classeur):

    def test_vide_et_alerte(self):
        alertes, pieds = self._generer(_document(['EPEULE'] * 46 + ['GRAND-BUT', None]))
        self.assertNotIn('EPEULE', pieds[47].value)
        self.assertIsNone(pieds[47].comment)
        self.assertIn("⚠ P.E.T. vide, non complété : page(s) 48 — les autres pages ne sont "
                      "pas unanimes (EPEULE, GRAND-BUT)", alertes)


class TestValeurLueDifferente(_Classeur):

    def test_epeulf_conserve_et_alerte(self):
        alertes, pieds = self._generer(_document(['EPEULE'] * 47 + ['EPEULF']))
        self.assertIn('EPEULF', pieds[47].value)
        self.assertIsNone(pieds[47].comment)
        self.assertEqual([a for a in alertes if 'P.E.T.' in a],
                         ["⚠ page 48 : P.E.T. EPEULF différent des autres pages (EPEULE), "
                          "conservé"])


class TestIndiceVide(_Classeur):

    def test_reste_vide_meme_liste_en_champ_constant(self):
        pages = _document(['EPEULE'] * 3)
        del pages[2]['metadata']['INDICE']
        resultats, _ = deduire_champs_constants(pages, ['PET', 'INDICE'], {})
        self.assertNotIn('INDICE', resultats[2]['metadata'])


class TestJamaisDUnDocumentALAutre(unittest.TestCase):

    def test_un_document_sans_valeur_reste_vide(self):
        deduire_champs_constants(_document(['EPEULE', 'EPEULE']), ['PET'], {})
        resultats, alertes = deduire_champs_constants(_document([None, None]), ['PET'], {})
        self.assertTrue(all('PET' not in r['metadata'] for r in resultats))
        self.assertEqual(alertes, [])

    def test_chaque_document_sa_propre_valeur(self):
        a, _ = deduire_champs_constants(_document(['EPEULE', None]), ['PET'], {})
        b, _ = deduire_champs_constants(_document(['GRAND-BUT', None]), ['PET'], {})
        self.assertEqual((a[1]['metadata']['PET'], b[1]['metadata']['PET']),
                         ('EPEULE', 'GRAND-BUT'))


class TestDeduireChampsConstants(unittest.TestCase):

    def test_trace_et_pied_brut(self):
        resultats, _ = deduire_champs_constants(_document(['EPEULE', None]), ['PET'], {})
        meta = resultats[1]['metadata']
        self.assertEqual(meta['DEDUITS'], ['PET'])
        self.assertEqual(meta['PIED_BRUT'][0], 'P.E.T. : EPEULE       JARRETIERAGE')

    def test_entree_non_modifiee(self):
        pages = _document(['EPEULE', None])
        avant = copy.deepcopy(pages)
        deduire_champs_constants(pages, ['PET'], {})
        self.assertEqual(pages, avant)

    def test_une_seule_page_lue_suffit(self):
        resultats, alertes = deduire_champs_constants(_document(['EPEULE', None]), ['PET'], {})
        self.assertEqual((resultats[1]['metadata']['PET'], alertes), ('EPEULE', []))

    def test_valeur_unique_lue_sans_autre_page_pas_d_alerte(self):
        self.assertEqual(deduire_champs_constants(_document(['EPEULE']), ['PET'], {})[1], [])


class TestChampsConstantsDuModele(unittest.TestCase):

    def test_pet_par_defaut(self):
        self.assertEqual(champs_constants('REPARTITEUR'), ['PET'])

    def test_par_modele_sans_les_champs_qui_varient(self):
        reglage = {'REPARTITEUR': ('PET', 'NO_PLAN', 'INDICE', 'PAGE', 'TYPE', 'CABLE')}
        with patch.object(Config, 'CHAMPS_CONSTANTS_PAR_MODELE', reglage):
            self.assertEqual(champs_constants('REPARTITEUR'), ['PET', 'NO_PLAN'])
            self.assertEqual(champs_constants('REPARTITEUR 2'), ['PET'])


class TestInsererValeur(unittest.TestCase):

    def test_apres_le_libelle_vide(self):
        self.assertEqual(inserer_valeur(['CABLE : X', 'P.E.T. :   JARRETIERAGE'], 'PET',
                                        'P.E.T.', 'GRAND-BUT'),
                         ['CABLE : X', 'P.E.T. : GRAND-BUT   JARRETIERAGE'])

    def test_libelle_absent_ajoute_en_fin_de_premiere_ligne(self):
        self.assertEqual(inserer_valeur(['CABLE : X', 'N° PLAN : P'], 'PET', 'P.E.T.', 'G'),
                         ['CABLE : X     P.E.T. : G', 'N° PLAN : P'])

    def test_sans_ligne(self):
        self.assertEqual(inserer_valeur([], 'PET', 'P.E.T.', 'G'), ['P.E.T. : G'])


class TestLibelleAffiche(unittest.TestCase):

    def test_libelles(self):
        self.assertEqual(libelle_affiche('PET'), 'P.E.T.')
        self.assertEqual(libelle_affiche('NO_PLAN'), 'N° PLAN')
        self.assertEqual(libelle_affiche('ARMOIRE', {'ARMOIRE': 'ARM.'}), 'ARM.')
        self.assertEqual(libelle_affiche('ARMOIRE'), 'ARMOIRE')


class TestMarquerDeduits(unittest.TestCase):

    def test_colore_la_ligne_qui_porte_la_valeur(self):
        ws = openpyxl.Workbook().active
        ws.cell(row=8, column=2, value='P.E.T. : GRAND-BUT   JARRETIERAGE')
        ws.cell(row=9, column=2, value='N° PLAN : P  INDICE : R')
        n = marquer_deduits(ws, 10, {'PET': 'GRAND-BUT', 'DEDUITS': ['PET']}, 'DDEBF7')
        self.assertEqual(n, 1)
        self.assertIn(DEDUIT, ws.cell(row=8, column=2).comment.text)
        self.assertIsNone(ws.cell(row=9, column=2).comment)

    def test_rien_de_deduit(self):
        ws = openpyxl.Workbook().active
        self.assertEqual(marquer_deduits(ws, 10, {'PET': 'X'}, 'DDEBF7'), 0)


if __name__ == '__main__':
    unittest.main()
