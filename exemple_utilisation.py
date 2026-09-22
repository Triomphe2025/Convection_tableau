"""
Exemple d'utilisation du script d'extraction d'images.

Ce fichier montre comment utiliser les classes pour extraire les images.
"""

from recuperer_image import ImageExtractionPipeline
from pathlib import Path


def exemple_basic():
    """
    Exemple simple d'utilisation.
    """
    # Chemin vers votre fichier Word
    word_file = "mon_document.docx"

    # Créer le pipeline avec le dossier de destination par défaut
    pipeline = ImageExtractionPipeline(word_file)

    # Exécuter l'extraction
    results = pipeline.run()

    # Afficher les résultats
    print("\nRésumé:")
    print(f"  Images trouvées: {results['total']}")
    print(f"  Images enregistrées: {results['saved']}")
    print(f"  Erreurs: {results['errors']}")
    print(f"  Dossier de destination: {results['output_path']}")


def exemple_avance():
    """
    Exemple avancé avec un nom de dossier personnalisé.
    """
    word_file = "mon_document.docx"
    dossier_personnalise = "VD23111 PE 162"

    # Créer le pipeline avec un nom de dossier personnalisé
    pipeline = ImageExtractionPipeline(word_file, output_folder=dossier_personnalise)

    # Exécuter l'extraction
    results = pipeline.run()


def exemple_chemin_absolu():
    """
    Exemple avec chemin absolu.
    """
    # Chemin complet vers le fichier
    word_file = r"C:\Users\YourUser\Documents\mon_document.docx"

    pipeline = ImageExtractionPipeline(word_file)
    results = pipeline.run()


if __name__ == "__main__":
    # Décommenter l'exemple à utiliser:

    # exemple_basic()
    # exemple_avance()
    # exemple_chemin_absolu()

    print("📝 Veuillez configurer le chemin du fichier Word et décommenter l'exemple à utiliser.")
