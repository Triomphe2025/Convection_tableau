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
    # 📊 STATISTIQUES
    # ========================================
    
    # Générer un rapport JSON à la fin
    GENERATE_REPORT = True
    
    # Nom du fichier rapport
    REPORT_FILENAME = "extraction_report.json"
    
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
        # Vérifier que le format d'image est valide
        if cls.IMAGE_NAME_FORMAT and "{index}" not in cls.IMAGE_NAME_FORMAT:
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
