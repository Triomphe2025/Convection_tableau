"""
Script d'extraction d'images depuis un fichier Word.

Ce script récupère toutes les images contenues dans un document Word
et les enregistre dans un dossier organisé avec un nommage automatique.

Auteur: Script automatisé
Date: 2026
"""

import logging
import os
import zipfile
from pathlib import Path
from typing import List, Tuple, Dict
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from io import BytesIO


# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ImageExtractor:
    """
    Classe responsable de l'extraction des images d'un document Word.
    
    Un document Word (.docx) est en réalité un fichier ZIP. Les images
    sont stockées dans le dossier 'word/media/' avec des relations
    définies dans les fichiers XML.
    
    Attributes:
        word_path (Path): Chemin vers le fichier Word
    """
    
    def __init__(self, word_path: str) -> None:
        """
        Initialise l'extracteur d'images.
        
        Args:
            word_path: Chemin vers le fichier Word à traiter
            
        Raises:
            FileNotFoundError: Si le fichier Word n'existe pas
            ValueError: Si le fichier n'est pas un .docx
        """
        self.word_path = Path(word_path)
        self._validate_file()
    
    def _validate_file(self) -> None:
        """Valide que le fichier existe et est un document Word."""
        if not self.word_path.exists():
            raise FileNotFoundError(f"Le fichier '{self.word_path}' n'existe pas")
        
        if self.word_path.suffix.lower() != '.docx':
            raise ValueError(f"Le fichier doit être au format .docx, trouvé: {self.word_path.suffix}")
        
        logger.info(f"✓ Fichier validé: {self.word_path.name}")
    
    def extract_images(self) -> List[Tuple[bytes, str]]:
        """
        Extrait toutes les images du document Word.
        
        La méthode:
        1. Ouvre le .docx comme archive ZIP
        2. Accède au dossier 'word/media/'
        3. Extrait chaque image avec son extension
        
        Returns:
            Liste de tuples contenant:
                - bytes: Données de l'image
                - str: Extension du fichier (jpg, png, etc.)
        """
        logger.info("🔍 Extraction des images en cours...")
        
        images = []
        
        try:
            # Un fichier .docx est un archive ZIP
            with zipfile.ZipFile(self.word_path, 'r') as docx_zip:
                # Lister tous les fichiers dans l'archive
                file_list = docx_zip.namelist()
                
                # Chercher les images (généralement dans word/media/)
                for file_name in file_list:
                    if file_name.startswith('word/media/'):
                        try:
                            # Lire le fichier image
                            image_bytes = docx_zip.read(file_name)
                            
                            # Extraire l'extension
                            extension = Path(file_name).suffix.lstrip('.')
                            
                            if extension and image_bytes:
                                images.append((image_bytes, extension))
                                logger.debug(f"  - Image trouvée: {file_name}")
                        
                        except Exception as e:
                            logger.warning(f"  ⚠ Erreur lors de la lecture de {file_name}: {e}")
                            continue
            
            logger.info(f"✓ {len(images)} image(s) extraite(s) avec succès")
            return images
        
        except zipfile.BadZipFile:
            logger.error("✗ Le fichier n'est pas un document Word valide")
            raise ValueError(f"Le fichier '{self.word_path}' n'est pas un .docx valide")
        except Exception as e:
            logger.error(f"✗ Erreur lors de l'extraction: {e}")
            raise


class ImageStorage:
    """
    Classe responsable du stockage des images extraites.
    
    Attributes:
        output_folder (Path): Chemin du dossier de destination
        folder_name (str): Nom du dossier à créer
    """
    
    def __init__(self, folder_name: str = "VD23111 PE 162") -> None:
        """
        Initialise le gestionnaire de stockage.
        
        Args:
            folder_name: Nom du dossier de destination
        """
        self.folder_name = folder_name
        self.output_folder = None
    
    def create_output_folder(self, base_path: str | None = None) -> Path:
        """
        Crée le dossier de destination s'il n'existe pas.
        
        Args:
            base_path: Chemin de base (par défaut: répertoire courant)
            
        Returns:
            Path: Chemin du dossier créé
        """
        if base_path is None:
            base_path = Path.cwd()
        else:
            base_path = Path(base_path)
        
        self.output_folder = base_path / self.folder_name
        
        try:
            self.output_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"✓ Dossier créé/existant: {self.output_folder}")
            return self.output_folder
        
        except Exception as e:
            logger.error(f"✗ Erreur lors de la création du dossier: {e}")
            raise
    
    def save_image(self, image_bytes: bytes, index: int, extension: str) -> Path:
        """
        Enregistre une image dans le dossier de destination.
        
        Args:
            image_bytes: Données binaires de l'image
            index: Numéro séquentiel de l'image (commence à 1)
            extension: Extension du fichier (jpg, png, etc.)
            
        Returns:
            Path: Chemin du fichier enregistré
            
        Raises:
            ValueError: Si le dossier de destination n'a pas été créé
        """
        if self.output_folder is None:
            raise ValueError("Le dossier de destination doit être créé d'abord")
        
        # Format du nom: bornier_1.jpg, bornier_2.png, etc.
        filename = f"bornier_{index}.{extension.lower()}"
        file_path = self.output_folder / filename
        
        try:
            with open(file_path, 'wb') as f:
                f.write(image_bytes)
            
            logger.info(f"✓ Image enregistrée: {filename}")
            return file_path
        
        except Exception as e:
            logger.error(f"✗ Erreur lors de l'enregistrement de {filename}: {e}")
            raise


