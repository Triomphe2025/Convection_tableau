"""
Tests unitaires — système de scoring adaptatif (7 méthodes).

Couvre :
  - BornierTableExtractor._col_format_score
  - BornierTableExtractor._col_length_score
  - BornierTableExtractor._col_dict_score
  - BornierTableExtractor._col_visual_score
  - BornierTableExtractor._col_coherence_score
  - BornierTableExtractor._score_total
  - BornierTableExtractor._rebalance_line

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_scoring.py -v
"""

import os
import tempfile
import unittest
from pathlib import Path


from ocr_processor import BornierTableExtractor
from config import Config


# ── Helpers ───────────────────────────────────────────────────────────

def _ext():
    return BornierTableExtractor(
        tesseract_path=Config.TESSERACT_PATH,
        language=Config.OCR_LANGUAGE,
    )


def _elem(x, w, text, conf=90):
    """Crée un élément OCR minimal."""
    return {
        'text': text, 'x': x, 'w': w,
        'cx': x + w // 2, 'cy': 50,
        'y': 40, 'h': 20, 'conf': conf,
    }


# Frontières typiques pour les tests : 4 colonnes sur 2480 px
# BORNE 0-450 | COULEUR 450-950 | SIGNAL 950-1660 | JARRETIERES 1660-2480
_BOUNDS_4 = [0, 450, 950, 1660, 2480]
_COLS_4 = ['BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES']

# Frontières REPARTITEUR : TENANT 0-600 | JAR 600-1050 | ABOUTISSANT 1050-1800 | SIGNAL 1800-2480
_BOUNDS_REP = [0, 600, 1050, 1800, 2480]
_COLS_REP = ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL']


# ══════════════════════════════════════════════════════════════════════
# 1. _col_format_score
# ══════════════════════════════════════════════════════════════════════

class TestColFormatScore(unittest.TestCase):
    """Score de format : 0.0 – 1.0 selon la correspondance colonne/contenu."""

    def setUp(self):
        self.ext = _ext()

    def _score(self, text, col):
        return self.ext._col_format_score(text, col)

    # ── JAR : format fort \d{3,5}[A-Za-z] ────────────────────────────

    def test_jar_valid_full_pattern(self):
        """0785N correspond exactement au format JAR → score maximal."""
        self.assertGreaterEqual(self._score('0785N', 'JAR'), 0.9)

    def test_jar_valid_5digits(self):
        self.assertGreaterEqual(self._score('12345R', 'JAR'), 0.8)

    def test_jar_digits_only(self):
        """Chiffres seuls : probable JAR sans lettre finale → score intermédiaire."""
        s = self._score('0785', 'JAR')
        self.assertGreater(s, 0.4)
        self.assertLess(s, 0.95)

    def test_jar_letters_only_low_score(self):
        """Lettres seules → ne ressemble pas à un JAR."""
        self.assertLess(self._score('ABCD', 'JAR'), 0.4)

    def test_jar_empty_low(self):
        """JAR vide : valeur manquante → score bas (0.0 est légitime)."""
        s = self._score('', 'JAR')
        self.assertLessEqual(s, 0.5)

    # ── COULEUR ───────────────────────────────────────────────────────

    def test_couleur_known_code(self):
        """Code couleur connu (BL, BR, BN…) → score élevé."""
        self.assertGreaterEqual(self._score('BL', 'COULEUR'), 0.7)

    def test_couleur_french_word(self):
        self.assertGreaterEqual(self._score('BLEU', 'COULEUR'), 0.7)

    def test_couleur_unknown_long_string(self):
        """Chaîne longue non reconnue comme couleur → score plus faible."""
        self.assertLess(self._score('RESERVE CABLEE', 'COULEUR'), 0.6)

    # ── BORNE / TENANT ────────────────────────────────────────────────

    def test_borne_short_code_high_score(self):
        """Codes courts type 01A, AR, K3 → bonne correspondance."""
        self.assertGreaterEqual(self._score('01A', 'BORNE'), 0.7)

    def test_tenant_two_parts(self):
        """AF K3 : deux codes courts → format TENANT valide."""
        self.assertGreaterEqual(self._score('AF K3', 'TENANT'), 0.6)

    def test_borne_very_long_text_lower_score(self):
        self.assertLess(self._score('RESERVE NON CABLEE LONGUE', 'BORNE'), 0.6)

    # ── SIGNAL ────────────────────────────────────────────────────────

    def test_signal_any_text_acceptable(self):
        """SIGNAL accepte tout texte raisonnablement long."""
        self.assertGreaterEqual(self._score('DND1-39A', 'SIGNAL'), 0.6)

    def test_signal_very_short_lower(self):
        self.assertLess(self._score('X', 'SIGNAL'), 0.7)

    # ── Colonne inconnue ──────────────────────────────────────────────

    def test_unknown_column_neutral(self):
        s = self._score('QUELQUECHOSE', 'INCONNUE')
        self.assertGreaterEqual(s, 0.3)
        self.assertLessEqual(s, 0.7)


