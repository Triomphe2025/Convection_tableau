"""
Fonctions pures de présentation (interface_helpers) — testées sans Tkinter.
Une classe par fonction (cas nominal / limite / erreur). Ces fonctions pilotent l'interface
(étapes 1, 4, 5, 6, 7, 10, 13, 14) ; interface.py ne fait que les appeler.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_interface_helpers.py -v
"""
import unittest

import interface_helpers as h


class TestNomModeleLisible(unittest.TestCase):

    def test_modeles_connus_noms_lisibles(self):
        self.assertEqual(h.nom_modele_lisible("claude-sonnet-5-5"), "Sonnet 5.5 — recommandé")
        self.assertEqual(h.nom_modele_lisible("claude-opus-5-5"),
                         "Opus 5.5 — documents difficiles")

    def test_identifiant_inconnu_rendu_tel_quel(self):
        self.assertEqual(h.nom_modele_lisible("modele-inconnu-x"), "modele-inconnu-x")

    def test_vide_rend_vide(self):
        self.assertEqual(h.nom_modele_lisible(""), "")

    def test_espaces_autour_ignores(self):
        self.assertEqual(h.nom_modele_lisible("  claude-sonnet-5-5  "), "Sonnet 5.5 — recommandé")

    def test_tous_les_modeles_de_config_ont_un_nom(self):
        # Devient rouge le jour où un modèle est ajouté à config.py sans nom lisible.
        from config import Config
        for identifiant in Config.CLAUDE_CAPACITES_MODELES:
            lisible = h.nom_modele_lisible(identifiant)
            self.assertTrue(lisible, f"nom vide pour {identifiant}")
            self.assertNotEqual(lisible, identifiant, f"nom manquant pour {identifiant}")


class TestMoteursVisibles(unittest.TestCase):

    def test_hors_dev_socle_seul(self):
        self.assertEqual(h.moteurs_visibles(False), ("tesseract", "claude"))

    def test_dev_ajoute_les_experimentaux(self):
        visibles = h.moteurs_visibles(True)
        self.assertEqual(visibles[:2], ("tesseract", "claude"))
        for moteur in ("docling", "ollama", "hybrid", "agent"):
            self.assertIn(moteur, visibles)

    def test_experimentaux_absents_hors_dev(self):
        for moteur in ("docling", "ollama", "hybrid", "agent"):
            self.assertNotIn(moteur, h.moteurs_visibles(False))

    def test_moteur_experimental_choisi_reste_visible(self):
        # Hors Dev, un moteur expérimental déjà sélectionné ne doit pas disparaître de l'écran.
        self.assertIn("hybrid", h.moteurs_visibles(False, "hybrid"))
        self.assertEqual(h.moteurs_visibles(False, "tesseract"), ("tesseract", "claude"))
        self.assertEqual(h.moteurs_visibles(True, "hybrid"),
                         ("tesseract", "claude", "docling", "ollama", "hybrid", "agent"))


class TestPageApresBasculeDev(unittest.TestCase):

    def test_quitte_page_dev_retour_accueil(self):
        for page in ("params", "ocr", "options"):
            self.assertEqual(h.page_apres_bascule_dev(page, False), "accueil")

    def test_page_dev_reste_si_dev_actif(self):
        self.assertEqual(h.page_apres_bascule_dev("params", True), "params")

    def test_page_non_dev_inchangee(self):
        self.assertEqual(h.page_apres_bascule_dev("accueil", False), "accueil")
        self.assertEqual(h.page_apres_bascule_dev("dashboard", False), "dashboard")


class TestEtatLancement(unittest.TestCase):

    def test_source_et_destination_actif(self):
        actif, message = h.etat_lancement("doc.pdf", "C:/sortie")
        self.assertTrue(actif)
        self.assertEqual(message, "")

    def test_sans_source_inactif_message(self):
        actif, message = h.etat_lancement("", "C:/sortie")
        self.assertFalse(actif)
        self.assertTrue(message.strip())

    def test_source_sans_destination_inactif(self):
        actif, message = h.etat_lancement("doc.pdf", "")
        self.assertFalse(actif)
        self.assertTrue(message.strip())

    def test_none_traite_comme_vide(self):
        actif, message = h.etat_lancement(None, None)
        self.assertFalse(actif)
        self.assertTrue(message.strip())


class TestNumeroPageValidation(unittest.TestCase):

    def test_meta_page_prioritaire(self):
        self.assertEqual(h.numero_page_validation("122a", 5), "122a")

    def test_meta_vide_rend_rang_traite(self):
        self.assertEqual(h.numero_page_validation("", 5), "5")

    def test_meta_espaces_rend_rang(self):
        self.assertEqual(h.numero_page_validation("   ", 7), "7")

    def test_meta_none_rend_rang(self):
        self.assertEqual(h.numero_page_validation(None, 3), "3")


class TestDpiAActiver(unittest.TestCase):

    def test_windows_reglage_actif(self):
        self.assertTrue(h.dpi_a_activer("win32", True))

    def test_windows_reglage_inactif(self):
        self.assertFalse(h.dpi_a_activer("win32", False))

    def test_hors_windows_jamais(self):
        self.assertFalse(h.dpi_a_activer("linux", True))
        self.assertFalse(h.dpi_a_activer("darwin", True))


