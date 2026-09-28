"""
Test doré de la mesure de précision : sortie v1.7 FIGÉE de l'extrait
223111PE011 contre la vérité terrain validée.

La sortie v1.7 est une donnée d'entrée figée (produite en mode Claude) : ce
test ne lance jamais le pipeline — zéro appel API, zéro Tesseract, zéro réseau.
Assertions sur des écarts nommés uniquement, jamais sur un total de cellules
fausses (il dépend de la stratégie d'alignement).

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_mesurer_precision_golden.py -v
"""
import re
import unittest
from pathlib import Path

import mesure_precision as mp
from mesurer_precision import lire_verite_excel, lire_xlsx

FIXTURES = Path(__file__).parent / 'fixtures'
VERITE = FIXTURES / '223111PE011_extrait_verite.xlsx'
SORTIE_V17 = FIXTURES / '223111PE011_extrait_sortie_v1.7.xlsx'


def _numero_page(page: dict) -> str:
    for ligne in page.get('pied_texte', []):
        m = re.search(r'PAGE\s*:\s*(\w+)', ligne)
        if m:
            return m.group(1)
    return ''


class TestFixtures(unittest.TestCase):

    def test_fichiers_presents(self):
        self.assertTrue(VERITE.exists(), VERITE)
        self.assertTrue(SORTIE_V17.exists(), SORTIE_V17)

    def test_sortie_v17_huit_blocs_168_lignes(self):
        pages = lire_xlsx(SORTIE_V17)
        self.assertEqual(len(pages), 8)
        self.assertEqual(sum(len(p['rows']) for p in pages), 168)


@unittest.skipUnless(VERITE.exists() and SORTIE_V17.exists(), 'fixtures absentes')
class TestSortieV17ContreVerite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reference, cls.colonnes = lire_verite_excel(VERITE)
        cls.converti = lire_xlsx(SORTIE_V17)
        cls.rapport = mp.mesurer(cls.reference, cls.converti, cls.colonnes)
        cls.num_ref = [_numero_page(p) for p in cls.reference]
        cls.num_conv = [_numero_page(p) for p in cls.converti]

    def _idx_ref(self, numero):
        return self.num_ref.index(numero)

    def _ecarts(self, page, colonne=None):
        i = self._idx_ref(page)
        return [
            e for e in self.rapport.ecarts_cellules
            if e.page_ref == i and (colonne is None or e.colonne == colonne)
        ]

    def _ecart(self, page, colonne, ref, conv):
        for e in self._ecarts(page, colonne):
            if e.valeur_ref == ref and e.valeur_conv == conv:
                return e
        self.fail(f"écart attendu absent : p.{page} [{colonne}] {ref!r} → {conv!r}")

    # ── Appariement ─────────────────────────────────────────────────

    def test_page_122a_appariee_a_la_page_128_malgre_nom_et_position(self):
        paire = (self._idx_ref('122a'), self.num_conv.index('128'))
        self.assertIn(paire, self.rapport.pages_appariees)

    def test_page_123_toujours_appariee_malgre_le_croisement(self):
        paire = (self._idx_ref('123'), self.num_conv.index('123'))
        self.assertIn(paire, self.rapport.pages_appariees)

    def test_pages_9_et_104_absentes_de_la_sortie(self):
        orphelines = {self.num_ref[i] for i in self.rapport.pages_ref_orphelines}
        self.assertIn('9', orphelines)
        self.assertIn('104', orphelines)

    # ── Page 1 : glissement de colonnes ─────────────────────────────

    def test_page_1_glissement_de_colonnes_sur_4_lignes(self):
        tenants = [e for e in self._ecarts('1', 'TENANT') if e.valeur_conv == 'PH']
        self.assertEqual(len(tenants), 4)
        signaux = [e for e in self._ecarts('1', 'SIGNAL') if 'QTEL2' in e.valeur_conv
                   or 'CITEL2' in e.valeur_conv]
        self.assertEqual(len(signaux), 4)

    def test_page_1_signal_tel_pms_q1_absent(self):
        e = self._ecart('1', 'SIGNAL', 'TEL PMS Q1', 'CITEL2 09')
        self.assertEqual(e.classe, mp.CONTENU_DIFFERENT)

    # ── Page 3 ──────────────────────────────────────────────────────

    def test_page_3_bubu_lu_bleu_en_contenu_different(self):
        e = self._ecart('3', 'FIL', 'BUBU', 'BLEU')
        self.assertEqual(e.classe, mp.CONTENU_DIFFERENT)

    def test_page_3_signal_de_deux_lignes_fusionne(self):
        self._ecart('3', 'SIGNAL', 'TERRE DIST', 'TERRE DIST R C200 DIST 1')

    # ── Page 52 ─────────────────────────────────────────────────────

    def test_page_52_fil_15b_m_lu_15_m_j(self):
        self._ecart('52', 'FIL', '15B/M', '15 M/J')

    # ── Page 119 ────────────────────────────────────────────────────

    def test_page_119_les_60_aboutissants_vides(self):
        manquants = [e for e in self._ecarts('119', 'ABOUTISSANT') if e.classe == mp.MANQUANT]
        self.assertEqual(len(manquants), 60)

    def test_page_119_itin_lu_ittn_4_fois_en_confusion(self):
        ittn = [e for e in self._ecarts('119', 'SIGNAL')
                if 'ITIN' in e.valeur_ref and 'ITTN' in e.valeur_conv]
        self.assertEqual(len(ittn), 4)
        self.assertTrue(all(e.classe == mp.CONFUSION for e in ittn))

    def test_page_119_talonnage_lu_talonage_en_confusion(self):
        e = self._ecart('119', 'SIGNAL', 'TSPAT TALONNAGE PH', 'TSPAT TALONAGE PH')
        self.assertEqual(e.classe, mp.CONFUSION)

    # ── Page 122 ────────────────────────────────────────────────────

    def test_page_122_quatre_lignes_en_trop(self):
        i_conv = self.num_conv.index('122')
        en_trop = [o for o in self.rapport.lignes_orphelines
                   if o.cote == mp._LIGNE_EN_TROP and o.page == i_conv]
        self.assertEqual(len(en_trop), 4)


if __name__ == '__main__':
    unittest.main()
