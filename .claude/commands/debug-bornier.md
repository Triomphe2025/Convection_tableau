Analyse les problèmes OCR sur un bornier spécifique et propose des corrections.

L'utilisateur doit indiquer : le nom ou numéro de l'image problématique (ex : bornier_12.jpg).

Étapes d'investigation :

1. Lis `config.py` pour connaître le dossier d'images (`IMAGES_FOLDER_NAME`) et le chemin Tesseract.

2. Vérifie que le fichier image existe dans le dossier images_borniers/.

3. Explique les causes possibles d'un mauvais résultat OCR pour ce type d'image :
   - Image trop floue (score de flou > 80% → en-tête orange dans Excel)
   - Résolution trop basse (agrandissement automatique déclenché si largeur < 1400px)
   - Mauvais contraste (binarisation Otsu peut échouer sur fond grisâtre)
   - En-tête non détectée (mots-clés BORNE/COULEUR/SIGNAL/JARRETIERES absents ou mal lus)
   - Pieds de page mal détectés (mots-clés NO PLAN/PAGE/BORNIER non reconnus)

4. Suggère des actions correctives concrètes :
   - Ajouter une correction dans `data_dictionary.json` pour les valeurs mal lues
   - Ajuster `MIN_DATA_ROWS` dans `config.py` si le bornier est filtré à tort
   - Vérifier dans l'Excel si l'en-tête est colorée en ORANGE (= image floue)

5. Si l'utilisateur veut tester manuellement, indique la commande :
   ```powershell
   env\Scripts\activate
   python -c "from ocr_processor import BornierTableExtractor; from pathlib import Path; r = BornierTableExtractor().extract(Path('images_borniers/bornier_12.jpg')); print(r)"
   ```
