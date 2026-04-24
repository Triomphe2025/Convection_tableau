#!/usr/bin/env python3
"""
Point d'entrée simple pour extraire les images.

Exécution:
    python run.py
"""

import sys
import logging
from pathlib import Path

# Importer la configuration et le pipeline
from config import Config, ConfigDev, ConfigProd
from recuperer_image import ImageExtractionPipeline


def setup_logging(log_level: str) -> None:
    """Configure le système de logging."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level)


def get_word_file_path() -> Path:
    """Demande à l'utilisateur le chemin du fichier Word à traiter, ou utilise la config."""
    if len(sys.argv) > 1 and sys.argv[1].strip():
        user_input = sys.argv[1].strip().strip('"').strip("'")
    else:
        user_input = str(Config.get_word_file_path())

    word_file = Path(user_input)
    if not word_file.is_absolute():
        word_file = Path.cwd() / word_file

    if word_file.exists():
        return word_file

    if word_file.suffix.lower() != ".docx":
        alternate = word_file.with_suffix(".docx")
        if alternate.exists():
            return alternate

    # Si pas trouvé, demander à l'utilisateur
    while not user_input:
        user_input = input("Entrez le chemin du document Word (.docx) : ").strip().strip('"').strip("'")
        if not user_input:
            print("Veuillez indiquer un chemin de fichier valide.")
        else:
            word_file = Path(user_input)
            if not word_file.is_absolute():
                word_file = Path.cwd() / word_file
            if word_file.exists():
                return word_file

    return word_file


def main() -> int:
    """
    Point d'entrée principal.
    
    Returns:
        int: Code de sortie (0 = succès, 1 = erreur)
    """
    try:
        # Afficher la bannière
        print("\n" + "=" * 60)
        print("🖼️  EXTRACTEUR D'IMAGES DEPUIS WORD")
        print("=" * 60 + "\n")
        
        # Demander le fichier Word à traiter
        word_file = get_word_file_path()
        
        # Valider la configuration globale
        Config.validate()
        
        # Afficher les paramètres
        Config.display_config(word_file=word_file)
        print()
        
        # Vérifications avant traitement
        if not word_file.exists():
            print(f"❌ Erreur: Le fichier Word n'existe pas")
            print(f"   Attendu: {word_file}")
            return 1
        
        print(f"✅ Fichier Word trouvé: {word_file.name}")
        print()
        
        # Créer et exécuter le pipeline
        print("🚀 Démarrage du traitement...\n")
        
        pipeline = ImageExtractionPipeline(
            word_path=str(word_file),
            output_folder=Config.IMAGES_FOLDER_NAME,
            enable_ocr=Config.ENABLE_OCR,
            tesseract_path=Config.TESSERACT_PATH,
            export_excel=Config.EXPORT_EXCEL
        )
        
        results = pipeline.run()
        
        # Afficher les résultats
        print()
        print("=" * 60)
        print("✅ TRAITEMENT RÉUSSI")
        print("=" * 60)
        print(f"📊 Résultats:")
        print(f"   • Images trouvées: {results['total']}")
        print(f"   • Images enregistrées: {results['saved']}")
        print(f"   • Erreurs: {results['errors']}")
        print(f"   • Localisation: {results['output_path']}")
        
        # Résultats OCR
        if results.get('ocr_enabled', False):
            ocr_results = results.get('ocr_results', [])
            successful_ocr = sum(1 for r in ocr_results if r.get('success', False))
            print(f"   • Documents OCR créés: {successful_ocr}/{len(ocr_results)}")
            if successful_ocr > 0:
                print(f"   • Tables OCR dans: {results['output_path']}/ocr_tables")
            if results.get('export_excel', False):
                print(f"   • Fichiers Excel créés dans: {results['output_path']}/ocr_tables")
        
        print("=" * 60 + "\n")
        
        # Vérifier s'il y a eu des erreurs
        if results['errors'] > 0:
            print(f"⚠️  Attention: {results['errors']} image(s) n'a pas pu être traitée(s)")
            print("   Consultez les messages ci-dessus pour plus de détails.\n")
            return 1
        
        if results['saved'] > 0:
            print(f"💾 Vos images sont prêtes dans: {results['output_path']}\n")
            if results.get('ocr_enabled', False) and successful_ocr > 0:
                print(f"📝 Vos tableaux OCR sont dans: {results['output_path']}/ocr_tables\n")
            return 0
        else:
            print("⚠️  Aucune image n'a été trouvée dans le document.\n")
            return 1
    
    except FileNotFoundError as e:
        print(f"❌ Fichier non trouvé: {e}\n")
        return 1
    
    except ValueError as e:
        print(f"❌ Erreur de configuration: {e}\n")
        return 1
    
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}\n")
        return 1


if __name__ == "__main__":
    # Configurer le logging
    setup_logging(Config.LOG_LEVEL)
    
    # Exécuter
    exit_code = main()
    sys.exit(exit_code)
