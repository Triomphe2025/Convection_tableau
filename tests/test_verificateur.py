"""
Tests unitaires de verificateur.py — sur des dicts fabriqués à la main, sans
Tesseract, sans PDF, sans Excel.

Couvre : normaliser, plier_confusions, similarite, apparier_pages,
aligner_lignes, classer_ecart, comparer_cellules, verifier, formater_rapport,
RapportVerification, Ecart.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_verificateur.py -v
"""

import dataclasses
import unittest
from difflib import SequenceMatcher
from unittest.mock import MagicMock, patch

from config import Config
from verificateur import (
    A_VERIFIER, BENIN, IDENTIQUE, Ecart, RapportVerification, aligner_lignes,
    apparier_pages, classer_ecart, comparer_cellules, formater_rapport,
    normaliser, plier_confusions, similarite, verifier,
)

COLONNES = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']


def _ligne(cells, conf=None):
    return {'type': 'data', 'cells': list(cells), 'confidence': conf or [100] * len(cells)}


def _page(rows, succes=True):
    return {'success': succes, 'headers': COLONNES, 'rows': rows, 'metadata': {}}


def _page_unique(tag, n=6):
    """Page au contenu distinct de toute autre page (tag différent)."""
    return _page([
        _ligne([f"{i:02d}", tag * 5 + str(i), tag * 9, tag * 4 + f"{i:04d}"])
        for i in range(1, n + 1)
    ])


class TestNormaliser(unittest.TestCase):

    def test_nominal_majuscules_sans_espaces(self):
        self.assertEqual(normaliser('  eP.stat / ts '), 'EP.STAT/TS')

    def test_accents_supprimes(self):
        self.assertEqual(normaliser('Élément détecté'), 'ELEMENTDETECTE')

    def test_vide_et_none(self):
        self.assertEqual(normaliser(''), '')
        self.assertEqual(normaliser(None), '')

    def test_nombre_converti_en_texte(self):
        self.assertEqual(normaliser(123), '123')


class TestPlierConfusions(unittest.TestCase):

    def test_o_et_zero_equivalents(self):
        self.assertEqual(plier_confusions('DISC0RDANCE'), plier_confusions('DISCORDANCE'))

    def test_i_un_et_l_equivalents(self):
        self.assertEqual(plier_confusions('1LI'), plier_confusions('ILL'))

    def test_texte_sans_confusion_seulement_normalise(self):
        self.assertEqual(plier_confusions('rouge'), plier_confusions('ROUGE'))

    def test_vide(self):
        self.assertEqual(plier_confusions(None), '')

    def test_table_lue_dans_config(self):
        with patch.object(Config, 'VERIF_CONFUSIONS_OCR', ('XY',)):
            self.assertEqual(plier_confusions('AY'), 'AX')


class TestSimilarite(unittest.TestCase):

    def test_sequences_identiques(self):
        self.assertEqual(similarite('ABC', 'ABC'), 1.0)

    def test_vides(self):
        self.assertEqual(similarite('', ''), 1.0)
        self.assertEqual(similarite('', 'A'), 0.0)
        self.assertEqual(similarite([], ['A']), 0.0)

    def test_accepte_des_listes(self):
        self.assertGreater(similarite(['a', 'b', 'c'], ['a', 'x', 'c']), 0.5)

    def test_piege_autojunk_au_dela_de_200_elements(self):
        a = 'ABCDE' * 80
        b = a[:200] + 'X' + a[201:]
        self.assertGreater(similarite(a, b), 0.9)
        # Le comportement par défaut de difflib s'effondre sur ce même cas.
        self.assertLess(SequenceMatcher(None, a, b).ratio(), 0.6)


