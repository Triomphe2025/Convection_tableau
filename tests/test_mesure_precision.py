"""
Tests de mesure_precision.py, sur données entièrement fabriquées : une classe
par fonction publique, cas nominal + cas limites + cas d'erreur (Règle 07).

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_mesure_precision.py -v
"""
import unittest

import mesure_precision as mp

COLONNES = ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT']


def _ligne(cells, exact=False):
    ligne = {'type': 'data', 'cells': list(cells), 'confidence': [100] * len(cells)}
    if exact:
        ligne['exact'] = True
    return ligne


def _page(rows, pied=None):
    return {'success': True, 'rows': rows, 'metadata': {}, 'pied_texte': pied or []}


class TestClasserCellule(unittest.TestCase):

    def test_valeurs_identiques(self):
        self.assertEqual(mp.classer_cellule('PH TA106 01', 'PH TA106 01'), mp.IDENTIQUE)

    def test_espacement_seul(self):
        # Un espace déplacé change la césure des mots sans changer leur texte.
        self.assertEqual(mp.classer_cellule('PHA 104', 'PH A104'), mp.ESPACEMENT)

    def test_confusion_de_caractere(self):
        # O/0 : paire dans Config.MESURE_CONFUSIONS_OCR
        self.assertEqual(mp.classer_cellule('B0RNE', 'BORNE'), mp.CONFUSION)

    def test_confusion_t_i(self):
        self.assertEqual(mp.classer_cellule('TSPAT ITIN', 'TSPAT ITTN'), mp.CONFUSION)

    def test_contenu_different_sans_rapport_avec_confusion(self):
        self.assertEqual(mp.classer_cellule('PH QTEL2 21', 'PH QUEL2 21'), mp.CONTENU_DIFFERENT)

    def test_reference_vide(self):
        self.assertEqual(mp.classer_cellule('', 'PH TB203 05'), mp.AJOUTE)

    def test_converti_vide(self):
        self.assertEqual(mp.classer_cellule('PH TB203 05', ''), mp.MANQUANT)

    def test_les_deux_vides_sont_identiques(self):
        self.assertEqual(mp.classer_cellule('', ''), mp.IDENTIQUE)

    def test_none_traite_comme_vide(self):
        self.assertEqual(mp.classer_cellule(None, 'TENANT'), mp.AJOUTE)


class TestExtrairePied(unittest.TestCase):

    def test_paires_multiples_sur_une_ligne(self):
        texte = 'CABLE : ACC/PH01  TYPE : 2P.279  N° PLAN : 223111PE011  INDICE : R  PAGE : 1'
        paires = mp.extraire_pied(texte)
        self.assertEqual(paires['CABLE'], 'ACC/PH01')
        self.assertEqual(paires['TYPE'], '2P.279')
        self.assertEqual(paires['N° PLAN'], '223111PE011')
        self.assertEqual(paires['INDICE'], 'R')
        self.assertEqual(paires['PAGE'], '1')

    def test_variantes_de_libelle_normalisees(self):
        self.assertIn('N° PLAN', mp.extraire_pied('NO PLAN : 223400PE137'))
        self.assertIn('PET', mp.extraire_pied('P.E.T. : EPEULE'))

    def test_libelle_complement_reconnu(self):
        paires = mp.extraire_pied('TYPE : 7P.279  COMPLÉMENT : 6/10')
        self.assertEqual(paires, {'TYPE': '7P.279', 'COMPLEMENT': '6/10'})

    def test_texte_sans_libelle_retourne_vide(self):
        self.assertEqual(mp.extraire_pied('juste du texte quelconque'), {})

    def test_chaine_vide(self):
        self.assertEqual(mp.extraire_pied(''), {})

    def test_none(self):
        self.assertEqual(mp.extraire_pied(None), {})


