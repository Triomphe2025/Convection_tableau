Aide l'utilisateur à créer un nouveau modèle de tableau pour TriosSeconverter.

Pose ces questions une par une (en français) :
1. Quel est le nom du modèle ? (ex : "Bornier 5 colonnes")
2. Quelles sont les colonnes ? (ex : BORNE, COULEUR, SIGNAL, JARRETIERES, SECTION) — une par une
3. Quel est le mot-clé de ligne de séparation ? (ex : NOM DU CABLE) — laisser vide si pas de séparation
4. Le tableau a-t-il un pied de page ? (oui/non)
5. Si oui : quelle est l'étiquette gauche ? (défaut : M  T  I)

Ensuite lis le fichier `templates.json` à la racine du projet.
Ajoute le nouveau modèle dans ce fichier en respectant exactement la structure JSON existante des autres modèles.

Après modification, confirme à l'utilisateur :
- Le nom du modèle créé
- La liste des colonnes
- Comment l'activer depuis l'interface graphique (liste déroulante "Modèle de tableau")
