"""
Tests de campagne_mesure.py avec un faux client Anthropic : aucun appel API.

Document réduit à 2 pages de l'extrait 223111PE011 (une page Paper Capture,
relue par le faux Claude ; une page vectorielle, lue en grille) pour que chaque
passage ne fasse qu'un appel simulé.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_campagne_mesure.py -v
"""
import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz

import campagne_mesure as cm
from config import Config

FIXTURES = Path(__file__).parent / 'fixtures'
EXTRAIT = FIXTURES / '223111PE011_extrait_10pages.pdf'
VERITE = FIXTURES / '223111PE011_extrait_verite.xlsx'
CLE_TEST = 'sk-cle-de-test-ne-doit-jamais-etre-ecrite'

TEXTE_FAUX = (
    "TYPE_PAGE: listing\n"
    "G | PH QTEL2 09 | TEL PMS Q1 | PH ACC/A 01\n"
    'META: {"PAGE": "1", "BORNIER": "", "PET": "", "NO_PLAN": "", "INDICE": "R"}\n'
)


class FauxAnthropic:
    """Remplace anthropic.Anthropic : 1000 tokens en entrée, 500 en sortie par appel."""

    requetes = []
    identifiant_fixe = None
    texte = TEXTE_FAUX

    def __init__(self, api_key=None):
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        FauxAnthropic.requetes.append(kwargs)
        ident = FauxAnthropic.identifiant_fixe or f"msg_faux_{len(FauxAnthropic.requetes)}"
        return SimpleNamespace(
            id=ident,
            content=[SimpleNamespace(type='text', text=FauxAnthropic.texte)],
            stop_reason='end_turn', model=kwargs['model'],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500,
                                  cache_read_input_tokens=0, cache_creation_input_tokens=0),
        )


def _pdf_deux_pages(dossier: Path) -> Path:
    sortie = fitz.open()
    with fitz.open(str(EXTRAIT)) as src:
        sortie.insert_pdf(src, from_page=0, to_page=0)   # Paper Capture → vision
        sortie.insert_pdf(src, from_page=8, to_page=8)   # page 122a vectorielle → grille
    chemin = dossier / 'extrait_2p.pdf'
    sortie.save(str(chemin))
    sortie.close()
    return chemin


class _BaseCampagne(unittest.TestCase):

    def setUp(self):
        FauxAnthropic.requetes = []
        FauxAnthropic.identifiant_fixe = None
        FauxAnthropic.texte = TEXTE_FAUX
        self._tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self._tmp.name)
        self.pdf = _pdf_deux_pages(self.dossier)
        self.racine = self.dossier / 'mesures'
        self.messages = []

    def tearDown(self):
        self._tmp.cleanup()

    def _campagne(self, modele='claude-haiku-4-5-20251001', effort='aucun', passages=1,
                  budget=None, pdf=None, rejouer=False):
        with patch('anthropic.Anthropic', FauxAnthropic):
            return cm.lancer_campagne(
                modele, effort, passages, pdf or self.pdf, VERITE, 'REPARTITEUR 2',
                self.racine, CLE_TEST, budget=budget, afficher=self.messages.append,
                rejouer=rejouer,
            )