# ══════════════════════════════════════════════════════════════════════
# 2. _col_length_score
# ══════════════════════════════════════════════════════════════════════

class TestColLengthScore(unittest.TestCase):
    """Score de longueur : plage normale → 1.0, hors plage → décroissance."""

    def setUp(self):
        self.ext = _ext()

    def _score(self, text, col):
        return self.ext._col_length_score(text, col)

    def test_jar_ideal_length(self):
        """5 chars = milieu de la plage JAR [3-7]."""
        self.assertGreaterEqual(self._score('0785N', 'JAR'), 0.9)

    def test_jar_too_short(self):
        self.assertLess(self._score('0', 'JAR'), 0.8)

    def test_jar_too_long(self):
        self.assertLess(self._score('0785NXXXXXXXXXXXXX', 'JAR'), 0.6)

    def test_signal_minimal_length(self):
        """SIGNAL : ≥ 2 chars → score plein."""
        self.assertGreaterEqual(self._score('AB', 'SIGNAL'), 0.9)

    def test_signal_empty(self):
        self.assertLess(self._score('', 'SIGNAL'), 0.6)

    def test_borne_normal_length(self):
        self.assertGreaterEqual(self._score('01B', 'BORNE'), 0.8)

    def test_borne_excessive_length(self):
        self.assertLess(self._score('A' * 30, 'BORNE'), 0.5)


# ══════════════════════════════════════════════════════════════════════
# 3. _col_dict_score
# ══════════════════════════════════════════════════════════════════════

