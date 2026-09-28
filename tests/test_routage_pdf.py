"""
Tests du routage PDF par page (pdf_extractor + Converter._extraire_pdf_comme_images) :
texte vectoriel → lecture de la couche texte en grille, sans OCR ni API ;
couche OCR invisible et scan → pipeline OCR inchangé.

Aucun appel API : le moteur vision est remplacé par un faux qui enregistre
les images reçues (ou qui échoue s'il est appelé).

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_routage_pdf.py -v
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

import pdf_extractor as pe
from config import Config
from converter import Converter
from template import TemplateManager

FIXTURES = Path(__file__).parent / 'fixtures'
PE137 = FIXTURES / '223400PE137.pdf'             # texte vectoriel exact (+ 2 gardes scannées)
EXTRAIT = FIXTURES / '223111PE011_extrait_10pages.pdf'   # Paper Capture (+ 2 pages vectorielles)
SCAN = FIXTURES / 'scan_6A23111PE102_15p.pdf'    # scan pur, sans couche texte
VERITE = FIXTURES / '223111PE011_extrait_verite.xlsx'


def _tpl(nom):
    return TemplateManager().get(nom)


def _page(chemin, numero):
    """Ouvre un PDF et retourne (doc, page numero 1-based) ; fermer doc après usage."""
    doc = fitz.open(str(chemin))
    return doc, doc[numero - 1]


def _pdf_compose(tmp, pages):
    """pages : liste de (chemin_pdf, numero 1-based). Écrit un PDF assemblé."""
    sortie = fitz.open()
    for chemin, numero in pages:
        with fitz.open(str(chemin)) as src:
            sortie.insert_pdf(src, from_page=numero - 1, to_page=numero - 1)
    chemin = Path(tmp) / 'compose.pdf'
    sortie.save(str(chemin))
    sortie.close()
    return chemin


class FauxVision:
    """Remplace ClaudeVisionExtractor : enregistre les images, aucun appel réseau."""

    images = []

    def __init__(self, template, on_column_mapping=None):
        self._tpl = template

    def extract(self, image_path, feedback=None):
        FauxVision.images.append(Path(image_path).name)
        return {
            'success': True, 'headers': list(self._tpl.columns),
            'rows': [{'type': 'data', 'cells': ['OCR'] * len(self._tpl.columns),
                      'confidence': [100] * len(self._tpl.columns)}],
            'metadata': {}, 'image_path': str(image_path),
            'detection_method': 'claude-vision',
        }


def _pdf_en_bandes(tmp, chemin, numero, bandes=4, part=0.10):
    """Rend une page scannée en `bandes` bandes d'image couvrant chacune `part`
    de la page, sans texte — comme les gardes de 223400PE137."""
    sortie = fitz.open()
    with fitz.open(str(chemin)) as src:
        origine = src[numero - 1]
        largeur, hauteur = origine.rect.width, origine.rect.height
        page = sortie.new_page(width=largeur, height=hauteur)
        for k in range(bandes):
            clip = fitz.Rect(0, k * hauteur / bandes, largeur, (k + 1) * hauteur / bandes)
            y = k * hauteur * part * 1.5
            page.insert_image(
                fitz.Rect(0, y, largeur, y + hauteur * part),
                pixmap=origine.get_pixmap(clip=clip),
            )
    chemin_sortie = Path(tmp) / 'bandes.pdf'
    sortie.save(str(chemin_sortie))
    sortie.close()
    return chemin_sortie


def _petite_image():
    return fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), 0)


def _pdf_petite_image(tmp):
    """Page sans texte avec une image couvrant 4 % de la page."""
    sortie = fitz.open()
    page = sortie.new_page(width=100, height=100)
    page.insert_image(fitz.Rect(0, 0, 20, 20), pixmap=_petite_image())
    chemin = Path(tmp) / 'petite.pdf'
    sortie.save(str(chemin))
    sortie.close()
    return chemin


def _vision_interdite(*args, **kwargs):
    raise AssertionError("appel au moteur vision (API) alors qu'aucun n'est attendu")


# ── Classement des pages ──────────────────────────────────────────────

class TestClasserPage(unittest.TestCase):

    def test_page_a_cadre_de_pe137_est_vectorielle(self):
        doc, page = _page(PE137, 6)
        self.assertEqual(pe.classer_page(page), pe.VECTORIEL)
        doc.close()

    def test_page_tp2_sans_cadre_est_vectorielle(self):
        doc, page = _page(PE137, 37)
        self.assertEqual(pe.classer_page(page), pe.VECTORIEL)
        doc.close()

    def test_page_de_garde_en_bandes_est_un_scan(self):
        # 4 bandes d'image de ~10 % : images cumulées ≥ PDF_SEUIL_IMAGE.
        doc, page = _page(PE137, 3)
        self.assertEqual(pe.classer_page(page), pe.SCAN)
        doc.close()

    def test_paper_capture_est_ocr_invisible(self):
        doc, page = _page(EXTRAIT, 1)
        self.assertEqual(pe.classer_page(page), pe.OCR_INVISIBLE)
        doc.close()

    def test_page_tp3_refaite_en_vectoriel_dans_l_extrait(self):
        doc, page = _page(EXTRAIT, 9)
        self.assertEqual(pe.classer_page(page), pe.VECTORIEL)
        doc.close()

    def test_scan_sans_couche_texte_est_scan(self):
        doc, page = _page(SCAN, 1)
        self.assertEqual(pe.classer_page(page), pe.SCAN)
        doc.close()

    def test_texte_en_police_non_integree_reste_sur_le_pipeline_actuel(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), 'TEXTE EN HELVETICA NON INTEGREE ' * 3)
        self.assertEqual(pe.classer_page(page), pe.SCAN)
        doc.close()

    def test_petite_image_sans_texte_est_ignoree(self):
        doc = fitz.open()
        page = doc.new_page(width=100, height=100)
        page.insert_image(fitz.Rect(0, 0, 20, 20), pixmap=_petite_image())
        self.assertEqual(pe.classer_page(page), pe.VIDE)
        doc.close()

    def test_page_blanche_est_vide(self):
        doc = fitz.open()
        self.assertEqual(pe.classer_page(doc.new_page()), pe.VIDE)
        doc.close()


class TestCouvertureImage(unittest.TestCase):

    def test_scan_couvre_toute_la_page(self):
        doc, page = _page(SCAN, 1)
        self.assertGreaterEqual(pe.couverture_image(page), 0.99)
        doc.close()

    def test_page_sans_image(self):
        doc = fitz.open()
        self.assertEqual(pe.couverture_image(doc.new_page()), 0.0)
        doc.close()

    def test_bandes_additionnees(self):
        # Garde de PE137 : 4 bandes d'environ 10 % chacune.
        doc, page = _page(PE137, 3)
        self.assertGreater(pe.couverture_image(page), 0.3)
        doc.close()


# ── Grille de caractères ──────────────────────────────────────────────

class TestGrillePage(unittest.TestCase):

    def test_spans_poses_a_leur_colonne(self):
        doc = fitz.open()
        page = doc.new_page(width=400, height=200)
        page.insert_text((72, 72), 'ABC', fontname='cour', fontsize=10)
        page.insert_text((172, 72), 'XYZ', fontname='cour', fontsize=10)
        ligne = pe.grille_page(page)[0]
        self.assertTrue(ligne.startswith('ABC'))
        self.assertGreater(ligne.index('XYZ'), 3)
        doc.close()

    def test_span_legerement_decale_reste_sur_sa_ligne(self):
        # Cas réel PE137 page 38 : cellule posée 0,7 pt plus haut que sa ligne.
        doc = fitz.open()
        page = doc.new_page(width=400, height=200)
        page.insert_text((72, 100.0), 'D_T', fontname='cour', fontsize=10)
        page.insert_text((172, 100.7), '1847N', fontname='cour', fontsize=10)
        self.assertEqual(len(pe.grille_page(page)), 1)
        doc.close()

    def test_lignes_distinctes_separees(self):
        doc = fitz.open()
        page = doc.new_page(width=400, height=200)
        page.insert_text((72, 100), 'UN', fontname='cour', fontsize=10)
        page.insert_text((72, 112), 'DEUX', fontname='cour', fontsize=10)
        self.assertEqual(pe.grille_page(page), ['UN', 'DEUX'])
        doc.close()

    def test_page_sans_texte(self):
        doc = fitz.open()
        self.assertEqual(pe.grille_page(doc.new_page()), [])
        doc.close()

    def test_espace_dans_un_span_a_part_conserve(self):
        # Cas réel 1769N : le span « …VERS » commence à une demi-colonne près
        # (3,53 colonnes) et « PCC », posé à sa propre x, tombe à 8,49 : compter
        # les caractères depuis le début du span collait « VERSPCC ».
        doc = fitz.open()
        page = doc.new_page(width=400, height=200)
        pas = fitz.get_text_length('A', fontname='cour', fontsize=10)
        page.insert_text((72, 88), 'X', fontname='cour', fontsize=10)   # fixe x0
        page.insert_text((72 + 3.53 * pas, 100), 'VERS', fontname='cour', fontsize=10)
        page.insert_text((72 + 8.49 * pas, 100), 'PCC', fontname='cour', fontsize=10)
        self.assertEqual(pe.grille_page(page)[1].strip(), 'VERS PCC')
        doc.close()

    def test_span_en_petite_police_place_au_pas_de_la_page(self):
        # Police 10 majoritaire (comme 11,04 sur PE137) ; un span en police 9 :
        # « 02A » doit tomber sous la colonne 10 des lignes de référence, pas
        # après 11 caractères comptés dans sa propre police.
        doc = fitz.open()
        page = doc.new_page(width=400, height=200)
        for k in range(4):
            page.insert_text((72, 60 + 12 * k), 'PJ        29', fontname='cour', fontsize=10)
        page.insert_text((72, 112), 'D_T        02A', fontname='cour', fontsize=9)
        lignes = pe.grille_page(page)
        self.assertEqual(lignes[0].index('29'), 10)
        self.assertEqual(lignes[-1].index('02A'), 10)
        doc.close()


class TestPositionsEntete(unittest.TestCase):

    def test_titres_trouves_dans_l_ordre(self):
        ligne = '      TENANT             JAR.       ABOUTISSANT                SIGNAL'
        pos = pe._positions_entete(ligne, ['TENANT', 'JAR', 'ABOUTISSANT', 'SIGNAL'])
        self.assertEqual(pos, [6, 25, 36, 63])

    def test_titre_absent(self):
        self.assertIsNone(pe._positions_entete('INDICE MODIFICATIONS', ['TENANT', 'JAR']))

    def test_ligne_vide(self):
        self.assertIsNone(pe._positions_entete('', ['TENANT']))


class TestCoupuresParGouttieres(unittest.TestCase):

    def test_coupure_dans_la_plus_large_gouttiere_et_non_au_titre(self):
        # SIGNAL commence avant son titre (col 10) : la coupure suit la gouttière.
        lignes = ['AB  12   XY', 'CD  34   ZZ']
        self.assertEqual(pe._coupures_par_gouttieres(lignes, [0, 10]), [0, 9])

    def test_sans_gouttiere_repli_sur_le_titre(self):
        self.assertEqual(pe._coupures_par_gouttieres(['ABCDEFGH'], [0, 4]), [0, 4])

    def test_sans_ligne(self):
        self.assertEqual(pe._coupures_par_gouttieres([], [0, 4]), [0, 4])


class TestExtractPageGrille(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.doc = fitz.open(str(PE137))
        cls.ex = pe.PdfTableExtractor(_tpl('REPARTITEUR'))

    @classmethod
    def tearDownClass(cls):
        cls.doc.close()

    def _lire(self, numero):
        return self.ex.extract_page_grille(self.doc[numero - 1], numero - 1)

    def test_page_a_cadre_espaces_interieurs_conserves(self):
        r = self._lire(6)
        self.assertTrue(r['success'])
        self.assertEqual(r['detection_method'], 'pdf-grille')
        attendu = ['B106R1A   01', '0001R', 'B_E       01A', 'ALIM + RCE-RC1/1-2-3']
        self.assertEqual(r['rows'][0]['cells'], attendu)

    def test_page_a_cadre_pied_de_page_en_metadonnees(self):
        meta = self._lire(6)['metadata']
        self.assertEqual(meta.get('PAGE'), '1')
        self.assertEqual(meta.get('PET'), 'GRAND-BUT')
        self.assertEqual(meta.get('INDICE'), '10')

    def test_page_a_cadre_lignes_vides_du_cadre_ignorees(self):
        r = self._lire(6)
        self.assertTrue(all(any(c.strip() for c in row['cells']) for row in r['rows']))

    def test_pages_tp2_signal_dans_sa_colonne(self):
        for numero in (37, 38, 51):
            r = self._lire(numero)
            self.assertTrue(r['success'], numero)
            self.assertEqual(r['metadata'].get('INDICE'), 'TP2', numero)
        attendu = ['PJ        29', '1738N', 'QA        29', 'TS ARTE']
        self.assertEqual(self._lire(37)['rows'][0]['cells'], attendu)

    def test_page_tp2_cellule_decalee_recollee_a_sa_ligne(self):
        cellules = [row['cells'] for row in self._lire(38)['rows']]
        # « D_T 01B » est en police 10,08 : « 01B » est visuellement en colonne 10.
        self.assertIn(['D_T       01B', '1847N', 'ER        06', 'TS MACH LAV COUP HT'], cellules)

    def test_page_tp2_espaces_entre_spans_conserves(self):
        cellules_37 = [row['cells'] for row in self._lire(37)['rows']]
        cellules_38 = [row['cells'] for row in self._lire(38)['rows']]
        self.assertIn('PHONIE RAME RAC VERS PCC', [c[3] for c in cellules_37])
        self.assertIn('PHONIE RAME G21 DU PCC', [c[3] for c in cellules_37])
        self.assertIn('TM/TC RAME G22 DU PCC', [c[3] for c in cellules_38])
        self.assertIn('TS MACH LAV EN COURS CYCL', [c[3] for c in cellules_38])

    def test_page_tp2_petite_police_alignee_sur_les_lignes_voisines(self):
        cellules = [row['cells'] for row in self._lire(38)['rows']]
        self.assertIn(['D_T       02A', '1845N', 'ER        13', 'TS MACH LAV COUP HT'], cellules)
        self.assertIn(
            ['PH        07', '1846N', 'D_S       01B', 'COMMUN +24V MACH A LAVER'], cellules,
        )

    def test_page_tp2_pet_malgre_les_espaces(self):
        self.assertEqual(self._lire(37)['metadata'].get('PET'), 'GRAND-BUT')

    def test_page_sans_entete_du_modele(self):
        r = self._lire(4)   # tableau des modifications
        self.assertFalse(r['success'])
        self.assertEqual(r['rows'], [])

    def test_page_vectorielle_de_l_extrait_identique_a_la_verite(self):
        from mesure_precision import mesurer
        from mesurer_precision import lire_verite_excel
        reference, colonnes = lire_verite_excel(VERITE)
        page_122a = next(
            p for p in reference if p['rows'] and 'QTELMG' in p['rows'][0]['cells'][1]
        )
        with fitz.open(str(EXTRAIT)) as doc:
            lu = pe.PdfTableExtractor(_tpl('REPARTITEUR 2')).extract_page_grille(doc[8], 8)
        rapport = mesurer([dict(page_122a, pied_texte=[])], [dict(lu, pied_texte=[])], colonnes)
        self.assertEqual(rapport.ecarts_cellules, [])
        self.assertEqual(rapport.nb_cellules_comparees, 56)


class TestGrilleNonReecriteDansExcel(unittest.TestCase):

    def test_valeurs_exactes_non_corrigees_par_le_dictionnaire(self):
        # Sans 'pdf-grille' dans l'exemption de ocr_processor._fill_worksheet,
        # 31 valeurs exactes de PE137 étaient réécrites vers une valeur voisine
        # du dictionnaire (« ALARME RUPTEURS Q1 » → « RU/ALARME RUPTEUR Q2 »).
        import contextlib
        import io
        import openpyxl
        from generer_classeur import generer_excel
        tpl = _tpl('REPARTITEUR')
        signaux = ['ALARME RUPTEURS Q1', 'COMMUN TS GR4 315TS', 'BS NORMAL (105G26)']
        resultat = {
            'success': True, 'headers': list(tpl.columns), 'metadata': {'PAGE': '1'},
            'image_path': 'page_1', 'detection_method': 'pdf-grille', 'blur_pct': 0.0,
            'rows': [{'type': 'data', 'cells': ['PF        12', '0792N', 'PH        12', s],
                      'confidence': [100] * 4} for s in signaux],
        }
        with tempfile.TemporaryDirectory() as tmp:
            sortie = Path(tmp) / 'grille.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                generer_excel([resultat], pe.PdfTableExtractor(tpl), sortie)
            valeurs = {
                str(v) for ligne in openpyxl.load_workbook(sortie).worksheets[0].iter_rows(
                    values_only=True) for v in ligne if v is not None
            }
        for signal in signaux:
            self.assertIn(signal, valeurs)


# ── Routage dans Converter ────────────────────────────────────────────

class _BaseConverter(unittest.TestCase):

    def setUp(self):
        self._modes = (Config.OCR_MODE, Config.PDF_ROUTAGE_VECTORIEL)
        Config.OCR_MODE = 'claude'
        Config.PDF_ROUTAGE_VECTORIEL = True
        FauxVision.images = []
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.logs = []

    def tearDown(self):
        Config.OCR_MODE, Config.PDF_ROUTAGE_VECTORIEL = self._modes
        self._tmp.cleanup()

    def _extraire(self, pdf, modele, vision=FauxVision):
        conv = Converter(
            word_file=Path(pdf), output_dir=Path(self.tmp) / 'sortie',
            template=_tpl(modele), on_log=self.logs.append,
        )
        conv.output_dir.mkdir(parents=True, exist_ok=True)
        with patch.object(Converter, '_activer_log_claude'), \
                patch('claude_ocr.ClaudeVisionExtractor', vision):
            return conv._extraire_pdf_comme_images()


class TestRoutageConverter(_BaseConverter):

    def test_pe137_seules_les_gardes_scannees_vont_en_vision(self):
        results, extractor = self._extraire(PE137, 'REPARTITEUR')
        self.assertEqual(len(results), 53)
        self.assertEqual(FauxVision.images, ['page_003.png', 'page_005.png'])
        grille = [r for r in results if r['detection_method'] == 'pdf-grille']
        self.assertEqual(len(grille), 51)
        self.assertEqual(sum(1 for r in grille if r['success']), 48)
        self.assertIsNotNone(extractor)

    def test_mode_choisi_journalise_pour_chaque_page(self):
        self._extraire(PE137, 'REPARTITEUR')
        for numero in range(1, 54):
            self.assertTrue(any(f'Page {numero}/53 :' in m for m in self.logs), numero)
        self.assertTrue(any('Page 3/53 : scan → OCR, images = ' in m for m in self.logs))

    def test_scan_en_bandes_de_10_pour_cent_passe_par_l_ocr(self):
        # Page 52 de l'extrait (scan) découpée en 4 bandes de 10 % de la page.
        pdf = _pdf_en_bandes(self.tmp, EXTRAIT, 5)
        results, _ = self._extraire(pdf, 'REPARTITEUR 2')
        self.assertEqual(FauxVision.images, ['page_001.png'])
        self.assertEqual(results[0]['detection_method'], 'claude-vision')

    def test_page_ignoree_journalise_motif_et_images(self):
        pdf = _pdf_petite_image(self.tmp)
        results, _ = self._extraire(pdf, 'REPARTITEUR', vision=_vision_interdite)
        self.assertEqual(results[0]['detection_method'], 'pdf-vide')
        attendu = ('page 1 ignorée : aucun texte et images sous le seuil de 10 %, '
                   'images = 4 % de la page')
        self.assertTrue(any(m.strip() == attendu for m in self.logs), self.logs)

    def test_page_scannee_passe_toujours_par_l_ocr(self):
        pdf = _pdf_compose(self.tmp, [(PE137, 6), (SCAN, 1)])
        results, _ = self._extraire(pdf, 'REPARTITEUR')
        self.assertEqual(FauxVision.images, ['page_002.png'])
        self.assertEqual(results[0]['detection_method'], 'pdf-grille')
        self.assertEqual(results[1]['detection_method'], 'claude-vision')

    def test_couche_ocr_invisible_ignoree_page_relue_par_ocr(self):
        pdf = _pdf_compose(self.tmp, [(EXTRAIT, 1), (EXTRAIT, 9)])
        results, _ = self._extraire(pdf, 'REPARTITEUR 2')
        self.assertEqual(FauxVision.images, ['page_001.png'])
        self.assertEqual(results[0]['detection_method'], 'claude-vision')
        self.assertEqual(results[1]['detection_method'], 'pdf-grille')

    def test_ordre_des_pages_conserve(self):
        pdf = _pdf_compose(self.tmp, [(SCAN, 1), (PE137, 6), (SCAN, 2)])
        results, _ = self._extraire(pdf, 'REPARTITEUR')
        methodes = [r['detection_method'] for r in results]
        self.assertEqual(methodes, ['claude-vision', 'pdf-grille', 'claude-vision'])

    def test_images_d_un_passage_precedent_non_relues(self):
        images = Path(self.tmp) / 'sortie' / 'images_pdf'
        images.mkdir(parents=True)
        (images / 'page_001.png').write_bytes(b'ancienne')
        pdf = _pdf_compose(self.tmp, [(PE137, 6)])
        self._extraire(pdf, 'REPARTITEUR', vision=_vision_interdite)
        self.assertFalse((images / 'page_001.png').exists())


class TestRoutageModeTesseract(unittest.TestCase):
    """Mode tesseract : routage dans PdfTableExtractor.extract_all (repli image simulé)."""

    def setUp(self):
        self._routage = Config.PDF_ROUTAGE_VECTORIEL
        Config.PDF_ROUTAGE_VECTORIEL = True
        self.ocr = []

    def tearDown(self):
        Config.PDF_ROUTAGE_VECTORIEL = self._routage

    def _faux_repli(self, ex_self, page, page_num):
        self.ocr.append(page_num + 1)
        return {'success': True, 'page_num': page_num + 1, 'headers': ex_self._tpl.columns,
                'rows': [{'type': 'data', 'cells': ['OCR'] * len(ex_self._tpl.columns),
                          'confidence': [100] * len(ex_self._tpl.columns)}],
                'metadata': {}, 'detection_method': 'pdf_ocr', 'blur_pct': 0.0}

    def _lire(self, pdf, modele):
        ex = pe.PdfTableExtractor(_tpl(modele))
        faux = lambda ex_self, page, num: self._faux_repli(ex_self, page, num)  # noqa: E731
        with patch.object(pe.PdfTableExtractor, '_extract_page_ocr', faux):
            results, _ = ex.extract_all(pdf)
        return results

    def test_extrait_paper_capture_couche_ignoree_repli_image(self):
        results = self._lire(EXTRAIT, 'REPARTITEUR 2')
        # 8 pages Paper Capture → repli image ; pages 104 et 122a → grille.
        self.assertEqual(self.ocr, [1, 2, 3, 4, 5, 7, 8, 10])
        self.assertEqual([r['detection_method'] for r in results].count('pdf-grille'), 2)
        self.assertEqual(results[0]['routage']['nature'], pe.OCR_INVISIBLE)

    def test_extrait_toutes_les_pages_a_tableau_produisent_des_lignes(self):
        results = self._lire(EXTRAIT, 'REPARTITEUR 2')
        avec_lignes = [i + 1 for i, r in enumerate(results) if r['rows']]
        # La page 104 (6e de l'extrait, câble « RESERVE ») n'a aucune ligne de
        # données, ni dans le PDF ni dans la vérité terrain.
        self.assertEqual(avec_lignes, [1, 2, 3, 4, 5, 7, 8, 9, 10])

    def test_pe137_gardes_en_repli_image_texte_en_grille(self):
        results = self._lire(PE137, 'REPARTITEUR')
        self.assertEqual(self.ocr, [3, 5])
        self.assertEqual([r['detection_method'] for r in results].count('pdf-grille'), 51)

    def test_routage_desactive_rend_la_v17(self):
        Config.PDF_ROUTAGE_VECTORIEL = False
        results = self._lire(EXTRAIT, 'REPARTITEUR 2')
        self.assertNotIn('pdf-grille', [r['detection_method'] for r in results])
        self.assertTrue(all('routage' not in r for r in results))


class TestSectionsDansLaGrille(unittest.TestCase):

    def test_ligne_nom_du_cable_est_une_section_pas_un_pied(self):
        # 6A23111PE102 exporté d'Excel : « NOM DU CABLE : » suit l'en-tête ;
        # pris pour un pied (« CABLE : »), il vidait les pages 7 à 12.
        with fitz.open(str(FIXTURES / 'final_6A23111PE102_13p.pdf')) as doc:
            r = pe.PdfTableExtractor(_tpl('Bornier standard')).extract_page_grille(doc[6], 6)
        self.assertEqual(r['rows'][0], {'type': 'section', 'text': 'NOM DU CABLE : GAT/CA 01'})
        self.assertEqual(sum(1 for x in r['rows'] if x['type'] == 'data'), 28)
        self.assertEqual(r['rows'][1]['cells'], ['01', 'N', '+ 48VG', ''])
        self.assertEqual(r['metadata'].get('PAGE'), '5')


class TestRoutageDesactive(_BaseConverter):

    def test_false_rend_le_comportement_v17(self):
        Config.PDF_ROUTAGE_VECTORIEL = False
        pdf = _pdf_compose(self.tmp, [(PE137, 6), (SCAN, 1)])
        results, _ = self._extraire(pdf, 'REPARTITEUR')
        self.assertEqual(FauxVision.images, ['page_001.png', 'page_002.png'])
        self.assertTrue(all(r['detection_method'] == 'claude-vision' for r in results))
        self.assertFalse(any('Page 1/2 :' in m for m in self.logs))


if __name__ == '__main__':
    unittest.main()