class TestLancerCampagne(_BaseCampagne):

    def test_ligne_csv_aux_bonnes_colonnes(self):
        self._campagne()
        with open(self.racine / cm.NOM_CSV, encoding='utf-8') as f:
            lecteur = csv.DictReader(f)
            self.assertEqual(lecteur.fieldnames, cm.COLONNES_CSV)
            lignes = list(lecteur)
        self.assertEqual(len(lignes), 1)
        ligne = lignes[0]
        self.assertEqual(ligne['modele'], 'claude-haiku-4-5-20251001')
        self.assertEqual(ligne['effort'], 'aucun')
        self.assertEqual(ligne['pages_envoyees'], '1')
        self.assertEqual((ligne['tokens_entree'], ligne['tokens_sortie']), ('1000', '500'))
        self.assertAlmostEqual(float(ligne['cout_usd']), (1000 * 1 + 500 * 5) / 1e6)
        for colonne in ('cellules_fausses', 'positions_fausses', 'pieds_faux',
                        'lignes_manquantes', 'lignes_en_trop', 'duree_s'):
            float(ligne[colonne])

    def test_compteur_de_colonnes_a_zero(self):
        ligne = self._campagne()[0]
        self.assertEqual((ligne['lignes_tableau_brutes'], ligne['lignes_hors_colonnes']), (1, 0))

    def test_ligne_a_5_segments_comptee_et_citee(self):
        FauxAnthropic.texte = TEXTE_FAUX.replace('| PH ACC/A 01', '| PH ACC | A 01')
        ligne = self._campagne()[0]
        self.assertEqual(ligne['lignes_hors_colonnes'], 1)
        self.assertTrue(any('5 segments' in m and 'PH ACC | A 01' in m for m in self.messages))
        with open(self.racine / cm.NOM_CSV, encoding='utf-8') as f:
            self.assertEqual(next(csv.DictReader(f))['lignes_hors_colonnes'], '1')

    def test_passage_range_dans_son_dossier(self):
        self._campagne(passages=2)
        for n in (1, 2):
            dossier = self.racine / f'extrait_2p_claude-haiku-4-5-20251001_aucun_{n}'
            self.assertTrue((dossier / 'extrait_2p.xlsx').exists())
            self.assertTrue((dossier / 'extrait_2p_claude.jsonl').exists())

    def test_numerotation_propre_a_chaque_document(self):
        self._campagne()
        autre = self.dossier / 'autre_doc.pdf'
        autre.write_bytes(self.pdf.read_bytes())
        self.pdf = autre
        self._campagne()
        self.assertTrue((self.racine / 'autre_doc_claude-haiku-4-5-20251001_aucun_1').exists())

    def test_plafond_arrete_la_campagne(self):
        # 1er passage : 0,0035 $ ; plafond 0,001 $ → arrêt avant le 2e.
        lignes = self._campagne(passages=3, budget=0.001)
        self.assertEqual(len(lignes), 1)
        self.assertEqual(len(FauxAnthropic.requetes), 1)
        self.assertTrue(any('Arrêt avant le passage 2/3' in m for m in self.messages))

    def test_budget_nul_aucun_passage(self):
        self.assertEqual(self._campagne(passages=2, budget=0.0), [])
        self.assertEqual(FauxAnthropic.requetes, [])

    def test_config_py_intacte_et_config_restauree(self):
        config_py = Path(cm.__file__).parent / 'config.py'
        empreinte = hashlib.sha256(config_py.read_bytes()).hexdigest()
        avant = (Config.OCR_MODE, Config.CLAUDE_OCR_MODEL, Config.CLAUDE_EFFORT,
                 Config.CLAUDE_API_KEY)
        self._campagne(modele='claude-opus-5-5', effort='high')
        self.assertEqual(hashlib.sha256(config_py.read_bytes()).hexdigest(), empreinte)
        self.assertEqual((Config.OCR_MODE, Config.CLAUDE_OCR_MODEL, Config.CLAUDE_EFFORT,
                          Config.CLAUDE_API_KEY), avant)

    def test_modele_et_effort_appliques_en_memoire(self):
        self._campagne(modele='claude-opus-5-5', effort='high')
        requete = FauxAnthropic.requetes[0]
        self.assertEqual(requete['model'], 'claude-opus-5-5')
        self.assertEqual(requete['output_config'], {'effort': 'high'})

    def test_effort_aucun_n_envoie_pas_d_effort(self):
        self._campagne(modele='claude-opus-5-5', effort='aucun')
        self.assertNotIn('output_config', FauxAnthropic.requetes[0])

    def test_cle_jamais_ecrite_sur_disque(self):
        self._campagne()
        for fichier in self.racine.rglob('*'):
            if fichier.is_file() and fichier.suffix in ('.csv', '.jsonl', '.log', '.xlsx'):
                self.assertNotIn(CLE_TEST.encode(), fichier.read_bytes(), fichier)

    def test_modele_sans_prix_refuse(self):
        with self.assertRaises(ValueError):
            self._campagne(modele='claude-inconnu')


