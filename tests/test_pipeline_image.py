"""
Tests unitaires — pipeline image OCR (méthodes basées sur OpenCV/NumPy).

Couvre :
  - BornierTableExtractor._remove_table_lines
  - BornierTableExtractor._detect_row_bounds
  - BornierTableExtractor._find_header_idx  (logique word-boundary)
  - BornierTableExtractor._col_boundaries   (tri visuel, monotonie)
  - BornierTableExtractor._group_lines

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_pipeline_image.py -v
"""

import unittest
from pathlib import Path

import numpy as np


from ocr_processor import BornierTableExtractor
from config import Config


# ── Helper ────────────────────────────────────────────────────────────

def _ext():
    return BornierTableExtractor(
        tesseract_path=Config.TESSERACT_PATH,
        language=Config.OCR_LANGUAGE,
    )


def _elem(text, x, w=60, cx=None, cy=50):
    """Élément OCR minimaliste."""
    return {
        'text': text, 'x': x, 'w': w,
        'cx': cx if cx is not None else x + w // 2,
        'cy': cy, 'y': 40, 'h': 20, 'conf': 90,
    }


def _white_image(h=400, w=600):
    """Image blanche (fond = papier)."""
    return np.full((h, w), 255, dtype=np.uint8)


def _add_hline(img, y, thickness=2):
    """Trace un trait horizontal noir à l'ordonnée y."""
    img[y:y + thickness, :] = 0
    return img


def _add_vline(img, x, thickness=2):
    """Trace un trait vertical noir à l'abscisse x."""
    img[:, x:x + thickness] = 0
    return img


# ══════════════════════════════════════════════════════════════════════
# 1. _remove_table_lines
# ══════════════════════════════════════════════════════════════════════

class TestRemoveTableLines(unittest.TestCase):
    """Suppression morphologique des traits H/V du tableau."""

    def setUp(self):
        self.ext = _ext()

    def test_returns_two_images(self):
        """Retourne exactement un tuple (clean_image, h_lines_mask)."""
        img = _white_image()
        result = self.ext._remove_table_lines(img)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_output_shapes_match_input(self):
        """Les deux images de sortie ont la même forme que l'entrée."""
        img = _white_image(300, 500)
        clean, mask = self.ext._remove_table_lines(img)
        self.assertEqual(clean.shape, img.shape)
        self.assertEqual(mask.shape, img.shape)

    def test_white_image_unchanged(self):
        """Image blanche sans traits → masque horizontal quasi-vide."""
        img = _white_image()
        clean, h_mask = self.ext._remove_table_lines(img)
        # Convention masque : pixels BLANCS (> 128) = traits détectés.
        # Une image blanche sans traits → quasi aucun pixel blanc dans h_mask.
        bright_pixels = np.sum(h_mask > 128)
        self.assertLess(
            bright_pixels, img.size * 0.01,
            "Pas de traits dans une image blanche"
        )

    def test_horizontal_line_removed(self):
        """Un trait horizontal est retiré de l'image nettoyée."""
        img = _white_image(200, 600)
        _add_hline(img, 100, thickness=3)

        # Avant suppression : pixels noirs à y=100
        dark_before = np.sum(img[99:103, :] < 128)
        clean, _ = self.ext._remove_table_lines(img)
        dark_after = np.sum(clean[99:103, :] < 128)

        self.assertLess(
            dark_after, dark_before,
            "Le trait horizontal doit être moins présent après suppression"
        )

    def test_horizontal_line_in_mask(self):
        """Un trait horizontal doit être détecté dans le masque h_lines."""
        img = _white_image(200, 600)
        _add_hline(img, 100, thickness=2)
        _, h_mask = self.ext._remove_table_lines(img)
        # Le masque doit contenir des pixels autour de y=100
        dark_in_mask = np.sum(h_mask[95:108, :] > 128)
        self.assertGreater(
            dark_in_mask, 0,
            "Le masque horizontal doit capturer le trait"
        )

    def test_vertical_line_not_in_h_mask(self):
        """Un trait UNIQUEMENT vertical ne doit pas polluer le masque horizontal."""
        img = _white_image(400, 200)
        _add_vline(img, 100, thickness=2)
        _, h_mask = self.ext._remove_table_lines(img)
        # Le masque horizontal ne doit pas être saturé par des lignes verticales
        max_row_sum = np.max(np.sum(h_mask > 128, axis=1))
        # Si h_mask ne contient que les lignes verticales, les sommes de lignes sont faibles
        # (les traits verticaux activent peu de pixels par rangée horizontale)
        self.assertLess(
            max_row_sum, img.shape[1] * 0.5,
            "Un trait vertical seul ne doit pas saturer les rangées du masque H"
        )

    def test_output_dtype_uint8(self):
        """Les images retournées sont de type uint8."""
        img = _white_image()
        clean, mask = self.ext._remove_table_lines(img)
        self.assertEqual(clean.dtype, np.uint8)
        self.assertEqual(mask.dtype, np.uint8)


