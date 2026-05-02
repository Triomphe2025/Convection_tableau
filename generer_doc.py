"""
Generateur de documentation PDF pour TriosSeconverter.

Produit un document PDF complet couvrant :
  - Architecture du projet
  - Role de chaque fichier
  - Explication des classes et methodes cles
  - Historique des erreurs et solutions
  - Guide d'evolution
  - Guide pour recoder depuis zero

Usage :
    python generer_doc.py
    → Cree : TriosSeconverter_Documentation.pdf
"""

from pathlib import Path
from fpdf import FPDF


# ── Constantes de mise en page ────────────────────────────────────────
MARGIN   = 18
COL_TITRE   = (42, 42, 90)      # bleu fonce
COL_SOUS    = (90, 40, 140)     # violet
COL_CODE    = (30, 30, 50)      # fond code
COL_CODE_FG = (200, 210, 240)   # texte code
COL_OK      = (40, 140, 80)
COL_ERR     = (160, 40, 40)
COL_WARN    = (160, 110, 20)
COL_RULE    = (200, 200, 220)
COL_BODY    = (30, 30, 40)
COL_ACCENT  = (233, 69, 96)     # rouge-rose TriosSeconverter


_UNICODE_MAP = str.maketrans({
    "→": "->",   # →
    "←": "<-",   # ←
    "▶": ">",    # ▶
    "▼": "v",    # ▼
    "│": "|",    # │
    "├": "+",    # ├
    "└": "+",    # └
    "─": "-",    # ─
    "═": "=",    # ═
    "•": "-",    # •
    "✓": "[OK]", # ✓
    "✗": "[X]",  # ✗
    "✕": "[X]",  # ✕
    "✘": "[X]",  # ✘
    "✔": "[OK]", # ✔
    "✅": "[OK]", # ✅
    "❌": "[X]",  # ❌
    "⚠": "[!]",  # ⚠
    "ℹ": "[i]",  # ℹ
    "—": " - ",  # — em dash
    "–": " - ",  # – en dash
    "…": "...",       # …
    "“": '"',    # "
    "”": '"',    # "
    "‘": "'",    # '
    "’": "'",    # '
})


def _c(text: str) -> str:
    """Convertit les caracteres Unicode en equivalents Latin-1 pour fpdf."""
    text = text.translate(_UNICODE_MAP)
    # Remplacer tout caractere encore hors Latin-1 par '?'
    return text.encode('latin-1', errors='replace').decode('latin-1')


