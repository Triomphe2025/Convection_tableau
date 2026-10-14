# Fiche d'essai — installation chez un collègue (exe protégé v1.8)

À faire une fois, avec le collègue, sur son poste. Cocher chaque ligne.

## 1. Licence
- [ ] Copier le dossier `TriosSeconverter\` (l'exe et ses fichiers) sur le poste du collègue.
- [ ] Lancer `TriosSeconverter.exe` **sans licence** : une fenêtre affiche un **identifiant de poste**
      (ex : `11B0-9E38-9601-2DB7`). Noter cet identifiant.
- [ ] Sur votre poste, fabriquer la clé :
      `python fabriquer_licence.py <identifiant> <échéance AAAA-MM-JJ> "<votre contact>"`
      (dossier `TriosSeconverter_prive\licence_outil`, clé privée requise).
- [ ] Renommer le fichier produit en `licence.triosse` et le poser **à côté de l'exe** du collègue.
- [ ] Relancer l'exe : il doit démarrer normalement.

## 2. Environnement
- [ ] **Tesseract présent** : la barre d'information ou le journal indique « Tesseract : …\tesseract.exe (trouvé) ».
- [ ] **Tesseract absent** (poste sans Tesseract) : le logiciel démarre quand même ; une ligne claire
      signale que le mode image n'est pas disponible. Les modes vectoriel et Claude restent utilisables.

## 3. Conversions
- [ ] **Mode vectoriel** : convertir un PDF vectoriel (ex. un REPARTITEUR 2). Vérifier l'Excel produit
      (tableaux, pied en bas, feuille A VERIFIER).
- [ ] **Mode Claude** : saisir **sa propre clé API** dans l'interface, convertir une page scannée,
      vérifier l'Excel. (La clé API du collègue est la sienne ; elle n'est jamais écrite dans un fichier.)
- [ ] **Formater Excel** : reformater un Excel produit ; vérifier blocs réguliers, A VERIFIER et LEGENDE intactes.
- [ ] **Ajouter au lexique** : ajouter un Excel corrigé ; vérifier le message de confirmation.

## 4. Images de travail
- [ ] Après une conversion, vérifier qu'**aucun dossier d'images** n'est apparu à côté du PDF source
      ni dans le dossier de sortie (elles vont dans `%LOCALAPPDATA%\TriosSeconverter\travail`).

## 5. Antivirus
- [ ] L'antivirus du poste n'a **pas bloqué** l'exe. Si une alerte apparaît, la noter (éditeur, message)
      et me la transmettre avant de poursuivre.

## En cas de blocage licence
- « licence expirée » : fabriquer une nouvelle clé avec une échéance plus lointaine, reposer `licence.triosse`.
- « pas celle de ce poste » : l'identifiant a changé (disque/Windows réinstallé) ; refaire l'étape 1.
