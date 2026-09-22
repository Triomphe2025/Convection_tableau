#!/usr/bin/env python3
"""
Checklist de Démarrage - Vérifiez que tout fonctionne correctement

Exécution:
    python startup_checklist.py
"""

import sys
from pathlib import Path


def print_header(text):
    """Affiche un en-tête stylisé."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_step(number, text, status=None):
    """Affiche une étape avec statut."""
    icon = "✅" if status is True else "❌" if status is False else "⏳"
    print(f"{icon} Étape {number}: {text}")


def print_section(title):
    """Affiche une section."""
    print(f"\n📋 {title}")
    print("-" * 60)


def check_file_exists(filename):
    """Vérifie qu'un fichier existe."""
    return Path(filename).exists()


def check_imports():
    """Vérifie que les dépendances sont installées."""
    results = {}

    packages = {
        'docx': 'python-docx',
        'PIL': 'Pillow',
        'zipfile': 'zipfile (builtin)',
        'logging': 'logging (builtin)',
    }

    for module, package_name in packages.items():
        try:
            __import__(module)
            results[package_name] = True
        except ImportError:
            results[package_name] = False

    return results


def main():
    """Exécute la checklist complète."""

    print_header("🚀 CHECKLIST DE DÉMARRAGE")
    print("\nVérifiez que tout est prêt pour extraire vos images!")

    # Section 1: Fichiers
    print_section("1. Vérification des fichiers")

    files_to_check = [
        ('recuperer_image.py', 'Code principal'),
        ('config.py', 'Configuration'),
        ('run.py', 'Point d\'entrée'),
        ('requirements.txt', 'Dépendances'),
        ('README.md', 'Documentation'),
        ('QUICK_START.md', 'Guide de démarrage'),
    ]

    all_files_exist = True
    for filename, description in files_to_check:
        exists = check_file_exists(filename)
        all_files_exist = all_files_exist and exists
        status_icon = "✅" if exists else "❌"
        print(f"  {status_icon} {filename:<25} ({description})")

    # Section 2: Dépendances
    print_section("2. Vérification des dépendances")

    imports = check_imports()
    all_imports_ok = True
    for package, available in imports.items():
        all_imports_ok = all_imports_ok and available
        status_icon = "✅" if available else "⚠️"
        status_text = "Installé" if available else "À INSTALLER"
        print(f"  {status_icon} {package:<25} {status_text}")

    if not all_imports_ok:
        print("\n  ⚠️  Pour installer les dépendances manquantes:")
        print("     pip install -r requirements.txt")

    # Section 3: Configuration
    print_section("3. Vérification de la configuration")

    try:
        from config import Config

        word_file = Config.WORD_FILE
        images_folder = Config.IMAGES_FOLDER_NAME

        print(f"  📄 Fichier Word: {word_file}")

        if word_file == "document.docx":
            print("     ⚠️  ⚠️  À CONFIGURER: Changez le chemin dans config.py")
        else:
            if Path(word_file).exists():
                print("     ✅ Le fichier existe")
            else:
                print("     ❌ Le fichier n'existe pas - Vérifiez le chemin")

        print(f"  📁 Dossier destination: {images_folder}")

    except ImportError as e:
        print(f"  ❌ Erreur d'import: {e}")

    # Section 4: Recommandations
    print_section("4. Checklist avant d'exécuter")

    print("""
  Avant de lancer python run.py, assurez-vous que:
  
  □ Vous avez lu QUICK_START.md
  □ Vous avez modifié config.py avec votre fichier Word
  □ Les dépendances sont installées (pip install -r requirements.txt)
  □ Votre fichier Word existe et est au bon chemin
  □ Le fichier Word n'est pas ouvert dans Word
  □ Le fichier est bien au format .docx (pas .doc ancien)
  □ Vous avez au moins une image dans le Word
    """)

    # Section 5: Résumé
    print_section("5. Résumé de la configuration")

    print(f"""
  ✨ Résumé:
  
  • Fichiers:         {'✅ OK' if all_files_exist else '❌ Erreur'}
  • Dépendances:      {'✅ OK' if all_imports_ok else '❌ À installer'}
  • Configuration:    {'✅ Prête' if word_file != 'document.docx' else '⚠️  À configurer'}
    """)

    # Section 6: Prochaines étapes
    print_section("6. Prochaines étapes")

    if not all_imports_ok:
        print_step(1, "Installer les dépendances", False)
        print("   Exécutez: pip install -r requirements.txt\n")
    else:
        print_step(1, "Installer les dépendances", True)

    if word_file == "document.docx":
        print_step(2, "Modifier config.py", False)
        print("   • Ouvrez config.py")
        print("   • Changez WORD_FILE avec votre document")
        print("   • Changez IMAGES_FOLDER_NAME si désiré\n")
    else:
        print_step(2, "Modifier config.py", True)

    print_step(3, "Exécuter l'extraction", None)
    print("   Exécutez: python run.py\n")

    print_step(4, "Vérifier les résultats", None)
    print(f"   Ouvrez le dossier: {images_folder}/\n")

    # Section 7: Aide
    print_section("7. Besoin d'aide?")

    print("""
  📖 Documentation:
     • QUICK_START.md ............ Guide rapide (3 min)
     • README.md ................. Documentation complète
     • ARCHITECTURE.md ........... Diagrammes et flux
     • SUMMARY.md ................ Vue d'ensemble du projet
  
  💻 Code:
     • recuperer_image.py ........ Code source (consultez les docstrings)
     • exemple_utilisation.py ... Exemples d'utilisation
     • test_recuperer_image.py ... Tests (exécutez: python test_recuperer_image.py)
  
  ⚙️ Configuration:
     • config.py ................. Modifiez ici!
    """)

    # Résumé final
    print_header("✅ CHECKLIST COMPLÈTE")

    ready = all_files_exist and word_file != "document.docx"

    if ready:
        print("""
  🎉 Vous êtes prêt à extraire vos images!
  
  Exécutez: python run.py
  
  Les images apparaîtront dans:
  • {}/bornier_1.jpg
  • {}/bornier_2.png
  • {}/bornier_3.jpeg
  • ... (etc)
        """.format(images_folder, images_folder, images_folder))
    else:
        print("""
  ⚠️  À faire avant de lancer run.py:
  
  1. Installer les dépendances (si nécessaire):
     pip install -r requirements.txt
  
  2. Configurer config.py:
     • Changez WORD_FILE avec votre chemin
     • Modifiez IMAGES_FOLDER_NAME si désiré
  
  3. Ensuite, exécutez:
     python run.py
        """)

    print("=" * 60)
    print()

    return 0 if ready else 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Erreur: {e}\n")
        sys.exit(1)
