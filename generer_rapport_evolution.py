"""
Rapport PDF d'evolution de TriosSeconverter et guide de lancement.

Usage :
    python generer_rapport_evolution.py
    -> Cree : TriosSeconverter_Rapport_Evolution.pdf
"""

from pathlib import Path
from fpdf import FPDF


# ── Palette ───────────────────────────────────────────────────────────
MARGIN      = 18
COL_TITRE   = (28, 56, 100)      # bleu marine
COL_V1      = (130, 50, 50)      # rouge fonce (ancien)
COL_V2      = (40, 120, 60)      # vert (nouveau)
COL_SOUS    = (60, 90, 160)      # bleu section
COL_CODE    = (25, 30, 45)       # fond code
COL_CODE_FG = (200, 215, 245)    # texte code
COL_OK      = (40, 140, 80)
COL_WARN    = (150, 100, 20)
COL_INFO    = (50, 90, 170)
COL_RULE    = (190, 195, 215)
COL_BODY    = (30, 32, 42)
COL_ACCENT  = (220, 60, 80)
COL_TAG_V1  = (180, 60, 60)
COL_TAG_V2  = (40, 150, 80)


_UNICODE_MAP = str.maketrans({
    "→": "->",   "←": "<-",   "►": ">",
    "▼": "v",    "│": "|",    "├": "+",
    "└": "+",    "─": "-",    "═": "=",
    "•": "-",    "✓": "[OK]", "✗": "[X]",
    "✕": "[X]",  "✘": "[X]",  "✔": "[OK]",
    "✅": "[OK]", "❌": "[X]",  "⚠": "[!]",
    "ℹ": "[i]",  "—": " - ",  "–": " - ",
    "…": "...",  "“": '"',    "”": '"',
    "‘": "'",    "’": "'",    "é": "e",
    "è": "e",    "ê": "e",    "ë": "e",
    "à": "a",    "â": "a",    "ä": "a",
    "î": "i",    "ï": "i",    "ô": "o",
    "ö": "o",    "ù": "u",    "û": "u",
    "ü": "u",    "ç": "c",    "É": "E",
    "È": "E",    "Ê": "E",    "À": "A",
    "Â": "A",    "Î": "I",    "Ô": "O",
    "Ù": "U",    "Û": "U",    "Ç": "C",
})


def _c(text: str) -> str:
    text = text.translate(_UNICODE_MAP)
    return text.encode('latin-1', errors='replace').decode('latin-1')