class TestComparerPieds(unittest.TestCase):

    def test_libelle_different_remonte_un_ecart(self):
        ref = _page([], pied=['CABLE : ACC/PH01  PAGE : 1'])
        conv = _page([], pied=['CABLE : ACC/PH02  PAGE : 1'])
        ecarts = mp.comparer_pieds(ref, conv, 0, 0)
        self.assertEqual(len(ecarts), 1)
        self.assertEqual(ecarts[0].libelle, 'CABLE')
        self.assertEqual(ecarts[0].valeur_ref, 'ACC/PH01')
        self.assertEqual(ecarts[0].valeur_conv, 'ACC/PH02')

    def test_libelles_identiques_aucun_ecart(self):
        ref = _page([], pied=['CABLE : ACC/PH01  PAGE : 1'])
        conv = _page([], pied=['CABLE : ACC/PH01  PAGE : 1'])
        self.assertEqual(mp.comparer_pieds(ref, conv, 0, 0), [])

    def test_libelle_present_seulement_cote_reference(self):
        ref = _page([], pied=['CABLE : ACC/PH01  TYPE : 2P.279'])
        conv = _page([], pied=['CABLE : ACC/PH01'])
        ecarts = mp.comparer_pieds(ref, conv, 0, 0)
        self.assertEqual([e.libelle for e in ecarts], ['TYPE'])
        self.assertEqual(ecarts[0].valeur_conv, '')

    def test_libelle_present_seulement_cote_converti(self):
        ref = _page([], pied=['CABLE : ACC/PH01'])
        conv = _page([], pied=['CABLE : ACC/PH01  INDICE : R'])
        ecarts = mp.comparer_pieds(ref, conv, 0, 0)
        self.assertEqual([e.libelle for e in ecarts], ['INDICE'])
        self.assertEqual(ecarts[0].valeur_ref, '')

    def test_complement_de_la_verite_compare_au_texte_libre_apres_le_type(self):
        ref = _page([], pied=['TYPE : 2P.279  COMPLEMENT : 8/10'])
        conv = _page([], pied=['TYPE :    2P.279 8/10'])
        self.assertEqual(mp.comparer_pieds(ref, conv, 0, 0), [])

    def test_complement_perdu_reste_un_pied_faux(self):
        ref = _page([], pied=['TYPE : 3PC200  COMPLEMENT : REF CE 8707905'])
        conv = _page([], pied=['TYPE :    3PC200'])
        ecarts = mp.comparer_pieds(ref, conv, 0, 0)
        self.assertEqual([(e.libelle, e.valeur_ref, e.valeur_conv) for e in ecarts],
                         [('COMPLEMENT', 'REF CE 8707905', '')])

    def test_complement_contenant_le_mot_type(self):
        ref = _page([], pied=['TYPE : 30P887  COMPLEMENT : CORDON TYPE 40'])
        conv = _page([], pied=['TYPE :    30P887 CORDON TYPE 40'])
        self.assertEqual(mp.comparer_pieds(ref, conv, 0, 0), [])

    def test_type_different_signale_sur_le_type_seul(self):
        ref = _page([], pied=['TYPE : 2P.279  COMPLEMENT : 8/10'])
        conv = _page([], pied=['TYPE : 2P.297 8/10'])
        ecarts = mp.comparer_pieds(ref, conv, 0, 0)
        self.assertEqual([e.libelle for e in ecarts], ['TYPE'])

    def test_pas_de_pied_du_tout(self):
        self.assertEqual(mp.comparer_pieds(_page([]), _page([]), 0, 0), [])


class TestAlignerLignes(unittest.TestCase):

    def test_lignes_identiques_appariees_1_pour_1(self):
        lignes = [_ligne(['1', 'A', 'X', 'Y']), _ligne(['2', 'B', 'X', 'Y'])]
        self.assertEqual(mp.aligner_lignes(lignes, lignes), [(0, 0), (1, 1)])

    def test_ligne_manquante_cote_converti(self):
        ref = [_ligne(['1', 'A', 'X', 'Y']), _ligne(['2', 'B', 'X', 'Y'])]
        conv = [_ligne(['1', 'A', 'X', 'Y'])]
        couples = mp.aligner_lignes(ref, conv)
        self.assertIn((1, None), couples)

    def test_ligne_en_trop_cote_converti(self):
        ref = [_ligne(['1', 'A', 'X', 'Y'])]
        conv = [_ligne(['1', 'A', 'X', 'Y']), _ligne(['2', 'B', 'X', 'Y'])]
        couples = mp.aligner_lignes(ref, conv)
        self.assertIn((None, 1), couples)

    def test_listes_vides(self):
        self.assertEqual(mp.aligner_lignes([], []), [])

    def test_bloc_different_aligne_par_needleman_wunsch(self):
        # Une ligne mal lue au milieu doit rester appariée à son homologue,
        # pas décalée sur toute la suite du bloc.
        ref = [_ligne(['1', 'A', 'SIGNAL UN', 'Y']), _ligne(['2', 'B', 'SIGNAL DEUX', 'Y'])]
        conv = [_ligne(['1', 'A', 'SIGNAL UN', 'Y']), _ligne(['2', 'B', 'SIGNAL DEUZ', 'Y'])]
        couples = mp.aligner_lignes(ref, conv)
        self.assertIn((1, 1), couples)