class TestApparierPages(unittest.TestCase):

    def test_documents_identiques_apparies_dans_l_ordre(self):
        pages = [_page_unique('A'), _page_unique('B'), _page_unique('C')]
        paires, ref_o, conv_o = apparier_pages(pages, pages)
        self.assertEqual(paires, [(0, 0), (1, 1), (2, 2)])
        self.assertEqual((ref_o, conv_o), ([], []))

    def test_pagination_differente_page_de_garde_ignoree(self):
        garde = _page([])
        ref = [garde, _page_unique('A'), _page_unique('B'), _page_unique('C')]
        conv = [_page_unique('A'), _page_unique('B')]
        paires, ref_o, conv_o = apparier_pages(ref, conv)
        self.assertEqual(paires, [(1, 0), (2, 1)])
        self.assertEqual(ref_o, [3])
        self.assertEqual(conv_o, [])

    def test_ordre_preserve_pas_de_croisement(self):
        ref = [_page_unique('A'), _page_unique('B')]
        conv = [_page_unique('B'), _page_unique('A')]
        paires, _, _ = apparier_pages(ref, conv)
        self.assertEqual(len(paires), 1)
        self.assertLess(paires[0][0] + paires[0][1], 3)

    def test_pages_en_echec_ignorees(self):
        ref = [_page_unique('A'), _page(_page_unique('B')['rows'], succes=False)]
        paires, ref_o, _ = apparier_pages(ref, [_page_unique('A')])
        self.assertEqual(paires, [(0, 0)])
        self.assertEqual(ref_o, [])

    def test_pages_lues_differemment_restent_appariees(self):
        # Aucune ligne identique d'un moteur à l'autre : sans tolérance, la page
        # ne serait jamais appariée donc jamais vérifiée.
        ref = _page([_ligne(['01', 'ROUGE', 'DISCORDANCE POMPE', '0033B']),
                     _ligne(['02', 'BLEU', 'NIVEAU TROP BAS', '0022B'])])
        conv = _page([_ligne(['01', 'ROUGE', 'DISCONTINUOSITE POMPE', '0033B']),
                      _ligne(['02', 'BLEU', 'NIVEAU TRQP BAS', '0022R'])])
        paires, _, _ = apparier_pages([ref], [conv])
        self.assertEqual(paires, [(0, 0)])

    def test_listes_vides(self):
        self.assertEqual(apparier_pages([], []), ([], [], []))

    def test_seuil_eleve_refuse_pages_peu_similaires(self):
        paires, _, _ = apparier_pages([_page_unique('A')], [_page_unique('Z')], seuil=0.99)
        self.assertEqual(paires, [])

    def test_entree_invalide_leve_typeerror(self):
        with self.assertRaises(TypeError):
            apparier_pages(None, [])
        with self.assertRaises(TypeError):
            apparier_pages('texte', [])

    def test_dict_seul_accepte(self):
        paires, _, _ = apparier_pages(_page_unique('A'), _page_unique('A'))
        self.assertEqual(paires, [(0, 0)])


