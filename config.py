"""
Fichier de configuration pour le script d'extraction d'images.

Modifiez ce fichier pour personnaliser le comportement sans toucher au code principal.
"""

import os
from pathlib import Path
from typing import Optional


def chemin_ressource(nom: str) -> Path:
    """Fichier livré avec l'appli : dans l'exe (dossier _MEIPASS de PyInstaller), sinon à côté
    du code. En lecture seule : ce que l'utilisateur crée va dans DOSSIER_UTILISATEUR."""
    import sys
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / nom
    return Path(__file__).parent / nom


def trouver_tesseract(configure: str, habituels) -> Optional[str]:
    """Premier tesseract.exe trouvé : variable TESSERACT_PATH, chemin configuré, chemins
    d'installation habituels, PATH ; None si aucun (message clair à l'utilisateur)."""
    import shutil
    for chemin in [os.environ.get('TESSERACT_PATH'), configure, *habituels]:
        if chemin and Path(chemin).is_file():
            return str(chemin)
    return shutil.which('tesseract')


_DOSSIER_UTILISATEUR = (Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
                        / 'TriosSeconverter')
_TESSERACT_CONFIGURE = r"C:\Tesseract\TesseractOCR\tesseract.exe"
_TESSERACT_HABITUELS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    str(Path(os.environ.get('LOCALAPPDATA') or '') / 'Programs' / 'Tesseract-OCR'
        / 'tesseract.exe'),
)


