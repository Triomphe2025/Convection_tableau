"""types_documents.py : registre des types de documents (champs optionnels, familles, doublons)."""
import json
import tempfile
import time
from pathlib import Path

import types_documents as td
from config import Config
from template import TableTemplate, TemplateManager

RACINE = Path(__file__).resolve().parent.parent
FIXTURES = RACINE / "tests" / "fixtures"

# Texte d'un tableau répartiteur (pied + colonnes), tel qu'il sort d'une page lisible.
TEXTE_REPARTITEUR = ("TENANT JAR ABOUTISSANT SIGNAL   "
                     "NO PLAN : 223111PE000  P.E.T : SAINT  INDICE : TP2  BORNIER :  M  T  I")


def _pdf_temporaire(largeur_pt, hauteur_pt, texte):
    """PDF d'une page de la taille demandée, portant `texte` en couche texte (pas de scan)."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=largeur_pt, height=hauteur_pt)
    page.insert_text((40, hauteur_pt - 60), texte, fontsize=9)
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    f.close()
    doc.save(f.name)
    doc.close()
    return Path(f.name)


def _modele(nom, colonnes, mots_pied, cartouche):
    return TableTemplate(
        name=nom,
        columns=list(colonnes),
        footer_detect_keywords=list(mots_pied),
        footer_left_label=cartouche,
    )


class TestRegistre:

    def test_contient_les_modeles_livres(self):
        types = td.registre()
        for nom in ("Bornier standard", "Répartiteur", "REPARTITEUR", "REPARTITEUR 2"):
            assert nom in types, nom
            assert types[nom].famille == "tableau"

    def test_familles_integrees_plan_excel_journal(self):
        types = td.registre()
        assert types["Plan"].famille == "plan"
        assert "dxf" in types["Plan"].sorties
        assert ".tif" in types["Plan"].extensions and ".pdf" in types["Plan"].extensions
        assert types["Excel"].famille == "excel"
        assert ".xlsx" in types["Excel"].extensions
        assert types["Journal"].famille == "journal"
        assert ".jsonl" in types["Journal"].extensions

    def test_defauts_deduits_du_modele(self):
        modele = _modele("Essai", ["A", "B"], ["NO PLAN", "P.E.T"], "SIEMENS")
        types = td.registre(modeles={"Essai": modele})
        assert "Essai" in types
        reco = types["Essai"].reconnaissance
        assert reco.entete_colonnes == ("A", "B")
        assert reco.mots_pied == ("NO PLAN", "P.E.T")
        assert reco.marque_cartouche == "SIEMENS"


class TestDoublons:

    def test_repartiteur_signale_comme_doublon(self):
        paires = {frozenset(p) for p in td.doublons(td.registre())}
        assert frozenset({"Répartiteur", "REPARTITEUR"}) in paires

    def test_modeles_distincts_non_signales(self):
        paires = {frozenset(p) for p in td.doublons(td.registre())}
        assert frozenset({"Bornier standard", "REPARTITEUR 2"}) not in paires

    def test_doublon_present_dans_les_deux_sens(self):
        a = _modele("Un", ["A", "B"], ["X"], "M")
        b = _modele("Deux", ["A", "B"], ["X"], "M")
        paires = td.doublons(td.registre(modeles={"Un": a, "Deux": b}))
        assert {frozenset(p) for p in paires} == {frozenset({"Un", "Deux"})}


class TestRelectureTemplatesJson:

    def test_champs_optionnels_ignores_par_template_manager(self):
        # La phase 2E écrira ces champs dans templates.json ; TemplateManager doit les ignorer
        # sans erreur et rendre exactement les mêmes modèles qu'avant.
        brut = json.loads((RACINE / "templates.json").read_text(encoding="utf-8"))
        avant = TemplateManager._lire(RACINE / "templates.json")
        enrichi = {}
        for nom, td_dict in brut.items():
            copie = dict(td_dict)
            copie["famille"] = "tableau"
            copie["reconnaissance"] = {"mots_pied": ["NO PLAN"], "format_page": "A4"}
            copie["sorties"] = ["excel"]
            copie["profil_lecture"] = "claude"
            copie["ecran_attente"] = "tableau"
            copie["relecture"] = True
            enrichi[nom] = copie
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(enrichi, f, ensure_ascii=False)
            chemin = Path(f.name)
        try:
            apres = TemplateManager._lire(chemin)
        finally:
            chemin.unlink(missing_ok=True)
        assert set(apres) == set(avant)
        for nom in avant:
            assert apres[nom].to_dict() == avant[nom].to_dict(), nom


class TestDecider:
    """_decider : cœur de la détection, sur du texte fabriqué (ni PDF ni Tesseract)."""

    def test_ex_aequo_repartiteur_a_preciser(self):
        type_, conf, preuves = td._decider(TEXTE_REPARTITEUR, td.registre(), grand_format=False)
        assert type_ is not None and type_.famille == "tableau"
        assert type_.nom in ("Répartiteur", "REPARTITEUR")
        assert 0.0 < conf <= Config.DETECTION_CONFIANCE_EX_AEQUO_MAX
        texte = " ".join(preuves)
        assert "à préciser" in texte
        assert "Répartiteur" in texte and "REPARTITEUR" in texte

    def test_modele_unique_confiance_pleine(self):
        unique = _modele("Spécial", ["ZZALPHA", "ZZBETA"], ["NO PLAN", "P.E.T"], "ACME")
        texte = "ZZALPHA ZZBETA  NO PLAN : X  P.E.T : Y  ACME"
        type_, conf, preuves = td._decider(texte, td.registre(modeles={"Spécial": unique}),
                                           grand_format=False)
        assert type_.nom == "Spécial"
        assert conf == 1.0
        assert "à préciser" not in " ".join(preuves)

    def test_texte_vide_format_standard_inconnu(self):
        type_, conf, preuves = td._decider("", td.registre(), grand_format=False)
        assert type_ is None
        assert conf == 0.0
        assert preuves  # une explication est donnée

    def test_grand_format_sans_bornier_est_plan(self):
        type_, conf, preuves = td._decider("schema electrique", td.registre(), grand_format=True)
        assert type_.nom == "Plan"
        assert conf == Config.DETECTION_CONFIANCE_PLAN_FORMAT

    def test_grand_format_avec_bornier_reste_tableau(self):
        type_, conf, preuves = td._decider(TEXTE_REPARTITEUR, td.registre(), grand_format=True)
        assert type_.famille == "tableau"


class TestDetecterType:
    """detecter_type sur des fichiers réels (fixtures) et fabriqués."""

    def test_jsonl_est_journal(self):
        type_, conf, preuves = td.detecter_type(FIXTURES / "journal_claude_6A23111PE102.jsonl")
        assert type_.nom == "Journal"
        assert conf == 1.0
        assert any("jsonl" in p.lower() for p in preuves)

    def test_xlsx_est_excel(self):
        type_, conf, preuves = td.detecter_type(FIXTURES / "223111PE011_extrait_sortie_v1.7.xlsx")
        assert type_.nom == "Excel"
        assert conf == 1.0

    def test_pdf_vectoriel_repartiteur_a_preciser(self):
        type_, conf, preuves = td.detecter_type(FIXTURES / "223400PE137.pdf")
        assert type_.famille == "tableau"
        assert type_.nom in ("Répartiteur", "REPARTITEUR")
        assert 0.0 < conf <= Config.DETECTION_CONFIANCE_EX_AEQUO_MAX
        texte = " ".join(preuves)
        assert "à préciser" in texte and "Répartiteur" in texte and "REPARTITEUR" in texte
        assert any("natif" in p for p in preuves)  # lu sans Tesseract

    def test_extension_inconnue_rend_none(self):
        f = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        f.write(b"texte quelconque")
        f.close()
        try:
            type_, conf, preuves = td.detecter_type(Path(f.name))
        finally:
            Path(f.name).unlink(missing_ok=True)
        assert type_ is None
        assert conf == 0.0
        assert any("inconnue" in p.lower() for p in preuves)

    def test_grand_format_sans_bornier_est_plan(self):
        chemin = _pdf_temporaire(2384, 3370, "juste un cadre de plan, aucun pied")
        try:
            type_, conf, preuves = td.detecter_type(chemin)
        finally:
            chemin.unlink(missing_ok=True)
        assert type_.nom == "Plan"
        assert conf == Config.DETECTION_CONFIANCE_PLAN_FORMAT

    def test_a3_ne_penalise_pas_le_tableau(self):
        a4 = _pdf_temporaire(595, 842, TEXTE_REPARTITEUR)
        a3 = _pdf_temporaire(842, 1191, TEXTE_REPARTITEUR)
        try:
            t4, c4, _ = td.detecter_type(a4)
            t3, c3, _ = td.detecter_type(a3)
        finally:
            a4.unlink(missing_ok=True)
            a3.unlink(missing_ok=True)
        # L'A3 n'est pas « grand format » : même type et même confiance qu'en A4.
        assert t3.famille == "tableau" and t4.famille == "tableau"
        assert t3.nom == t4.nom
        assert c3 == c4

    def test_scan_lu_par_tesseract(self):
        if not Config.TESSERACT_TROUVE:
            raise AssertionError("Tesseract requis pour ce test (présent en CI du projet)")
        debut = time.perf_counter()
        type_, conf, preuves = td.detecter_type(FIXTURES / "scan_6A23111PE102_15p.pdf")
        duree = time.perf_counter() - debut
        assert type_ is not None and type_.famille == "tableau"
        assert conf > 0.0
        assert any("Tesseract" in p for p in preuves)
        assert duree < 30.0  # bande du pied, basse résolution : détection rapide

    def test_docx_fabrique_est_tableau(self):
        from docx import Document
        doc = Document()
        doc.add_paragraph("TENANT JAR ABOUTISSANT SIGNAL")
        doc.add_paragraph("NO PLAN : 1  P.E.T : 2  INDICE : TP2  BORNIER :  M T I")
        f = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        f.close()
        doc.save(f.name)
        try:
            type_, conf, preuves = td.detecter_type(Path(f.name))
        finally:
            Path(f.name).unlink(missing_ok=True)
        assert type_.famille == "tableau"
        assert conf > 0.0


class TestAPreciser:
    """a_preciser : indicateur « à préciser » que l'interface lira (correction 1)."""

    def test_confiance_sous_seuil_est_a_preciser(self):
        assert td.a_preciser(0.4, ["modèle le plus proche : X"]) is True

    def test_confiance_haute_sans_mention_est_sure(self):
        assert td.a_preciser(0.85, ["modèle le plus proche : X"]) is False

    def test_seuil_exact_est_sur(self):
        # Borne inférieure stricte : pile au seuil = sûr.
        assert td.a_preciser(Config.DETECTION_SEUIL_SUR, ["modèle le plus proche : X"]) is False

    def test_mention_a_preciser_force_meme_haute(self):
        assert td.a_preciser(0.95, ["à préciser entre : A, B"]) is True