class TestAnalyserProgresPage(unittest.TestCase):

    def test_message_on_progress_page(self):
        # Formes exactes de converter.py:1026 : f"Page {done}/{total} [{engine}] — {ok_flag}".
        self.assertEqual(h.analyser_progres_page("Page 3/48 [Claude] — 12 lignes"), (3, 48))
        self.assertEqual(h.analyser_progres_page("Page 4/48 [OCR] — vide"), (4, 48))
        self.assertEqual(h.analyser_progres_page("Page 5/48 [PDF] — 3 lignes"), (5, 48))

    def test_ligne_analyse_scan_donne_none(self):
        # Ligne de _log (converter.py:161), pas on_progress : deux-points, pas de crochet.
        self.assertIsNone(h.analyser_progres_page("Page 12/720 : scannée, images = 80 %"))

    def test_autres_messages_progres_none(self):
        self.assertIsNone(h.analyser_progres_page("OCR 2/48 : img.png"))
        self.assertIsNone(h.analyser_progres_page("Rastérisation 4/10…"))

    def test_vide_ou_none(self):
        self.assertIsNone(h.analyser_progres_page(""))
        self.assertIsNone(h.analyser_progres_page(None))


class TestEstimerTempsRestant(unittest.TestCase):

    def test_debut_done_zero_rend_none(self):
        # Mode lot / tout début : pas d'estimation tant qu'aucune page n'est faite.
        self.assertIsNone(h.estimer_temps_restant(10.0, 0, 48))

    def test_termine_rend_zero(self):
        self.assertEqual(h.estimer_temps_restant(100.0, 48, 48), 0.0)

    def test_proportionnel_au_temps_par_page(self):
        self.assertAlmostEqual(h.estimer_temps_restant(10.0, 1, 11), 100.0)
        self.assertAlmostEqual(h.estimer_temps_restant(20.0, 5, 10), 20.0)

    def test_total_nul_rend_none(self):
        self.assertIsNone(h.estimer_temps_restant(10.0, 0, 0))

    def test_depuis_premiere_page_exclut_analyse(self):
        # 60 s d'analyse exclues : 12 pages en 60 s depuis la 1re page = 5 s/page → 36 × 5 = 180.
        # Le même temps compté depuis le lancement (120 s) donnerait 10 s/page = 360 : à éviter.
        self.assertAlmostEqual(h.estimer_temps_restant(60.0, 12, 48), 180.0)

    def test_mode_lot_jamais_estimation(self):
        self.assertIsNone(h.estimer_temps_restant(60.0, 12, 48, mode_lot=True))


class TestJalonPremierePage(unittest.TestCase):

    def test_ignore_analyse_et_lancement(self):
        # Le jalon est la 1re VRAIE page (on_progress) ; lancement et lignes d'analyse exclus.
        evenements = [
            (0.0, "Démarrage de la conversion"),
            (10.0, "Page 1/48 : scannée, images = 80 %"),     # analyse → ne compte pas
            (60.0, "Page 1/48 [Claude] — 12 lignes"),
            (65.0, "Page 2/48 [Claude] — vide"),
        ]
        self.assertEqual(h.jalon_premiere_page(evenements), 60.0)

    def test_aucune_vraie_page_rend_none(self):
        self.assertIsNone(h.jalon_premiere_page(
            [(0.0, "Démarrage"), (5.0, "OCR 1/3 : a.png")]))

    def test_liste_vide_rend_none(self):
        self.assertIsNone(h.jalon_premiere_page([]))


class TestFormatDuree(unittest.TestCase):

    def test_none_rend_tiret(self):
        self.assertEqual(h.format_duree(None), "—")

    def test_zero(self):
        self.assertEqual(h.format_duree(0), "0:00")

    def test_minutes_secondes(self):
        self.assertEqual(h.format_duree(65), "1:05")
        self.assertEqual(h.format_duree(125), "2:05")


class TestRatioContraste(unittest.TestCase):

    def test_noir_blanc_21(self):
        self.assertAlmostEqual(h.ratio_contraste("#000000", "#ffffff"), 21.0, places=1)

    def test_meme_couleur_rend_1(self):
        self.assertAlmostEqual(h.ratio_contraste("#0f3460", "#0f3460"), 1.0, places=6)

    def test_symetrique(self):
        self.assertAlmostEqual(h.ratio_contraste("#7878a0", "#0f3460"),
                               h.ratio_contraste("#0f3460", "#7878a0"), places=6)

    def test_couleur_invalide_leve(self):
        with self.assertRaises(ValueError):
            h.ratio_contraste("#fff", "#000000")


class TestDoitSignalerFin(unittest.TestCase):

    def test_windows_sans_focus_signale(self):
        self.assertTrue(h.doit_signaler_fin("win32", a_le_focus=False))

    def test_windows_avec_focus_ne_signale_pas(self):
        self.assertFalse(h.doit_signaler_fin("win32", a_le_focus=True))

    def test_autre_plateforme_jamais(self):
        self.assertFalse(h.doit_signaler_fin("linux", a_le_focus=False))


class TestEtatCleApi(unittest.TestCase):

    def test_cle_presente_configuree(self):
        self.assertEqual(h.etat_cle_api("sk-ant-xxx"), "configurée")

    def test_cle_vide_absente(self):
        self.assertEqual(h.etat_cle_api(""), "absente")

    def test_espaces_seuls_absente(self):
        self.assertEqual(h.etat_cle_api("   "), "absente")

    def test_none_absente(self):
        self.assertEqual(h.etat_cle_api(None), "absente")


if __name__ == '__main__':
    unittest.main()