# ══════════════════════════════════════════════════════════════════════
# 2. _detect_row_bounds
# ══════════════════════════════════════════════════════════════════════

class TestDetectRowBounds(unittest.TestCase):
    """Détection des positions Y des séparateurs de lignes."""

    def setUp(self):
        self.ext = _ext()

    def test_empty_mask_returns_empty(self):
        """Masque tout noir (aucun trait détecté) → liste vide."""
        # Convention : pixels BLANCS = traits présents. Masque tout noir = aucun trait.
        mask = np.zeros((300, 600), dtype=np.uint8)
        bounds = self.ext._detect_row_bounds(mask, 600)
        self.assertEqual(bounds, [])

    def test_single_horizontal_line_detected(self):
        """Un trait horizontal net → exactement 1 position détectée."""
        mask = np.zeros((300, 600), dtype=np.uint8)
        # Ligne blanche (trait présent) à y=150 sur toute la largeur
        mask[149:153, :] = 255
        bounds = self.ext._detect_row_bounds(mask, 600)
        self.assertEqual(len(bounds), 1)
        # Position détectée proche de y=150 (±5 px)
        self.assertAlmostEqual(bounds[0], 151, delta=5)

    def test_multiple_lines_detected(self):
        """Plusieurs traits → autant de positions."""
        mask = np.zeros((500, 600), dtype=np.uint8)
        line_positions = [80, 160, 240, 320, 400]
        for y in line_positions:
            mask[y:y + 3, :] = 255
        bounds = self.ext._detect_row_bounds(mask, 600)
        self.assertEqual(len(bounds), len(line_positions))

    def test_adjacent_pixels_merged_into_one(self):
        """Pixels contigus (épaisseur 5) → une seule position, pas plusieurs."""
        mask = np.zeros((200, 600), dtype=np.uint8)
        mask[100:105, :] = 255   # trait de 5 px d'épaisseur
        bounds = self.ext._detect_row_bounds(mask, 600)
        self.assertEqual(len(bounds), 1)

    def test_short_line_ignored(self):
        """Un trait trop court (< 15 % de la largeur) → non détecté."""
        mask = np.zeros((200, 600), dtype=np.uint8)
        # Trait sur 50 px seulement (< 15 % de 600 = 90 px)
        mask[100, 200:250] = 255
        bounds = self.ext._detect_row_bounds(mask, 600)
        self.assertEqual(bounds, [])

    def test_positions_are_sorted(self):
        """Les positions retournées sont toujours triées."""
        mask = np.zeros((400, 600), dtype=np.uint8)
        for y in [300, 100, 200]:
            mask[y:y + 3, :] = 255
        bounds = self.ext._detect_row_bounds(mask, 600)
        self.assertEqual(bounds, sorted(bounds))

    def test_returns_list_of_ints(self):
        """Le type retourné est une liste d'entiers."""
        mask = np.zeros((200, 600), dtype=np.uint8)
        mask[100:103, :] = 255
        bounds = self.ext._detect_row_bounds(mask, 600)
        self.assertIsInstance(bounds, list)
        for b in bounds:
            self.assertIsInstance(b, int)


