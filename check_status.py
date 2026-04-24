#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

from config import Config

def diagnose():
    """Diagnostique l'état du pipeline."""
    
    print("\n" + "="*70)
    print("DIAGNOSTIC DU PIPELINE OCR")
    print("="*70)
    
    # 1. Verifier le fichier Word
    print("\n1. FICHIER WORD SOURCE")
    word_path = Config.get_word_file_path()
    print(f"   Chemin: {word_path}")
    print(f"   Existe: {'OUI' if word_path.exists() else 'NON'}")
    if word_path.exists():
        print(f"   Taille: {word_path.stat().st_size} bytes")
    
    # 2. Verifier le dossier de sortie
    print("\n2. DOSSIER DE SORTIE")
    output_folder = Config.get_output_folder()
    print(f"   Chemin: {output_folder}")
    print(f"   Existe: {'OUI' if output_folder.exists() else 'NON'}")
    
    if output_folder.exists():
        images = list(output_folder.glob("bornier_*.jpg")) + list(output_folder.glob("bornier_*.png"))
        print(f"   Nombre d'images: {len(images)}")
        
        if len(images) > 0:
            print(f"   Premieres images:")
            for img in sorted(images)[:5]:
                print(f"     - {img.name} ({img.stat().st_size} bytes)")
        
        # 3. Verifier les dossiers OCR
        print("\n3. DOSSIERS OCR")
        ocr_folder = output_folder / "ocr_tables"
        print(f"   Chemin: {ocr_folder}")
        print(f"   Existe: {'OUI' if ocr_folder.exists() else 'NON'}")
        
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
            print(f"   ATTENTION: Dossier OCR n'existe pas")
    else:
        print(f"   ATTENTION: Dossier de sortie n'existe pas!")
    
    # 4. Verifier la configuration OCR
    print("\n4. CONFIGURATION OCR")
    print(f"   OCR active: {Config.ENABLE_OCR}")
    print(f"   Chemin Tesseract: {Config.TESSERACT_PATH}")
    print(f"   Tesseract existe: {'OUI' if Path(Config.TESSERACT_PATH).exists() else 'NON'}")
    print(f"   Langue: {Config.OCR_LANGUAGE}")
    print(f"   Export Excel: {Config.EXPORT_EXCEL}")
    
    # 5. Verifier le rapport
    print("\n5. RAPPORT D'EXTRACTION")
    report_path = output_folder / Config.REPORT_FILENAME
    if report_path.exists():
        print(f"   Rapport trouve: {report_path.name}")
        import json
        try:
            with open(report_path) as f:
                report = json.load(f)
                print(f"   Contenu:")
                for key, value in report.items():
                    if isinstance(value, dict):
                        print(f"     - {key}: {len(value)} items")
                    else:
                        print(f"     - {key}: {value}")
        except Exception as e:
            print(f"   Erreur lecture rapport: {e}")
    else:
        print(f"   Aucun rapport trouve")
    
    print("\n" + "="*70)
    print("DIAGNOSTIC TERMINE")
    print("="*70 + "\n")

if __name__ == "__main__":
    diagnose()