class Rapport(FPDF):

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=MARGIN + 2)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self._toc = []

    def header(self):
        if self.page_no() <= 2:
            return
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*COL_RULE)
        self.cell(0, 5,
                  "TriosSeconverter  |  Rapport d'evolution v2  |  Mai 2026",
                  align="L")
        self.cell(0, 5, f"Page {self.page_no()}", align="R",
                  new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*COL_RULE)
        self.line(MARGIN, self.get_y(), 210 - MARGIN, self.get_y())
        self.ln(2)

    def footer(self):
        if self.page_no() <= 2:
            return
        self.set_y(-13)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*COL_RULE)
        self.cell(0, 5,
                  "(c) 2026  Triomphe Tchounda  -  Document genere automatiquement",
                  align="C")

    # ── Titres ─────────────────────────────────────────────────────────

    def h1(self, text):
        text = _c(text)
        self._toc.append((1, text, self.page_no()))
        self.ln(3)
        self.set_fill_color(*COL_TITRE)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, f"  {text}", fill=True,
                  new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*COL_BODY)
        self.ln(2)

    def h2(self, text):
        text = _c(text)
        self._toc.append((2, text, self.page_no()))
        self.ln(3)
        self.set_text_color(*COL_SOUS)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*COL_SOUS)
        self.line(MARGIN, self.get_y(), 210 - MARGIN, self.get_y())
        self.set_text_color(*COL_BODY)
        self.ln(2)

    def h3(self, text):
        text = _c(text)
        self.ln(2)
        self.set_text_color(*COL_ACCENT)
        self.set_font("Helvetica", "B", 9.5)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*COL_BODY)

    # ── Corps ──────────────────────────────────────────────────────────

    def body(self, text, indent=0):
        text = _c(text)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*COL_BODY)
        self.set_x(MARGIN + indent)
        self.multi_cell(0, 5, text)
        self.set_x(MARGIN)

    def bullet(self, text, indent=6, symbol="-"):
        text = _c(text)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*COL_BODY)
        self.set_x(MARGIN + indent)
        self.cell(5, 5, symbol)
        self.multi_cell(0, 5, text)
        self.set_x(MARGIN)

    def code(self, lines, caption=""):
        if caption:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(*COL_SOUS)
            self.cell(0, 5, _c(caption), new_x="LMARGIN", new_y="NEXT")
        self.set_fill_color(*COL_CODE)
        self.set_text_color(*COL_CODE_FG)
        self.set_font("Courier", "", 8)
        block = _c("\n".join(lines))
        self.multi_cell(0, 4.5, block, fill=True)
        self.set_text_color(*COL_BODY)
        self.ln(1)

    def note(self, text, kind="info"):
        text = _c(text)
        cfg = {
            "info":  ((60, 100, 190), "[i] INFO"),
            "ok":    (COL_OK,         "[OK]   "),
            "warn":  (COL_WARN,       "[!] ATTENTION"),
            "v1":    (COL_TAG_V1,     "[AVANT]"),
            "v2":    (COL_TAG_V2,     "[APRES]"),
        }
        color, label = cfg.get(kind, cfg["info"])
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.cell(30, 6, label, fill=True)
        self.set_fill_color(242, 244, 252)
        self.set_text_color(*COL_BODY)
        self.set_font("Helvetica", "", 8)
        self.multi_cell(0, 6, f"  {text}", fill=True)
        self.set_x(MARGIN)
        self.ln(1)

    def rule(self):
        self.set_draw_color(*COL_RULE)
        self.line(MARGIN, self.get_y(), 210 - MARGIN, self.get_y())
        self.ln(3)

    def tag(self, label, color):
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 7.5)
        self.cell(22, 5, _c(label), fill=True)
        self.set_text_color(*COL_BODY)
        self.ln(1)

    # ── Table des matières ─────────────────────────────────────────────

    def toc(self):
        self.add_page()
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*COL_TITRE)
        self.cell(0, 12, "Sommaire", align="C",
                  new_x="LMARGIN", new_y="NEXT")
        self.rule()
        for level, title, page in self._toc:
            indent = (level - 1) * 8
            size = 9 if level == 1 else 8
            bold = "B" if level == 1 else ""
            self.set_font("Helvetica", bold, size)
            self.set_text_color(*COL_BODY if level > 1 else COL_TITRE)
            self.set_x(MARGIN + indent)
            dots = "." * max(2, 58 - len(title) - indent)
            self.cell(0, 6, f"{title}  {dots}  p.{page}",
                      new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*COL_BODY)


# ─────────────────────────────────────────────────────────────────────
# Sections du rapport
# ─────────────────────────────────────────────────────────────────────