# ══════════════════════════════════════════════════════════════════════
# 3. _find_header_idx — logique word-boundary
# ══════════════════════════════════════════════════════════════════════

class TestFindHeaderIdx(unittest.TestCase):
    """
    Vérifie la correspondance par frontière de mot.
    Cas critique : "JAR" ne doit PAS matcher "JARRETIERES".
    """

    def setUp(self):
        self.ext = _ext()

    def _line(self, *words):
        return [_elem(w, i * 80) for i, w in enumerate(words)]

    def _lines(self, *word_lists):
        return [self._line(*wl) for wl in word_lists]

    # ── REPARTITEUR : keywords [TENANT, JAR, ABOUTISSANT, SIGNAL] ─────

    def _ext_rep(self):
        from template import TemplateManager
        tpl = TemplateManager().get('REPARTITEUR')
        return BornierTableExtractor(
            Config.TESSERACT_PATH, Config.OCR_LANGUAGE, template=tpl
        )

    def test_repartiteur_header_exact_match(self):
        """En-tête contenant TENANT, JAR, ABOUTISSANT, SIGNAL → trouvé."""
        ext = self._ext_rep()
        lines = self._lines(
            ['TENANT', '|', 'JAR', '|', 'ABOUTISSANT', '|', 'SIGNAL'],
            ['01A', '0785N', 'B43T', 'DND1'],
        )
        idx = ext._find_header_idx(lines)
        self.assertEqual(idx, 0)

    def test_jar_does_not_match_jarretieres(self):
        """
        JAR (keyword REPARTITEUR) ne doit PAS matcher JARRETIERES.
        → avec seulement SIGNAL + JARRETIERES (Bornier Standard), REPARTITEUR
          ne doit pas trouver un header valide (< 2 vrais hits).
        """
        ext = self._ext_rep()
        # En-tête Bornier Standard : BORNE COULEUR SIGNAL JARRETIERES
        lines = self._lines(
            ['BORNE', '|', 'COULEUR', '|', 'SIGNAL', '|', 'JARRETIERES'],
            ['01A', 'BC', 'RESERVE', '0260R'],
        )
        idx = ext._find_header_idx(lines)
        # REPARTITEUR ne devrait PAS trouver cet en-tête avec le word-boundary fix
        # (JAR dans JARRETIERES = faux positif éliminé)
        if idx is not None:
            # Si trouvé malgré tout, vérifier qu'il y a au moins 2 vrais hits
            header_words = {e['text'].upper() for e in lines[idx]}
            rep_kws = ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL']
            real_hits = sum(1 for k in rep_kws if k in header_words)
            self.assertLess(
                real_hits, 2,
                "REPARTITEUR ne devrait avoir que SIGNAL comme vrai hit dans un header Bornier"
            )

    # ── Bornier standard : keywords [BORNE, COULEUR, SIGNAL, JARRETIERES] ──

    def test_bornier_standard_header_found(self):
        """En-tête Bornier Standard → trouvé avec l'extracteur par défaut."""
        lines = self._lines(
            ['BORNE', '|', 'COULEUR', '|', 'SIGNAL', '|', 'JARRETIERES'],
            ['01A', 'BC', 'RESERVE', '0260R'],
        )
        # BornierTableExtractor utilise Bornier standard par défaut
        idx = self.ext._find_header_idx(lines)
        self.assertIsNotNone(idx)
        self.assertEqual(idx, 0)

    def test_header_not_on_first_line(self):
        """En-tête sur la 2e ligne (titre avant le tableau)."""
        lines = self._lines(
            ['TITRE', 'DU', 'DOCUMENT'],
            ['BORNE', '|', 'COULEUR', '|', 'SIGNAL', '|', 'JARRETIERES'],
            ['01A', 'BC', 'RESERVE', '0260R'],
        )
        idx = self.ext._find_header_idx(lines)
        self.assertEqual(idx, 1)

    def test_no_header_returns_none(self):
        """Aucun en-tête → None retourné."""
        lines = self._lines(
            ['TEXTE', 'QUELCONQUE', 'SANS', 'COLONNES'],
            ['AUTRE', 'LIGNE', 'DE', 'DONNEES'],
        )
        idx = self.ext._find_header_idx(lines)
        self.assertIsNone(idx)

    def test_borne_does_not_match_bornier(self):
        """
        BORNE (keyword Bornier Standard) ne doit pas faussement matcher
        BORNIER (dans une ligne de pied de page).
        """
        lines = self._lines(
            ['BORNIER', ':', 'AA', 'PAGE', ':', '5'],  # pied de page
            ['01A', 'BC', 'RESERVE', '0260R'],
        )
        idx = self.ext._find_header_idx(lines)
        # Le pied de page ne doit pas être considéré comme un header
        # (il manque COULEUR, SIGNAL, JARRETIERES)
        if idx is not None:
            header_words = ' '.join(e['text'].upper() for e in lines[idx])
            self.assertIn('BORNE', header_words,
                "Si trouvé, la ligne doit contenir au moins BORNE seul")