class TestAppelsReels(_BaseCampagne):

    def test_n_passages_n_vrais_appels(self):
        lignes = self._campagne(passages=3)
        self.assertEqual(len(FauxAnthropic.requetes), 3)
        self.assertEqual([lg['erreurs'] for lg in lignes], ['', '', ''])

    def test_identifiant_repete_signale_comme_rejoue(self):
        FauxAnthropic.identifiant_fixe = 'msg_identique'
        lignes = self._campagne(passages=2)
        self.assertEqual(lignes[0]['erreurs'], '')
        self.assertIn('réponse rejouée', lignes[1]['erreurs'])
        self.assertIn('msg_identique', lignes[1]['erreurs'])

    def test_identifiant_d_une_campagne_precedente_signale(self):
        FauxAnthropic.identifiant_fixe = 'msg_ancien'
        self._campagne()
        self.assertIn('réponse rejouée', self._campagne()[0]['erreurs'])

    def test_journal_comme_source_refuse_sans_option(self):
        journal = self.dossier / 'ancien_claude.jsonl'
        journal.write_text('', 'utf-8')
        with self.assertRaises(ValueError):
            self._campagne(pdf=journal)
        self.assertEqual(FauxAnthropic.requetes, [])


class TestControleAppelsReels(unittest.TestCase):

    def test_sans_identifiant_signale(self):
        problemes = cm.controle_appels_reels({'pages_envoyees': 2, '_ids': ['msg_a']}, set())
        self.assertEqual(problemes, ['1 réponse(s) sans identifiant'])

    def test_identifiants_nouveaux_retenus(self):
        vus = set()
        self.assertEqual(cm.controle_appels_reels({'pages_envoyees': 1, '_ids': ['m1']}, vus), [])
        self.assertEqual(vus, {'m1'})


class TestLireJournal(unittest.TestCase):

    def _journal(self, lignes):
        tmp = tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False, encoding='utf-8')
        tmp.write('\n'.join(lignes))
        tmp.close()
        return Path(tmp.name)

    def test_tokens_additionnes_et_non_listing_pas_une_erreur(self):
        chemin = self._journal([
            '{"image": "p1.png", "success": true,'
            ' "usage": {"input_tokens": 10, "output_tokens": 3}}',
            '{"image": "p2.png", "success": false, "error": "non-listing",'
            ' "usage": {"input_tokens": 5, "output_tokens": 1}}',
            '{"image": "p3.png", "success": false, "error": "reponse tronquee",'
            ' "usage": {"input_tokens": 7, "output_tokens": 9}}',
        ])
        bilan = cm.lire_journal(chemin)
        chemin.unlink()
        self.assertEqual(bilan['pages_envoyees'], 3)
        self.assertEqual((bilan['tokens_entree'], bilan['tokens_sortie']), (22, 13))
        self.assertEqual(bilan['erreurs'], ['p3.png: reponse tronquee'])

    def test_journal_absent(self):
        self.assertEqual(cm.lire_journal(Path('absent.jsonl'))['pages_envoyees'], 0)


class TestLignesHorsColonnes(unittest.TestCase):

    def _journal(self, *entrees):
        import json
        self._tmp = tempfile.TemporaryDirectory()
        chemin = Path(self._tmp.name) / 'x_claude.jsonl'
        chemin.write_text(''.join(json.dumps(e) + '\n' for e in entrees), encoding='utf-8')
        return chemin

    def tearDown(self):
        if hasattr(self, '_tmp'):
            self._tmp.cleanup()

    def test_compte_et_exemples(self):
        brut = '\n'.join(['TYPE_PAGE: listing', 'A | B | C | D', 'A | B | C', 'A | B | C | D | E',
                          'SECTION: NOM DU CABLE : X', 'META: {"PAGE": "1"}',
                          'PIED_BRUT: NO PLAN : P | INDICE : R | PAGE : 1', 'LOGO: M A T R A'])
        bilan = cm.lignes_hors_colonnes(self._journal({'image': 'p1.png', 'raw': brut}), 4)
        self.assertEqual((bilan['lignes_tableau_brutes'], bilan['lignes_hors_colonnes']), (3, 2))
        self.assertEqual(bilan['exemples'], [('p1.png', 3, 'A | B | C'),
                                             ('p1.png', 5, 'A | B | C | D | E')])

    def test_cinq_exemples_au_plus(self):
        brut = '\n'.join(['X | Y'] * 8)
        bilan = cm.lignes_hors_colonnes(self._journal({'image': 'p.png', 'raw': brut}), 4)
        self.assertEqual((bilan['lignes_hors_colonnes'], len(bilan['exemples'])), (8, 5))

    def test_journal_absent_ou_sans_reponse(self):
        self.assertEqual(cm.lignes_hors_colonnes(Path('absent.jsonl'), 4)['lignes_tableau_brutes'],
                         0)
        bilan = cm.lignes_hors_colonnes(self._journal({'image': 'p.png', 'error': 'x'}), 4)
        self.assertEqual(bilan['lignes_tableau_brutes'], 0)