def couverture(pdf: Rapport):
    pdf.add_page()
    # Fond dégradé simulé avec deux rectangles
    pdf.set_fill_color(*COL_TITRE)
    pdf.rect(0, 0, 210, 297, 'F')
    pdf.set_fill_color(20, 40, 80)
    pdf.rect(0, 200, 210, 97, 'F')

    # Titre principal
    pdf.set_font("Helvetica", "B", 38)
    pdf.set_text_color(*COL_ACCENT)
    pdf.set_y(50)
    pdf.cell(0, 22, "TriosSeconverter", align="C",
             new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(200, 215, 245)
    pdf.cell(0, 10, "Rapport d'evolution & Guide de lancement",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_draw_color(*COL_ACCENT)
    pdf.set_line_width(1)
    pdf.line(35, pdf.get_y(), 175, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(10)

    # Badge version
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(255, 220, 80)
    pdf.cell(0, 8, "Version 2.0  -  Mai 2026", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Bloc d'informations
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(160, 175, 225)
    infos = [
        "Auteur   :  Triomphe Tchounda",
        "Projet   :  Conversion OCR de tableaux de borniers electriques",
        "Source   :  Document Word scanne  ->  Excel + Word structures",
        "Cible    :  Station EPEULE  |  Plan VD23111 PE 162",
        "Outil    :  Python 3.10+  |  Tesseract OCR  |  openpyxl",
    ]
    for line in infos:
        pdf.cell(0, 7, _c(line), align="C",
                 new_x="LMARGIN", new_y="NEXT")

    # Encadre bas
    pdf.set_y(220)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 120, 180)
    pdf.cell(0, 6,
             "Ce document decrit les ameliorations apportees au logiciel",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "et explique pas a pas comment le lancer.",
             align="C", new_x="LMARGIN", new_y="NEXT")


def section_contexte(pdf: Rapport):
    pdf.add_page()
    pdf.h1("1. Contexte et objectif du logiciel")

    pdf.body(
        "TriosSeconverter automatise l'extraction de tableaux de borniers "
        "electriques depuis des images scannees (fichier Word). "
        "Il produit deux fichiers de sortie exploitables directement :\n\n"
        "  - tous_les_borniers.xlsx : classeur Excel, un bornier par page A4\n"
        "  - tous_les_borniers.docx : document Word, un bornier par page"
    )

    pdf.h2("Le probleme initial")
    pdf.body(
        "Le document source (VD23111 PE 162) contient plus de 460 tableaux "
        "de borniers sous forme d'images. Chaque image represente un bornier "
        "avec 4 colonnes : BORNE, COULEUR, SIGNAL, JARRETIERES.\n\n"
        "Saisir ces tableaux manuellement prendrait plusieurs jours de travail. "
        "Le logiciel reduit cette tache a quelques minutes."
    )

    pdf.h2("Les 4 colonnes d'un tableau de bornier")
    colonnes = [
        ("BORNE",       "Identifiant de la borne (ex: A1, B2, 01, 02...)"),
        ("COULEUR",     "Code couleur du cable (ex: G, BC, I, B, J, R...)"),
        ("SIGNAL",      "Nom du signal electrique (ex: RESERVE CABLEE, FSI-31...)"),
        ("JARRETIERES", "Numero de jarretiere de raccordement (ex: 0191N, 1431B...)"),
    ]
    for col, desc in colonnes:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COL_ACCENT)
        pdf.set_x(MARGIN + 6)
        pdf.cell(32, 6, col)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COL_BODY)
        pdf.cell(0, 6, _c(desc), new_x="LMARGIN", new_y="NEXT")

    pdf.h2("Pipeline de traitement")
    pdf.code([
        "Fichier Word (.docx)",
        "    |",
        "    |  Etape 1 : recuperer_image.py",
        "    v      Extraction des images depuis l'archive ZIP du .docx",
        "  Images/  bornier_1.jpg, bornier_2.jpg, ...  bornier_N.jpg",
        "    |",
        "    |  Etape 2 : ocr_processor.py  (Tesseract OCR)",
        "    v      Lecture du texte + affectation aux colonnes",
        "  Resultats OCR : [{headers, rows, metadata}, ...]",
        "    |",
        "    |-- Etape 3a : generer_classeur.generer_excel()",
        "    |     -> tous_les_borniers.xlsx",
        "    |",
        "    +-- Etape 3b : generer_classeur.generer_word()",
        "          -> tous_les_borniers.docx",
    ], caption="Flux complet de traitement")


def section_etat_initial(pdf: Rapport):
    pdf.add_page()
    pdf.h1("2. Etat initial du logiciel (version 1)")

    pdf.body(
        "La version 1 fonctionnait et produisait un classeur Excel et un "
        "document Word. Cependant, le resultat Excel presentait plusieurs "
        "ecarts importants par rapport au document source :"
    )

    pdf.h2("Probleme 1 — Mise en page Excel : pas de simulation de page")
    pdf.note(
        "Chaque bornier etait suivi de 2 lignes vides. "
        "Il n'y avait aucune simulation de page A4, aucun saut de page, "
        "et les footers (M T I / NO PLAN) apparaissaient juste apres "
        "les donnees sans espacement.",
        "v1"
    )
    pdf.note(
        "Chaque bornier occupe exactement 48 lignes (simulation page A4). "
        "Le pied de page est toujours aux lignes 47-48 du bloc. "
        "Des sauts de page Excel sont inseres pour l'impression.",
        "v2"
    )

    pdf.h2("Probleme 2 — Footer : espacement et valeurs manquantes")
    pdf.note(
        "Le nom de station P.E.T. (ex: EPEULE) et le nom du bornier "
        "(ex: AA) etaient souvent vides dans le footer, car le regex "
        "d'extraction OCR etait trop restrictif (1 seul mot).",
        "v1"
    )
    pdf.note(
        "Regex ameliore pour capturer les noms multi-mots. "
        "Valeur de repli STATION_NAME dans config.py si l'OCR echoue. "
        "Espacement du footer reproduit fidelement (f-string avec ljust).",
        "v2"
    )

    pdf.h2("Probleme 3 — Borniers OCR rates inclus dans le classeur")
    pdf.note(
        "Les images ou l'OCR echouait completement (ex: page de couverture, "
        "sommaire, image floue) generaient des lignes de bruit dans le classeur "
        "(texte aleatoire, 0-1 lignes de donnees).",
        "v1"
    )
    pdf.note(
        "Filtrage actif : les borniers avec moins de MIN_DATA_ROWS (defaut: 1) "
        "lignes de donnees sont ignores. Un compteur indique le nombre d'exclusions.",
        "v2"
    )

    pdf.h2("Probleme 4 — Aucune correction des erreurs OCR")
    pdf.note(
        "Les valeurs lues par l'OCR etaient utilisees telles quelles, "
        "meme en cas d'erreur evidente ('RESFRVE CABLEE' au lieu de "
        "'RESERVE CABLEE', '0' au lieu de 'O', etc.).",
        "v1"
    )
    pdf.note(
        "Nouveau dictionnaire de donnees (data_dictionary.json) : "
        "apprend les valeurs correctes depuis les Excel corriges par l'utilisateur "
        "et les applique automatiquement (correspondance floue a 82%).",
        "v2"
    )


def section_ameliorations(pdf: Rapport):
    pdf.add_page()
    pdf.h1("3. Ameliorations apportees en version 2")

    # ── A1 : Page A4
    pdf.h2("A1 — Simulation de pages A4 dans Excel")
    pdf.body(
        "Chaque bornier occupe exactement 48 lignes dans la feuille Excel, "
        "ce qui correspond exactement a une page A4 portrait avec les "
        "marges standard (17.5 mm gauche/droite, 19 mm haut/bas) "
        "et une hauteur de ligne de 15 points."
    )
    pdf.body(
        "Formule du rembourrage (lignes vides avant le footer) :"
    )
    pdf.code([
        "PAGE_SIZE    = 48   # lignes par page (config.py)",
        "n_data_rows  = nombre de lignes de donnees du bornier",
        "",
        "footer_row   = start_row + PAGE_SIZE - 2",
        "# Les lignes entre la derniere donnee et footer_row",
        "# sont automatiquement vides (rembourrage implicite).",
        "",
        "# Hauteur de ligne fixe pour garantir le rendu A4 :",
        "ws.row_dimensions[ri].height = 15   # 15 pt = hauteur standard",
    ], caption="Logique de positionnement (ocr_processor._fill_worksheet)")
    pdf.body(
        "Un saut de page manuel (openpyxl Break) est insere apres chaque "
        "bornier, ce qui permet d'imprimer directement depuis Excel "
        "avec une mise en page correcte."
    )

    # ── A2 : Filtrage
    pdf.h2("A2 — Filtrage des borniers invalides")
    pdf.body(
        "Avant la generation du classeur, chaque resultat OCR est evalue. "
        "Un bornier est exclu si le nombre de lignes de type 'data' est "
        "inferieur au seuil MIN_DATA_ROWS (configurable dans config.py)."
    )
    pdf.code([
        "# config.py",
        "MIN_DATA_ROWS = 1   # 0 = inclure tout, 3 = plus strict",
        "",
        "# generer_classeur.py — filtrage avant la boucle",
        "for r in results:",
        "    if extractor._count_data_rows(r) >= min_rows:",
        "        valides.append(r)",
        "    else:",
        "        ignores += 1",
    ], caption="Filtrage dans generer_excel()")

    # ── A3 : Footer
    pdf.h2("A3 — Footer fidelement reproduit")
    pdf.body(
        "Le footer de chaque bornier reproduit exactement le format "
        "du document source, avec un espacement long entre P.E.T. et BORNIER :"
    )
    pdf.code([
        "# template.py — render_footer_row1()",
        'left  = f"P.E.T.   :     {pet}"',
        'right = f"BORNIER :    {bornier}"',
        'return f"{left:<65}{right}"',
        "",
        "# Resultat obtenu :",
        "# P.E.T.   :     EPEULE                            BORNIER :    AA",
    ], caption="Rendu de la premiere ligne du pied de page")
    pdf.body(
        "Si l'OCR ne parvient pas a lire le nom de station (P.E.T.), "
        "la valeur Config.STATION_NAME ('EPEULE' par defaut) est utilisee "
        "automatiquement comme repli."
    )

    # ── A4 : Dictionnaire
    pdf.h2("A4 — Dictionnaire de donnees evolutif")
    pdf.body(
        "Le fichier data_dictionary.json stocke les valeurs validees "
        "par colonne (BORNE, COULEUR, SIGNAL, JARRETIERES). "
        "Il est enrichi a chaque fois que l'utilisateur envoie "
        "un fichier Excel corrige et accepte."
    )
    pdf.code([
        "# Alimenter le dictionnaire depuis un Excel corrige",
        "from data_dictionary import get_dictionary",
        "from pathlib import Path",
        "",
        "dico  = get_dictionary()",
        "stats = dico.update_from_excel(",
        "    Path('tous_les_bornier_corrige.xlsx')",
        ")",
        "print(stats)",
        "# -> {'BORNE': 32, 'SIGNAL': 87, 'JARRETIERES': 156}",
        "",
        "# Correction automatique lors de la generation :",
        "# 'RESFRVE CABLEE'  ->  'RESERVE CABLEE'  (82% de similarite)",
    ], caption="Utilisation du dictionnaire (data_dictionary.py)")

    pdf.h2("Fichiers modifies / crees")
    fichiers = [
        ("data_dictionary.py", "NOUVEAU",  COL_TAG_V2,
         "Classe DataDictionary : apprentissage et correction OCR"),
        ("config.py",          "MODIFIE",  COL_INFO,
         "Ajout : STATION_NAME, PAGE_SIZE, MIN_DATA_ROWS"),
        ("template.py",        "MODIFIE",  COL_INFO,
         "render_footer_row1/row2 avec espacement f-string"),
        ("ocr_processor.py",   "MODIFIE",  COL_INFO,
         "_fill_worksheet : page_size, padding, correction dico"),
        ("ocr_processor.py",   "MODIFIE",  COL_INFO,
         "_extract_meta : regex PET multi-mots, BORNIER etendu"),
        ("generer_classeur.py", "MODIFIE",  COL_INFO,
         "A4 setup, sauts de page, filtrage, dictionnaire"),
    ]
    for fich, statut, col, desc in fichiers:
        self = pdf
        self.set_fill_color(*col)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 7.5)
        self.set_x(MARGIN)
        self.cell(18, 5.5, _c(statut), fill=True)
        self.set_text_color(*COL_BODY)
        self.set_font("Helvetica", "B", 9)
        self.cell(44, 5.5, _c(fich))
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5.5, _c(desc), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def section_guide_lancement(pdf: Rapport):
    pdf.add_page()
    pdf.h1("4. Guide de lancement complet")

    # ── Prerequis
    pdf.h2("Prerequis — ce qui doit etre installe")

    pdf.h3("Python 3.10 ou superieur")
    pdf.bullet(
        "Telecharger depuis https://python.org "
        "- cocher 'Add Python to PATH' lors de l'installation."
    )
    pdf.bullet(
        "Verifier l'installation : ouvrir un terminal et taper :"
    )
    pdf.code(["python --version", "# -> Python 3.10.x ou superieur"])

    pdf.h3("Tesseract OCR avec pack francais")
    pdf.bullet(
        "Telecharger l'installateur UB-Mannheim depuis GitHub "
        "(chercher 'tesseract windows installer')."
    )
    pdf.bullet(
        "Lors de l'installation : cocher 'French' dans "
        "les paquets de langues supplementaires."
    )
    pdf.bullet(
        "Chemin d'installation configure dans config.py :"
    )
    pdf.code([
        r"TESSERACT_PATH = r'C:\Tesseract\TesseractOCR\tesseract.exe'",
    ], caption="A verifier / modifier dans config.py si necessaire")

    pdf.h3("Librairies Python")
    pdf.body(
        "Toutes les librairies sont installees automatiquement par install.bat. "
        "Pour une installation manuelle :"
    )
    pdf.code([
        "pip install python-docx openpyxl pytesseract",
        "pip install opencv-python Pillow numpy fpdf2",
    ])

    # ── Lancement GUI
    pdf.h2("Methode 1 — Interface graphique (recommandee)")

    pdf.h3("Premiere utilisation (installation)")
    pdf.body(
        "Double-cliquer sur install.bat dans le dossier du projet. "
        "Ce script :"
    )
    steps_install = [
        "Cree un environnement virtuel Python (dossier venv/)",
        "Installe toutes les librairies Python necessaires",
        "Cree un fichier lanceur TriosSeconverter.bat",
        "Cree un raccourci sur le Bureau Windows",
    ]
    for s in steps_install:
        pdf.bullet(s)

    pdf.h3("Lancement quotidien")
    pdf.body(
        "Une fois l'installation faite, lancer le logiciel de l'une "
        "de ces trois facons :"
    )
    pdf.bullet(
        "Double-cliquer sur le raccourci 'TriosSeconverter' "
        "cree sur le Bureau."
    )
    pdf.bullet(
        "Ou double-cliquer sur TriosSeconverter.bat "
        "dans le dossier du projet."
    )
    pdf.bullet(
        "Ou, depuis un terminal dans le dossier du projet :"
    )
    pdf.code([
        r"venv\Scripts\activate",
        "python interface.py",
    ])

    pdf.h3("Utilisation de l'interface")
    etapes_gui = [
        "1. Cliquer 'Parcourir' et selectionner le fichier Word source (.docx)",
        "2. Cliquer 'Parcourir' et choisir le dossier de sortie",
        "3. Cliquer le bouton 'Lancer la conversion'",
        "4. Surveiller la barre de progression et le journal",
        "5. Une fois termine, cliquer 'Ouvrir Excel' ou 'Ouvrir Word'",
    ]
    for e in etapes_gui:
        pdf.bullet(_c(e))
    pdf.note(
        "Ne pas fermer la fenetre pendant la conversion. "
        "Le traitement peut durer quelques minutes selon le nombre d'images.",
        "warn"
    )

    # ── Lancement CLI
    pdf.h2("Methode 2 — Ligne de commande (utilisateurs avances)")
    pdf.body(
        "run.py execute les 4 etapes avec affichage dans le terminal. "
        "Utile pour automatiser le traitement ou deboguer."
    )
    pdf.code([
        "# Ouvrir un terminal dans le dossier du projet",
        r"venv\Scripts\activate",
        "",
        "# Lancer le pipeline complet",
        "python run.py",
        "",
        "# Ou uniquement la generation Excel/Word (si images deja extraites)",
        "python generer_classeur.py",
    ])

    pdf.h3("Configurer le fichier source")
    pdf.body(
        "Avant de lancer, verifier config.py : "
    )
    pdf.code([
        "# config.py",
        'WORD_FILE          = "VD23111PE162 triomphepropre"',
        '                     # Nom du .docx source (sans extension)',
        'IMAGES_FOLDER_NAME = "VD23111 PE 162"',
        '                     # Dossier ou seront stockees les images',
        'STATION_NAME       = "EPEULE"',
        '                     # Nom de station pour le pied de page',
        'PAGE_SIZE          = 48',
        '                     # Lignes par page A4 (ne pas modifier)',
        'MIN_DATA_ROWS      = 1',
        '                     # Minimum de lignes pour garder un bornier',
    ], caption="Parametres a verifier dans config.py")