class TestCompteMot:
    """_compte_mot : un mot n'est reconnu qu'entier, espaces du scan tolérés (correction 2)."""

    def test_mot_entier_present(self):
        assert td._compte_mot("SIGNAL JAR ABOUTISSANT", "JAR") == 1

    def test_mot_espace_scan_compte(self):
        assert td._compte_mot("SIGNAL J A R ABOUTISSANT", "JAR") == 1

    def test_ponctuation_toleree(self):
        assert td._compte_mot("NO PLAN : X  P.E.T : Y", "P.E.T") == 1

    def test_sous_chaine_profil_rejetee(self):
        # « FIL » dans PROFIL / FILERIE ne compte pas pour la colonne FIL.
        assert td._compte_mot("DIVERS PROFIL FILERIE", "FIL") == 0

    def test_absent_rend_zero(self):
        assert td._compte_mot("BORNE COULEUR", "SIGNAL") == 0


class TestMotEntierScore:
    """_score_type compte les colonnes au mot entier (correction 2)."""

    def test_fil_dans_filaire_ne_compte_pas(self):
        rep2 = _modele("REP2", ["FIL", "TENANT"], ["NO PLAN"], "SIEMENS")
        texte = "TENANT  DRIDPO FILAIRE Q2  NO PLAN : 1  SIEMENS"
        t = td.registre(modeles={"REP2": rep2})["REP2"]
        n_pied, n_cart, n_col = td._score_type(texte.upper(), t)
        assert n_col == 1  # TENANT compte, FIL (dans FILAIRE) non