class TestAlignerLignes(unittest.TestCase):

    def test_sequences_identiques(self):
        lignes = [_ligne(['01', 'ROUGE', 'A', '0001B']), _ligne(['02', 'BLEU', 'B', '0002B'])]
        self.assertEqual(aligner_lignes(lignes, lignes), [(0, 0), (1, 1)])

    def test_borne_mal_lue_reste_appariee(self):
        ref = [_ligne(['01', 'ROUGE', 'SIGNAL ALPHA', '0013B']),
               _ligne(['0O2', 'BLEU', 'SIGNAL BETA', '0014B'])]
        conv = [_ligne(['01', 'ROUGE', 'SIGNAL ALPHA', '0013B']),
                _ligne(['072', 'BLEU', 'SIGNAL BETA', '0014B'])]
        self.assertEqual(aligner_lignes(ref, conv), [(0, 0), (1, 1)])

    def test_debordement_de_colonne_ne_change_pas_l_alignement(self):
        ref = [_ligne(['01', 'G', 'COMMUN TS', 'GR3 0013B'])]
        conv = [_ligne(['01', 'G', 'COMMUN TS GR3', '0013B'])]
        self.assertEqual(aligner_lignes(ref, conv), [(0, 0)])

    def test_ligne_manquante_cote_converti(self):
        ref = [_ligne(['01', 'A', 'X', '1']), _ligne(['02', 'B', 'Y', '2']),
               _ligne(['03', 'C', 'Z', '3'])]
        conv = [ref[0], ref[2]]
        self.assertEqual(aligner_lignes(ref, conv), [(0, 0), (1, None), (2, 1)])

    def test_ligne_en_trop_cote_converti(self):
        ref = [_ligne(['01', 'A', 'X', '1'])]
        conv = [ref[0], _ligne(['99', 'Q', 'INVENTE', '9'])]
        self.assertEqual(aligner_lignes(ref, conv), [(0, 0), (None, 1)])

    def test_listes_vides_ou_une_seule_vide(self):
        self.assertEqual(aligner_lignes([], []), [])
        lignes = [_ligne(['01', 'A', 'X', '1'])]
        self.assertEqual(aligner_lignes(lignes, []), [(0, None)])
        self.assertEqual(aligner_lignes([], lignes), [(None, 0)])

    def test_plus_de_200_lignes_repetitives_restent_alignees(self):
        motifs = [_ligne([f"{i}", 'X', 'RESERVE CABLEE', '']) for i in range(5)]
        lignes = [motifs[i % 5] for i in range(250)]
        self.assertEqual(aligner_lignes(lignes, lignes), [(i, i) for i in range(250)])


class TestClasserEcart(unittest.TestCase):

    def test_identique(self):
        self.assertEqual(classer_ecart('ROUGE', 'ROUGE'), (IDENTIQUE, '', 0))

    def test_none_traite_comme_vide(self):
        self.assertEqual(classer_ecart(None, None)[0], IDENTIQUE)

    def test_mise_en_forme_benigne(self):
        classe, raison, _ = classer_ecart('EP. STAT/TS', 'EP.STAT/TS')
        self.assertEqual((classe, raison), (BENIN, 'MISE_EN_FORME'))

    def test_confusion_ocr_benigne(self):
        classe, raison, _ = classer_ecart('DISC0RDANCE', 'DISCORDANCE')
        self.assertEqual((classe, raison), (BENIN, 'CONFUSION_OCR'))

    def test_reference_vide_benigne(self):
        self.assertEqual(classer_ecart('', 'TEXTE')[:2], (BENIN, 'REFERENCE_VIDE'))

    def test_confiance_basse_benigne(self):
        classe, raison, _ = classer_ecart('DISCORDANCE', 'DISCONTINUOSITE', confiance_ref=40)
        self.assertEqual((classe, raison), (BENIN, 'CONFIANCE_BASSE'))

    def test_confiance_haute_a_verifier(self):
        classe, raison, dist = classer_ecart('DISCORDANCE', 'DISCONTINUOSITE', confiance_ref=91)
        self.assertEqual((classe, raison), (A_VERIFIER, 'DIVERGENCE'))
        self.assertGreater(dist, Config.VERIF_DISTANCE_BENIGNE)

    def test_confiance_inconnue_traitee_comme_haute(self):
        self.assertEqual(classer_ecart('0033B', '0033R', confiance_ref=None)[0], A_VERIFIER)

    def test_ecart_d_un_caractere_benin_si_confiance_moyenne(self):
        with patch.object(Config, 'VERIF_DISTANCE_BENIGNE', 2):
            classe, raison, _ = classer_ecart('0033B', '0033R', confiance_ref=80)
        self.assertEqual((classe, raison), (BENIN, 'ECART_MINEUR'))

    def test_ecart_d_un_caractere_a_verifier_si_confiance_sure(self):
        self.assertEqual(classer_ecart('0033B', '0033R', confiance_ref=95)[0], A_VERIFIER)

    def test_valeur_convertie_connue_excuse_la_reference(self):
        connues = {'TC IDPO1'.replace(' ', '')}
        classe, raison, _ = classer_ecart('TC IDPO8', 'TC IDPO1', 80, connues)
        self.assertEqual((classe, raison), (BENIN, 'REFERENCE_INCONNUE'))

    def test_valeur_convertie_inconnue_signalee_comme_telle(self):
        connues = {'DISCORDANCE'}
        classe, raison, _ = classer_ecart('DISCORDANCE', 'DISCONTINUOSITE', 95, connues)
        self.assertEqual((classe, raison), (A_VERIFIER, 'CONVERTI_INCONNU'))

    def test_distance_injectee_utilisee_sur_les_valeurs_repliees(self):
        distance = MagicMock(return_value=5)
        classer_ecart('ab c', 'xyz', 95, None, distance)
        distance.assert_called_once_with(plier_confusions('ab c'), plier_confusions('xyz'))