class TestApparierPagesParContenu(unittest.TestCase):

    def _page_avec_contenu(self, tag):
        lignes = [_ligne([f'{tag}{i}', 'A', 'SIGNAL', 'ABOUT']) for i in range(5)]
        return _page(lignes)

    def test_deux_documents_identiques(self):
        pages = [self._page_avec_contenu('A'), self._page_avec_contenu('B')]
        paires, ref_orph, conv_orph = mp.apparier_pages_par_contenu(pages, pages)
        self.assertEqual(paires, [(0, 0), (1, 1)])
        self.assertEqual(ref_orph, [])
        self.assertEqual(conv_orph, [])

    def test_page_reference_absente_du_converti(self):
        ref = [self._page_avec_contenu('A'), self._page_avec_contenu('B')]
        conv = [self._page_avec_contenu('A')]
        paires, ref_orph, conv_orph = mp.apparier_pages_par_contenu(ref, conv)
        self.assertEqual(paires, [(0, 0)])
        self.assertEqual(ref_orph, [1])

    def test_pages_rangees_dans_un_autre_ordre_toutes_appariees(self):
        # La sortie range B avant A : un appariement monotone en perdrait une.
        ref = [self._page_avec_contenu('A'), self._page_avec_contenu('B')]
        conv = [self._page_avec_contenu('B'), self._page_avec_contenu('A')]
        paires, ref_orph, conv_orph = mp.apparier_pages_par_contenu(ref, conv)
        self.assertEqual(paires, [(0, 1), (1, 0)])
        self.assertEqual((ref_orph, conv_orph), ([], []))

    def test_un_seul_candidat_par_page_suffit_pour_des_pages_distinctes(self):
        from unittest.mock import patch
        ref = [self._page_avec_contenu(t) for t in 'ABC']
        conv = [self._page_avec_contenu(t) for t in 'CAB']
        with patch.object(mp.Config, 'MESURE_CANDIDATS_PAGE', 1):
            paires, ref_orph, conv_orph = mp.apparier_pages_par_contenu(ref, conv)
        self.assertEqual(paires, [(0, 1), (1, 2), (2, 0)])

    def test_page_sans_ligne_de_donnees_mais_avec_pied_reste_utile(self):
        ref = [_page([], pied=['CABLE : RESERVE  PAGE : 104'])]
        conv = [_page([], pied=[])]
        paires, ref_orph, conv_orph = mp.apparier_pages_par_contenu(ref, conv)
        # Aucune page utile côté converti -> la page réf reste orpheline.
        self.assertEqual(paires, [])
        self.assertEqual(ref_orph, [0])

    def test_page_entierement_vide_ignoree_des_deux_cotes(self):
        ref = [_page([])]
        conv = [_page([])]
        paires, ref_orph, conv_orph = mp.apparier_pages_par_contenu(ref, conv)
        self.assertEqual((paires, ref_orph, conv_orph), ([], [], []))

    def test_listes_vides(self):
        self.assertEqual(mp.apparier_pages_par_contenu([], []), ([], [], []))


class TestMotsEtJaccard(unittest.TestCase):

    def test_mots_de_toutes_les_cellules(self):
        page = _page([_ligne(['PH A104', 'RESERVE CABLEE'])])
        self.assertEqual(mp._mots_page(page), {'PH', 'A104', 'RESERVE', 'CABLEE'})

    def test_page_sans_ligne(self):
        self.assertEqual(mp._mots_page(_page([])), set())

    def test_jaccard(self):
        self.assertEqual(mp._jaccard({'A', 'B'}, {'B', 'C'}), 1 / 3)
        self.assertEqual(mp._jaccard(set(), set()), 1.0)
        self.assertEqual(mp._jaccard({'A'}, set()), 0.0)