class TestRectsBandes:
    """_rects_bandes : la lecture d'un scan couvre l'en-tête (haut) ET le pied (bas) (corr. 3)."""

    def test_deux_bandes_haut_et_bas(self):
        bandes = td._rects_bandes(0.0, 0.0, 100.0, 1000.0)
        assert len(bandes) == 2
        (hx0, hy0, hx1, hy1), (px0, py0, px1, py1) = bandes
        assert hy0 == 0.0
        assert hy1 == 1000.0 * Config.DETECTION_ENTETE_BANDE
        assert py1 == 1000.0
        assert py0 == 1000.0 - 1000.0 * Config.DETECTION_PIED_BANDE
        assert hx0 == 0.0 and hx1 == 100.0 and px0 == 0.0 and px1 == 100.0


class TestDeciderSeuil:
    """_decider ajoute « à préciser » sous le seuil sûr, avec le modèle proche (corr. 1)."""

    def test_confiance_faible_ajoute_a_preciser(self):
        faible = _modele("Faible", ["ZZALPHA", "ZZBETA"], ["NO PLAN", "P.E.T"], "ACME")
        texte = "NO PLAN : X  blabla divers"  # un seul mot de pied, aucune colonne
        type_, conf, preuves = td._decider(texte, td.registre(modeles={"Faible": faible}),
                                           grand_format=False)
        assert type_.nom == "Faible"
        assert conf < Config.DETECTION_SEUIL_SUR
        texte_preuves = " ".join(preuves)
        assert "à préciser" in texte_preuves
        assert "Faible" in texte_preuves  # le type le plus proche est suggéré