class TestComparerCellules(unittest.TestCase):

    def test_ligne_identique(self):
        ligne = _ligne(['01', 'ROUGE', 'SIGNAL', '0001B'])
        ecarts = comparer_cellules(ligne, ligne, COLONNES)
        self.assertEqual([e.classe for e in ecarts], [IDENTIQUE] * 4)

    def test_cellules_vides_des_deux_cotes_ignorees(self):
        ligne = _ligne(['01', '', 'RESERVE', ''])
        self.assertEqual(len(comparer_cellules(ligne, ligne, COLONNES)), 2)

    def test_debordement_de_colonne_benin(self):
        ref = _ligne(['01', 'G', 'COMMUN TS', 'GR3 0013B'])
        conv = _ligne(['01', 'G', 'COMMUN TS GR3', '0013B'])
        ecarts = comparer_cellules(ref, conv, COLONNES)
        self.assertNotIn(A_VERIFIER, [e.classe for e in ecarts])
        self.assertIn('DEBORDEMENT_COLONNE', [e.raison for e in ecarts])

    def test_divergence_isolee_une_seule_cellule(self):
        ref = _ligne(['01', 'ROUGE', 'TC IDPO1', '0001B'], [95, 95, 95, 95])
        conv = _ligne(['01', 'ROUGE', 'TC IDXY9', '0001B'])
        ecarts = [e for e in comparer_cellules(ref, conv, COLONNES) if e.classe != IDENTIQUE]
        self.assertEqual(len(ecarts), 1)
        self.assertEqual((ecarts[0].colonne, ecarts[0].classe), ('SIGNAL', A_VERIFIER))

    def test_cas_reel_discordance_un_ecart_et_un_debordement_benin(self):
        ref = _ligne(['08', '2 M', 'EP.STAT/TS DISCORDANCE', 'POMPE 0033B'], [96, 74, 91, 90])
        conv = _ligne(['08', '2 M', 'EP.STAT/TS DISCONTINUOSITE POMPE', '0033B'])
        ecarts = [e for e in comparer_cellules(ref, conv, COLONNES) if e.classe != IDENTIQUE]
        a_verifier = [e for e in ecarts if e.classe == A_VERIFIER]
        self.assertEqual(len(a_verifier), 1)
        self.assertEqual(a_verifier[0].colonne, 'SIGNAL')
        self.assertEqual(a_verifier[0].confiance_ref, 91)
        self.assertIn('DISCONTINUOSITE', a_verifier[0].valeur_conv)
        # « POMPE » a glissé de SIGNAL vers JARRETIERES : bénin, pas une alerte.
        benins = [e for e in ecarts if e.classe == BENIN]
        self.assertEqual([(e.colonne, e.raison) for e in benins],
                         [('JARRETIERES', 'DEBORDEMENT_COLONNE')])

    def test_texte_qui_glisse_sur_plusieurs_colonnes_reste_benin(self):
        ref = _ligne(['01', 'R', 'ESERVE', 'CABLEE 0013B'])
        conv = _ligne(['01', 'R ESERVE', 'CABLEE', '0013B'])
        ecarts = comparer_cellules(ref, conv, COLONNES)
        self.assertNotIn(A_VERIFIER, [e.classe for e in ecarts])

    def test_mot_oublie_par_le_scan_benin_si_valeur_connue(self):
        ref = _ligne(['05', 'MB CABLEE'])
        conv = _ligne(['05', 'MB RESERVE CABLEE'])
        connues = {'COULEUR': {normaliser('MB RESERVE CABLEE')}}
        ecarts = comparer_cellules(ref, conv, COLONNES, connues)
        self.assertEqual([e.raison for e in ecarts if e.classe == BENIN],
                         ['REFERENCE_INCOMPLETE'])

    def test_mot_ajoute_par_la_conversion_a_verifier_si_inconnu(self):
        ref = _ligne(['05', 'MB CABLEE'])
        conv = _ligne(['05', 'MB INVENTE CABLEE'])
        ecarts = comparer_cellules(ref, conv, COLONNES)
        self.assertEqual([e.raison for e in ecarts if e.classe == A_VERIFIER],
                         ['AJOUT_CONVERTI'])

    def test_contenu_perdu_par_la_conversion_a_verifier(self):
        ref = _ligne(['05', 'MB', 'DISCORDANCE POMPE', '0033B'], [95] * 4)
        conv = _ligne(['05', 'MB', '', '0033B'])
        ecarts = comparer_cellules(ref, conv, COLONNES)
        self.assertEqual([e.raison for e in ecarts if e.classe == A_VERIFIER],
                         ['CONTENU_PERDU'])

    def test_colonnes_sans_noms_numerotees(self):
        ref, conv = _ligne(['A', 'B', 'C']), _ligne(['A', 'B', 'ZZZ9'])
        ecarts = [e for e in comparer_cellules(ref, conv) if e.classe != IDENTIQUE]
        self.assertEqual(ecarts[0].colonne, 'COL3')

    def test_longueurs_differentes_completees(self):
        ecarts = comparer_cellules(_ligne(['A', 'B']), _ligne(['A', 'B', 'SUPPLEMENT']))
        self.assertEqual(len(ecarts), 3)
        self.assertEqual(ecarts[2].valeur_ref, '')

    def test_liste_blanche_utilisee_pour_la_colonne(self):
        ref = _ligne(['01', 'R', 'TC IDPO8', '1'], [1, 1, 80, 1])
        conv = _ligne(['01', 'R', 'TC IDPO1', '1'])
        connues = {'SIGNAL': {normaliser('TC IDPO1')}}
        ecarts = comparer_cellules(ref, conv, COLONNES, connues)
        signal = [e for e in ecarts if e.colonne == 'SIGNAL'][0]
        self.assertEqual(signal.raison, 'REFERENCE_INCONNUE')

    def test_lignes_sans_cellules(self):
        self.assertEqual(comparer_cellules({}, {}), [])

    def test_numeros_de_page_et_de_ligne_reportes(self):
        ref, conv = _ligne(['A']), _ligne(['B'])
        e = comparer_cellules(ref, conv, page_ref=3, page_conv=2, num_ref=7, num_conv=6)[0]
        self.assertEqual((e.page_ref, e.page_conv, e.ligne_ref, e.ligne_conv), (3, 2, 7, 6))