def section_guide_dictionnaire(pdf: Rapport):
    pdf.add_page()
    pdf.h1("5. Guide du dictionnaire de donnees")

    pdf.body(
        "Le dictionnaire de donnees est un mecanisme d'apprentissage : "
        "plus vous lui fournissez de tableaux corriges, plus le logiciel "
        "produit des resultats propres et fideles aux images sources."
    )

    pdf.h2("Principe de fonctionnement")
    pdf.code([
        "data_dictionary.json",
        "{",
        '  "BORNE":       ["A1", "A3", "A5", "B2", "B4", ...],',
        '  "COULEUR":     ["G", "BC", "I", "B", "J", "R", ...],',
        '  "SIGNAL":      ["RESERVE CABLEE", "FSI-31...", ...],',
        '  "JARRETIERES": ["0191N", "0192W", "1431B", ...]',
        "}",
    ], caption="Structure du fichier data_dictionary.json")
    pdf.body(
        "A chaque generation, pour chaque cellule de donnees, "
        "le logiciel cherche si la valeur OCR ressemble a une valeur "
        "connue du dictionnaire (seuil : 82% de similarite). "
        "Si oui, la valeur connue est utilisee a la place."
    )

    pdf.h2("Comment alimenter le dictionnaire")

    pdf.h3("Etape 1 — Lancer la conversion")
    pdf.bullet(
        "Generer le classeur Excel via l'interface ou run.py."
    )

    pdf.h3("Etape 2 — Corriger le classeur Excel")
    pdf.bullet(
        "Ouvrir tous_les_borniers.xlsx dans Excel."
    )
    pdf.bullet(
        "Corriger les erreurs OCR, nettoyer les valeurs incorrectes."
    )
    pdf.bullet(
        "Sauvegarder sous un nouveau nom (ex: borniers_corriges_mai2026.xlsx)."
    )
    pdf.bullet(
        "Ne pas modifier les lignes d'en-tete (BORNE/COULEUR/SIGNAL/JARRETIERES) "
        "ni les lignes de footer (M T I / NO PLAN)."
    )

    pdf.h3("Etape 3 — Envoyer le fichier corrige au logiciel")
    pdf.body(
        "Placer le fichier Excel corrige dans le meme dossier que le projet, "
        "puis executer :"
    )
    pdf.code([
        r"venv\Scripts\activate",
        "python -c \"",
        "from data_dictionary import get_dictionary",
        "from pathlib import Path",
        "dico  = get_dictionary()",
        "stats = dico.update_from_excel(",
        "    Path('borniers_corriges_mai2026.xlsx')",
        ")",
        "print('Valeurs apprises :', stats)",
        "\"",
    ], caption="Commande pour alimenter le dictionnaire")
    pdf.body(
        "Le programme affiche le nombre de nouvelles valeurs apprises "
        "par colonne, par exemple :"
    )
    pdf.code([
        "Valeurs apprises : {",
        "    'BORNE': 32,        # 32 codes de bornes uniques",
        "    'COULEUR': 12,      # 12 codes couleur uniques",
        "    'SIGNAL': 87,       # 87 signaux uniques",
        "    'JARRETIERES': 156  # 156 numeros de jarretieres uniques",
        "}",
    ])

    pdf.h3("Etape 4 — Relancer la conversion")
    pdf.bullet(
        "A la prochaine generation, le dictionnaire est charge "
        "automatiquement et toutes les corrections sont appliquees."
    )
    pdf.note(
        "Le dictionnaire est cumulatif : chaque nouveau fichier corrige "
        "enrichit les donnees existantes sans les effacer.",
        "ok"
    )
    pdf.note(
        "Ne fournir que des fichiers deja verifies et corriges. "
        "Le logiciel valide les valeurs (longueur, caracteres autorises) "
        "mais fait confiance au contenu fourni par l'utilisateur.",
        "warn"
    )

    pdf.h2("Reinitialiser le dictionnaire")
    pdf.body(
        "Pour repartir de zero (si le dictionnaire contient des erreurs) :"
    )
    pdf.code([
        "# Supprimer ou vider le fichier",
        r"del data_dictionary.json",
        "# Le fichier sera recree vide au prochain lancement.",
    ])