class TestVeriteTerrain:
    """Un test par fichier affirmant le type métier connu de l'utilisateur (point 4)."""

    def test_pe137_repartiteur_a_preciser(self):
        type_, conf, preuves = td.detecter_type(FIXTURES / "223400PE137.pdf")
        assert type_.nom in ("Répartiteur", "REPARTITEUR")
        assert td.a_preciser(conf, preuves) is True
        assert "REPARTITEUR 2" not in " ".join(preuves)

    def test_pe133_repartiteur_a_preciser(self):
        type_, conf, preuves = td.detecter_type(FIXTURES / "6A23111PE133_extrait_8pages.pdf")
        assert type_.nom in ("Répartiteur", "REPARTITEUR")
        assert td.a_preciser(conf, preuves) is True
        assert "REPARTITEUR 2" not in " ".join(preuves)

    def test_pe135_repartiteur2(self):
        type_, conf, preuves = td.detecter_type(FIXTURES / "223400PE135.pdf")
        assert type_.nom == "REPARTITEUR 2"

    def test_pe011_repartiteur2(self):
        # « FIL » est ici un vrai mot (colonne) : REPARTITEUR 2 reste le bon type.
        type_, conf, preuves = td.detecter_type(FIXTURES / "223111PE011_extrait_10pages.pdf")
        assert type_.nom == "REPARTITEUR 2"

    def test_pe012_bornier_standard(self):
        type_, conf, preuves = td.detecter_type(FIXTURES / "223111PE012_extrait_10pages.pdf")
        assert type_.nom == "Bornier standard"

    def test_scan_pe102_colonnes_lues_par_tesseract(self):
        # La bande d'en-tête (correction 3) fait lire les colonnes du scan : le modèle
        # est distingué avec certitude (plus d'ex æquo du seul pied).
        if not Config.TESSERACT_TROUVE:
            raise AssertionError("Tesseract requis (présent en CI du projet)")
        debut = time.perf_counter()
        type_, conf, preuves = td.detecter_type(FIXTURES / "scan_6A23111PE102_15p.pdf")
        duree = time.perf_counter() - debut
        texte = " ".join(preuves)
        assert type_ is not None and type_.famille == "tableau"
        # Le vrai modèle du scan n'est pas confirmé : on affirme seulement que les colonnes
        # sont lues et qu'un modèle unique l'emporte avec certitude, pas son nom exact.
        assert any("Tesseract" in p for p in preuves)
        assert "colonnes" in texte           # en-tête lu grâce à la bande haute
        assert "à préciser entre" not in texte  # modèle unique, plus d'ex æquo du pied seul
        assert conf >= Config.DETECTION_SEUIL_SUR
        assert duree < 8.0  # budget détection < 4 s visé ; marge pour les CI lentes