class TestGlissements(unittest.TestCase):

    def test_valeur_passee_dans_la_colonne_suivante(self):
        self.assertEqual(mp.glissements(['G', 'PH Q 09', '', 'X'], ['G', '', 'PH Q 09', 'X']),
                         {1, 2})

    def test_vers_la_colonne_precedente_avec_texte_deja_present(self):
        self.assertEqual(mp.glissements(['A', 'B', 'C', 'PH 01'], ['A', 'B', 'C PH 01', '']),
                         {2, 3})

    def test_mot_perdu_sans_reapparition_n_est_pas_un_glissement(self):
        self.assertEqual(mp.glissements(['A', 'TEL PMS', 'X', ''], ['A', 'TEL', 'X', '']), set())

    def test_echange_avec_autre_changement_n_est_pas_un_glissement(self):
        self.assertEqual(mp.glissements(['A', 'B', '', ''], ['A', '', 'B Z', '']), set())

    def test_ligne_identique(self):
        self.assertEqual(mp.glissements(['A', 'B'], ['A', 'B']), set())


class TestApparierDeplacees(unittest.TestCase):

    def test_absente_et_en_trop_de_meme_contenu(self):
        orph = [mp.LigneOrpheline('MANQUANTE', 0, 4, 'A|B'),
                mp.LigneOrpheline('EN_TROP', 0, 5, 'A|B'),
                mp.LigneOrpheline('EN_TROP', 0, 9, 'C|D')]
        restantes, deplacees = mp.apparier_deplacees(orph, 0, 0)
        self.assertEqual(deplacees, [mp.LigneDeplacee(0, 4, 0, 5, 'A|B')])
        self.assertEqual(restantes, [orph[2]])

    def test_contenus_differents_restent_orphelins(self):
        orph = [mp.LigneOrpheline('MANQUANTE', 0, 4, 'A|B'),
                mp.LigneOrpheline('EN_TROP', 0, 5, 'A|C')]
        self.assertEqual(mp.apparier_deplacees(orph, 0, 0), (orph, []))


class TestComparerPage(unittest.TestCase):

    def test_cellule_differente_remonte_un_ecart(self):
        ref = _page([_ligne(['G', 'PH QTEL2 21', 'TEL PET', 'PH TELPH/A 01'])])
        conv = _page([_ligne(['G', 'PH QUEL2 21', 'TEL PET', 'PH TELPH/A 01'])])
        ecarts, positions, orph = mp.comparer_page(ref, conv, 0, 0, COLONNES)
        self.assertEqual(len(ecarts), 1)
        self.assertEqual(ecarts[0].colonne, 'TENANT')
        self.assertEqual(orph, [])

    def test_cellule_manquante_cote_converti(self):
        ref = _page([_ligne(['5 M', 'PH QC 05', 'OC FS 14 50', 'PH TB203 05'])])
        conv = _page([_ligne(['5 M', 'PH QC 05', 'OC FS 14 50', ''])])
        ecarts, positions, orph = mp.comparer_page(ref, conv, 0, 0, COLONNES)
        self.assertEqual(len(ecarts), 1)
        self.assertEqual(ecarts[0].classe, mp.MANQUANT)
        self.assertEqual(ecarts[0].colonne, 'ABOUTISSANT')

    def test_ligne_orpheline_remontee(self):
        ref = _page([_ligne(['1', 'A', 'X', 'Y']), _ligne(['2', 'B', 'X', 'Y'])])
        conv = _page([_ligne(['1', 'A', 'X', 'Y'])])
        ecarts, positions, orph = mp.comparer_page(ref, conv, 0, 0, COLONNES)
        self.assertEqual(len(orph), 1)
        self.assertEqual(orph[0].cote, mp._LIGNE_MANQUANTE)

    def test_ecart_de_position_si_reference_exacte(self):
        # Même texte une fois les espaces réduits (donc IDENTIQUE), mais la
        # césure d'origine diffère : la référence exacte doit le signaler.
        ref = _page([_ligne(['1', 'A', 'PH   A104', 'Y'], exact=True)])
        conv = _page([_ligne(['1', 'A', 'PH A104', 'Y'])])
        ecarts, positions, orph = mp.comparer_page(ref, conv, 0, 0, COLONNES)
        self.assertEqual(ecarts, [])
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].colonne, 'SIGNAL')

    def test_pages_vides(self):
        ecarts, positions, orph = mp.comparer_page(_page([]), _page([]), 0, 0, COLONNES)
        self.assertEqual((ecarts, positions, orph), ([], [], []))


