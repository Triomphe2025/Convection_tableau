Modifie un paramètre de configuration du projet TriosSeconverter dans `config.py`.

L'utilisateur indique quel paramètre il veut changer et quelle est la nouvelle valeur.

Paramètres disponibles et leur impact :

| Paramètre | Impact si modifié |
|-----------|------------------|
| TESSERACT_PATH | Chemin vers tesseract.exe — à changer si Tesseract est réinstallé |
| OCR_LANGUAGE | Langue OCR : "fra" (français), "eng" (anglais), "fra+eng" (les deux) |
| PAGE_SIZE | Lignes par page A4 dans Excel (défaut 48 — ne pas dépasser 56) |
| STATION_NAME | Nom P.E.T. affiché si l'OCR ne trouve pas le nom dans l'image |
| MIN_DATA_ROWS | Seuil minimal de lignes de données pour valider un bornier |
| IMAGES_FOLDER_NAME | Nom du dossier où les images extraites sont sauvegardées |

Étapes :
1. Lis le fichier `config.py` pour voir la valeur actuelle du paramètre demandé.
2. Explique l'impact du changement en termes simples (pas de jargon technique).
3. Demande confirmation avant de modifier.
4. Effectue la modification dans `config.py`.
5. Confirme la modification et rappelle que le logiciel doit être relancé pour la prendre en compte.

Ne jamais toucher aux paramètres de classe ConfigDev et ConfigProd sauf si l'utilisateur le demande explicitement.
