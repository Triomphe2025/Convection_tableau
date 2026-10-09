"""
Étape 9 — controle_qualite.py, une classe par règle, sur pages pivot fabriquées.
Le module ne modifie jamais une valeur : il rend des alertes (page, ligne, colonne, règle,
message, proposition).

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_controle_qualite.py -v
"""
import copy
import unittest
from unittest.mock import patch

import controle_qualite as cq
from config import Config

COLS = ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL']


def _page(*lignes, methode='claude-vision'):
    return {'success': True, 'headers': COLS, 'detection_method': methode,
            'rows': [{'type': 'data', 'cells': list(ligne), 'confidence': [100] * 4}
                     for ligne in lignes]}


def _cellules(alertes):
    return sorted((a['page'], a['ligne'], a['colonne']) for a in alertes)


class TestVariantes(unittest.TestCase):

    def test_une_confusion_a_la_fois(self):
        self.assertEqual(set(cq.variantes('OC1')),
                         {'CC1', '0C1', 'OO1', 'OCI'})

    def test_hors_des_confusions_rien(self):
        self.assertEqual(list(cq.variantes('XY')), [])


class TestCoherence(unittest.TestCase):

    def test_forme_minoritaire_signalee_majoritaire_proposee(self):
        pages = [_page(*[('PA 01', '0001N', 'P310TS 10', 'OC FS 14 50')] * 3,
                       ('PA 02', '0002N', 'P310TS 11', 'CC FS 14 50'))]
        alertes = cq.regle_coherence(pages)
        self.assertEqual(_cellules(alertes), [(0, 3, 3)])
        self.assertEqual(alertes[0]['proposition'], 'OC FS 14 50')

    def test_mot_de_4_caracteres_et_plus(self):
        # Confusion B/8 : « Q4BVG » parmi des « Q48VG » (mot de 5 caractères).
        pages = [_page(('A 1', '0001N', 'Q48VG 01', 'X'), ('A 2', '0002N', 'Q48VG 02', 'X'),
                       ('A 3', '0003N', 'Q4BVG 03', 'X'))]
        self.assertEqual(_cellules(cq.regle_coherence(pages)), [(0, 2, 2)])

    def test_mots_courts_ignores(self):
        pages = [_page(*[('PA 01', '', '', 'OC')] * 3, ('PA 02', '', '', 'CC'))]
        self.assertEqual(cq.regle_coherence(pages), [])

    def test_egalite_pas_d_alerte(self):
        pages = [_page(('PA 01', '', '', 'OCFSCS'), ('PA 02', '', '', 'CCFSCS'))]
        self.assertEqual(cq.regle_coherence(pages), [])

    def test_lexique_meme_forme_unique(self):
        # « CC FS 14 50 » une seule fois dans le document, « OC FS 14 50 » dans le lexique.
        pages = [_page(('PA 01', '0001N', 'P310TS 10', 'CC FS 14 50'))]
        alertes = cq.regle_coherence(pages, lexique={'OC FS 14 50'})
        self.assertEqual(_cellules(alertes), [(0, 0, 3)])
        self.assertEqual(alertes[0]['proposition'], 'OC FS 14 50')

    def test_forme_du_lexique_jamais_signalee(self):
        pages = [_page(('PA 01', '', '', 'OC FS 14 50'))]
        self.assertEqual(cq.regle_coherence(pages, lexique={'OC FS 14 50', 'CC FS 14 50'}), [])

    def test_valeur_jamais_modifiee(self):
        pages = [_page(*[('PA 01', '', '', 'OC FS 14 50')] * 3, ('PA 02', '', '', 'CC FS 14 50'))]
        avant = copy.deepcopy(pages)
        cq.regle_coherence(pages, lexique={'OC FS 14 50'})
        self.assertEqual(pages, avant)


class _Dico:
    def correct(self, colonne, valeur):
        return ({'315TS': '312TS', 'G26': 'G36'}.get(valeur, valeur),
                valeur in ('315TS', 'G26'))