class TestMesurer(unittest.TestCase):

    def test_cas_reel_discordance_tel2(self):
        pied = ['CABLE : WPHR/TEL  PAGE : 122']
        ref = [_page([_ligne(['G', 'PH QTEL2 21', 'TEL PET', 'PH TELPH/A 01'])], pied=pied)]
        conv = [_page([_ligne(['G', 'PH QUEL2 21', 'TEL PET', 'PH TELPH/A 01'])], pied=pied)]
        rapport = mp.mesurer(ref, conv, COLONNES)
        self.assertEqual(len(rapport.ecarts_cellules), 1)
        self.assertIn('QTEL2', rapport.ecarts_cellules[0].valeur_ref)

    def test_page_absente_remontee(self):
        utile = [_ligne(['1', 'A', 'X', 'Y'])]
        ref = [_page(utile), _page([], pied=['CABLE : RESERVE  PAGE : 104'])]
        conv = [_page(utile)]
        rapport = mp.mesurer(ref, conv, COLONNES)
        self.assertEqual(rapport.pages_ref_orphelines, [1])

    def test_precision_1_0_si_tout_identique(self):
        utile = [_ligne(['1', 'A', 'X', 'Y'])]
        rapport = mp.mesurer([_page(utile)], [_page(utile)], COLONNES)
        self.assertEqual(rapport.precision, 1.0)

    def test_deux_listes_vides(self):
        rapport = mp.mesurer([], [], COLONNES)
        self.assertEqual(rapport.nb_cellules_comparees, 0)
        self.assertEqual(rapport.precision, 1.0)


class TestRapportMesure(unittest.TestCase):

    def test_precision_sans_cellule_comparee(self):
        self.assertEqual(mp.RapportMesure().precision, 1.0)

    def test_cellules_par_classe_compte_par_categorie(self):
        rapport = mp.RapportMesure(ecarts_cellules=[
            mp.EcartCellule(0, 0, 0, 0, 'SIGNAL', 'A', 'B', mp.CONTENU_DIFFERENT),
            mp.EcartCellule(0, 0, 1, 1, 'SIGNAL', 'C', 'D', mp.CONTENU_DIFFERENT),
            mp.EcartCellule(0, 0, 2, 2, 'SIGNAL', 'E', '', mp.MANQUANT),
        ])
        self.assertEqual(rapport.cellules_par_classe(), {mp.CONTENU_DIFFERENT: 2, mp.MANQUANT: 1})

    def test_cellules_par_classe_vide(self):
        self.assertEqual(mp.RapportMesure().cellules_par_classe(), {})


class TestDebutAbsolu(unittest.TestCase):
    """Début d'un mot compté depuis le caractère le plus à gauche de la colonne sur la page."""

    def test_origines_colonnes(self):
        lignes = [_ligne(['  A', 'PH 01', '', '']), _ligne([' B', '   PH 02', '', 'X'])]
        self.assertEqual(mp.origines_colonnes(lignes, 4), [1, 0, 0, 0])

    def test_retrait_d_une_cellule_detecte(self):
        ref = _page([_ligne(['RM 03B', 'X'], exact=True), _ligne(['DA 22', 'Y'], exact=True)])
        conv = _page([_ligne([' RM 03B', 'X']), _ligne(['DA 22', 'Y'])])
        _, positions, _ = mp.comparer_page(ref, conv, 0, 0, ['TENANT', 'JAR'])
        self.assertEqual([(e.ligne_ref, e.decalages_ref, e.decalages_conv) for e in positions],
                         [(0, (0, 3), (1, 4))])

    def test_retrait_commun_a_toute_la_colonne_sans_effet(self):
        ref = _page([_ligne(['RM 03B', 'X'], exact=True), _ligne(['DA 22', 'Y'], exact=True)])
        conv = _page([_ligne(['  RM 03B', 'X']), _ligne(['  DA 22', 'Y'])])
        self.assertEqual(mp.comparer_page(ref, conv, 0, 0, ['TENANT', 'JAR'])[1], [])


