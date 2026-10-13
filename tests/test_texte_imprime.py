"""
Lecture des pages vectorielles telle qu'imprimée : texte surimprimé lu une fois, texte caché
par le PDF non lu, mot-clé de section en orthographe équivalente (« NOM DE CABLE »).

Pages réelles : tests/fixtures/223111PE022_extrait_surimpression.pdf = 223111PE022 p. 14
(lignes 13 à 16 imprimées deux fois à 1,7 pt, deux « RESERVE NON CABLEE » cachés par le
découpage) et p. 9 (sections « NOM DE CABLE : DI/BO »).

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_texte_imprime.py -v
"""
import tempfile
import unittest
from pathlib import Path

import fitz

from pdf_extractor import (PdfTableExtractor, grille_page, mot_visible, mots_visibles,
                           surimprime)
from template import TemplateManager

FIXTURE = Path(__file__).parent / 'fixtures' / '223111PE022_extrait_surimpression.pdf'
TPL = TemplateManager().get('Bornier standard')


def _lire(numero):
    with fitz.open(str(FIXTURE)) as doc:
        return PdfTableExtractor(TPL).extract_page_grille(doc[numero], numero)


def _pdf(dessiner):
    tmp = tempfile.mkdtemp()
    chemin = Path(tmp) / 'p.pdf'
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    dessiner(page)
    doc.save(str(chemin))
    return fitz.open(str(chemin))[0]


class TestPE022Page14(unittest.TestCase):

    def setUp(self):
        self.rows = _lire(0)['rows']
        self.donnees = [r['cells'] for r in self.rows if r['type'] == 'data']

    def test_31_lignes_comme_sur_le_papier(self):
        self.assertEqual(sum(1 for r in self.rows if r['type'] in ('data', 'section')), 31)

    def test_lignes_surimprimees_lues_une_fois_avec_leur_borne(self):
        for borne in ('13', '14', '15', '16'):
            ligne = next(c for c in self.donnees if c[0] == borne)
            self.assertEqual(ligne[2], 'RESERVE NON CABLEE')
        self.assertFalse(any('RESERVERESERVE' in c[2] for c in self.donnees))
        self.assertFalse(any(not c[0].strip() for c in self.donnees))

    def test_jarretieres_entieres(self):
        self.assertEqual(self.donnees[0][2:], ['- PVS14-49 & PVS21-49', '0399N'])

    def test_texte_cache_non_lu(self):
        self.assertEqual(self.donnees[-1][0], '28')


class TestSectionNomDeCable(unittest.TestCase):

    def test_page_lue_et_sections_reconnues(self):
        rows = _lire(1)['rows']
        self.assertEqual(sum(1 for r in rows if r['type'] in ('data', 'section')), 30)
        self.assertEqual(rows[0], {'type': 'section', 'text': 'NOM DE CABLE : DI/BO'})


class TestSurimpression(unittest.TestCase):

    def test_meme_mot_presque_au_meme_endroit(self):
        self.assertTrue(surimprime((100, 200, 160, 213.8, 'NON'),
                                   (100.2, 201.7, 160.2, 215.5, 'NON'), 6.0))

    def test_ligne_suivante_pas_une_surimpression(self):
        self.assertFalse(surimprime((100, 200, 160, 213.8, 'NON'),
                                    (100, 211.3, 160, 225.1, 'NON'), 6.0))

    def test_autre_mot_ou_autre_colonne(self):
        self.assertFalse(surimprime((100, 200, 160, 213.8, 'NON'),
                                    (100, 200.5, 160, 214, 'OUI'), 6.0))
        self.assertFalse(surimprime((100, 200, 160, 213.8, 'NON'),
                                    (130, 200.5, 190, 214, 'NON'), 6.0))

    def test_grille_fabriquee_double_lu_une_fois(self):
        def dessiner(page):
            page.insert_text((40, 100), "13", fontname='cour', fontsize=11)
            page.insert_text((200, 100), "RESERVE NON CABLEE", fontname='cour', fontsize=11)
            page.insert_text((200, 98.3), "RESERVE NON CABLEE", fontname='cour', fontsize=11)
        lignes = grille_page(_pdf(dessiner))
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0].split(), ['13', 'RESERVE', 'NON', 'CABLEE'])


class TestTexteCache(unittest.TestCase):

    def _page_masquee(self):
        def dessiner(page):
            page.insert_text((40, 100), "VISIBLE", fontname='cour', fontsize=11)
            page.insert_text((40, 130), "CACHE", fontname='cour', fontsize=11)
            page.draw_rect(fitz.Rect(30, 118, 200, 140), color=None, fill=(1, 1, 1))
        return _pdf(dessiner)

    def test_mot_sous_un_masque_blanc_non_lu(self):
        self.assertEqual([m[4] for m in mots_visibles(self._page_masquee())], ['VISIBLE'])
        self.assertEqual(grille_page(self._page_masquee()), ['VISIBLE'])

    def test_point_seul_garde(self):
        def dessiner(page):
            page.insert_text((40, 100), "FIN", fontname='cour', fontsize=11)
            page.insert_text((80, 100), ".", fontname='cour', fontsize=11)
        self.assertEqual([m[4] for m in mots_visibles(_pdf(dessiner))], ['FIN', '.'])

    def test_mot_visible_bande_vide(self):
        import numpy as np
        blanc = np.full((100, 100), 255.0)
        self.assertFalse(mot_visible(blanc, 1.0, (10, 10, 60, 30)))
        blanc[17:24, 10:60] = 0
        self.assertTrue(mot_visible(blanc, 1.0, (10, 10, 60, 30)))


if __name__ == '__main__':
    unittest.main()