class TestPagesSansPositions(unittest.TestCase):

    def test_pages_non_recalculees_comptees(self):
        journal = [
            "  positions d'origine p. 5 : 420 mot(s) au jumeau exact, 106 par rang",
            "  positions d'origine p. 10 non recalculées : colonnes du cadre non trouvées",
            "  ⚠ positions d'origine p. 11 non recalculées : Tesseract absent",
            "  positions d'origine non recalculées : source Word ou images, sans page PDF",
        ]
        self.assertEqual(cm.pages_sans_positions(journal), 2)

    def test_journal_vide(self):
        self.assertEqual(cm.pages_sans_positions([]), 0)

    def test_colonne_du_csv(self):
        self.assertIn('pages_sans_positions', cm.COLONNES_CSV)


class TestAjouterLigneCsv(unittest.TestCase):

    def test_ancien_entete_reecrit_valeurs_a_leur_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / 'campagne.csv'
            ancien = [c for c in cm.COLONNES_CSV if c not in ('glissement', 'lignes_deplacees')]
            with open(chemin, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=ancien)
                w.writeheader()
                w.writerow({c: c for c in ancien})
            cm.ajouter_ligne_csv(chemin, {c: 'neuf' for c in cm.COLONNES_CSV})
            with open(chemin, encoding='utf-8') as f:
                lecteur = csv.DictReader(f)
                lignes = list(lecteur)
                self.assertEqual(lecteur.fieldnames, cm.COLONNES_CSV)
        self.assertEqual(lignes[0]['cout_usd'], 'cout_usd')
        self.assertEqual(lignes[0]['glissement'], '')
        self.assertEqual(lignes[1]['glissement'], 'neuf')


class TestCoutUsd(unittest.TestCase):

    def test_opus55(self):
        self.assertAlmostEqual(cm.cout_usd('claude-opus-5-5', 1_000_000, 1_000_000), 24.0)

    def test_modele_inconnu(self):
        with self.assertRaises(KeyError):
            cm.cout_usd('claude-inconnu', 1, 1)


class TestTableauComparatif(unittest.TestCase):

    def test_moyenne_ecart_et_cout_par_reglage(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / 'campagne.csv'
            base = {c: '0' for c in cm.COLONNES_CSV}
            base.update(modele='m', effort='medium', document='d.pdf', erreurs='')
            for fausses, cout in ((10, 1.0), (14, 3.0)):
                cm.ajouter_ligne_csv(chemin, dict(base, cellules_fausses=fausses, cout_usd=cout))
            tableau = cm.tableau_comparatif(chemin)
        ligne = [lg for lg in tableau.splitlines() if lg.startswith('m ')][0]
        self.assertIn('12.0', ligne)     # moyenne des cellules fausses
        self.assertIn(' 4 ', ligne)      # écart entre passages
        self.assertIn('2.0000', ligne)   # coût moyen
        self.assertIn('4.0000 $ sur 2 passage(s)', tableau)

    def test_sans_fichier(self):
        self.assertEqual(cm.tableau_comparatif(Path('absent.csv')), "Aucune mesure enregistrée.")


class TestMain(unittest.TestCase):

    def test_sans_cle_refuse(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': ''}), \
                patch.object(Config, 'CLAUDE_API_KEY', ''):
            self.assertEqual(cm.main(['--modele', 'claude-opus-5-5', '--effort', 'medium']), 2)


if __name__ == '__main__':
    unittest.main()