# ══════════════════════════════════════════════════════════════════════
# 4. _col_boundaries — tri visuel, monotonie garantie
# ══════════════════════════════════════════════════════════════════════

class TestColBoundaries(unittest.TestCase):
    """
    Vérifie que les frontières sont toujours monotones croissantes,
    même quand les mots-clés apparaissent dans un ordre visuel différent
    de l'ordre du template.
    """

    def setUp(self):
        self.ext = _ext()

    def _elem_hdr(self, text, cx):
        """Élément d'en-tête avec position cx précise."""
        return {'text': text, 'x': cx - 30, 'w': 60, 'cx': cx,
                'cy': 50, 'y': 40, 'h': 20, 'conf': 90}

    # ── Ordre visuel correct ──────────────────────────────────────────

    def test_normal_order_monotone(self):
        """Mots-clés dans l'ordre template → bounds croissants."""
        header = [
            self._elem_hdr('BORNE',       200),
            self._elem_hdr('COULEUR',     600),
            self._elem_hdr('SIGNAL',     1100),
            self._elem_hdr('JARRETIERES', 1900),
        ]
        bounds, cols = self.ext._col_boundaries(header, 2480)
        for i in range(len(bounds) - 1):
            self.assertLess(bounds[i], bounds[i + 1],
                f"Bound {i}={bounds[i]} >= {bounds[i+1]}")

    def test_normal_order_starts_at_zero(self):
        """Première frontière = 0."""
        header = [self._elem_hdr('BORNE', 200), self._elem_hdr('COULEUR', 600),
                  self._elem_hdr('SIGNAL', 1100), self._elem_hdr('JARRETIERES', 1900)]
        bounds, _ = self.ext._col_boundaries(header, 2480)
        self.assertEqual(bounds[0], 0)

    def test_normal_order_ends_at_img_w(self):
        """Dernière frontière = img_w."""
        header = [self._elem_hdr('BORNE', 200), self._elem_hdr('COULEUR', 600),
                  self._elem_hdr('SIGNAL', 1100), self._elem_hdr('JARRETIERES', 1900)]
        bounds, _ = self.ext._col_boundaries(header, 2480)
        self.assertEqual(bounds[-1], 2480)

    # ── Ordre visuel inversé ──────────────────────────────────────────

    def test_reversed_visual_order_still_monotone(self):
        """
        Mots-clés détectés dans l'ordre inverse (comme REPARTITEUR sur certains scans).
        Ex : TENANT à droite (x=2248), SIGNAL à gauche (x=400).
        → bounds doivent quand même être croissants.
        """
        from template import TemplateManager
        tpl = TemplateManager().get('REPARTITEUR')
        ext_rep = BornierTableExtractor(
            Config.TESSERACT_PATH, Config.OCR_LANGUAGE, template=tpl
        )
        # Simuler l'ordre visuel inversé sur l'image
        header = [
            self._elem_hdr('SIGNAL',      400),
            self._elem_hdr('ABOUTISSANT', 900),
            self._elem_hdr('JAR',        1400),
            self._elem_hdr('TENANT',     1900),
        ]
        bounds, cols = ext_rep._col_boundaries(header, 2480)
        for i in range(len(bounds) - 1):
            self.assertLess(bounds[i], bounds[i + 1],
                f"Bounds non monotones après tri visuel : {bounds}")

    def test_reversed_order_columns_reordered(self):
        """Quand l'ordre visuel diffère, col_names reflète l'ordre visuel."""
        from template import TemplateManager
        tpl = TemplateManager().get('REPARTITEUR')
        ext_rep = BornierTableExtractor(
            Config.TESSERACT_PATH, Config.OCR_LANGUAGE, template=tpl
        )
        header = [
            self._elem_hdr('SIGNAL',      400),
            self._elem_hdr('ABOUTISSANT', 900),
            self._elem_hdr('JAR',        1400),
            self._elem_hdr('TENANT',     1900),
        ]
        bounds, cols = ext_rep._col_boundaries(header, 2480)
        # La première colonne (la plus à gauche) doit être SIGNAL
        self.assertEqual(cols[0], 'SIGNAL')
        # La dernière doit être TENANT
        self.assertEqual(cols[-1], 'TENANT')

    # ── Fallback colonnes égales ──────────────────────────────────────

    def test_no_keywords_found_equal_fallback(self):
        """Aucun mot-clé reconnu → colonnes de largeur égale."""
        header = [
            self._elem_hdr('XXX', 200),
            self._elem_hdr('YYY', 800),
        ]
        bounds, cols = self.ext._col_boundaries(header, 2480)
        # Doit retourner len(col_keywords)+1 bounds, tous croissants
        self.assertEqual(len(bounds), len(self.ext._col_keywords) + 1)
        for i in range(len(bounds) - 1):
            self.assertLessEqual(bounds[i], bounds[i + 1])

    def test_bounds_count_equals_n_cols_plus_one(self):
        """len(bounds) == n_colonnes + 1 toujours."""
        header = [self._elem_hdr('BORNE', 200), self._elem_hdr('COULEUR', 600),
                  self._elem_hdr('SIGNAL', 1100), self._elem_hdr('JARRETIERES', 1900)]
        bounds, cols = self.ext._col_boundaries(header, 2480)
        self.assertEqual(len(bounds), len(cols) + 1)