class TestDictionnaire(unittest.TestCase):

    def _pages(self):
        return [_page(('PA 01', '', '', '315TS'), methode='header'),
                _page(('PA 01', '', '', 'G26'), methode='claude-vision'),
                _page(('PA 01', '', '', '315TS'), methode='pdf-grille')]

    def test_alerte_avec_proposition_au_lieu_de_correction(self):
        with patch.object(Config, 'QUALITE_DICTIONNAIRE_MODES', {'claude': False, 'ocr': True}):
            alertes = cq.regle_dictionnaire(self._pages(), _Dico())
        self.assertEqual([(a['page'], a['proposition']) for a in alertes], [(0, '312TS')])

    def test_mode_claude_par_interrupteur(self):
        with patch.object(Config, 'QUALITE_DICTIONNAIRE_MODES', {'claude': True, 'ocr': True}):
            alertes = cq.regle_dictionnaire(self._pages(), _Dico())
        self.assertEqual([a['page'] for a in alertes], [0, 1])

    def test_page_vectorielle_jamais(self):
        with patch.object(Config, 'QUALITE_DICTIONNAIRE_MODES', {'claude': True, 'ocr': True}):
            alertes = cq.regle_dictionnaire(self._pages(), _Dico())
        self.assertNotIn(2, [a['page'] for a in alertes])


class TestContinuite(unittest.TestCase):

    def test_saut_dans_la_suite_du_tenant(self):
        pages = [_page(('PA 01', '0001N', '', ''), ('PA 02', '0002N', '', ''),
                       ('PA 20', '0003N', '', ''), ('PA 21', '0004N', '', ''))]
        alertes = cq.regle_continuite(pages, ['TENANT'], saut_max=5)
        self.assertEqual(_cellules(alertes), [(0, 2, 0)])

    def test_suffixes_de_lettre_et_changement_de_code(self):
        pages = [_page(('D3T 01A', '', '', ''), ('D3T 01B', '', '', ''), ('D3T 02A', '', '', ''),
                       ('RM 15', '', '', ''), ('RM 16', '', '', ''))]
        self.assertEqual(cq.regle_continuite(pages, ['TENANT'], saut_max=1), [])

    def test_jar_descente_signalee(self):
        pages = [_page(('', '0281W', '', ''), ('', '0282W', '', ''), ('', '0228W', '', ''),
                       ('', '0284W', '', ''))]
        self.assertEqual(_cellules(cq.regle_continuite(pages, ['JAR'], saut_max=10)),
                         [(0, 2, 1)])

    def test_vrai_trou_sous_le_seuil(self):
        pages = [_page(('', '0652B', '', ''), ('', '0662B', '', ''))]
        self.assertEqual(cq.regle_continuite(pages, ['JAR'], saut_max=10), [])


class TestColonneVide(unittest.TestCase):

    def test_colonne_obligatoire_vide_signalee(self):
        pages = [_page(('PA 01', '', 'P310TS 10', 'X'), ('PA 02', '', 'P310TS 11', 'Y'))]
        alertes = cq.regle_colonne_vide(pages, ['JAR'])
        self.assertEqual([(a['page'], a['ligne'], a['colonne']) for a in alertes],
                         [(0, None, 1)])

    def test_colonne_facultative_vide_ignoree(self):
        pages = [_page(('PA 01', '', 'P310TS 10', 'X'))]
        self.assertEqual(cq.regle_colonne_vide(pages, ['TENANT']), [])

    def test_page_sans_ligne_ignoree(self):
        self.assertEqual(cq.regle_colonne_vide([_page()], ['JAR']), [])


class TestFormat(unittest.TestCase):

    def test_hors_motif_signale(self):
        pages = [_page(('PA 01', '0281W', '', ''), ('PA 02', '028IW', '', ''),
                       ('PA 03', '', '', ''))]
        alertes = cq.regle_format(pages, {'JAR': r'\d{4}[A-Z]'})
        self.assertEqual(_cellules(alertes), [(0, 1, 1)])

    def test_espaces_ramenes_a_un(self):
        pages = [_page(('PA     01', '', '', ''))]
        self.assertEqual(cq.regle_format(pages, {'TENANT': r'[A-Z]+ \d{2}'}), [])

    def test_colonne_sans_motif_libre(self):
        pages = [_page(('PA 01', '', '', 'n importe quoi'))]
        self.assertEqual(cq.regle_format(pages, {}), [])


class TestControlerDocument(unittest.TestCase):

    def test_seules_les_regles_actives(self):
        pages = [_page(('PA 01', '028IW', '', ''))]
        with patch.object(Config, 'QUALITE_REGLES', {'format': True}), \
                patch.object(Config, 'QUALITE_FORMATS', {'REPARTITEUR': {'JAR': r'\d{4}[A-Z]'}}):
            alertes = cq.controler_document(pages, 'REPARTITEUR')
        self.assertEqual([a['regle'] for a in alertes], ['format'])
        with patch.object(Config, 'QUALITE_REGLES', {}):
            self.assertEqual(cq.controler_document(pages, 'REPARTITEUR'), [])


if __name__ == '__main__':
    unittest.main()