class TestVerifier(unittest.TestCase):

    def test_documents_identiques_fideles(self):
        pages = [_page_unique('A'), _page_unique('B')]
        rapport = verifier(pages, pages)
        self.assertEqual(rapport.a_verifier, [])
        self.assertEqual(rapport.concordance, 1.0)
        self.assertTrue(rapport.fidele)

    def test_divergence_discordance_trouvee(self):
        ref = [_page([
            _ligne(['07', '2 I', 'EP. STAT/TS NIVEAU TROP BAS', '0022B'], [95, 80, 90, 92]),
            _ligne(['08', '2 M', 'EP.STAT/TS DISCORDANCE', 'POMPE 0033B'], [96, 74, 91, 90]),
            _ligne(['09', '3 G', 'EP. STAT/TS FUSION FUSIBLE', '0023B'], [95, 80, 90, 92]),
        ])]
        conv = [_page([
            _ligne(['07', '2 I', 'EP.STAT/TS NIVEAU TROP BAS', '0022B']),
            _ligne(['08', '2 M', 'EP.STAT/TS DISCONTINUOSITE POMPE', '0033B']),
            _ligne(['09', '3 G', 'EP.STAT/TS FUSION FUSIBLE', '0023B']),
        ])]
        rapport = verifier(ref, conv)
        self.assertEqual(len(rapport.a_verifier), 1)
        ecart = rapport.a_verifier[0]
        self.assertIn('DISCORDANCE', ecart.valeur_ref)
        self.assertIn('DISCONTINUOSITE', ecart.valeur_conv)
        self.assertEqual(ecart.ligne_ref, 2)

    def test_pagination_differente_pages_orphelines_signalees(self):
        ref = [_page([]), _page_unique('A'), _page_unique('B'), _page_unique('C')]
        conv = [_page_unique('A'), _page_unique('B')]
        rapport = verifier(ref, conv)
        self.assertEqual(rapport.pages_appariees, [(2, 1), (3, 2)])
        self.assertEqual(rapport.pages_ref_orphelines, [4])

    def test_ligne_manquante_a_verifier(self):
        ref = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B']),
                      _ligne(['02', 'B', 'SIGNAL DEUX', '0002B'])])]
        conv = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B'])])]
        rapport = verifier(ref, conv)
        self.assertEqual([e.raison for e in rapport.a_verifier], ['LIGNE_MANQUANTE'])

    def test_ligne_en_trop_a_verifier(self):
        ref = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B'])])]
        conv = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B']),
                       _ligne(['02', 'B', 'SIGNAL INVENTE', '0002B'])])]
        rapport = verifier(ref, conv)
        self.assertEqual([e.raison for e in rapport.a_verifier], ['LIGNE_EN_TROP'])

    def test_ligne_de_bruit_benigne(self):
        ref = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B']), _ligne(['|', '', '', ''])])]
        conv = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B'])])]
        rapport = verifier(ref, conv)
        self.assertEqual(rapport.a_verifier, [])
        self.assertEqual([e.raison for e in rapport.benins], ['LIGNE_BRUIT'])

    def test_ligne_manquante_a_faible_confiance_benigne(self):
        ref = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B']),
                      _ligne(['02', 'B', 'SIGNAL DEUX', '0002B'], [20, 20, 20, 20])])]
        conv = [_page([_ligne(['01', 'A', 'SIGNAL UN', '0001B'])])]
        self.assertEqual(verifier(ref, conv).a_verifier, [])

    def test_distance_injectee_appelee(self):
        distance = MagicMock(return_value=9)
        ref = [_page([_ligne(['01', 'A', 'DISCORDANCE', '1'], [95] * 4)])]
        conv = [_page([_ligne(['01', 'A', 'DISCONTINUOSITE', '1'])])]
        verifier(ref, conv, distance=distance)
        distance.assert_called()

    def test_valeurs_connues_prises_en_compte(self):
        ref = [_page([_ligne(['01', 'R', 'TC IDPO8', '1'], [90, 90, 80, 90])])]
        conv = [_page([_ligne(['01', 'R', 'TC IDPO1', '1'])])]
        rapport = verifier(ref, conv, valeurs_connues={'signal': ['TC IDPO1']})
        self.assertEqual(rapport.a_verifier, [])

    def test_dict_seul_accepte(self):
        page = _page_unique('A')
        self.assertEqual(verifier(page, page).concordance, 1.0)

    def test_documents_vides(self):
        rapport = verifier([], [])
        self.assertEqual((rapport.nb_cellules, rapport.concordance), (0, 1.0))

    def test_entree_invalide_leve_typeerror(self):
        with self.assertRaises(TypeError):
            verifier(None, [])
        with self.assertRaises(TypeError):
            verifier([], 42)
        with self.assertRaises(TypeError):
            verifier([1, 2], [])

    def test_seuil_de_concordance_lu_dans_config(self):
        ref = [_page_unique('A')]
        conv = [_page([
            _ligne([c[0], c[1], c[2] + 'X', c[3]])
            for c in (r['cells'] for r in ref[0]['rows'])
        ])]
        rapport = verifier(ref, conv)
        self.assertLess(rapport.concordance, Config.VERIF_SEUIL_CONCORDANCE)
        self.assertFalse(rapport.fidele)
        with patch.object(Config, 'VERIF_SEUIL_CONCORDANCE', 0.0):
            self.assertTrue(rapport.fidele)