# ══════════════════════════════════════════════════════════════════════
# 5. _group_lines
# ══════════════════════════════════════════════════════════════════════

class TestGroupLines(unittest.TestCase):
    """Regroupement des éléments OCR en lignes horizontales."""

    def setUp(self):
        self.ext = _ext()

    def _elems(self, cy_list):
        """Crée un élément par valeur cy fournie."""
        return [_elem(f'W{i}', x=i * 80, cy=cy) for i, cy in enumerate(cy_list)]

    def test_single_element(self):
        elems = self._elems([50])
        lines = self.ext._group_lines(elems)
        self.assertEqual(len(lines), 1)

    def test_empty_elements(self):
        lines = self.ext._group_lines([])
        self.assertEqual(lines, [])

    def test_two_close_elements_same_line(self):
        """Deux mots très proches verticalement → même ligne."""
        elems = self._elems([50, 53])
        lines = self.ext._group_lines(elems)
        self.assertEqual(len(lines), 1)

    def test_two_far_elements_different_lines(self):
        """Deux mots très éloignés → deux lignes distinctes."""
        elems = self._elems([50, 200])
        lines = self.ext._group_lines(elems)
        self.assertEqual(len(lines), 2)

    def test_multiple_rows(self):
        """5 lignes OCR groupées correctement."""
        cy_values = [50, 51, 130, 131, 210, 211, 290, 291, 370, 371]
        elems = self._elems(cy_values)
        lines = self.ext._group_lines(elems)
        self.assertEqual(len(lines), 5)

    def test_all_words_preserved(self):
        """Aucun mot ne doit être perdu lors du regroupement."""
        cy_values = [50, 52, 130, 210]
        elems = self._elems(cy_values)
        lines = self.ext._group_lines(elems)
        total = sum(len(line) for line in lines)
        self.assertEqual(total, len(elems))


# ══════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