class Config:
    """Configuration centralisée pour l'extraction d'images."""

    # ========================================
    # 📝 CONFIGURATION DE BASE
    # ========================================

    # Chemin vers le fichier Word à traiter
    # Exemples:
    #   - "mon_document.docx" (même dossier que le script)
    #   - r"C:\Users\Utilisateur\Documents\rapport.docx" (chemin complet)
    #   - r"C:\Users\Utilisateur\Documents\mon document.docx" (avec espaces)
    WORD_FILE = "VD23111PE162 triomphepropre"

    # Nom du dossier de destination
    # Les images seront enregistrées dans: OUTPUT_FOLDER / IMAGES_FOLDER_NAME
    IMAGES_FOLDER_NAME = "VD23111 PE 162"

    # Chemin de base pour le dossier de sortie
    # None = même dossier que le script (répertoire courant)
    # ou spécifiez un chemin complet
    OUTPUT_BASE_PATH = None
    # OUTPUT_BASE_PATH = r"C:\Donnees\Extractions"

    # ========================================
    # 🎨 OPTIONS D'AFFICHAGE
    # ========================================

    # Niveau de détail des logs
    # Options: "DEBUG", "INFO", "WARNING", "ERROR"
    LOG_LEVEL = "INFO"

    # Afficher les détails lors du traitement
    VERBOSE = True

    # ========================================
    # ⚙️ OPTIONS DE TRAITEMENT
    # ========================================

    # Format de nommage des images
    # Utiliser {index} pour le numéro auto-incrémenté
    # Exemples:
    #   "bornier_{index}" → bornier_1.jpg, bornier_2.png
    #   "image_{index}" → image_1.jpg, image_2.png
    #   "scan_{index:03d}" → scan_001.jpg, scan_002.jpg (avec zéros)
    IMAGE_NAME_FORMAT = "bornier_{index}"

    # Continuer même en cas d'erreur sur une image
    CONTINUE_ON_ERROR = True

    # ========================================
    # 🖼️ OPTIONS D'IMAGES
    # ========================================

    # Formats d'images à extraire (None = tous)
    # Exemples:
    #   None → Extraire toutes les images
    #   ["jpg", "png"] → Uniquement JPG et PNG
    ALLOWED_FORMATS = None

    # Qualité JPEG (si redimensionnement)
    # 0-100, par défaut 85
    JPEG_QUALITY = 85

    # ========================================
    # � OPTIONS OCR (TRAITEMENT DES IMAGES)
    # ========================================

    # Activer le traitement OCR des images extraites
    ENABLE_OCR = True

    # Dossier de l'utilisateur (jamais à côté de l'exe, qui peut être en lecture seule) :
    # cache Tesseract, mesures du mode ombre, modèles créés, ajouts au lexique.
    DOSSIER_UTILISATEUR = _DOSSIER_UTILISATEUR

    # Tesseract OCR, installé à part sur chaque poste : chemin configuré, sinon les chemins
    # d'installation habituels, sinon le PATH. Introuvable : TESSERACT_TROUVE = False, le
    # journal et l'interface le disent (le chemin configuré est gardé pour le message).
    TESSERACT_CHEMINS_HABITUELS = _TESSERACT_HABITUELS
    TESSERACT_PATH = (trouver_tesseract(_TESSERACT_CONFIGURE, _TESSERACT_HABITUELS)
                      or _TESSERACT_CONFIGURE)
    TESSERACT_TROUVE = Path(TESSERACT_PATH).is_file()

    # Langue pour l'OCR
    OCR_LANGUAGE = "fra"

    # Extensions d'images à traiter avec OCR
    OCR_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp"]

    # Exporter aussi en Excel
    EXPORT_EXCEL = True

    # ========================================
    # 📄 OPTIONS MISE EN PAGE EXCEL
    # ========================================

    # Nom de la station (rapports de livraison). Ne remplit plus jamais le pied :
    # un P.E.T. absent du document reste vide, avec une alerte (étape 7).
    STATION_NAME = "EPEULE"

    # Nombre de lignes par page A4 (1 en-tête + données + rembourrage + 2 pied).
    # 59 lignes à 12,6 pt = exactement une page A4 portrait avec marges standard.
    PAGE_SIZE = 59

    # Nombre minimal de lignes de données pour conserver un bornier.
    # 1 et non 3 : les vrais tableaux de 1 ou 2 lignes existent (24 pages sur 127
    # dans 223111PE011). Une page de tableau vide (CABLE : RESERVE) est toujours
    # conservée ; toute page écartée est écrite dans le journal avec sa raison.
    MIN_DATA_ROWS = 1

    # Part minimale de cellules de données contenant un caractère alphanumérique ;
    # en dessous, la page est écartée comme gribouillage (raison journalisée).
    PAGE_DENSITE_MIN = 0.15

    # Marqueur qu'écrit Claude à la place d'un caractère illisible (prompt), gardé
    # tel quel dans l'Excel et coloré : une valeur devinée passerait inaperçue.
    MARQUEUR_ILLISIBLE = "??"
    # Rouge clair, distinct du jaune « confiance OCR basse » (FFFF99).
    COULEUR_ILLISIBLE = "FFC7CE"

    # ══════════════════════════════════════════════════════════════════
    # PIED DE PAGE (pied_page.py) — lu tel quel, jamais complété
    # ══════════════════════════════════════════════════════════════════
    # Libellés dont la valeur est un seul mot : le texte qui suit (« 8/10 »,
    # « CORDON TYPE 40 », « REF CE 8707905 ») va dans COMPLEMENT. Les autres
    # libellés (N° PLAN, P.E.T., libellés inconnus) gardent tout leur segment.
    PIED_LIBELLES_UN_MOT = ("TYPE", "CABLE", "INDICE", "PAGE", "BORNIER")
    # Logos du bloc gauche du pied, écrits sans blancs (« M A T R A » imprimé espacé) : une
    # cellule qui n'en porte qu'un appartient au pied (reformatage d'un Excel).
    # Modèles créés par l'utilisateur (les modèles livrés sont relus à chaque version).
    MODELES_UTILISATEUR = _DOSSIER_UTILISATEUR / 'templates.json'
    # Reformatage : un bloc uniforme de plus de N × PAGE_SIZE lignes est signalé (pied mal
    # reconnu, chaque tableau prendrait deux pages).
    REFORMAT_BLOC_MAX_PAGE = 1.5
    PIED_LOGOS = ("MATRA", "SIEMENS", "MTI", "ALSTOM", "SCHNEIDER")
    # Seuls libellés derrière lesquels « n/m » est un compteur de pages ; ailleurs
    # « 6/10 » est un diamètre de conducteur (dixièmes de mm), donc du COMPLEMENT.
    PIED_LIBELLES_COMPTEUR = ("PAGE", "FOLIO")
    # En-têtes de colonne d'un tableau des révisions (page de garde).
    PIED_ENTETES_REVISIONS = ("INDICE", "RÉVISION", "REVISION", "EDITION", "ÉDITION")
    # Forme d'un indice de révision : « A », « R », « 00 », « R10 », « TP2 ».
    PIED_INDICE_MOTIF = r"[A-Z]{0,2}\d{1,2}|[A-Z]"
    # Champs constants d'un document : une case vide est reprise des autres pages
    # du MÊME document si toutes celles qui portent le champ donnent la même valeur.
    # Par modèle de tableau (nom du modèle → clés) ; modèle absent → défaut.
    CHAMPS_CONSTANTS_DEFAUT = ("PET",)
    CHAMPS_CONSTANTS_PAR_MODELE = {}
    # Champs qui varient d'une page à l'autre : jamais repris, même listés ci-dessus.
    PIED_CHAMPS_JAMAIS_DEDUITS = ("INDICE", "PAGE", "TYPE", "CABLE")
    # Emplacement d'un champ = fin de la ligne du champ cité, après sa valeur. Un texte
    # sans libellé à cet emplacement (« JARRETIERAGE » à la place de « BORNIER : … »)
    # remplace le champ : il n'est pas absent (EMPLACEMENT_<champ>, aucune alerte).
    PIED_EMPLACEMENTS = {"BORNIER": "PET"}
    # Blancs qui séparent la valeur d'un texte posé à l'emplacement (pages vectorielles) ;
    # Claude ramène les blancs à un : seul un mot fixe du modèle y est alors reconnu.
    PIED_ECART_EMPLACEMENT = 3
    # Fond d'une case de pied complétée depuis les autres pages du document
    # (bleu clair, distinct du jaune « confiance basse » et du rouge « ?? »).
    COULEUR_DEDUIT = "DDEBF7"

    # Coquille de l'original (lettre O tapée pour un zéro dans « D3T O1A ») : corrigée
    # dans l'Excel livré, seulement dans le numéro de borne (2e mot) de ces colonnes ;
    # « OC21-37 », « 0VG (EAS) » ou un O ailleurs restent tels quels.
    CORRECTION_O_COLONNES = ("TENANT", "ABOUTISSANT", "BORNE")
    CORRECTION_O_MOTIF = r"O\d{1,2}[A-Z]?"
    # Orange clair, distinct du bleu « déduit », du jaune et du rouge « ?? ».
    COULEUR_CORRIGE = "F8CBAD"

    # Nombre max de colonnes de template affectées automatiquement.
    # Au-delà, l'affectation automatique par frontières pixel devient peu
    # fiable — un mapping manuel est demandé à l'utilisateur (si un callback
    # on_column_mapping est fourni au Converter).
    MAX_AUTO_COLUMNS = 4

    # ========================================
    # 📄 ROUTAGE PDF PAR PAGE (tous modes OCR)
    # ========================================

    # True : chaque page d'un PDF est classée selon sa nature, quel que soit
    # le moteur — texte vectoriel exact → lecture de la couche texte en grille
    # (aucun OCR ni appel API) ; couche OCR invisible → couche ignorée, page
    # relue comme un scan ; scan → pipeline OCR du mode choisi. False :
    # comportement v1.7.
    PDF_ROUTAGE_VECTORIEL = True

    # Surface cumulée des images (part de la page) à partir de laquelle une
    # page sans texte exploitable part dans le pipeline scan ; en dessous elle
    # est ignorée (motif journalisé). Bas à dessein : les gardes scannées de
    # 223400PE137 sont stockées en 4 bandes de 10 % chacune.
    PDF_SEUIL_IMAGE = 0.10

    # Au-delà de cette couverture, un texte posé sur l'image n'est pas lu en
    # grille (image pleine page : ce texte est une couche OCR, pas le document).
    PDF_SEUIL_IMAGE_PLEINE_PAGE = 0.8

    # Nombre minimal de caractères visibles pour traiter une page comme du
    # texte vectoriel (en dessous : titre isolé, tampon — pipeline actuel).
    PDF_MIN_CARS_VECTORIEL = 20

    # Écart vertical (points PDF) en dessous duquel deux spans sont sur la
    # même ligne de la grille ; l'interligne des listings est d'environ 11 pt.
    PDF_GRILLE_TOLERANCE_Y = 2.0
    # Orthographes équivalentes du mot-clé de section d'un modèle (pages vectorielles) : le
    # texte reste tel qu'imprimé (223111PE022 p. 35 et 36 impriment « NON DU CABLE »).
    SECTION_EQUIVALENTS = {'NOM DU CABLE': ('NOM DE CABLE', 'NON DU CABLE')}
    # Texte tel qu'imprimé (pages vectorielles) : deux mots identiques à moins de
    # DX_PAS caractères et DY_PART de leur hauteur l'un de l'autre sont un texte surimprimé,
    # lu une fois (223111PE022 p. 14) ; un mot qui ne laisse aucune encre, même grisée (<
    # PDF_VISIBILITE_GRIS) au cœur de ses lettres, bords de sa boîte écartés de
    # PDF_VISIBILITE_MARGE, page rendue à PDF_VISIBILITE_DPI, est caché et n'est pas lu.
    PDF_SURIMPRESSION_DX_PAS = 0.5
    PDF_SURIMPRESSION_DY_PART = 0.5
    PDF_VISIBILITE_DPI = 100
    PDF_VISIBILITE_GRIS = 220
    PDF_VISIBILITE_MARGE = 0.15

    # ========================================
    # 🔎 VÉRIFICATION DE CONVERSION
    # ========================================

    # Similarité minimale (0-1) entre deux pages pour les apparier : les deux
    # documents n'ont pas forcément la même pagination (pages de garde).
    VERIF_SEUIL_PAGE = 0.30

    # Similarité minimale (0-1) entre deux lignes pour les considérer comme la
    # même ligne lue différemment (sinon : ligne manquante / en trop).
    VERIF_SEUIL_LIGNE = 0.55

    # Un écart d'au plus N caractères est bénin si la confiance OCR de la
    # lecture de référence reste sous VERIF_CONFIANCE_SURE.
    VERIF_DISTANCE_BENIGNE = 2
    VERIF_CONFIANCE_SURE = 90

    # Deux zones qui diffèrent séparées de moins de N caractères identiques
    # sont regroupées en un seul écart (un mot lu de travers = un écart).
    VERIF_FUSION_ECARTS = 3

    # Au-delà de cette similarité de lignes identiques, deux pages sont
    # appariées sans chercher les lignes proches (économie de calcul).
    VERIF_SEUIL_PAGE_EXACTE = 0.9

    # En dessous de N caractères alphanumériques, une ligne présente d'un seul
    # côté est du bruit (trait, logo) et non une ligne manquante ou en trop.
    VERIF_LIGNE_BRUIT_MIN_CARS = 3

    # Confusions OCR courantes : chaque groupe est replié sur son 1er caractère
    # avant comparaison (O/0, I/1/L, S/5, T/7, B/8, Z/2).
    VERIF_CONFUSIONS_OCR = ("0O", "1IL", "5S", "T7", "8B", "2Z", ".,")

    # Ponctuation que l'OCR ajoute autour du texte (traits du cadre lus « | »,
    # taches lues « ! », « ‘ ») : ignorée avant toute comparaison.
    VERIF_PONCTUATION_PARASITE = "|!‘’`\"_;:"

    # Concordance minimale (cellules identiques ou bénignes / cellules
    # comparées) au-dessus de laquelle la conversion est jugée fidèle.
    VERIF_SEUIL_CONCORDANCE = 0.98

    # Relecture indépendante d'un scan (relecture_scan.py), réglages repris de
    # outils_reference/pdf_table_compare.py : psm 6 (bloc de texte uniforme) à
    # 300 DPI lit « RESERVE CABLEE » et « EP. STAT/TS » que le moteur de
    # conversion (rendu ×3, ~216 DPI) laissait tomber sur 6A 23111PE102.
    VERIF_RELECTURE_DPI = 300
    VERIF_RELECTURE_PSM = "6"
    # Écart vertical (pixels à VERIF_RELECTURE_DPI) : en dessous, même ligne.
    VERIF_RELECTURE_TOL_LIGNE = 12
    # Forme d'une clé de ligne (1re colonne) : 10, A01, 12B, P1. Une ligne dont la
    # clé n'a pas cette forme (pied « MATRA … », cartouche) n'est pas une donnée.
    VERIF_MOTIF_CLE = r"^[A-Z]?[0-9]{1,3}[A-Z]?$"
    # Après la 1re lettre d'une clé, lettres lues à la place d'un chiffre (« AO1 »,
    # « col », « Pl ») : repliées pour le seul test du motif, la cellule reste telle quelle.
    VERIF_REPLI_CLE = {"O": "0", "Q": "0", "I": "1", "L": "1"}
    # Une ligne sans clé lue reste une donnée (borne illisible), sauf si elle porte
    # un libellé de pied : c'est alors le cartouche, pas le tableau.
    VERIF_MOTS_PIED = ("P.E.T", "PET", "NO PLAN", "N° PLAN", "INDICE", "BORNIER", "PAGE")

    # ========================================
    # 📐 POSITIONS D'ORIGINE (pages scannées, positions_scan.py)
    # ========================================
    # Claude ramène les blancs à un : chaque mot reprend la colonne de son jumeau
    # lu par Tesseract (boîtes des mots) sur une grille de caractères par page.
    # False = comportement d'avant (espaces de Claude, police par défaut).
    POSITIONS_ORIGINALES = True
    # Lecture séparée de VERIF_RELECTURE_* : le calibrage du vérificateur n'en dépend pas.
    POSITIONS_DPI = 300
    # Grand côté d'un A4 (pt) : une page plus grande est rendue au même nombre de pixels.
    POSITIONS_COTE_A4_PT = 842
    POSITIONS_PSM = "6"
    POSITIONS_TOL_LIGNE = 12
    # Pas cherché à ± cette part du pas estimé (pente largeur / nombre de caractères, à
    # quelques % du vrai pas) : un pas voisin peut aligner par hasard les quelques
    # colonnes où commencent la plupart des mots (223111PE012 p. 6 : 22,98 au lieu de 28,6).
    POSITIONS_MARGE_PAS = 0.05
    POSITIONS_PRECISION_PAS = 0.001
    # Confusions repliées pour reconnaître le jumeau d'un mot (le mot écrit reste celui lu) ;
    # « l » minuscule : Tesseract lit « Al04 » pour « A104 » (famille I/1).
    POSITIONS_REPLIS = {"O": "0", "I": "1", "l": "1"}
    # Ressemblance minimale (texte replié) pour apparier une ligne lue à une ligne Tesseract
    # hors des blocs identiques.
    POSITIONS_SEUIL_LIGNE = 0.5
    # Caractères que Tesseract lit à la place d'un trait vertical du cadre (« 0815B/|RM »).
    POSITIONS_CARACTERES_TRAIT = "|/\\!"
    # Un mot n'est déplacé vers la colonne de gauche que si son jumeau finit à au moins N
    # caractères du trait : un texte imprimé à cheval sur le trait appartient à sa colonne.
    POSITIONS_MARGE_DEBORDEMENT = 1.0
    # Police des cellules de données : chasse fixe, sinon les colonnes ne s'alignent pas.
    # Lectures Tesseract gardées pour la double lecture et le contrôle de conservation, sans
    # 2e OCR : dans un dossier de l'appli, jamais à côté des fichiers de l'utilisateur (et
    # loin des 260 caractères de chemin de Windows). Clé = empreinte du PDF + page + réglages.
    POSITIONS_CACHE_DOSSIER = _DOSSIER_UTILISATEUR / 'cache'
    # Purge à chaque écriture : plus vieux que N jours, puis les plus anciens tant que le
    # dossier dépasse la taille maximale.
    POSITIONS_CACHE_AGE_MAX_JOURS = 30
    POSITIONS_CACHE_TAILLE_MAX_MO = 200
    POSITIONS_POLICE = "Courier New"
    POSITIONS_TAILLE_POLICE = 11

    # ========================================
    # 🧭 CONTRÔLE DES PAGES SCANNÉES (controle_conservation.py)
    # ========================================
    # Taux de divergence Claude / Tesseract parmi les mots appariés au-delà duquel la page
    # est un « scan dégradé » : Tesseract y lit trop mal pour contrôler la lecture (mesure
    # B0 : 18 à 50 % sur 223111PE011, 1 à 6 % sur 6A23111PE133 et 223111PE012).
    PAGE_DEGRADEE = 0.10
    # Contrôle de conservation (pages non dégradées) : un mot Tesseract sans mot Claude en
    # face (élément peut-être omis), une ligne Tesseract sans ligne Claude (ligne peut-être
    # manquante). La cellule garde toujours la valeur de Claude.
    CONTROLE_CONSERVATION = True
    # Confiance Tesseract minimale d'un mot (médiane pour une ligne) : en dessous, une
    # tache, un tampon ou un trait lu comme du texte ne donne pas d'alerte (mesure B0).
    CONSERVATION_CONFIANCE_MIN = 60
    # Fond d'une cellule où un élément est peut-être omis (lavande, distincte du bleu
    # « déduit », de l'orange « corrigé » et du rouge « ?? »).
    COULEUR_CONSERVATION = "E4DFEC"

    # ========================================
    # ✅ CONTRÔLE QUALITÉ (controle_qualite.py, étape 9)
    # ========================================
    # Le contrôle qualité ne modifie jamais une valeur : alerte dans A VERIFIER, cellule
    # colorée, proposition en commentaire. Une règle n'est activée qu'après la mesure C0
    # (au plus 1 fausse alerte par page en moyenne sur les 3 extraits).
    # Mesure C0 du 2026-10-09 (21 pages, rejeu) : cohérence + lexique, colonne vide et
    # format à 0 fausse alerte. Continuité : 0 vraie alerte, 2,76 fausses par page au seuil
    # 20 (suites non croissantes). Dictionnaire : 4,5 fausses par page en Claude, 3,2 en
    # Tesseract (74 cellules justes qu'il aurait changées) — coupé dans tous les modes.
    QUALITE_REGLES = {'coherence': True, 'dictionnaire': False, 'continuite': False,
                      'colonne_vide': True, 'format': True}
    # Confusions de caractère de la règle de cohérence (une substitution à la fois).
    QUALITE_CONFUSIONS = (('O', 'C'), ('O', '0'), ('I', '1'), ('S', '5'), ('B', '8'))
    # Mots plus courts (« OC », « PH ») trop fréquents pour être comparés seuls ; la
    # cellule entière l'est aussi (« CC FS 14 50 » contre « OC FS 14 50 »).
    QUALITE_LONGUEUR_MIN = 4
    # Forme majoritaire : au moins N occurrences et RATIO fois la forme suspecte.
    QUALITE_MIN_MAJORITE = 2
    QUALITE_RATIO_MAJORITE = 1.5
    # Lexique de référence : Excel déjà corrigés par l'utilisateur (hors de git), compilés
    # au build (formes seules, QUALITE_LEXIQUE_COMPILE, embarqué dans l'exe) ; à l'exécution,
    # + les classeurs ajoutés avec « Ajouter au lexique » dans QUALITE_LEXIQUE_DOSSIER.
    QUALITE_LEXIQUE_REFERENCE = Path(__file__).parent / 'references' / 'excels_valides'
    QUALITE_LEXIQUE_COMPILE = 'lexique_compile.json'
    QUALITE_LEXIQUE_DOSSIER = _DOSSIER_UTILISATEUR / 'lexique'
    QUALITE_LEXIQUE_FEUILLE = 'Listing'
    # Dictionnaire en alerte, par mode ; jamais sur une page vectorielle (texte exact).
    # 'claude' = moteurs vision (décidé par la mesure C0), 'ocr' = Tesseract, Docling, Word.
    QUALITE_DICTIONNAIRE_MODES = {'claude': False, 'ocr': False}
    # Continuité des numéros : colonnes par modèle de sortie et saut maximal (les originaux
    # ont de vrais trous : 6A23111PE133 p. 6 0303W → 0308R, p. 12 0652B → 0662B).
    QUALITE_CONTINUITE = {
        'REPARTITEUR': ('TENANT', 'JAR', 'ABOUTISSANT'),
        'REPARTITEUR 2': ('TENANT', 'ABOUTISSANT'),
        'Bornier standard': ('BORNE', 'JARRETIERES'),
    }
    QUALITE_SAUT_MAX = 10
    # Colonnes qui ne sont jamais entièrement vides sur une page, par modèle de sortie
    # (COULEUR de 223111PE012 p. 1 est vide à juste titre).
    QUALITE_COLONNES_OBLIGATOIRES = {
        'REPARTITEUR': ('TENANT', 'JAR', 'ABOUTISSANT'),
        # TENANT et ABOUTISSANT vides sur des lignes « NON CABLEE » (vérité 223111PE011 :
        # 158 et 162 remplis sur 166) : pas obligatoires.
        'REPARTITEUR 2': ('FIL',),
        'Bornier standard': ('BORNE', 'SIGNAL'),
    }
    # Format des cellules, par modèle de sortie (espaces ramenés à un) ; colonne absente =
    # texte libre (SIGNAL, FIL, COULEUR). Motifs tirés des vérités des 3 extraits.
    QUALITE_FORMATS = {
        'REPARTITEUR': {
            'TENANT': r'[A-Z0-9/]+ \d{1,3}[A-Z]?',
            'JAR': r'\d{4}[A-Z]|\d{5}',
            'ABOUTISSANT': r'[A-Z0-9/]+ \d{1,3}[A-Z]?',
        },
        'REPARTITEUR 2': {
            'TENANT': r'[A-Z]{2} [A-Z0-9/\-]+ \d{2}( [A-Z0-9])?',
            'ABOUTISSANT': r'[A-Z]{2} [A-Z0-9/\-]+ \d{2}( [A-Z0-9])?',
        },
        'Bornier standard': {
            # Lettre de tête A à Z sans O ni I (repérage des borniers) : « O1 », « I2 » sont
            # très probablement 01 et 12.
            'BORNE': r'[A-HJ-NP-Z]?\d{1,2}[A-Z]?',
            'JARRETIERES': r'\d{4,5}[A-Z]?( \d{4,5}[A-Z]?)*',
        },
    }
    # Garde-fou pour un document jamais vu : plus de cette part des cellules non vides
    # d'une colonne hors du motif (ou des pages avec une colonne obligatoire vide), c'est
    # le motif qui ne convient pas : une seule ligne de synthèse, contrôle coupé.
    QUALITE_GARDE_FOU = 0.20
    # Confusions de lecture du lexique de référence : une substitution, jamais un chiffre
    # contre un autre (« RA 17 » / « RA 11 » sont deux numéros voisins normaux).
    QUALITE_CONFUSIONS_LEXIQUE = (('O', 'C'), ('O', '0'), ('O', 'D'), ('O', 'Q'), ('I', '1'),
                                  ('I', 'L'), ('S', '5'), ('B', '8'), ('Z', '2'), ('G', '6'),
                                  ('E', 'F'))
    # Fond d'une cellule signalée par le contrôle qualité : cyan clair. Le jaune pâle d'abord
    # choisi (FFF2CC) se confondait avec le jaune « confiance OCR basse » (FFFF99).
    COULEUR_QUALITE = "A9E2E8"
    # Jaune « confiance OCR basse » posé par ocr_processor._fill_worksheet (valeur écrite
    # dans ce fichier-là) : repris ici pour la légende de l'Excel.
    COULEUR_CONFIANCE_BASSE = "FFFF99"
    # En-tête orange : tableau source très flou (ocr_processor._fill_worksheet).
    COULEUR_ENTETE_FLOU = "FFA500"

    # ========================================
    # 📏 NOMBRE DE LIGNES VISIBLES (compte_lignes.py, étape 9, mesure D0)
    # ========================================
    # Lignes de texte visibles dans la zone du tableau comparées aux lignes lues, sans lire
    # les mots (seul filet contre une ligne perdue sur un scan dégradé).
    # False = coupé ; 'ombre' = le compteur tourne pendant la lecture et écrit au journal et
    # dans un fichier de mesure, rien dans l'Excel ni dans l'écran de validation ; True =
    # alertes de page (A VERIFIER, ordre de validation). Contre-épreuve D1 : 10,5 % de
    # fausses alertes (bornes de la zone) → ombre en v1.8, jugé à l'étape 10.
    CONTROLE_LIGNES = 'ombre'
    # Pages vectorielles : le compte vient de la couche texte, il est exact (0 fausse alerte
    # sur les 85 pages vues) → alertes actives ; tout écart est une alerte, sans garde-fou.
    CONTROLE_LIGNES_VECTORIEL = True
    # Fichiers de mesure du mode ombre (un par document), hors des dossiers de l'utilisateur.
    LIGNES_OMBRE_DOSSIER = _DOSSIER_UTILISATEUR / 'ombre_lignes'
    # Pas de ligne cherché entre ces bornes, en pixels d'une page rendue à 300 DPI : les
    # listings mesurés sont à 6 lignes par pouce (46,7 à 50 px) ; plus large, la recherche
    # prend la moitié ou le double du pas sur une page de quelques lignes.
    LIGNES_PAS_MIN = 33
    LIGNES_PAS_MAX = 70
    # Une case de la grille est une ligne si elle contient une tache d'au moins cette part de
    # la hauteur d'un caractère (médiane mesurée sur la page) et de largeur au moins
    # LIGNES_TACHE_LARGEUR_MIN de cette hauteur : poussière, reste de trait, rayure écartés.
    LIGNES_TACHE_HAUTEUR_MIN = 0.7
    LIGNES_TACHE_LARGEUR_MIN = 0.15
    # Une tache plus haute que N pas de ligne est un reste de trait vertical, pas un caractère.
    LIGNES_TACHE_HAUTEUR_MAX_PAS = 1.5
    # Régularité minimale du profil d'encre (0 à 1) ; en dessous : comptage impossible.
    LIGNES_REGULARITE_MIN = 0.25
    # Trait vertical du cadre : sur au moins cette part de la hauteur de la page ; un trait à
    # moins de LIGNES_MARGE_BORD (part de la largeur) du bord de l'image est le bord du scan.
    LIGNES_PART_TRAIT_VERTICAL = 0.25
    LIGNES_MARGE_BORD = 0.015
    # Trait horizontal : bande d'au plus N pixels (300 DPI) dont l'encre, blancs entre tirets
    # comblés, couvre au moins cette part de la largeur du tableau ; plein si l'encre brute
    # en couvre au moins LIGNES_COUVERTURE_PLEIN.
    LIGNES_EPAISSEUR_TRAIT = 12
    # Rangées réunies pour mesurer un trait scanné, qui ondule sur plusieurs rangées.
    LIGNES_FENETRE_TRAIT = 6
    LIGNES_COUVERTURE_TRAIT = 0.6
    LIGNES_COUVERTURE_PLEIN = 0.85
    # Le trait sous l'en-tête est dans cette part haute du cadre ; plus bas, c'est le pied.
    LIGNES_PART_ENTETE_MAX = 0.25
    # Écart au-delà duquel ce n'est plus une alerte mais « comptage incertain » (au-delà de
    # 2 lignes, c'est presque toujours la zone qui est fausse, contre-épreuve D1).
    LIGNES_ECART_ALERTE_MAX = 2
    # Blanc maximal (pixels à 300 DPI) entre deux tirets d'un trait en pointillés
    # (6A23111PE133 : jusqu'à 18 px).
    LIGNES_BLANC_POINTILLES = 24
    # Redressement du scan : angle cherché à ± N degrés, par pas de N degrés.
    LIGNES_INCLINAISON_MAX = 1.5
    LIGNES_INCLINAISON_PAS = 0.05

    # ========================================
    # 📏 MESURE DE PRÉCISION (outil de QA sur jeu de test connu)
    # ========================================
    # Compare une sortie .xlsx à une référence organisée à l'avance (PDF
    # vectoriel ou Excel de vérité terrain). Seuils séparés de VERIF_* :
    # cet outil a besoin d'une vérité terrain et sert au suivi de version en
    # version, contrairement à verificateur.py qui vérifie une conversion en
    # direct sans référence préparée.

    # Similarité minimale (0-1) entre deux pages pour les apparier par contenu.
    MESURE_SEUIL_PAGE = 0.30

    # Au-delà de cette similarité de lignes identiques, deux pages sont
    # appariées sans chercher les lignes proches (économie de calcul).
    MESURE_SEUIL_PAGE_EXACTE = 0.9

    # Nombre de pages converties, les plus proches en mots, sur lesquelles
    # chaque page de référence est comparée finement (coût quadratique sinon).
    MESURE_CANDIDATS_PAGE = 3

    # Pénalité par insertion/suppression dans l'alignement Needleman-Wunsch
    # (négative : plus elle est proche de 0, plus les trous sont tolérés).
    MESURE_PENALITE_GAP = -0.35

    # Bonus retranché à la similarité de deux lignes appariées (calibré pour
    # que deux lignes proches mais imparfaites restent préférées à un trou).
    MESURE_BONUS_APPARIEMENT = 0.5

    # Au-delà de N*M paires lignes_ref × lignes_conv, l'alignement optimal
    # Needleman-Wunsch est trop coûteux : repli sur un appariement 1-pour-1.
    MESURE_NW_MAX_PAIRES = 250000

    # Paires de caractères facilement confondus par l'OCR (classification
    # "Confusion de caractère" : un seul caractère substitué par sa paire).
    # Reprise telle quelle de outils_reference/comparateur.py (ITIN/ITTN = T/I).
    MESURE_CONFUSIONS_OCR = (
        "1I", "1L", "IL", "0O", "0D", "DO", "5S", "8B", "2Z", "6G",
        "PF", " _", "'\"", "R_", "MN", "EF", "CG", "HK", "UV", "VY",
        "17", "RK", "TI",
    )

    # Fichier d'historique des mesures (une ligne par exécution de
    # mesurer_precision.py), à la racine du projet.
    MESURE_CSV_PATH = "mesures.csv"

    # Libellés de pied dont la valeur peut être suivie d'un complément en texte
    # libre (« TYPE : 2P.279 8/10 » → TYPE 2P.279, complément 8/10), comparé
    # comme un champ à part au « Complement » d'une vérité terrain.
    MESURE_LIBELLES_A_COMPLEMENT = ("TYPE",)
    # Début d'une ligne de section du tableau (« NOM DU CABLE : WPHR/A105 ») :
    # comparée comme une section, texte entier, pas comme une ligne de données.
    MESURE_MOT_SECTION = "NOM DU CABLE"

    # ========================================
    # 📐 PARAMÈTRES FORMATAGE EXCEL
    # ========================================

    # Hauteur de ligne en points pour le reformatage (12.6 pt ≈ A4 portrait 59 lignes)
    FORMAT_ROW_HEIGHT = 12.6

    # Largeur par défaut de toutes les colonnes (sauf SIGNAL)
    FORMAT_COL_WIDTH_DEFAULT = 19

    # Largeur de la colonne SIGNAL
    FORMAT_COL_WIDTH_SIGNAL = 33

    # Marges de page en centimètres (converties en pouces avant envoi à openpyxl)
    FORMAT_MARGIN_TOP = 0.9
    FORMAT_MARGIN_BOTTOM = 0.9
    FORMAT_MARGIN_LEFT = 1.75
    FORMAT_MARGIN_RIGHT = 1.75
    FORMAT_MARGIN_HEADER = 0.0
    FORMAT_MARGIN_FOOTER = 0.0

    # ========================================
    # 🔬 OCR PAR COLONNE — re-OCR ciblé sur les cellules douteuses
    # ========================================

    # Activer le re-OCR cellule par cellule pour les confiances < OCR_REOCR_THRESHOLD.
    # Chaque cellule douteuse est recadrée et re-soumise à Tesseract avec :
    #   - PSM 7 (ligne unique)
    #   - whitelist de caractères adaptée à la colonne (BORNE, COULEUR, SIGNAL…)
    # Impact : +10 à +20 % sur les colonnes à caractères ambigus (A↔4, l↔1).
    # Coût : +10 à +30 % de temps de traitement (une requête Tesseract par cellule douteuse).
    OCR_PER_COLUMN = True

    # Seuil de confiance (0-100) en dessous duquel une cellule est re-OCR-isée.
    OCR_REOCR_THRESHOLD = 60

    # ========================================
    # 🔲 OCR GRILLE — découpe cellule par cellule
    # ========================================

    # Activer la détection de la grille du tableau et l'OCR cellule par cellule.
    # OpenCV localise les traits H/V, les supprime avant Tesseract, puis découpe
    # chaque cellule individuellement avec PSM 7.
    # Produit une nette amélioration sur les tableaux à bordures nettes.
    # Désactiver pour les images sans traits visibles (tableaux implicites).
    OCR_CELL_BY_CELL = True

    # Désactiver les dictionnaires linguistiques Tesseract pour les colonnes
    # techniques (BORNE, JAR, ABOUTISSANT, TENANT, COULEUR).
    # Évite que Tesseract « corrige » les codes vers des mots du dictionnaire.
    # Ex : "0113R" ne devient pas "OI13R".
    OCR_DISABLE_DICT = True

    # Langue Tesseract pour les colonnes de codes techniques.
    # "eng" est plus fiable que "fra" sur des codes alphanumériques courts.
    # La colonne SIGNAL garde la langue principale (OCR_LANGUAGE) car elle
    # contient du texte français naturel.
    OCR_LANGUAGE_TECHNICAL = "eng"

    # Activer le vote multi-passes par cellule.
    # Lance 3 lectures (image originale, ×2, seuillage adaptatif) et garde
    # le meilleur résultat selon la confiance et le patron de colonne.
    # Coût : ×2 à ×3 le temps de traitement des cellules douteuses.
    OCR_CELL_VOTE = True

    # ========================================
    # 📏 ESPACEMENT VERTICAL — fidélité à l'image source
    # ========================================

    # Reproduire dans Excel les espacements verticaux visibles dans l'image source.
    # Quand True, un écart entre deux blocs de données ≥ OCR_SPACING_THRESHOLD × hauteur
    # médiane de ligne génère des lignes vides dans le classeur Excel, fidèles à l'original.
    OCR_PRESERVE_SPACING = True

    # Facteur déclencheur : gap > N × hauteur_médiane_ligne → ligne vide insérée.
    # 1.6 = seuil équilibré (ignore le léger interligne, capture les vrais blancs).
    # Augmenter (2.0+) pour ne capturer que les grands espacements.
    # Diminuer (1.2) pour reproduire même les petits écarts.
    OCR_SPACING_THRESHOLD = 1.6

    # Reproduire l'espacement horizontal entre les sous-blocs d'une même colonne.
    # Quand True, si l'OCR détecte plusieurs mots séparés par un grand espace visuel
    # (ex: TENANT = TGV   TE203A   C12), ces espaces proportionnels sont conservés
    # dans la cellule Excel plutôt que normalisés en un seul espace.
    OCR_PRESERVE_INTRA_CELL_SPACING = True

    # ========================================
    # 📋 JOURNAL DEBUG OCR
    # ========================================

    # Activer la journalisation détaillée de ce que Tesseract détecte.
    # Crée « ocr_debug.log » dans le répertoire courant.
    # Contient : texte brut détecté, positions, confiances, frontières colonnes.
    # Désactivez en production pour éviter un fichier log volumineux.
    OCR_DEBUG_LOG = True

    # Chemin du fichier log OCR (None = répertoire courant)
    OCR_DEBUG_LOG_PATH = None

    # ========================================
    # 🤖 MODE OCR — choix du moteur d'extraction
    # ========================================

    # Moteur OCR à utiliser :
    #   "tesseract" — Tesseract OCR local (défaut, nécessite Tesseract installé)
    #   "claude"    — Claude Vision API (Anthropic) — précision maximale, ~0.001€/image
    #   "docling"   — Docling IBM — IA locale, sans coût par appel (GPU recommandé)
    #   "ollama"    — Ollama Vision local (qwen2.5vl:7b) — gratuit, hors ligne
    #   "hybrid"    — Structure Ollama + valeurs Claude : meilleure fidélité,
    #                 coûte ~0.001€/image (appel Claude) + Ollama local gratuit
    OCR_MODE = "tesseract"

    # Clé API Anthropic (requis uniquement si OCR_MODE == "claude")
    # Obtenir sur : https://console.anthropic.com
    CLAUDE_API_KEY = ""

    # Modèle Claude pour l'OCR Vision (modes "claude" et "hybrid"). Il doit
    # figurer dans CLAUDE_CAPACITES_MODELES ci-dessous, sinon la conversion est
    # refusée avant tout appel.
    #   "claude-haiku-4-5-20251001" — rapide, économique
    #   "claude-sonnet-5"           — précis, coût intermédiaire
    #   "claude-opus-5"             — 5 $ / 25 $ par million de tokens
    #   "claude-opus-5-5"           — recommandé (défaut), 4 $ / 20 $ ; réflexion toujours active
    #   "claude-fable-5-1"          — le plus capable ; réflexion toujours active
    CLAUDE_OCR_MODEL = "claude-opus-5-5"

    # Ce que chaque modèle accepte :
    #   "thinking" : True  → le champ thinking est envoyé selon CLAUDE_THINKING ;
    #                False → champ omis (Haiku n'a pas de réflexion réglable ;
    #                        Opus 5.5 et Fable 5.1 réfléchissent toujours et
    #                        renvoient une erreur 400 si on tente de la désactiver)
    #   "effort"   : True  → output_config.effort envoyé (Haiku 4.5 le refuse).
    CLAUDE_CAPACITES_MODELES = {
        "claude-haiku-4-5-20251001": {"thinking": False, "effort": False},
        "claude-sonnet-5":           {"thinking": True,  "effort": True},
        "claude-opus-5":             {"thinking": True,  "effort": True},
        "claude-opus-5-5":           {"thinking": False, "effort": True},
        "claude-fable-5-1":          {"thinking": False, "effort": True},
    }

    # Réflexion avant la réponse, pour les modèles où elle se règle ("thinking":
    # True) : "disabled" (réponse directe) ou "adaptive". Désactivée, l'effort
    # ne peut pas dépasser "high" : "xhigh" et "max" sont refusés avant l'appel
    # (l'API répondrait par une erreur 400). Ignoré par Opus 5.5 et Fable 5.1.
    CLAUDE_THINKING = "disabled"

    # Effort : "low" | "medium" | "high" | "xhigh" | "max".
    CLAUDE_EFFORT = "medium"

    # Limite de tokens de la réponse (la réflexion, si active, compte dedans).
    CLAUDE_MAX_TOKENS = 16000

    # Limite portée à cette valeur quand CLAUDE_EFFORT vaut "xhigh" ou "max"
    # (recommandation Anthropic : ≥ 64000) ; l'appel passe alors en streaming,
    # que le SDK exige au-delà de ~21 000 tokens. Une réponse coupée par la
    # limite met toujours la page en erreur, jamais acceptée en silence.
    CLAUDE_MAX_TOKENS_EFFORT_ELEVE = 64000

    # Prix en dollars par million de tokens (entrée, sortie), pour estimer le coût
    # d'une campagne de mesure (campagne_mesure.py). Les tokens de réflexion sont
    # facturés comme des tokens de sortie.
    CLAUDE_PRIX_MODELES = {
        "claude-haiku-4-5-20251001": (1.0, 5.0),
        "claude-sonnet-5":           (2.0, 10.0),
        "claude-opus-5":             (5.0, 25.0),
        "claude-opus-5-5":           (4.0, 20.0),
        "claude-fable-5-1":          (10.0, 50.0),
    }

    # Plafond de dépense d'une campagne de mesure : la campagne s'arrête avant
    # un passage si le coût cumulé l'a atteint.
    CAMPAGNE_BUDGET_MAX_USD = 10.0

    # Grand côté maximal (px) des images envoyées à Claude : au-delà, l'image
    # est réduite avant l'envoi (limite de résolution des modèles actuels).
    CLAUDE_IMAGE_MAX_PX = 2576

    # ========================================
    # 🤖 MODE OCR — Agent Managed Agents
    # ========================================

    # ID de session d'un agent Managed Agents Anthropic déjà créé.
    # Requis uniquement si OCR_MODE == "agent".
    # Format : "sesn_XXXXXXXXXXXXXXXXXXXX"
    # Créer une session : client.beta.sessions.create(agent_id="...")
    CLAUDE_AGENT_SESSION_ID = ""

    # ========================================
    # 🦙 MODE OCR — Ollama Vision local
    # ========================================

    # URL de l'API Ollama — endpoint OpenAI-compatible (requis pour qwen2.5vl)
    OLLAMA_URL = "http://localhost:11434/v1/chat/completions"

    # Modèle vision à utiliser.
    # Recommandations :
    #   "qwen2.5vl:7b"  — meilleure précision, ~8 Go RAM
    #   "qwen2.5vl:3b"  — PC limité (~4 Go RAM)
    # Télécharger : ollama pull qwen2.5vl:7b
    OLLAMA_MODEL = "qwen2.5vl:3b"

    # Délai d'attente maximum par image (secondes).
    # Augmenter si le modèle est lent sur votre machine.
    # Premier démarrage à froid : ~250 s pour charger 6 Go en RAM — mettre 360 minimum.
    OLLAMA_TIMEOUT = 360

    # Activer le mode débogage Ollama (False en production).
    # Quand True, sauvegarde pour chaque image dans ollama_debug/ :
    #   <image>_raw.txt       — réponse brute Ollama
    #   <image>_lignes.txt    — lignes finales après validation
    #   <image>_decisions.json — structure détectée + rapport de validation
    OLLAMA_DEBUG = False

    # ========================================
    # 🤖 OPTIONS TATR (Microsoft Table Transformer)
    # ========================================

    # Mettre à True pour activer la détection de colonnes par IA.
    # Nécessite : pip install transformers torch
    # Le modèle (~115 Mo) est téléchargé automatiquement au premier lancement.
    # Incompatible avec le .exe PyInstaller — utiliser uniquement en mode Python.
    USE_TATR = False

    # Nom du modèle HuggingFace (ne pas modifier sauf mise à jour officielle)
    TATR_MODEL_NAME = "microsoft/table-transformer-structure-recognition"

    # Seuil de confiance minimum pour retenir une colonne détectée (0.0 – 1.0)
    TATR_CONFIDENCE = 0.5

    # ========================================
    # ✋ MODE VALIDATION INTERACTIVE
    # ========================================

    # Activer la validation manuelle page par page.
    # Quand True, un dialogue s'affiche après chaque page extraite avec succès :
    # l'utilisateur peut approuver ou signaler un problème avant de continuer.
    # Les commentaires sont enregistrés dans feedback_log.jsonl dans le dossier de sortie.
    VALIDATION_INTERACTIVE = False

    # ========================================
    # 📊 STATISTIQUES
    # ========================================

    # Générer un rapport JSON à la fin
    GENERATE_REPORT = True

    # Nom du fichier rapport
    REPORT_FILENAME = "extraction_report.json"

    # ── Paramètres CAD — pipeline TIF→DXF ────────────────────────────────────
    CAD_L_MAX_TIRET_MM: float = 40.0   # longueur max d'un fragment candidat tiret (mm)
    CAD_L_MIN_TIRET_MM: float = 1.0    # longueur min (en dessous = bruit, ignoré)
    CAD_CV_SEUIL: float = 0.20         # seuil CV σ/μ pour valider pattern périodique
    CAD_D_GAP_FUSION_MM: float = 2.0   # lacune max pour fusionner segments colinéaires
    CAD_EPS_GAP_MM: float = 0.5        # lacune max fusion micro-segments squelette (mm)
    CAD_TEXT_THRESH_PX: int = 60      # taille max bbox composante texte (px) à ~200 DPI
    CAD_MAX_SAMPLES: int = 180        # nb points rééchantillonnés pour splprep
    CAD_PRESMOOTH_SIGMA_PX: float = 2.5   # sigma filtre gaussien avant détection de coin
    CAD_MIN_CORNER_SEP_PX: float = 15.0   # distance min entre 2 coins consécutifs (mm)
    CAD_PDF_RASTER_DPI: float = 150.0    # résolution de rendu PDF raster (DPI cible, réduit si la page dépasse CAD_PDF_MAX_MPX)
    CAD_PDF_MAX_MPX: float = 25.0        # plafond en mégapixels par page — DPI auto-réduit au-delà (pages panoramiques)

    # ========================================
    # 🔧 MÉTHODES UTILITAIRES
    # ========================================

    @classmethod
    def get_output_folder(cls) -> Path:
        """
        Retourne le chemin complet du dossier de destination.

        Returns:
            Path: Chemin du dossier d'images
        """
        if cls.OUTPUT_BASE_PATH is None:
            base = Path.cwd()
        else:
            base = Path(cls.OUTPUT_BASE_PATH)

        return base / cls.IMAGES_FOLDER_NAME

    @classmethod
    def get_word_file_path(cls) -> Path:
        """
        Retourne le chemin complet du fichier Word.

        Returns:
            Path: Chemin du fichier Word
        """
        word_path = Path(cls.WORD_FILE)

        # Si c'est un chemin relatif, le résoudre depuis le répertoire courant
        if not word_path.is_absolute():
            word_path = Path.cwd() / word_path

        return word_path

    @classmethod
    def validate(cls) -> bool:
        """
        Valide la configuration.

        Returns:
            bool: True si la configuration est valide
        """
        # Vérifier que le format d'image contient {index} ou {index:...}
        # Les deux formes sont valides en Python : bornier_{index} et scan_{index:03d}
        import re as _re
        if cls.IMAGE_NAME_FORMAT and not _re.search(r'\{index', cls.IMAGE_NAME_FORMAT):
            raise ValueError("IMAGE_NAME_FORMAT doit contenir {index}")

        # Vérifier les formats autorisés
        if cls.ALLOWED_FORMATS is not None:
            if not isinstance(cls.ALLOWED_FORMATS, list):
                raise ValueError("ALLOWED_FORMATS doit être une liste ou None")

        return True

    @classmethod
    def display_config(cls, word_file: Path | None = None) -> None:
        """Affiche la configuration actuelle (utile pour le débogage)."""
        if word_file is None:
            word_file = cls.get_word_file_path()
        print("=" * 50)
        print("📋 CONFIGURATION ACTUELLE")
        print("=" * 50)
        print(f"Fichier Word: {word_file}")
        print(f"Dossier sortie: {cls.get_output_folder()}")
        print(f"Format images: {cls.IMAGE_NAME_FORMAT}")
        print(f"Continuer sur erreur: {cls.CONTINUE_ON_ERROR}")
        print(f"Activer OCR: {cls.ENABLE_OCR}")
        print(f"Chemin Tesseract: {cls.TESSERACT_PATH}")
        print(f"Exporter Excel: {cls.EXPORT_EXCEL}")
        print(f"Générer rapport: {cls.GENERATE_REPORT}")
        print("=" * 50)


# ========================================
# 🚀 PROFILS DE CONFIGURATION
# ========================================

class ConfigDev(Config):
    """Configuration pour le développement (avec logs détaillés)."""
    LOG_LEVEL = "DEBUG"
    VERBOSE = True
    GENERATE_REPORT = True


class ConfigProd(Config):
    """Configuration pour la production (minimal)."""
    LOG_LEVEL = "INFO"
    VERBOSE = False
    CONTINUE_ON_ERROR = True


# Utilisation:
# from config import ConfigDev, ConfigProd
# config = ConfigDev()  # ou ConfigProd()
