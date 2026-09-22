Ajoute une correction OCR au dictionnaire de données du projet TriosSeconverter.

L'utilisateur va te donner : le nom de la colonne, la valeur mal lue par l'OCR, et la valeur correcte.

Lis d'abord le fichier `data_dictionary.json` s'il existe pour voir les corrections déjà présentes.
Ensuite modifie-le en ajoutant la nouvelle entrée sous la bonne colonne.
Si le fichier n'existe pas, crée-le avec la structure de base.

Format attendu du fichier :
```json
{
  "COULEUR": {
    "ROUSE": "ROUGE"
  },
  "BORNIER": {
    "B7O2A": "B702A"
  }
}
```

Confirme à l'utilisateur que la correction a été ajoutée et rappelle-lui qu'elle sera appliquée automatiquement au prochain lancement de la conversion.