class TestRapportVerification(unittest.TestCase):

    def _ecart(self, classe, nb=1):
        return Ecart(1, 1, 1, 1, 'SIGNAL', 'a', 'b', classe, nb_cellules=nb)

    def test_rapport_vide_concordance_totale(self):
        self.assertEqual(RapportVerification().concordance, 1.0)

    def test_ajouter_compte_par_classe(self):
        r = RapportVerification()
        r.ajouter([self._ecart(IDENTIQUE), self._ecart(BENIN), self._ecart(A_VERIFIER, 2)])
        self.assertEqual((r.nb_cellules, r.nb_identiques, r.nb_benins), (4, 1, 1))
        self.assertEqual(r.nb_a_verifier, 2)
        self.assertAlmostEqual(r.concordance, 0.5)

    def test_seuls_les_a_verifier_remontent(self):
        r = RapportVerification()
        r.ajouter([self._ecart(BENIN), self._ecart(A_VERIFIER)])
        self.assertEqual(len(r.a_verifier), 1)
        self.assertEqual(len(r.benins), 1)


class TestFormaterRapport(unittest.TestCase):

    def test_sans_divergence(self):
        page = _page_unique('A')
        texte = formater_rapport(verifier(page, page))
        self.assertIn('concordance 100.0 %', texte)
        self.assertIn('Aucune divergence à vérifier', texte)

    def test_liste_les_divergences(self):
        ref = [_page([_ligne(['01', 'A', 'DISCORDANCE POMPE', '1'], [95] * 4)])]
        conv = [_page([_ligne(['01', 'A', 'DISCONTINUOSITE POMPE', '1'])])]
        texte = formater_rapport(verifier(ref, conv))
        self.assertIn('DISCORDANCE POMPE', texte)
        self.assertIn('DISCONTINUOSITE POMPE', texte)
        self.assertIn('À VÉRIFIER (1)', texte)

    def test_max_ecarts_tronque_la_liste(self):
        r = RapportVerification()
        for i in range(5):
            r.ajouter([Ecart(1, 1, i, i, 'SIGNAL', f"a{i}", f"b{i}", A_VERIFIER)])
        texte = formater_rapport(r, max_ecarts=2)
        self.assertIn('a0', texte)
        self.assertNotIn('a4', texte)


class TestEcart(unittest.TestCase):

    def test_ecart_immuable(self):
        e = Ecart(1, 1, 1, 1, 'SIGNAL', 'a', 'b', A_VERIFIER)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.classe = BENIN

    def test_valeurs_par_defaut(self):
        e = Ecart(1, 1, None, None, 'SIGNAL', 'a', 'b', BENIN)
        defauts = (e.raison, e.confiance_ref, e.distance, e.nb_cellules)
        self.assertEqual(defauts, ('', None, None, 1))


if __name__ == '__main__':
    unittest.main()