def section_parametres(pdf: Rapport):
    pdf.add_page()
    pdf.h1("6. Parametres configurables (config.py)")

    pdf.body(
        "Tous les parametres du logiciel sont centralises dans config.py. "
        "Modifier ce fichier suffit pour adapter le logiciel sans toucher "
        "au code de traitement."
    )

    params = [
        ("WORD_FILE",           "VD23111PE162 triomphepropre",
         "Nom du fichier Word source (sans .docx)"),
        ("IMAGES_FOLDER_NAME",  "VD23111 PE 162",
         "Sous-dossier de stockage des images extraites"),
        ("TESSERACT_PATH",      r"C:\Tesseract\...\tesseract.exe",
         "Chemin complet vers l'executable Tesseract"),
        ("OCR_LANGUAGE",        "fra",
         "Code de langue Tesseract (fra = francais)"),
        ("STATION_NAME",        "EPEULE",
         "Nom de station P.E.T. pour le pied de page (repli si OCR echoue)"),
        ("PAGE_SIZE",           "48",
         "Lignes par page A4. Ne pas modifier (calcule pour 15pt/ligne)."),
        ("MIN_DATA_ROWS",       "1",
         "Seuil minimal de lignes de donnees pour inclure un bornier"),
        ("EXPORT_EXCEL",        "True",
         "Exporter le classeur Excel"),
        ("GENERATE_REPORT",     "True",
         "Generer un rapport JSON a la fin"),
    ]

    for param, valeur, desc in params:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COL_ACCENT)
        pdf.set_x(MARGIN)
        pdf.cell(48, 6, param)
        pdf.set_font("Courier", "", 8.5)
        pdf.set_text_color(*COL_SOUS)
        pdf.cell(42, 6, _c(valeur))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COL_BODY)
        pdf.cell(0, 6, _c(desc), new_x="LMARGIN", new_y="NEXT")

    pdf.h2("Exemple de modification")
    pdf.body(
        "Pour traiter un second document Word (ex: deuxieme fichier "
        "de borniers manquants) :"
    )
    pdf.code([
        "# Dans config.py :",
        'WORD_FILE          = "VD23111PE162_partie2"',
        'IMAGES_FOLDER_NAME = "VD23111 PE 162 partie2"',
        "",
        "# Puis lancer :",
        "python run.py",
    ])


