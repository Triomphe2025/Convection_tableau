"""
Script de diagnostic pour vérifier l'état du pipeline OCR.
"""

import os
from pathlib import Path
from config import Config

def diagnose():
    """Diagnostique l'état du pipeline."""
    
    print("\n" + "="*70)
    print("🔍 DIAGNOSTIC DU PIPELINE OCR")
    print("="*70)
    
    # 1. Vérifier le fichier Word
    print("\n1️⃣  FICHIER WORD SOURCE")
    word_path = Config.get_word_file_path()
    print(f"   Chemin configuré: {word_path}")
    print(f"   Existe: {'✓' if word_path.exists() else '✗'}")
    if word_path.exists():
        print(f"   Taille: {word_path.stat().st_size} bytes")
    
    # 2. Vérifier le dossier de sortie
    print("\n2️⃣  DOSSIER DE SORTIE")
    output_folder = Config.get_output_folder()
    print(f"   Chemin: {output_folder}")
    print(f"   Existe: {'✓' if output_folder.exists() else '✗'}")
    
    if output_folder.exists():
        images = list(output_folder.glob("bornier_*.jpg")) + list(output_folder.glob("bornier_*.png"))
        print(f"   Nombre d'images: {len(images)}")
        
        if len(images) > 0:
            print(f"   Premières images:")
            for img in sorted(images)[:5]:
                print(f"     - {img.name} ({img.stat().st_size} bytes)")
        
        # 3. Vérifier les dossiers OCR
        print("\n3️⃣  DOSSIERS OCR")
        ocr_folder = output_folder / "ocr_tables"
        print(f"   Chemin: {ocr_folder}")
        print(f"   Existe: {'✓' if ocr_folder.exists() else '✗'}")
        
        if ocr_folder.exists():
            word_docs = list(ocr_folder.glob("*.docx"))
            excel_docs = list(ocr_folder.glob("*.xlsx"))
            print(f"   Documents Word: {len(word_docs)}")
            print(f"   Documents Excel: {len(excel_docs)}")
            
            if word_docs:
                print(f"   Premiers documents Word:")
                for doc in sorted(word_docs)[:3]:
                    print(f"     - {doc.name}")
        else:
            print(f"   ⚠️  Dossier OCR n'existe pas - pas de documents créés")
    else:
        print(f"   ⚠️  Dossier de sortie n'existe pas!")
    
    # 4. Vérifier la configuration OCR
    print("\n4️⃣  CONFIGURATION OCR")
    print(f"   OCR activé: {Config.ENABLE_OCR}")
    print(f"   Chemin Tesseract: {Config.TESSERACT_PATH}")
    print(f"   Tesseract existe: {'✓' if Path(Config.TESSERACT_PATH).exists() else '✗'}")
    print(f"   Langue: {Config.OCR_LANGUAGE}")
    print(f"   Export Excel: {Config.EXPORT_EXCEL}")
    
    # 5. Vérifier le rapport
    print("\n5️⃣  RAPPORT D'EXTRACTION")
    report_path = output_folder / Config.REPORT_FILENAME
    if report_path.exists():
        print(f"   Rapport trouvé: {report_path.name}")
        import json
        try:
            with open(report_path) as f:
                report = json.load(f)
                print(f"   Contenu:")
                for key, value in report.items():
                    print(f"     - {key}: {value}")
        except Exception as e:
            print(f"   Erreur lecture rapport: {e}")
    else:
        print(f"   Aucun rapport trouvé")
    
    print("\n" + "="*70)
    print("✅ DIAGNOSTIC TERMINÉ")
    print("="*70 + "\n")

if __name__ == "__main__":
    diagnose()