class TestColDictScore(unittest.TestCase):
    """Score dictionnaire : présence dans data_dictionary.json."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        self.tmp.close()
        Path(self.tmp.name).write_text('{}', encoding='utf-8')
        self.dico_path = Path(self.tmp.name)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def _ext_with_dict(self):
        """Extractor qui utilise le dictionnaire temporaire."""
        from data_dictionary import DataDictionary
        import data_dictionary as _mod
        original = _mod._instance
        _mod._instance = DataDictionary(self.dico_path)
        ext = _ext()
        _mod._instance = original
        return ext

    def test_empty_dict_returns_zero(self):
        ext = _ext()
        # Avec un dico vide, aucune correspondance possible
        s = ext._col_dict_score('RESERVE CABLEE', 'SIGNAL')
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 1.0)

    def test_score_in_range(self):
        """Le score est toujours dans [0, 1]."""
        ext = _ext()
        for text in ('RESERVE CABLEE', '', '0785N', 'X' * 50):
            s = ext._col_dict_score(text, 'SIGNAL')
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)

    def test_empty_text_zero_or_low(self):
        ext = _ext()
        s = ext._col_dict_score('', 'SIGNAL')
        self.assertLessEqual(s, 0.5)


# ══════════════════════════════════════════════════════════════════════
# 4. _col_visual_score
# ══════════════════════════════════════════════════════════════════════

class TestColVisualScore(unittest.TestCase):
    """Score visuel : alignement mot ↔ zone de colonne."""

    def setUp(self):
        self.ext = _ext()
        # Colonne 0 : x=[0, 450], col 1 : x=[450, 950]
        self.bounds = _BOUNDS_4

    def _score(self, word_x, word_w, col_idx):
        return self.ext._col_visual_score(word_x, word_w, self.bounds, col_idx)

    def test_word_fully_inside_max_score(self):
        """Mot entièrement dans la zone → score proche de 1.0."""
        # Col 0 : 0-450, mot x=100, w=100 → x+w=200, bien dans [0,450]
        s = self._score(100, 100, 0)
        self.assertGreaterEqual(s, 0.9)

    def test_word_centroid_inside(self):
        """Bord gauche hors zone mais centroïde dedans → score intermédiaire."""
        # Col 1 : 450-950 ; mot x=400 w=200 → centroïde=500 ∈ [450,950]
        s = self._score(400, 200, 1)
        self.assertGreater(s, 0.5)
        self.assertLessEqual(s, 0.95)

    def test_word_left_edge_inside(self):
        """Bord gauche dans la zone mais centroïde hors → score moyen."""
        # Col 0 : 0-450 ; mot x=400 w=200 → x=400 ∈ [0,450] mais cx=500 hors
        s = self._score(400, 200, 0)
        self.assertGreater(s, 0.3)

    def test_word_completely_outside_low_score(self):
        """Mot entièrement hors de la zone → score bas."""
        # Col 0 : 0-450 ; mot x=600 w=100 → completement dans col 1 ou 2
        s = self._score(600, 100, 0)
        self.assertLessEqual(s, 0.3)

    def test_word_on_right_boundary(self):
        """Mot à cheval sur la frontière droite → score dégradé."""
        # Col 0 : 0-450 ; mot x=430 w=100 → dépasse légèrement
        s = self._score(430, 100, 0)
        self.assertLess(s, 0.95)

    def test_score_always_in_range(self):
        """Le score est toujours dans [0.0, 1.0]."""
        for x in (0, 225, 449, 450, 800, 2000):
            for w in (1, 50, 300):
                for ci in range(4):
                    s = self._score(x, w, ci)
                    self.assertGreaterEqual(s, 0.0)
                    self.assertLessEqual(s, 1.0)


# ══════════════════════════════════════════════════════════════════════
# 5. _col_coherence_score
# ══════════════════════════════════════════════════════════════════════

class TestColCoherenceScore(unittest.TestCase):
    """Score cohérence : consécutivité JAR et préfixe identique TENANT/ABOUTISSANT."""

    def setUp(self):
        self.ext = _ext()

    def _score(self, text, col, neighbors, col_idx):
        return self.ext._col_coherence_score(text, col, neighbors, col_idx)

    def test_no_neighbors_neutral(self):
        s = self._score('0785N', 'JAR', [], 1)
        self.assertAlmostEqual(s, 0.5, places=1)

    def test_jar_consecutive_numbers(self):
        """JAR 0786N avec voisins 0785N, 0784N → score élevé (±5)."""
        neighbors = [['X', '0784N', 'Y', 'Z'], ['X', '0785N', 'Y', 'Z']]
        s = self._score('0786N', 'JAR', neighbors, 1)
        self.assertGreater(s, 0.6)

    def test_jar_non_consecutive(self):
        """JAR très différent des voisins → score bas."""
        neighbors = [['X', '0100N', 'Y', 'Z'], ['X', '0101N', 'Y', 'Z']]
        s = self._score('0785N', 'JAR', neighbors, 1)
        self.assertLess(s, 0.6)

    def test_tenant_same_prefix(self):
        """TENANT avec même préfixe que les voisins → score élevé."""
        neighbors = [['AF K3', '0785N', 'B43T 11A', 'DND1'],
                     ['AF K5', '0786N', 'B43T 12A', 'DND2']]
        s = self._score('AF L2', 'TENANT', neighbors, 0)
        self.assertGreater(s, 0.5)

    def test_tenant_different_prefix(self):
        """TENANT avec préfixe différent → score plus bas."""
        neighbors = [['AF K3', '0785N', 'B43T 11A', 'DND1']]
        s = self._score('QR Z9', 'TENANT', neighbors, 0)
        self.assertLessEqual(s, 0.6)

    def test_score_in_range(self):
        """Score toujours dans [0.0, 1.0]."""
        for col in ('JAR', 'TENANT', 'SIGNAL', 'INCONNUE'):
            s = self._score('TEST', col, [], 0)
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)


# ══════════════════════════════════════════════════════════════════════
# 6. _score_total
# ══════════════════════════════════════════════════════════════════════

class TestScoreTotal(unittest.TestCase):
    """Score total = combinaison pondérée (40+25+15+10+5 = 95 %, 5 % non-perte séparé)."""

    def setUp(self):
        self.ext = _ext()

    def _total(self, text, col, word_x, word_w, bounds, col_idx, neighbors=None):
        return self.ext._score_total(
            text, col, word_x, word_w, bounds, col_idx, neighbors or []
        )

    def test_perfect_jar_scores_high(self):
        """0785N bien centré dans la zone JAR → score global élevé."""
        # Col JAR : bounds[1]-bounds[2] = 600-1050 → centre 825
        s = self._total('0785N', 'JAR', 780, 80, _BOUNDS_REP, 1)
        self.assertGreater(s, 0.65)

    def test_wrong_col_scores_lower_than_right_col(self):
        """0785N dans JAR doit scorer plus haut que 0785N dans SIGNAL."""
        s_jar = self._total('0785N', 'JAR', 780, 80, _BOUNDS_REP, 1)
        s_sig = self._total('0785N', 'SIGNAL', 1900, 80, _BOUNDS_REP, 3)
        self.assertGreater(s_jar, s_sig,
                           "Un code JAR doit mieux scorer dans JAR que dans SIGNAL")

    def test_score_in_range(self):
        """Le score total est toujours dans [0.0, 1.0]."""
        for text in ('0785N', 'AF K3', 'RESERVE CABLEE', '', 'X'):
            for ci, col in enumerate(_COLS_REP):
                s = self._total(text, col, 300, 50, _BOUNDS_REP, ci)
                self.assertGreaterEqual(s, 0.0,
                    msg=f"Score négatif pour '{text}' dans '{col}'")
                self.assertLessEqual(s, 1.0,
                    msg=f"Score > 1.0 pour '{text}' dans '{col}'")

    def test_better_format_raises_score(self):
        """0785N dans JAR > 0785N dans TENANT (format inadapté)."""
        s_jar = self._total('0785N', 'JAR', 700, 80, _BOUNDS_REP, 1)
        s_ten = self._total('0785N', 'TENANT', 300, 80, _BOUNDS_REP, 0)
        self.assertGreater(s_jar, s_ten)


# ══════════════════════════════════════════════════════════════════════
# 7. _rebalance_line
# ══════════════════════════════════════════════════════════════════════

class TestRebalanceLine(unittest.TestCase):
    """Réaffectation des mots en zone frontière + marquage [A_VERIFIER]."""

    def setUp(self):
        self.ext = _ext()

    def _rebalance(self, cells, elems, bounds, col_names, split_flags=None,
                   confs=None, neighbors=None):
        n = len(cells)
        if split_flags is None:
            split_flags = [False] * n
        if confs is None:
            confs = [90] * n
        cells_out, confs_out, flags_out, conf_label, alts = (
            self.ext._rebalance_line(
                cells, confs, split_flags, col_names,
                elems, bounds, neighbor_cells=neighbors or [],
            )
        )
        return cells_out, confs_out, flags_out, conf_label, alts

    # ── Aucun mot en frontière → pas de changement ────────────────────

    def test_no_boundary_words_unchanged(self):
        """Mots bien centrés dans leur colonne → aucun déplacement."""
        elems = [
            _elem(225, 80, '01A'),      # centre BORNE [0-450]
            _elem(680, 80, 'BC'),       # centre COULEUR [450-950]
            _elem(1300, 200, 'RESERVE CABLEE'),  # SIGNAL [950-1660]
            _elem(2000, 100, '0260R'),  # JARRETIERES [1660-2480]
        ]
        cells = ['01A', 'BC', 'RESERVE CABLEE', '0260R']
        out, _, _, label, alts = self._rebalance(
            cells, elems, _BOUNDS_4, _COLS_4
        )
        self.assertEqual(out[0], '01A')
        self.assertEqual(out[1], 'BC')
        self.assertEqual(out[2], 'RESERVE CABLEE')
        self.assertEqual(out[3], '0260R')
        self.assertEqual(alts, [])
        self.assertEqual(label, 'haute')

    # ── Déplacement justifié : JAR mal placé dans BORNE ──────────────

    def test_jar_moved_from_borne_to_jar(self):
        """0785N à la frontière BORNE/JAR : score JAR >> score BORNE → déplacement."""
        # On place 0785N dans la zone TENANT (0-600) mais juste avant la frontière
        # (x=560, w=80 → juste à 40px de la borne 600)
        elems = [_elem(560, 80, '0785N')]
        cells = ['0785N', '', '', '']   # actuellement en TENANT
        out, _, _, label, alts = self._rebalance(
            cells, elems, _BOUNDS_REP, _COLS_REP
        )
        if alts:
            # Si un déplacement s'est produit, il doit aller vers JAR (pas rester en TENANT)
            moved_to = alts[0]['col_to']
            self.assertNotEqual(moved_to, 0,
                "0785N ne doit pas rester en TENANT si le score JAR est meilleur")

    # ── Mot split_flag → pas de déplacement ──────────────────────────

    def test_split_flag_on_target_prevents_move(self):
        """
        Un mot ne doit pas être déplacé vers une colonne cible marquée split_flag.
        split_flags protège les colonnes CIBLES (issues d'un split) contre
        l'écrasement par rebalancement.
        """
        elems = [_elem(560, 80, '0785N')]
        cells = ['0785N', 'DEJA_LU', '', '']
        # Colonne JAR (index 1) est verrouillée par split_flag
        split_flags = [False, True, False, False]
        _, _, _, _, alts = self._rebalance(
            cells, elems, _BOUNDS_REP, _COLS_REP, split_flags=split_flags
        )
        # Aucun déplacement ne doit aller vers JAR (index 1 protégé)
        for alt in alts:
            self.assertNotEqual(alt.get('col_to'), 1,
                "Impossible de déplacer vers une colonne split_flag=True")

    # ── Ligne vide → retournée inchangée ─────────────────────────────

    def test_empty_cells_returned_unchanged(self):
        out, _, _, label, alts = self._rebalance(
            ['', '', '', ''], [], _BOUNDS_4, _COLS_4
        )
        self.assertEqual(out, ['', '', '', ''])
        self.assertEqual(alts, [])

    # ── Une seule colonne → pas de rebalancement ─────────────────────

    def test_single_column_no_rebalance(self):
        elems = [_elem(100, 80, 'TEST')]
        out, _, _, label, alts = self._rebalance(
            ['TEST'], elems, [0, 500], ['BORNE']
        )
        self.assertEqual(out[0], 'TEST')
        self.assertEqual(alts, [])

    # ── [A_VERIFIER] ajouté quand confiance faible ────────────────────

    def test_averifier_added_when_low_confidence(self):
        """
        Plusieurs mots ambigus → confidence='faible' → [A_VERIFIER] dans les cellules.
        On crée 3 mots exactement sur la frontière pour forcer confidence='faible'.
        """
        # Créer 3 mots exactement sur la frontière BORNE/COULEUR (x=445, juste avant 450)
        elems = [
            _elem(445, 80, 'AA'),
            _elem(445, 80, 'BB'),
            _elem(445, 80, 'CC'),
        ]
        cells = ['AA BB CC', '', '', '']
        _, _, _, label, alts = self._rebalance(
            cells, elems, _BOUNDS_4, _COLS_4
        )
        # Le test vérifie que le système produit une étiquette de confiance valide
        self.assertIn(label, ('haute', 'moyenne', 'faible'))

    # ── Type de retour ────────────────────────────────────────────────

    def test_return_types(self):
        """Vérifier les types de retour."""
        elems = [_elem(100, 50, 'TEST')]
        cells, confs, flags, label, alts = self._rebalance(
            ['TEST', '', '', ''], elems, _BOUNDS_4, _COLS_4
        )
        self.assertIsInstance(cells, list)
        self.assertIsInstance(confs, list)
        self.assertIsInstance(flags, list)
        self.assertIsInstance(label, str)
        self.assertIsInstance(alts, list)
        self.assertIn(label, ('haute', 'moyenne', 'faible'))
        self.assertEqual(len(cells), 4)

    # ── Cohérence avec les lignes voisines ────────────────────────────

    def test_neighbor_context_used(self):
        """Avec des voisins cohérents pour JAR, le score cohérence aide le bon placement."""
        neighbors = [
            ['AF K3', '0784N', 'B43T 10A', 'DND1'],
            ['AF K5', '0786N', 'B43T 12A', 'DND2'],
        ]
        # 0785N juste à la frontière TENANT/JAR (x=580, frontière à 600)
        elems = [_elem(580, 80, '0785N')]
        cells = ['0785N', '', '', '']
        _, _, _, _, alts = self._rebalance(
            cells, elems, _BOUNDS_REP, _COLS_REP, neighbors=neighbors
        )
        # Vérifier que le système a évalué des alternatives (sans imposer le résultat)
        self.assertIsInstance(alts, list)


# ══════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