def section_résumé(pdf: Rapport):
    pdf.add_page()
    pdf.h1("7. Resume des commandes essentielles")

    pdf.h2("Installation (une seule fois)")
    pdf.code([
        "# Double-cliquer sur install.bat",
        "# OU en ligne de commande :",
        "python -m venv venv",
        r"venv\Scripts\activate",
        "pip install python-docx openpyxl pytesseract opencv-python Pillow fpdf2",
    ])

    pdf.h2("Lancement quotidien — Interface graphique")
    pdf.code([
        "# Raccourci Bureau : TriosSeconverter",
        "# OU :",
        r"venv\Scripts\activate",
        "python interface.py",
    ])

    pdf.h2("Lancement quotidien — Terminal")
    pdf.code([
        r"venv\Scripts\activate",
        "",
        "# Pipeline complet (extraction + OCR + Excel + Word)",
        "python run.py",
        "",
        "# OCR + Excel + Word uniquement (images deja extraites)",
        "python generer_classeur.py",
    ])

    pdf.h2("Alimenter le dictionnaire de donnees")
    pdf.code([
        r"venv\Scripts\activate",
        "python -c \"",
        "from data_dictionary import get_dictionary; from pathlib import Path",
        "print(get_dictionary().update_from_excel(Path('fichier_corrige.xlsx')))",
        "\"",
    ])

    pdf.h2("Regenerer ce rapport PDF")
    pdf.code([
        r"venv\Scripts\activate",
        "python generer_rapport_evolution.py",
        "# -> TriosSeconverter_Rapport_Evolution.pdf",
    ])

    pdf.h2("Regenerer la documentation technique complete")
    pdf.code([
        r"venv\Scripts\activate",
        "python generer_doc.py",
        "# -> TriosSeconverter_Documentation.pdf",
    ])

    pdf.ln(4)
    pdf.rule()
    pdf.h2("Arborescence du projet")
    pdf.code([
        "convertion Tableau/",
        "  config.py              Configuration centrale",
        "  recuperer_image.py     Extraction images du .docx",
        "  ocr_processor.py       OCR et extraction structuree",
        "  generer_classeur.py    Generation Excel + Word combines",
        "  converter.py           Orchestrateur (callbacks GUI)",
        "  interface.py           Interface graphique tkinter",
        "  template.py            Modeles de tableaux configurables",
        "  data_dictionary.py     Dictionnaire evolutif (NOUVEAU v2)",
        "  run.py                 Point d'entree ligne de commande",
        "  install.bat            Script d'installation",
        "  build_exe.bat          Packaging PyInstaller",
        "  data_dictionary.json   Valeurs apprises (cree automatiquement)",
        "  tous_les_borniers.xlsx Fichier de sortie Excel",
        "  tous_les_borniers.docx Fichier de sortie Word",
        "  VD23111 PE 162/        Dossier des images extraites",
        "    bornier_1.jpg",
        "    bornier_2.jpg",
        "    ...",
    ], caption="Structure des fichiers")


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main():
    pdf = Rapport()

    # Couverture (page 1 - sans header/footer)
    couverture(pdf)

    # Sections (remplissent le TOC)
    section_contexte(pdf)
    section_etat_initial(pdf)
    section_ameliorations(pdf)
    section_guide_lancement(pdf)
    section_guide_dictionnaire(pdf)
    section_parametres(pdf)
    section_résumé(pdf)

    # Sommaire en derniere position (apres toutes les sections pour avoir les numeros)
    pdf.toc()

    output = Path("TriosSeconverter_Rapport_Evolution.pdf")
    pdf.output(str(output))
    size_ko = output.stat().st_size // 1024
    n_pages = len(pdf.pages)
    print(f"\n  [OK] Rapport PDF genere : {output}")
    print(f"       {size_ko} Ko  |  {n_pages} pages")


if __name__ == '__main__':
    main()
