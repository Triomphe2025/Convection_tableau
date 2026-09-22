"""
Fichier de configuration pour le script d'extraction d'images.

Modifiez ce fichier pour personnaliser le comportement sans toucher au code principal.
"""

from pathlib import Path


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

    # Chemin vers Tesseract OCR (laisser None pour auto-détection)
    # Windows: r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # Linux/Mac: généralement dans le PATH
    TESSERACT_PATH = r"C:\Tesseract\TesseractOCR\tesseract.exe"

    # Langue pour l'OCR
    OCR_LANGUAGE = "fra"

    # Extensions d'images à traiter avec OCR
    OCR_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp"]

    # Exporter aussi en Excel
    EXPORT_EXCEL = True

    # ========================================
    # 📄 OPTIONS MISE EN PAGE EXCEL
    # ========================================

    # Nom de la station P.E.T. affiché dans le pied de page de chaque bornier.
    # Utilisé comme valeur de repli si l'OCR ne parvient pas à l'extraire.
    STATION_NAME = "EPEULE"

    # Nombre de lignes par page A4 (1 en-tête + données + rembourrage + 2 pied).
    # 59 lignes à 12,6 pt = exactement une page A4 portrait avec marges standard.
    PAGE_SIZE = 59

    # Nombre minimal de lignes de données pour conserver un bornier.
    # Les borniers avec moins de lignes (OCR raté) sont exclus du classeur.
    MIN_DATA_ROWS = 3

    # Nombre max de colonnes de template affectées automatiquement.
    # Au-delà, l'affectation automatique par frontières pixel devient peu
    # fiable — un mapping manuel est demandé à l'utilisateur (si un callback
    # on_column_mapping est fourni au Converter).
    MAX_AUTO_COLUMNS = 4

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
    VERIF_CONFUSIONS_OCR = ("0O", "1IL", "5S", "T7", "8B", "2Z")

    # Concordance minimale (cellules identiques ou bénignes / cellules
    # comparées) au-dessus de laquelle la conversion est jugée fidèle.
    VERIF_SEUIL_CONCORDANCE = 0.98

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

    # Modèle Claude pour l'OCR Vision :
    #   "claude-haiku-4-5-20251001"  — rapide, économique (recommandé)
    #   "claude-sonnet-4-6"          — plus précis, coût plus élevé
    CLAUDE_OCR_MODEL = "claude-haiku-4-5-20251001"

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