class TestComparerSections(unittest.TestCase):

    def _p(self, *textes):
        return _page([{'type': 'section', 'text': t} for t in textes])

    def test_identiques_espaces_reduits(self):
        self.assertEqual(mp.comparer_sections(self._p('NOM DU CABLE : A'),
                                              self._p('NOM DU CABLE :  A'), 0, 0), ([], []))

    def test_texte_different_et_section_absente(self):
        ecarts, orph = mp.comparer_sections(self._p('NOM DU CABLE : A', 'NOM DU CABLE : B'),
                                            self._p('NOM DU CABLE: A'), 0, 0)
        self.assertEqual([(e.colonne, e.classe) for e in ecarts], [('SECTION', 'ESPACEMENT')])
        self.assertEqual([(o.cote, o.contenu) for o in orph],
                         [('MANQUANTE', 'SECTION NOM DU CABLE : B')])


class TestPositionsSections(unittest.TestCase):
    """Section dont la vérité donne les positions : mesurée depuis la colonne 0 du tableau."""

    TEXTE = 'NOM DU CABLE : WPHR/A105'

    def _ref(self):
        return _page([{'type': 'section', 'text': self.TEXTE, 'cells': [self.TEXTE, '', '', ''],
                       'positions': {'FIL': (0, 4, 7, 13, 18)}}, _ligne(['01', 'X', '', ''])])

    def _conv(self, brut):
        return _page([{'type': 'section', 'text': brut.strip(), 'cells': [brut, '', '', '']},
                      _ligne(['01', 'X', '', ''])])

    def test_espaces_ecrases_signales(self):
        positions = mp.positions_sections(self._ref(), self._conv(self.TEXTE), 0, 0, COLONNES)
        self.assertEqual([(e.colonne, e.decalages_ref, e.decalages_conv) for e in positions],
                         [('FIL', (0, 4, 7, 13, 18), (0, 4, 7, 13, 15))])

    def test_positions_d_origine_conformes(self):
        brut = 'NOM DU CABLE :    WPHR/A105'
        self.assertEqual(mp.positions_sections(self._ref(), self._conv(brut), 0, 0, COLONNES), [])

    def test_texte_different_ou_sans_verite_non_mesure(self):
        sans = _page([{'type': 'section', 'text': self.TEXTE, 'cells': [self.TEXTE]}])
        self.assertEqual(mp.positions_sections(sans, self._conv(self.TEXTE), 0, 0, COLONNES), [])
        autre = self._conv('NOM DU CABLE : WPHR/A107')
        self.assertEqual(mp.positions_sections(self._ref(), autre, 0, 0, COLONNES), [])

    def test_compte_dans_la_mesure(self):
        rapport = mp.mesurer([self._ref()], [self._conv(self.TEXTE)], COLONNES)
        self.assertEqual(len(rapport.ecarts_positions), 1)


class TestComparerAlertes(unittest.TestCase):

    def test_attendue_trouvee_sans_accents_ni_ponctuation(self):
        manquantes, fausses = mp.comparer_alertes(
            ["Corrigé O → 0 : l'original porte « D3T O1A »"],
            ["page 18 l.3 TENANT : corrige O -> 0 : l'original porte D3T O1A"])
        self.assertEqual((manquantes, fausses), ([], []))

    def test_manquante_et_fausse(self):
        manquantes, fausses = mp.comparer_alertes(['PAGE non imprimée'], ['BORNIER absent'])
        self.assertEqual((manquantes, fausses), (['PAGE non imprimée'], ['BORNIER absent']))

    def test_une_ligne_ne_couvre_qu_une_attente(self):
        manquantes, _ = mp.comparer_alertes(['O1A', 'O1A'], ['porte O1A'])
        self.assertEqual(manquantes, ['O1A'])


