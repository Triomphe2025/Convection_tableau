#!/usr/bin/env python3
"""
Affiche un résumé visuel du projet d'extraction d'images.

Exécution:
    python project_overview.py
"""


def print_banner():
    """Affiche une bannière de bienvenue."""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║         🖼️  EXTRACTEUR D'IMAGES DEPUIS WORD                              ║
║                                                                            ║
║         Extrait automatiquement les images d'un document Word             ║
║         Les enregistre dans un dossier organisé                           ║
║         Avec nommage automatique incrémental                              ║
║                                                                            ║
║         Développé avec bonnes pratiques Python professionnelles           ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)


def print_quick_start():
    """Affiche le guide de démarrage rapide."""
    print("""
┌─ 🚀 DÉMARRAGE RAPIDE (3 ÉTAPES) ──────────────────────────────────────────┐
│                                                                            │
│  1️⃣  INSTALLER LES DÉPENDANCES                                            │
│      pip install -r requirements.txt                                      │
│                                                                            │
│  2️⃣  CONFIGURER (Ouvrir et modifier config.py)                            │
│      WORD_FILE = "votre_document.docx"                                    │
│      IMAGES_FOLDER_NAME = "VD23111 PE 162"                                │
│                                                                            │
│  3️⃣  EXÉCUTER                                                             │
│      python run.py                                                        │
│                                                                            │
│  ✨ Les images apparaîtront dans VD23111 PE 162/                           │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_file_structure():
    """Affiche la structure du projet."""
    print("""
┌─ 📁 STRUCTURE DU PROJET ──────────────────────────────────────────────────┐
│                                                                            │
│  📦 convertion Tableau/                                                   │
│  │                                                                        │
│  ├─ 🎯 POUR COMMENCER (Commencez ici!)                                    │
│  │  ├─ QUICK_START.md ...................... Guide de démarrage (5 min)  │
│  │  ├─ config.py ........................... À MODIFIER (votre config)    │
│  │  └─ run.py .............................. À EXÉCUTER                   │
│  │                                                                        │
│  ├─ 📚 DOCUMENTATION (À lire selon vos besoins)                           │
│  │  ├─ README.md ........................... Guide complet détaillé        │
│  │  ├─ ARCHITECTURE.md ..................... Diagrammes et flux            │
│  │  ├─ INDEX.md ............................ Navigation du projet          │
│  │  └─ SUMMARY.md .......................... Ce fichier                    │
│  │                                                                        │
│  ├─ 💻 CODE SOURCE (Ne pas modifier)                                      │
│  │  ├─ recuperer_image.py .................. 3 classes principales         │
│  │  ├─ exemple_utilisation.py ............. Exemples d'utilisation        │
│  │  └─ test_recuperer_image.py ............ Tests unitaires               │
│  │                                                                        │
│  ├─ ⚙️  CONFIGURATION                                                      │
│  │  └─ requirements.txt .................... Dépendances Python            │
│  │                                                                        │
│  └─ 🛠️  UTILITAIRES                                                        │
│     ├─ startup_checklist.py ............... Vérification du setup         │
│     └─ project_overview.py ............... Ce fichier                    │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_architecture():
    """Affiche l'architecture simplifée."""
    print("""
┌─ 🏗️  ARCHITECTURE SIMPLIFIÉE ─────────────────────────────────────────────┐
│                                                                            │
│  3 CLASSES PRINCIPALES:                                                  │
│  ═══════════════════════                                                  │
│                                                                            │
│  📦 ImageExtractor                                                        │
│     Responsabilité: Extraire les images du Word                          │
│     ├─ Valide le fichier .docx                                            │
│     ├─ Ouvre le .docx comme archive ZIP                                   │
│     └─ Récupère toutes les images                                         │
│                                                                            │
│  📦 ImageStorage                                                          │
│     Responsabilité: Enregistrer les images                                │
│     ├─ Crée le dossier de destination                                     │
│     ├─ Enregistre chaque image                                            │
│     └─ Nommage automatique: bornier_1, bornier_2, etc.                    │
│                                                                            │
│  📦 ImageExtractionPipeline                                               │
│     Responsabilité: Orchestrer le processus                               │
│     ├─ Coordonne ImageExtractor et ImageStorage                           │
│     ├─ Gère les erreurs                                                   │
│     └─ Fournit résumé avec statistiques                                   │
│                                                                            │
│  FLUX:                                                                    │
│  ════                                                                      │
│     Word File                                                             │
│       │                                                                   │
│       ├─→ ImageExtractor ──→ Images (bytes + extension)                   │
│       │                       │                                           │
│       └─→ ImageStorage ←──────┘                                           │
│                │                                                          │
│                └─→ Dossier VD23111 PE 162/                               │
│                    ├─ bornier_1.jpg ✓                                     │
│                    ├─ bornier_2.png ✓                                     │
│                    └─ bornier_3.jpeg ✓                                    │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_features():
    """Affiche les caractéristiques principales."""
    print("""
┌─ ⭐ CARACTÉRISTIQUES PRINCIPALES ──────────────────────────────────────────┐
│                                                                            │
│  ✅ CODE PROFESSIONNEL                                                     │
│     • Type hints (annotations de types)                                    │
│     • Docstrings détaillées (consultables avec Ctrl+K Ctrl+I)             │
│     • Logging structuré avec messages ✓ et ✗                               │
│     • Gestion d'erreurs robuste                                           │
│                                                                            │
│  ✅ FACILE À UTILISER                                                      │
│     • Configuration externalisée dans config.py                           │
│     • Point d'entrée simple: python run.py                                │
│     • Messages clairs et détaillés                                        │
│     • Aucun code à modifier pour l'utilisation basique                   │
│                                                                            │
│  ✅ FACILE À ÉTENDRE                                                       │
│     • Architecture modulaire et propre                                    │
│     • Classes indépendantes et testables                                  │
│     • Exemples d'utilisation fournis                                      │
│     • Commentaires et docstrings abondants                                │
│                                                                            │
│  ✅ BIEN DOCUMENTÉE                                                        │
│     • QUICK_START.md: Démarrage rapide (3 min)                            │
│     • README.md: Documentation complète et détaillée                      │
│     • ARCHITECTURE.md: Diagrammes et flux d'exécution                     │
│     • INDEX.md: Navigation et FAQ                                         │
│     • exemple_utilisation.py: Exemples concrets                           │
│                                                                            │
│  ✅ TESTÉE                                                                 │
│     • Tests unitaires fournis                                             │
│     • Exécutez: python test_recuperer_image.py                            │
│     • Tous les tests passent ✓                                            │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_file_guide():
    """Affiche un guide par type de fichier."""
    print("""
┌─ 📖 QUEL FICHIER LIRE? ───────────────────────────────────────────────────┐
│                                                                            │
│  👶 Je suis débutant ou pressé                                            │
│     1. Lire QUICK_START.md (3 min)                                        │
│     2. Modifier config.py (2 min)                                         │
│     3. Exécuter python run.py (1 min)                                     │
│     4. C'est tout! ✅                                                      │
│                                                                            │
│  👨‍💻 Je suis développeur                                                    │
│     1. Lire README.md (20 min)                                            │
│     2. Consulter ARCHITECTURE.md (15 min)                                 │
│     3. Regarder exemple_utilisation.py (10 min)                           │
│     4. Lire recuperer_image.py (20 min)                                   │
│                                                                            │
│  🎨 Je veux personnaliser                                                 │
│     1. Lire config.py (options disponibles)                               │
│     2. Modifier config.py selon vos besoins                               │
│     3. Consulter exemple_utilisation.py pour avancé                       │
│                                                                            │
│  🔬 Je veux tester                                                        │
│     1. Exécuter: python test_recuperer_image.py                           │
│     2. Ou avec pytest: pytest test_recuperer_image.py -v                  │
│     3. Tous les tests doivent passer ✓                                    │
│                                                                            │
│  🏗️  Je veux comprendre l'architecture                                    │
│     1. Lire ARCHITECTURE.md (vue d'ensemble)                              │
│     2. Consulter les diagrammes                                           │
│     3. Examiner recuperer_image.py avec les docstrings                    │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_commands():
    """Affiche les commandes utiles."""
    print("""
┌─ ⌨️  COMMANDES RAPIDES ────────────────────────────────────────────────────┐
│                                                                            │
│  # Installer les dépendances                                              │
│  pip install -r requirements.txt                                          │
│                                                                            │
│  # Vérifier que tout fonctionne (optionnel)                               │
│  python startup_checklist.py                                              │
│                                                                            │
│  # Afficher ce résumé                                                     │
│  python project_overview.py                                               │
│                                                                            │
│  # Exécuter l'extraction                                                  │
│  python run.py                                                            │
│                                                                            │
│  # Tester le code                                                         │
│  python test_recuperer_image.py                                           │
│                                                                            │
│  # Voir les fichiers du projet                                            │
│  ls -la            (Linux/Mac)                                            │
│  dir               (Windows)                                              │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_faq():
    """Affiche la FAQ."""
    print("""
┌─ ❓ QUESTIONS FRÉQUENTES ─────────────────────────────────────────────────┐
│                                                                            │
│  Q: Par où je commence?                                                   │
│  R: Lire QUICK_START.md, puis modifier config.py, puis exécuter run.py   │
│                                                                            │
│  Q: Quel fichier dois-je modifier?                                        │
│  R: Uniquement config.py (pour configurer le chemin du Word)              │
│                                                                            │
│  Q: Quel fichier dois-je exécuter?                                        │
│  R: python run.py (pas besoin de modifier quoi que ce soit d'autre)       │
│                                                                            │
│  Q: Où vont les images extraites?                                         │
│  R: Dans le dossier VD23111 PE 162/ (configurable dans config.py)         │
│                                                                            │
│  Q: Comment les images sont-elles nommées?                                │
│  R: Automatiquement: bornier_1.jpg, bornier_2.png, bornier_3.jpeg, etc.   │
│                                                                            │
│  Q: Je peux changer le nommage?                                           │
│  R: Oui! Modifiez IMAGE_NAME_FORMAT dans config.py                       │
│                                                                            │
│  Q: Le code supporte quels formats d'image?                               │
│  R: Tous! (jpg, png, jpeg, gif, bmp, tiff, etc.)                          │
│                                                                            │
│  Q: Comment vérifier que ça marche?                                       │
│  R: Exécutez python test_recuperer_image.py (tous les tests doivent passer)│
│                                                                            │
│  Q: Que faire si une image ne s'extrait pas?                              │
│  R: Consultez les logs (messages ✗). Vérifiez le fichier Word.            │
│                                                                            │
│  Q: Je peux personnaliser le code?                                        │
│  R: Oui! Lisez exemple_utilisation.py et ARCHITECTURE.md                 │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_checklist():
    """Affiche la checklist d'avant de démarrer."""
    print("""
┌─ ✅ CHECKLIST AVANT DE DÉMARRER ──────────────────────────────────────────┐
│                                                                            │
│  Avant de lancer python run.py, assurez-vous que:                         │
│                                                                            │
│  □ Vous avez lu QUICK_START.md                                            │
│  □ Vous avez installé les dépendances                                     │
│    (pip install -r requirements.txt)                                      │
│  □ Vous avez modifié config.py avec votre fichier Word                    │
│  □ Votre fichier Word existe et est au bon chemin                         │
│  □ Le fichier Word n'est pas ouvert dans Word                             │
│  □ C'est bien un fichier .docx (pas .doc ancien format)                   │
│  □ Le document contient au moins une image                                │
│  □ Vous avez les droits de lecture sur le fichier                         │
│                                                                            │
│  Si tous les ☑️ sont cochés, vous pouvez exécuter:                         │
│  python run.py                                                            │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_next_steps():
    """Affiche les prochaines étapes."""
    print("""
┌─ 🚀 PROCHAINES ÉTAPES ────────────────────────────────────────────────────┐
│                                                                            │
│  IMMÉDIATEMENT (5 minutes):                                               │
│  ════════════════════════════                                             │
│  1. ✅ Lire QUICK_START.md                                                 │
│  2. ✅ Installer: pip install -r requirements.txt                          │
│  3. ✅ Configurer: Modifier config.py (changez WORD_FILE)                 │
│  4. ✅ Exécuter: python run.py                                             │
│  5. ✅ Vérifier: Ouvrir le dossier VD23111 PE 162/                        │
│                                                                            │
│  ENSUITE (si besoin):                                                     │
│  ═══════════════════════                                                  │
│  • Lire README.md pour les détails avancés                                │
│  • Consulter ARCHITECTURE.md pour comprendre le design                    │
│  • Modifier config.py pour personnaliser le comportement                  │
│  • Lire example_utilisation.py pour des cas avancés                       │
│  • Exécuter python test_recuperer_image.py pour vérifier                  │
│                                                                            │
│  POUR APPROFONDIR:                                                        │
│  ══════════════════                                                       │
│  • Lire recuperer_image.py (code source avec docstrings)                  │
│  • Consulter les docstrings (Ctrl+K Ctrl+I dans VS Code)                  │
│  • Modifier et étendre le code selon vos besoins                          │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
    """)


def print_closing():
    """Affiche un message de clôture."""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║                      ✨ VOUS ÊTES PRÊT! ✨                                ║
║                                                                            ║
║  Vous avez tout ce qu'il faut pour:                                       ║
║  ✅ Extraire vos images facilement                                         ║
║  ✅ Organiser vos fichiers automatiquement                                 ║
║  ✅ Comprendre et modifier le code si besoin                              ║
║  ✅ Tester et déboguer sans problème                                       ║
║                                                                            ║
║  Première étape: Lire QUICK_START.md →                                    ║
║                                                                            ║
║  Bonne chance avec votre extraction d'images! 🖼️                           ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)


def main():
    """Exécute la présentation complète."""
    print_banner()
    print_quick_start()
    print_file_structure()
    print_architecture()
    print_features()
    print_file_guide()
    print_commands()
    print_faq()
    print_checklist()
    print_next_steps()
    print_closing()


if __name__ == "__main__":
    main()