class ImageExtractionPipeline:
    """
    Classe orchestrant l'ensemble du processus d'extraction et de stockage.
    """
    
    def __init__(self, word_path: str, output_folder: str = "VD23111 PE 162",
                 enable_ocr: bool = False, tesseract_path: str = None,
                 export_excel: bool = False) -> None:
        """
        Initialise le pipeline d'extraction.
        
        Args:
            word_path: Chemin vers le fichier Word
            output_folder: Nom du dossier de destination
            enable_ocr: Activer le traitement OCR des images extraites
            tesseract_path: Chemin vers Tesseract (requis si OCR activé)
            export_excel: Générer également un fichier Excel pour chaque image
        """
        self.extractor = ImageExtractor(word_path)
        self.storage = ImageStorage(output_folder)
        self.enable_ocr = enable_ocr
        self.tesseract_path = tesseract_path
        self.export_excel = export_excel
        
        if self.enable_ocr:
            try:
                from ocr_processor import BatchOCRProcessor
                self.ocr_processor = BatchOCRProcessor(tesseract_path=tesseract_path)
                logger.info("✓ OCR activé pour le traitement des images")
            except ImportError as e:
                logger.error(f"✗ Impossible d'activer l'OCR: {e}")
                logger.error("Assurez-vous que les dépendances OCR sont installées")
                self.enable_ocr = False
    
    def run(self) -> dict:
        """
        Exécute le pipeline complet.
        
        Returns:
            dict: Dictionnaire contenant les statistiques du traitement
        """
        logger.info("=" * 50)
        logger.info("🚀 Début du traitement")
        if self.enable_ocr:
            logger.info("📝 Mode OCR activé")
        logger.info("=" * 50)
        
        try:
            # Créer le dossier de destination
            self.storage.create_output_folder()
            
            # Extraire les images
            images = self.extractor.extract_images()
            
            if not images:
                logger.warning("⚠ Aucune image trouvée dans le document")
                return {"total": 0, "saved": 0, "errors": 0, "ocr_results": []}
            
            # Sauvegarder les images
            saved_count = 0
            error_count = 0
            saved_paths = []
            
            for index, (image_bytes, extension) in enumerate(images, start=1):
                try:
                    saved_path = self.storage.save_image(image_bytes, index, extension)
                    saved_paths.append(saved_path)
                    saved_count += 1
                except Exception as e:
                    logger.error(f"✗ Erreur avec l'image {index}: {e}")
                    error_count += 1
            
            # Traitement OCR si activé
            ocr_results = []
            if self.enable_ocr and saved_paths:
                logger.info("🔄 Début du traitement OCR...")
                try:
                    # Créer un dossier pour les documents Word OCR
                    ocr_output_folder = self.storage.output_folder / "ocr_tables"
                    
                    # Traiter toutes les images avec OCR
                    ocr_results = self.ocr_processor.process_folder(
                        input_folder=self.storage.output_folder,
                        output_folder=ocr_output_folder,
                        save_excel=self.export_excel
                    )
                    
                    logger.info(f"✓ OCR terminé: {len(ocr_results)} documents créés")
                    
                except Exception as e:
                    logger.error(f"✗ Erreur lors du traitement OCR: {e}")
                    ocr_results = []
            
            # Résumé
            logger.info("=" * 50)
            logger.info(f"✅ Traitement terminé")
            logger.info(f"   - Images trouvées: {len(images)}")
            logger.info(f"   - Images enregistrées: {saved_count}")
            logger.info(f"   - Erreurs: {error_count}")
            logger.info(f"   - Localisation: {self.storage.output_folder}")
            if self.enable_ocr:
                successful_ocr = sum(1 for r in ocr_results if r.get('success', False))
                logger.info(f"   - Documents OCR créés: {successful_ocr}/{len(ocr_results)}")
            logger.info("=" * 50)
            
            return {
                "total": len(images),
                "saved": saved_count,
                "errors": error_count,
                "output_path": str(self.storage.output_folder),
                "saved_paths": [str(p) for p in saved_paths],
                "ocr_enabled": self.enable_ocr,
                "export_excel": self.export_excel,
                "ocr_results": ocr_results
            }
        
        except Exception as e:
            logger.error(f"✗ Erreur critique: {e}")
            raise


def main() -> None:
    """Point d'entrée du script."""
    try:
        # 📝 À CONFIGURER: Chemin vers votre fichier Word
        word_file = "document.docx"  # Modifier avec le chemin réel
        
        # Créer et exécuter le pipeline
        pipeline = ImageExtractionPipeline(word_file)
        results = pipeline.run()
        
    except FileNotFoundError as e:
        logger.error(f"Fichier non trouvé: {e}")
    except ValueError as e:
        logger.error(f"Erreur de validation: {e}")
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")


if __name__ == "__main__":
    main()