class TestVerifierControleIndice(unittest.TestCase):

    def test_ok_attendu_et_emis_avec_les_bons_indices(self):
        conforme, _ = mp.verifier_controle_indice(
            ['R', 'TP2', '03'], ['R', 'TP2', '03'],
            ['  ✓ contrôle INDICE : OK, 3 page(s), indices lus : R, TP2, 03'])
        self.assertTrue(conforme)

    def test_ok_attendu_absent(self):
        journal = ['⚠ contrôle INDICE impossible']
        self.assertFalse(mp.verifier_controle_indice(['R'], ['R'], journal)[0])

    def test_indices_lus_differents(self):
        conforme, detail = mp.verifier_controle_indice(
            ['R', 'R4'], ['R', 'R4'], ['✓ contrôle INDICE : OK, 1 page(s), indices lus : R'])
        self.assertFalse(conforme)
        self.assertIn('R4', detail)


class TestComparerPiedsStrictsEtSchema(unittest.TestCase):

    def test_libelle_strict_espaces_comptent(self):
        ref = _page([], pied=['N° PLAN : 223111PE012  LOGO : SIEMENS'])
        ref.update(libelles_pied=['LOGO', 'N° PLAN'], libelles_stricts=['LOGO', 'N° PLAN'])
        conv = _page([], pied=['LOGO : S I E M E N S', 'N° PLAN : 223 111 PE 012'])
        self.assertEqual(sorted(e.libelle for e in mp.comparer_pieds(ref, conv, 0, 0)),
                         ['LOGO', 'N° PLAN'])

    def test_texte_fixe_retire_et_libelle_hors_schema_ignore(self):
        ref = _page([], pied=['P.E.T. : SAINT MAURICE'])
        ref.update(libelles_pied=['PET'], libelles_stricts=[], pied_autre=['JARRETIERAGE'])
        conv = _page([], pied=['P.E.T. : SAINT MAURICE JARRETIERAGE  BORNIER : X'])
        self.assertEqual(mp.comparer_pieds(ref, conv, 0, 0), [])

    def test_reference_sans_schema_ignore_le_logo(self):
        conv = _page([], pied=['LOGO : MATRA', 'PAGE : 3'])
        self.assertEqual(mp.comparer_pieds(_page([], pied=['PAGE : 3']), conv, 0, 0), [])


class TestRemplacerPositions(unittest.TestCase):

    def _pos(self, page_conv):
        return mp.EcartPosition(0, page_conv, 0, 0, 'SIGNAL', (0, 3), (0, 4))

    def test_pages_couvertes_remplacees_les_autres_gardees(self):
        rapport = mp.RapportMesure(ecarts_positions=[self._pos(1), self._pos(2)])
        geometrie = mp.RapportMesure(pages_appariees=[(5, 2)], ecarts_positions=[self._pos(2)])
        mp.remplacer_positions(rapport, geometrie)
        self.assertEqual(rapport.ecarts_positions, [self._pos(1), self._pos(2)])
        self.assertEqual(rapport.pages_positions_geometriques, [(5, 2)])

    def test_page_couverte_sans_ecart_efface_l_ancien(self):
        rapport = mp.RapportMesure(ecarts_positions=[self._pos(2)])
        mp.remplacer_positions(rapport, mp.RapportMesure(pages_appariees=[(5, 2)]))
        self.assertEqual(rapport.ecarts_positions, [])


class TestFormaterRapport(unittest.TestCase):

    def test_contient_les_comptes_principaux(self):
        ecart = mp.EcartCellule(0, 0, 0, 0, 'SIGNAL', 'A', 'B', mp.CONTENU_DIFFERENT)
        rapport = mp.RapportMesure(
            pages_appariees=[(0, 0)], nb_cellules_comparees=10, nb_cellules_identiques=9,
            ecarts_cellules=[ecart],
        )
        texte = mp.formater_rapport(rapport)
        self.assertIn('Pages appariées', texte)
        self.assertIn('90.0%', texte)
        self.assertIn('CONTENU_DIFFERENT', texte)

    def test_max_ecarts_tronque_la_liste(self):
        ecarts = [
            mp.EcartCellule(0, 0, i, i, 'SIGNAL', 'A', 'B', mp.CONTENU_DIFFERENT) for i in range(5)
        ]
        texte = mp.formater_rapport(mp.RapportMesure(ecarts_cellules=ecarts), max_ecarts=2)
        self.assertIn('supplémentaire', texte)

    def test_rapport_vide(self):
        texte = mp.formater_rapport(mp.RapportMesure())
        self.assertIn('100.0%', texte)


if __name__ == '__main__':
    unittest.main()