class Doc(FPDF):
    """Sous-classe FPDF avec helpers de style."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=MARGIN)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self._toc = []            # [(niveau, titre, page)]
        self._current_section = ""

    # ── En-tête / pied de page ────────────────────────────────────────

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*COL_RULE)
        self.cell(0, 6, "TriosSeconverter - Documentation technique", align="L")
        self.cell(0, 6, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*COL_RULE)
        self.line(MARGIN, self.get_y(), 210 - MARGIN, self.get_y())
        self.ln(2)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*COL_RULE)
        self.cell(0, 6, "(c) 2026 - Triomphe Tchounda - Document genere automatiquement",
                  align="C")

    # ── Helpers de typographie ────────────────────────────────────────

    def h1(self, text):
        text = _c(text)
        self._toc.append((1, text, self.page_no()))
        self.ln(4)
        self.set_fill_color(*COL_TITRE)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 10, f"  {text}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*COL_BODY)
        self.ln(2)

    def h2(self, text):
        text = _c(text)
        self._toc.append((2, text, self.page_no()))
        self.ln(3)
        self.set_text_color(*COL_SOUS)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*COL_SOUS)
        self.line(MARGIN, self.get_y(), 210 - MARGIN, self.get_y())
        self.set_text_color(*COL_BODY)
        self.ln(2)

    def h3(self, text):
        text = _c(text)
        self.ln(2)
        self.set_text_color(*COL_ACCENT)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*COL_BODY)

    def body(self, text, indent=0):
        text = _c(text)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*COL_BODY)
        x0 = self.get_x() + indent
        self.set_x(x0)
        self.multi_cell(0, 5, text)
        self.set_x(MARGIN)

    def bullet(self, text, symbol="-", indent=6):
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
        colors = {"info": (70, 100, 180), "ok": COL_OK,
                  "warn": COL_WARN, "err": COL_ERR}
        labels = {"info": "[i] INFO", "ok": "[OK]",
                  "warn": "[!] ATTENTION", "err": "[X] ERREUR"}
        c = colors.get(kind, colors["info"])
        self.set_fill_color(*c)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.cell(28, 6, labels[kind], fill=True)
        self.set_fill_color(240, 242, 250)
        self.set_text_color(*COL_BODY)
        self.set_font("Helvetica", "", 8)
        self.multi_cell(0, 6, f"  {text}", fill=True)
        self.set_x(MARGIN)
        self.ln(1)

    def rule(self):
        self.set_draw_color(*COL_RULE)
        self.line(MARGIN, self.get_y(), 210 - MARGIN, self.get_y())
        self.ln(3)

    def toc_page(self):
        """Insere une page de table des matieres (apres la couverture)."""
        self.add_page()
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*COL_TITRE)
        self.cell(0, 12, "Table des matieres", align="C",
                  new_x="LMARGIN", new_y="NEXT")
        self.rule()
        self.set_text_color(*COL_BODY)
        for level, title, page in self._toc:
            indent = (level - 1) * 8
            size = 9 if level == 1 else 8
            bold = "B" if level == 1 else ""
            self.set_font("Helvetica", bold, size)
            self.set_x(MARGIN + indent)
            dots = "." * max(2, 60 - len(title) - level * 4)
            self.cell(0, 6, f"{title}  {dots}  {page}",
                      new_x="LMARGIN", new_y="NEXT")


# ── Contenu du document ───────────────────────────────────────────────

def build_cover(pdf: Doc):
    pdf.add_page()
    pdf.set_fill_color(*COL_TITRE)
    pdf.rect(0, 0, 210, 297, 'F')

    pdf.set_font("Helvetica", "B", 36)
    pdf.set_text_color(*COL_ACCENT)
    pdf.set_y(60)
    pdf.cell(0, 20, "TriosSeconverter", align="C",
             new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(200, 210, 240)
    pdf.cell(0, 10, "Documentation technique complète", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_draw_color(*COL_ACCENT)
    pdf.line(40, pdf.get_y(), 170, pdf.get_y())
    pdf.ln(8)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(160, 170, 220)
    infos = [
        "Auteur   :  Triomphe Tchounda",
        "Version  :  1.0",
        "Date     :  Avril 2026",
        "Langage  :  Python 3.10+",
        "Objet    :  Conversion OCR de borniers electriques",
        "          -> Classeur Excel + Document Word uniques",
    ]
    for line in infos:
        pdf.cell(0, 8, line, align="C", new_x="LMARGIN", new_y="NEXT")


def section_intro(pdf: Doc):
    pdf.add_page()
    pdf.h1("1. Introduction et objectif du projet")

    pdf.body(
        "TriosSeconverter est un outil Python qui automatise la transformation "
        "de tableaux de borniers électriques (images scannées dans un document Word) "
        "en fichiers numériques editables : un classeur Excel et un document Word.\n\n"
        "Un bornier électrique est un tableau de connexions utilisé en électrotechnique "
        "industrielle. Chaque tableau liste les bornes (BORNE), leur couleur de câble "
        "(COULEUR), le signal associé (SIGNAL) et les jarretières (JARRETIERES).\n\n"
        "Le problème résolu : traiter manuellement 200+ tableaux prendrait plusieurs "
        "jours. TriosSeconverter le fait en quelques minutes."
    )

    pdf.h2("Pourquoi ce projet ?")
    pdf.bullet("Les tableaux existent uniquement sous forme d'images dans des fichiers Word.")
    pdf.bullet("Il n'est pas possible de chercher, filtrer ou modifier ces données.")
    pdf.bullet("La saisie manuelle est longue, coûteuse en temps et source d'erreurs.")
    pdf.bullet("L'OCR (reconnaissance optique de caractères) permet d'automatiser cette tâche.")

    pdf.h2("Ce que le logiciel produit")
    pdf.bullet("tous_les_borniers.xlsx : tous les tableaux sur une feuille Excel unique.")
    pdf.bullet("tous_les_borniers.docx : tous les tableaux dans un document Word unique.")
    pdf.bullet("Une interface graphique intuitive pour les non-développeurs.")


def section_architecture(pdf: Doc):
    pdf.add_page()
    pdf.h1("2. Architecture du projet")

    pdf.h2("Vue d'ensemble")
    pdf.body(
        "Le projet est organisé en couches claires, chaque fichier ayant "
        "une responsabilité unique (principe de séparation des préoccupations) :"
    )

    couches = [
        ("Interface (interface.py)",    "Fenêtre tkinter, interaction utilisateur"),
        ("Orchestration (converter.py)","Pipeline complet avec callbacks"),
        ("Génération (generer_classeur.py)", "Assemblage Excel et Word"),
        ("OCR (ocr_processor.py)",      "Extraction du texte depuis les images"),
        ("Extraction (recuperer_image.py)", "Décompression des images du .docx"),
        ("Configuration (config.py)",   "Paramètres centralisés"),
    ]

    for nom, role in couches:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COL_ACCENT)
        pdf.cell(70, 6, nom)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COL_BODY)
        pdf.cell(0, 6, _c(f"->  {role}"), new_x="LMARGIN", new_y="NEXT")

    pdf.h2("Flux de traitement")
    pdf.code([
        "Fichier Word (.docx)",
        "       │",
        "       ▼  recuperer_image.py — ImageExtractionPipeline",
        "   images/  (bornier_1.jpg, bornier_2.jpg, ...)",
        "       │",
        "       ▼  ocr_processor.py — BornierTableExtractor",
        "   résultats OCR  [{headers, rows, metadata}, ...]",
        "       │",
        "       ├──▶  generer_classeur.py — generer_excel()",
        "       │     tous_les_borniers.xlsx",
        "       │",
        "       └──▶  generer_classeur.py — generer_word()",
        "             tous_les_borniers.docx",
    ], caption="Flux de données de haut en bas")

    pdf.h2("Flux avec l'interface graphique")
    pdf.code([
        "interface.py (thread principal — tkinter)",
        "    │  clic sur 'Lancer'",
        "    ▼",
        "  threading.Thread(target=converter.run)",
        "    │  callbacks : on_progress(pct, msg) / on_log(msg)",
        "    ▼",
        "  queue.Queue  ←── messages de progression",
        "    │  after(80ms, poll)",
        "    ▼",
        "  Mise à jour barre de progression + journal",
    ], caption="Communication thread worker ↔ thread UI")


def section_fichiers(pdf: Doc):
    pdf.add_page()
    pdf.h1("3. Description détaillée de chaque fichier")

    fichiers = [
        (
            "config.py",
            "Configuration centralisée",
            [
                "Classe Config avec attributs de classe (constantes).",
                "TESSERACT_PATH : chemin vers l'exécutable Tesseract.",
                "OCR_LANGUAGE : langue OCR, 'fra' pour le français.",
                "IMAGES_FOLDER_NAME : nom du sous-dossier d'images.",
                "WORD_FILE : chemin par défaut du fichier Word source.",
                "Méthodes : get_output_folder(), get_word_file_path(), validate().",
                "Modifiez ce fichier pour adapter le logiciel à un nouveau projet.",
            ]
        ),
        (
            "recuperer_image.py",
            "Extraction des images du document Word",
            [
                "Un fichier .docx est une archive ZIP : on l'ouvre avec zipfile.",
                "Les images se trouvent dans word/media/ à l'intérieur du ZIP.",
                "ImageExtractor.extract_images() retourne [(bytes, extension), ...].",
                "ImageStorage.save_image() enregistre chaque image avec le nom bornier_N.",
                "ImageExtractionPipeline orchestre les deux classes ci-dessus.",
                "pipeline.run() retourne un dict {total, saved, errors, ...}.",
            ]
        ),
        (
            "ocr_processor.py",
            "Reconnaissance optique et extraction structurée",
            [
                "BornierTableExtractor est la classe centrale du projet.",
                "extract(image_path) → dict {success, headers, rows, metadata}.",
                "Prétraitement : niveaux de gris + seuil Otsu + upscaling x2.",
                "Détection des colonnes : pixel X du centre de chaque en-tête.",
                "Affectation des mots : chaque mot va dans la colonne la plus proche.",
                "_fill_worksheet(ws, result, start_row) → remplit une feuille Excel.",
                "_add_table_to_doc(doc, result) → insère un tableau dans un doc Word.",
                "to_excel() et to_word() : wrappers pour fichiers individuels.",
            ]
        ),
        (
            "generer_classeur.py",
            "Génération des fichiers combinés",
            [
                "extraire_tous(images_dir) : boucle OCR sur toutes les images.",
                "generer_excel(results, extractor, path) : une feuille, tous les tableaux.",
                "generer_word(results, extractor, path) : un doc, saut de page entre borniers.",
                "barre(current, total, label) : affiche une barre ASCII dans le terminal.",
                "_cle_num(path) : tri numérique (bornier_1, bornier_2, ... bornier_100).",
                "2 lignes vides entre chaque tableau dans Excel.",
                "Titre de section (heading niveau 2) avant chaque tableau dans Word.",
            ]
        ),
        (
            "converter.py",
            "Orchestrateur avec callbacks (pour l'interface graphique)",
            [
                "Classe Converter(word_file, output_dir, on_progress, on_log).",
                "run() exécute les 4 étapes et signale la progression via callbacks.",
                "on_progress(pct, msg) : pct dans [0.0, 1.0] pour la barre de progression.",
                "on_log(msg) : messages texte pour le journal de l'interface.",
                "Images stockées dans output_dir/images_borniers/ (chemin absolu).",
                "_extraire_avec_progres() : version de extraire_tous() avec callbacks.",
            ]
        ),
        (
            "interface.py",
            "Interface graphique tkinter",
            [
                "TriosSeconverterApp hérite de tk.Tk.",
                "RoundedButton : bouton Canvas à coins arrondis (dessin natif tkinter).",
                "Sélection de fichiers via filedialog.askopenfilename / askdirectory.",
                "Converter.run() s'exécute dans un thread daemon (threading.Thread).",
                "Les messages arrivent via queue.Queue et sont lus toutes les 80 ms.",
                "Boutons 'Excel', 'Word', 'Dossier' activés uniquement après succès.",
                "os.startfile() pour ouvrir les fichiers avec leur application par défaut.",
            ]
        ),
        (
            "run.py",
            "Point d'entrée en ligne de commande",
            [
                "Alternative à l'interface graphique pour les utilisateurs avancés.",
                "Exécute les 4 étapes avec affichage dans le terminal.",
                "Utilise Config.IMAGES_FOLDER_NAME comme dossier d'images.",
                "Les fichiers de sortie sont créés dans le répertoire courant.",
            ]
        ),
    ]

    for nom, titre, bullets in fichiers:
        pdf.h2(nom + "  —  " + titre)
        for b in bullets:
            pdf.bullet(b)
        pdf.ln(1)


def section_classes(pdf: Doc):
    pdf.add_page()
    pdf.h1("4. Classes et méthodes clés")

    pdf.h2("BornierTableExtractor (ocr_processor.py)")

    pdf.h3("extract(image_path) → dict")
    pdf.body(
        "Méthode principale. Charge l'image, la prétraite, détecte les colonnes "
        "depuis les en-têtes, lit le texte ligne par ligne et classe chaque mot "
        "dans la bonne colonne."
    )
    pdf.code([
        "result = {",
        "    'success': True,",
        "    'image_path': str(image_path),",
        "    'headers': ['BORNE','COULEUR','SIGNAL','JARRETIERES'],",
        "    'rows': [",
        "        {'type': 'data',    'cells': ['A1','ROUGE','SIG1','']},",
        "        {'type': 'section', 'text':  'NOM DU CABLE : 24V'},",
        "        {'type': 'footer',  'cells': ['M','T','I',''], 'is_mti': True},",
        "    ],",
        "    'metadata': {'BORNIER': 'A', 'NO PLAN': '12'},",
        "}",
    ], caption="Structure du dict retourné par extract()")

    pdf.h3("_detect_column_boundaries(data) → list[int]")
    pdf.body(
        "Cherche les mots-clés BORNE, COULEUR, SIGNAL, JARRETIERES dans les "
        "premières lignes du texte OCR. Retourne les positions x (pixels) du "
        "centre de chaque colonne. Cette approche est robuste car elle utilise "
        "les positions réelles des en-têtes, pas un clustering qui échoue "
        "quand une colonne est souvent vide."
    )

    pdf.h3("_fill_worksheet(ws, result, start_row) → int")
    pdf.body(
        "Remplit une feuille openpyxl à partir de la ligne start_row. "
        "Retourne la première ligne libre après le pied de tableau. "
        "Gère trois types de lignes : data, section, footer. "
        "Les bordures des cellules fusionnées doivent être posées individuellement "
        "sur chaque cellule du périmètre (limitation openpyxl)."
    )
    pdf.code([
        "# Correction border merge : poser sur CHAQUE cellule du bord",
        "ws.cell(row=r,   column=1).border = Border(left=thin, right=thin,",
        "                                           top=thin, bottom=ns)",
        "ws.cell(row=r+1, column=1).border = Border(left=thin, right=thin,",
        "                                           top=ns,   bottom=thin)",
    ], caption="Pourquoi cette approche (erreur découverte en phase 3)")

    pdf.h2("Converter (converter.py)")
    pdf.body(
        "Classe légère qui relie le pipeline de traitement à l'interface. "
        "Elle n'a aucune dépendance tkinter et peut donc être réutilisée "
        "dans des scripts ou des APIs. Le découplage repose sur les deux "
        "callables on_progress et on_log."
    )

    pdf.h2("TriosSeconverterApp (interface.py)")
    pdf.body(
        "Hérite de tk.Tk. L'UI est construite entièrement en code Python "
        "(pas de fichier .ui ou de ressource externe). Le thread worker "
        "ne touche jamais aux widgets directement — toutes les mises à jour "
        "passent par la queue, lue dans le thread principal par after()."
    )


def section_erreurs(pdf: Doc):
    pdf.add_page()
    pdf.h1("5. Historique des erreurs et solutions")

    erreurs = [
        (
            "Double traitement OCR",
            "err",
            "ImageExtractionPipeline avec enable_ocr=True ET generer_classeur "
            "qui relance BornierTableExtractor → chaque image traitée deux fois, "
            "temps d'exécution doublé.",
            "Fixer enable_ocr=False dans l'appel à ImageExtractionPipeline dans "
            "run.py (et converter.py). L'OCR est fait exclusivement par "
            "BornierTableExtractor via generer_classeur."
        ),
        (
            "Bordures manquantes sur les cellules fusionnées",
            "err",
            "Dans Excel, les bordures posées sur la cellule en haut à gauche "
            "d'une plage fusionnée ne s'affichent pas sur les autres bords "
            "de la zone fusionnée. openpyxl n'applique pas les bordures à toute "
            "la zone automatiquement.",
            "Poser les bordures manuellement sur chaque cellule du périmètre "
            "de la région fusionnée (top sur la ligne du haut, bottom sur "
            "la ligne du bas, left sur la colonne de gauche, right sur la droite)."
        ),
        (
            "PermissionError lors de la sauvegarde du fichier Word",
            "warn",
            "PermissionError: [Errno 13] Permission denied: 'tous_les_borniers.docx' "
            "→ le fichier est ouvert dans Microsoft Word au moment où Python "
            "essaie de l'écrire.",
            "Fermer le fichier dans Word avant de relancer le script. "
            "L'interface affiche un message d'erreur clair dans ce cas."
        ),
        (
            "Détection de colonnes par clustering (ancienne approche)",
            "warn",
            "L'ancien code utilisait un clustering des positions x de tous "
            "les mots pour deviner les colonnes. Cela échouait souvent : "
            "la colonne COULEUR est fréquemment vide, donc sans point de "
            "clustering → mauvaise détection.",
            "Nouvelle approche : lire les pixels x des mots-clés d'en-tête "
            "(BORNE, COULEUR, SIGNAL, JARRETIERES) directement depuis l'OCR "
            "des premières lignes. Robuste même si des colonnes sont vides."
        ),
        (
            "Texte mal affecté aux colonnes",
            "err",
            "Des mots appartenant à la colonne SIGNAL se retrouvaient dans "
            "COULEUR à cause de zones de colonnes mal délimitées.",
            "Utiliser les positions x réelles des en-têtes pour définir "
            "des zones par moitié : un mot appartient à la colonne dont "
            "le bord médian est le plus proche de son centre x."
        ),
    ]

    for titre, kind, cause, solution in erreurs:
        pdf.h3(titre)
        pdf.note(f"Cause : {cause}", kind)
        pdf.note(f"Solution : {solution}", "ok")
        pdf.ln(1)


def section_evolution(pdf: Doc):
    pdf.add_page()
    pdf.h1("6. Guide d'évolution du code")

    pdf.h2("Comment ajouter une nouvelle colonne (ex: SECTION)")
    pdf.body(
        "La liste des colonnes est implicite dans BornierTableExtractor. "
        "Pour ajouter une colonne :"
    )
    pdf.bullet("Ajouter le mot-clé dans la liste de mots-clés d'en-tête dans "
               "_detect_column_boundaries().")
    pdf.bullet("Ajuster la logique de fusion dans _fill_worksheet() si la "
               "nouvelle colonne participe aux fusions du pied de tableau.")
    pdf.bullet("Mettre à jour les tests dans test_nouveau_ocr.py.")

    pdf.h2("Comment changer la mise en forme Excel")
    pdf.bullet("Les styles de bordures sont définis dans _fill_worksheet() "
               "via openpyxl Border / Side.")
    pdf.bullet("thin = Side(style='thin', color='000000')")
    pdf.bullet("ns   = Side(style=None)  ← pas de bordure")
    pdf.bullet("Pour les lignes de section (NOM DU CABLE) : bordure en pointillés "
               "en haut (style='dashed').")

    pdf.h2("Comment supporter un autre format de Word")
    pdf.bullet("recuperer_image.py → ImageExtractor.extract_images() "
               "cherche word/media/ dans le ZIP. Si les images sont ailleurs "
               "dans le ZIP, modifier le filtre startswith().")
    pdf.bullet("Si le fichier source est un .doc (ancien format), "
               "le convertir d'abord en .docx (python-docx ne supporte que .docx).")

    pdf.h2("Comment améliorer la précision OCR")
    pdf.bullet("Augmenter le facteur de zoom dans _preprocess_image() (actuellement x2).")
    pdf.bullet("Essayer d'autres modes de page Tesseract : --psm 6 (bloc de texte) "
               "ou --psm 4 (colonne de texte).")
    pdf.bullet("Ajouter une liste blanche de caractères dans la config Tesseract "
               "pour les tableaux de bornes (souvent alphanumériques).")
    pdf.bullet("Ajouter un filtrage des artefacts OCR communs (0/O, l/1, etc.).")

    pdf.h2("Comment déployer sur Linux / macOS")
    pdf.bullet("Remplacer TESSERACT_PATH dans config.py par le chemin système "
               "(souvent /usr/bin/tesseract).")
    pdf.bullet("Remplacer os.startfile() dans interface.py par subprocess.run "
               "(['xdg-open', path]) sur Linux ou ['open', path] sur macOS.")
    pdf.bullet("PyInstaller supporte Linux et macOS avec les mêmes commandes "
               "(adapter le .spec si nécessaire).")


def section_guide_recodage(pdf: Doc):
    pdf.add_page()
    pdf.h1("7. Guide pour recoder TriosSeconverter depuis zéro")

    pdf.h2("Étape 1 — Environnement de développement")
    etapes1 = [
        "Installer Python 3.10+ depuis python.org (cocher 'Add to PATH').",
        "Installer Tesseract OCR (UB Mannheim) avec le pack de langue 'fra'.",
        "Créer un dossier de projet et un environnement virtuel :",
    ]
    for e in etapes1:
        pdf.bullet(e)
    pdf.code([
        "mkdir TriosSeconverter && cd TriosSeconverter",
        "python -m venv venv",
        "venv\\Scripts\\activate      # Windows",
        "pip install python-docx openpyxl pytesseract opencv-python Pillow fpdf2",
    ], caption="Commandes d'initialisation")

    pdf.h2("Étape 2 — Extraction des images (recuperer_image.py)")
    pdf.body(
        "Un .docx est un ZIP. Ouvrez-le avec zipfile.ZipFile et extrayez "
        "tous les fichiers de word/media/. Nommez-les bornier_1.jpg, bornier_2.jpg..."
    )
    pdf.code([
        "import zipfile",
        "from pathlib import Path",
        "",
        "with zipfile.ZipFile('source.docx', 'r') as z:",
        "    medias = [f for f in z.namelist() if f.startswith('word/media/')]",
        "    for i, name in enumerate(medias, 1):",
        "        data = z.read(name)",
        "        ext  = Path(name).suffix",
        "        Path(f'images/bornier_{i}{ext}').write_bytes(data)",
    ])

    pdf.h2("Étape 3 — OCR structuré (ocr_processor.py)")
    pdf.body(
        "Pour chaque image, appliquez pytesseract avec image_to_data() "
        "qui retourne les positions x, y de chaque mot. Identifiez les "
        "colonnes par les en-têtes, puis affectez chaque mot à sa colonne."
    )
    pdf.code([
        "import cv2, pytesseract",
        "",
        "img  = cv2.imread(str(path))",
        "gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)",
        "_, thresh = cv2.threshold(gray, 0, 255,",
        "                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)",
        "big  = cv2.resize(thresh, None, fx=2, fy=2,",
        "                  interpolation=cv2.INTER_CUBIC)",
        "",
        "data = pytesseract.image_to_data(",
        "    big, lang='fra',",
        "    config='--psm 6',",
        "    output_type=pytesseract.Output.DICT",
        ")",
    ])

    pdf.h2("Étape 4 — Génération Excel (generer_classeur.py)")
    pdf.body(
        "Créez un Workbook openpyxl, une feuille 'Borniers'. "
        "Pour chaque tableau de résultats, appelez _fill_worksheet() "
        "en incrémentant start_row (+ 2 lignes vides entre les tableaux)."
    )
    pdf.code([
        "from openpyxl import Workbook",
        "",
        "wb = Workbook()",
        "ws = wb.active",
        "ws.title = 'Borniers'",
        "row = 1",
        "for result in ocr_results:",
        "    row = extractor._fill_worksheet(ws, result, start_row=row)",
        "    row += 2   # 2 lignes vides de séparation",
        "wb.save('tous_les_borniers.xlsx')",
    ])

    pdf.h2("Étape 5 — Génération Word (generer_classeur.py)")
    pdf.code([
        "from docx import Document",
        "",
        "doc = Document()",
        "for i, result in enumerate(ocr_results):",
        "    if i > 0:",
        "        doc.add_page_break()",
        "    doc.add_heading(result['metadata'].get('BORNIER',''), level=2)",
        "    extractor._add_table_to_doc(doc, result)",
        "doc.save('tous_les_borniers.docx')",
    ])

    pdf.h2("Étape 6 — Interface graphique (interface.py)")
    pdf.bullet("Créer une classe héritant de tk.Tk.")
    pdf.bullet("Ajouter deux champs Entry + bouton 'Parcourir' pour le fichier Word et le dossier.")
    pdf.bullet("Lancer la conversion dans threading.Thread(daemon=True).")
    pdf.bullet("Communiquer avec le thread UI via queue.Queue et after(80, poll).")
    pdf.bullet("N'JAMAIS modifier un widget tkinter depuis un thread worker.")

    pdf.h2("Étape 7 — Packaging (optionnel)")
    pdf.code([
        "pip install pyinstaller",
        "pyinstaller --onedir --windowed --name TriosSeconverter interface.py",
        "# Le résultat est dans dist/TriosSeconverter/",
    ])


def section_deps(pdf: Doc):
    pdf.add_page()
    pdf.h1("8. Dépendances et installation")

    pdf.h2("Bibliothèques Python")
    deps = [
        ("python-docx",     "1.1.2+",  "Lire/écrire des fichiers .docx"),
        ("openpyxl",        "3.1.5+",  "Créer et formater des fichiers Excel .xlsx"),
        ("pytesseract",     "0.3.10+", "Interface Python pour Tesseract OCR"),
        ("opencv-python",   "4.8+",    "Prétraitement des images (seuillage, zoom)"),
        ("Pillow",          "10+",     "Chargement d'images pour pytesseract"),
        ("numpy",           "1.24+",   "Requis par opencv-python"),
        ("fpdf2",           "2.7+",    "Génération PDF (ce document)"),
    ]
    for pkg, ver, role in deps:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COL_ACCENT)
        pdf.cell(42, 6, pkg)
        pdf.set_text_color(*COL_SOUS)
        pdf.cell(18, 6, ver)
        pdf.set_text_color(*COL_BODY)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, role, new_x="LMARGIN", new_y="NEXT")

    pdf.h2("Tesseract OCR (logiciel externe)")
    pdf.body(
        "Tesseract est le moteur OCR. Il doit être installé séparément "
        "sur la machine (pas un package Python). Le chemin est configuré "
        "dans config.py (TESSERACT_PATH)."
    )
    pdf.bullet("Windows : télécharger l'installateur UB-Mannheim depuis GitHub.")
    pdf.bullet("Lors de l'installation, cocher le support de la langue 'French (fra)'.")
    pdf.bullet("Chemin par défaut configuré : C:\\Tesseract\\TesseractOCR\\tesseract.exe")

    pdf.h2("Installation complète")
    pdf.code([
        "# 1. Cloner / copier le projet dans un dossier",
        "# 2. Double-cliquer sur install.bat",
        "#    → crée l'environnement venv",
        "#    → installe toutes les dépendances Python",
        "#    → crée TriosSeconverter.bat (lanceur)",
        "#    → crée un raccourci sur le Bureau",
        "# 3. S'assurer que Tesseract est installé séparément",
        "# 4. Lancer via le raccourci ou TriosSeconverter.bat",
    ])


# ── Main ──────────────────────────────────────────────────────────────

def main():
    pdf = Doc()

    # Page de couverture (sans numéro, sans header)
    build_cover(pdf)

    # Sections de contenu (remplissent le TOC automatiquement)
    section_intro(pdf)
    section_architecture(pdf)
    section_fichiers(pdf)
    section_classes(pdf)
    section_erreurs(pdf)
    section_evolution(pdf)
    section_guide_recodage(pdf)
    section_deps(pdf)

    output = Path("TriosSeconverter_Documentation.pdf")
    pdf.output(str(output))
    print(f"\n[OK] Documentation PDF générée : {output}")
    print(f"     {output.stat().st_size // 1024} Ko")


if __name__ == '__main__':
    main()
