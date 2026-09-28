# Kit de départ — mise à niveau TriosSeconverter

À copier dans ton projet (`convertion Tableau`) avant l'étape 2 du plan.

## fixtures/  →  à copier dans `tests/fixtures/`

| Fichier | Rôle |
|---|---|
| `223400PE137.pdf` | PDF **vectoriel** : sa couche texte est la vérité exacte (caractères + positions). Sert aux tests des étapes 4 et 7. |
| `223111PE011_extrait_10pages.pdf` | 10 pages du **scan** 223111PE011 (pages 1, 2, 3, 9, 52, 104, 119, 122, 122a, 123), choisies parce que la v1.7 s'y trompe. 2,6 Mo au lieu de 38 Mo. |
| `223111PE011_extrait_verite_BROUILLON.xlsx` | Vérité terrain de ces 10 pages : **brouillon à valider par toi** (colonne « Valide par moi »). Renomme-le sans `_BROUILLON` une fois validé. |

## outils_reference/  →  à copier dans `outils_reference/` (hors du code de l'appli)

Scripts écrits pendant l'audit. Ils fonctionnent, mais ne sont pas au standard du projet
(pas de tests, pas de config.py). Donne-les à Claude Code comme **point de départ**, pas à copier tels quels.

| Fichier | Ce qu'il fait |
|---|---|
| `grille.py` | Reconstruit une page de PDF vectoriel en grille de caractères (positions exactes). Base de l'étape 4. |
| `comparateur.py` | Lit original et Excel, aligne les lignes (difflib + Needleman-Wunsch), classe les écarts. Base de l'étape 3. |
| `pieds.py` | Capture toutes les paires `LIBELLÉ : valeur` d'un pied de page, sans liste figée. Base de l'étape 7. |
| `coherence.py` | Repère un même code écrit de deux façons dans un document. Utilisé à l'étape 9. |
| `annoter.py` | Produit l'Excel annoté (feuilles RÉSUMÉ / ÉCARTS, cellules colorées + commentaires). |
| `pdf_table_compare.py` | Premier prototype (scan vs PDF Excel). Contient le piège `autojunk=False` documenté. |
