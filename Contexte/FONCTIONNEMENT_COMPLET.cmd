@echo off
chcp 65001 >nul 2>&1
color 0A
cls

echo.
echo  ╔══════════════════════════════════════════════════════════════════════╗
echo  ║          TRIOSSECONVERTER — PRINCIPE DE FONCTIONNEMENT COMPLET      ║
echo  ║     Documentation technique v1.2 — Double-cliquer pour lire        ║
echo  ╚══════════════════════════════════════════════════════════════════════╝
echo.
echo  Appuyez sur une touche pour commencer la lecture...
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   1/10 — QU'EST-CE QUE TRIOSSECONVERTER ?
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  TriosSeconverter est un logiciel développé pour les ingénieurs
echo  en électrotechnique travaillant sur des borniers électriques.
echo.
echo  PROBLÈME RÉSOLU :
echo    Les plans de borniers sont stockés dans des fichiers Word (.docx)
echo    sous forme d'IMAGES scannées ou de captures d'écran. Ces images
echo    ne sont pas exploitables directement dans Excel pour la gestion,
echo    la modification ou l'impression standardisée.
echo.
echo  SOLUTION APPORTÉE :
echo    Le logiciel extrait chaque image du fichier Word, la passe à travers
echo    un moteur OCR (Reconnaissance Optique de Caractères), reconstruit
echo    le tableau de données, puis génère automatiquement :
echo      → un classeur Excel formaté et paginé (tous_les_borniers.xlsx)
echo      → un document Word propre    (tous_les_borniers.docx)
echo.
echo  FICHIERS DU PROJET :
echo    interface.py          → Interface graphique (GUI Tkinter)
echo    converter.py          → Moteur de conversion (orchestration)
echo    ocr_processor.py      → Traitement OCR (BornierTableExtractor)
echo    generer_classeur.py   → Génération Excel + Word combinés
echo    word_table_importer.py→ Import de tableaux depuis Word structuré
echo    template.py           → Modèles de tableau (colonnes, pied de page)
echo    config.py             → Configuration (Tesseract, langue, chemins)
echo    data_dictionary.py    → Dictionnaire de correction OCR
echo    recuperer_image.py    → Extraction des images depuis Word
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   2/10 — ÉTAPE 1 : EXTRACTION DES IMAGES DU FICHIER WORD
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  FICHIERS CONCERNÉS : recuperer_image.py, converter.py
echo.
echo  L'utilisateur fournit un fichier Word (.docx) contenant des images
echo  de borniers électriques (scans ou captures d'écran).
echo.
echo  CLASSE ImageExtractor (recuperer_image.py) :
echo    → Ouvre le fichier Word avec la bibliothèque python-docx
echo    → Parcourt tous les éléments du document (paragraphes, tableaux)
echo    → Détecte les images embarquées (format JPEG, PNG, BMP, etc.)
echo    → Retourne la liste des images sous forme de données binaires
echo.
echo  CLASSE ImageStorage (recuperer_image.py) :
echo    → Crée le dossier de destination (images_borniers/)
echo    → Sauvegarde chaque image avec un nom numéroté : bornier_1.jpg,
echo       bornier_2.jpg, etc.
echo    → Le format de nommage est configurable dans config.py
echo.
echo  RÉSULTAT : un dossier images_borniers/ contenant N fichiers images,
echo  un par tableau de bornier présent dans le document Word source.
echo.
echo  CONFIGURATION (config.py) :
echo    IMAGE_NAME_FORMAT = "bornier_{index}"
echo    ALLOWED_FORMATS   = None  (tous les formats acceptés)
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   3/10 — ÉTAPE 2 : PRÉTRAITEMENT DE L'IMAGE (OCR STEP 1)
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  FICHIER CONCERNÉ : ocr_processor.py → BornierTableExtractor._preprocess()
echo.
echo  Avant de lire le texte, l'image est préparée pour maximiser
echo  la qualité de la reconnaissance :
echo.
echo  1. CHARGEMENT avec OpenCV (cv2.imread)
echo.
echo  2. CONVERSION en niveaux de gris
echo       L'OCR n'a pas besoin de la couleur ; le gris est plus précis.
echo.
echo  3. AGRANDISSEMENT si largeur ^< 1400 pixels
echo       Tesseract lit mieux les images larges. Si l'image est petite
echo       (scan basse résolution), elle est agrandie proportionnellement
echo       avec l'interpolation INTER_CUBIC (la plus fidèle).
echo.
echo  4. BINARISATION OTSU
echo       L'image est convertie en noir pur / blanc pur.
echo       L'algorithme d'Otsu calcule automatiquement le seuil optimal
echo       séparant le texte du fond, même si l'éclairage est irrégulier.
echo.
echo  RÉSULTAT : image binaire 1 bit (noir = texte, blanc = fond)
echo             + largeur en pixels utilisée pour les frontières de colonnes.
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   4/10 — ÉTAPE 3 : RECONNAISSANCE OCR (LECTURE DU TEXTE)
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  FICHIER CONCERNÉ : ocr_processor.py → BornierTableExtractor._ocr_elements()
echo.
echo  Le moteur OCR Tesseract analyse l'image binarisée et retourne
echo  la position précise de chaque mot détecté.
echo.
echo  PARAMÈTRES TESSERACT :
echo    --oem 3   → Moteur LSTM (réseau de neurones) : le plus précis
echo    --psm 6   → Mode "bloc de texte uniforme" : adapté aux tableaux
echo    -l fra    → Langue française (configurable dans config.py)
echo.
echo  FILTRAGE DE QUALITÉ :
echo    Seuls les mots avec une CONFIANCE ^>= 15%% sont conservés.
echo    Les mots avec confiance inférieure sont des bruits (artefacts
echo    de scan, taches, ombres) et sont ignorés.
echo.
echo  POUR CHAQUE MOT RETENU, le logiciel mémorise :
echo    text  : le texte reconnu         (ex: "B702A")
echo    x, y  : position du coin haut-gauche du mot (en pixels)
echo    w, h  : largeur et hauteur du mot
echo    cx,cy : centre du mot
echo    conf  : niveau de confiance Tesseract (0-100)
echo.
echo  SCORE DE FLOU (blur_pct) :
echo    Avant OCR, un score de flou est calculé via la variance du
echo    filtre Laplacien. Si le score dépasse 80%%, l'en-tête du
echo    bornier est colorié en ORANGE dans Excel pour alerter
echo    l'utilisateur que la source image est de mauvaise qualité.
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   5/10 — ÉTAPE 4 : RECONSTRUCTION DE LA STRUCTURE DU TABLEAU
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  FICHIER CONCERNÉ : ocr_processor.py → BornierTableExtractor
echo.
echo  Les mots OCR sont des points dispersés sur l'image. Cette étape
echo  reconstitue les lignes et colonnes du tableau.
echo.
echo  A) REGROUPEMENT EN LIGNES (_group_lines) :
echo     - Calcul d'une tolérance verticale = 60%% de la hauteur médiane
echo       des mots (adaptative selon la taille de police du scan)
echo     - Les mots dont les centres verticaux sont proches (± tolérance)
echo       sont regroupés dans la même ligne horizontale
echo     - Dans chaque ligne, les mots sont triés de gauche à droite
echo.
echo  B) DÉTECTION DE L'EN-TÊTE (_find_header_idx) :
echo     - Le logiciel cherche la ligne qui contient au moins la moitié
echo       des mots-clés de colonnes du MODÈLE (ex: BORNE, COULEUR,
echo       SIGNAL, JARRETIERES)
echo     - La correspondance est partielle : gère les fautes OCR mineures
echo.
echo  C) FRONTIÈRES DE COLONNES (_col_boundaries) :
echo     - La position horizontale (cx) de chaque mot-clé de l'en-tête
echo       est mémorisée
echo     - Les frontières sont placées au MILIEU de chaque paire de
echo       centres successifs
echo     - Exemple :
echo         BORNE(cx=120) COULEUR(cx=320) SIGNAL(cx=520) JARR.(cx=720)
echo         Frontières : 0 | 220 | 420 | 620 | largeur_image
echo.
echo  D) CLASSIFICATION DE CHAQUE LIGNE (_classify_line) :
echo     - "section" : contient le mot-clé de séparation (ex: NOM DU CABLE)
echo     - "footer"  : contient NO PLAN, INDICE, PAGE, BORNIER, M T I...
echo     - "data"    : toute autre ligne = ligne de données du bornier
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   6/10 — ÉTAPE 5 : AFFECTATION AUX COLONNES ET NETTOYAGE
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  FICHIER CONCERNÉ : ocr_processor.py → _line_to_cells() et _clean_cell()
echo.
echo  Pour chaque ligne de données, les mots sont assignés à leur colonne.
echo.
echo  MÉTHODE D'AFFECTATION :
echo    → La position du BORD GAUCHE (x) du mot est comparée aux frontières
echo      de colonnes calculées à l'étape précédente.
echo    → On utilise le bord gauche (pas le centre) car un mot long
echo      qui commence dans SIGNAL ne doit pas aller dans JARRETIERES
echo      parce que son centre dépasse la frontière.
echo    → Si plusieurs mots tombent dans la même colonne, leur texte
echo      est concaténé avec un espace.
echo.
echo  NETTOYAGE DE CHAQUE CELLULE (_clean_cell) :
echo    → Suppression des pipes ^| en début/fin (séparateurs de colonnes
echo      mal lus par Tesseract)
echo    → Renvoi de chaîne vide si aucun caractère alphanumérique
echo    → Renvoi de chaîne vide si 5+ caractères identiques consécutifs
echo      (ex: "|||||||" = bruit de scanner)
echo.
echo  CORRECTION DICTIONNAIRE (data_dictionary.py) :
echo    → Un fichier dictionnaire peut contenir des correspondances
echo      erreur OCR → valeur correcte, organisées par colonne
echo    → Ex: colonne COULEUR, "ROUSE" → "ROUGE"
echo    → Les corrections sont appliquées automatiquement
echo.
echo  EXTRACTION DES MÉTADONNÉES DU PIED (_extract_meta) :
echo    → Les lignes "footer" sont concaténées en un seul texte
echo    → Des expressions régulières extraient :
echo        PET      = nom de la station (ex: EPEULE)
echo        BORNIER  = code du bornier   (ex: B702A)
echo        NO_PLAN  = numéro de plan    (ex: VD23111 PE 162)
echo        INDICE   = révision du plan  (ex: 0)
echo        PAGE     = numéro de page    (ex: 92)
echo    → La confusion OCR "O" ↔ "0" est normalisée sur le champ INDICE
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   7/10 — GÉNÉRATION DU CLASSEUR EXCEL
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  FICHIERS CONCERNÉS : generer_classeur.py → generer_excel()
echo                        ocr_processor.py   → _fill_worksheet()
echo                        converter.py       → run()
echo.
echo  Le classeur Excel contient DEUX FEUILLES STRICTEMENT SÉPARÉES :
echo.
echo  ── FEUILLE "Borniers" (tableaux issus de l'OCR sur les images) ──
echo.
echo    Chaque bornier occupe exactement PAGE_SIZE lignes (défaut: 48)
echo    simulant une page A4 portrait avec marges standard.
echo.
echo    STRUCTURE D'UN BORNIER DANS EXCEL :
echo      Ligne 1         : En-tête des colonnes (gris D9D9D9 ou ORANGE si flou)
echo      Lignes 2 à N    : Données (bordures latérales uniquement)
echo      Lignes section  : Texte fusionné sur toute la largeur (italique gras)
echo      Lignes vides    : Rembourrage jusqu'à PAGE_SIZE (bordures latérales)
echo      Ligne N-1       : Pied ligne 1 → M T I ^| P.E.T.: xxx  BORNIER: xxx
echo      Ligne N         : Pied ligne 2 → M T I ^| NO PLAN: xxx  INDICE: x  PAGE: xx
echo.
echo    Les borniers sont TRIÉS par numéro de PAGE croissant.
echo    Les borniers avec moins de MIN_DATA_ROWS lignes sont ignorés.
echo    Si un bornier dépasse PAGE_SIZE lignes : sauts de page automatiques.
echo.
echo  ── FEUILLE "tableaux word" (tableaux importés depuis Word) ──
echo.
echo    POURQUOI UNE FEUILLE SÉPARÉE ?
echo    Avant la version 1.2, les tableaux Word étaient fusionnés avec les
echo    résultats OCR dans la feuille "Borniers". Cela écrasait la mise en
echo    forme des pieds de page (bordures, fusions de cellules) des borniers
echo    issus des images. Bogue corrigé : les deux sources sont maintenant
echo    dans des feuilles indépendantes et ne s'affectent jamais.
echo.
echo    Si un fichier Word structuré (Doc.2) est fourni par l'utilisateur,
echo    ses tableaux sont placés dans cette feuille avec la même mise en
echo    forme que "Borniers" (pagination, pieds de page, marges A4).
echo.
echo    converter.py maintient word_results séparé de ocr_results et
echo    transmet : generer_excel(ocr_results, extractor, chemin,
echo                             word_results=word_results)
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   8/10 — IMPORT DE TABLEAUX WORD ET MODÈLES DE TABLEAU
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  ── IMPORT DEPUIS WORD (word_table_importer.py) ──
echo.
echo  L'utilisateur peut fournir un SECOND fichier Word (Doc.2) contenant
echo  des tableaux déjà proprement structurés (pas des images, de vrais
echo  tableaux Word). Ces tableaux sont importés et placés dans la feuille
echo  "tableaux word" du classeur Excel.
echo.
echo  CLASSE WordTableImporter :
echo    → Ouvre le .docx avec python-docx
echo    → Pour chaque tableau Word :
echo        - Détecte le pied de page (lignes contenant les mots-clés)
echo          en remontant depuis la fin du tableau (max 4 lignes)
echo        - Extrait l'en-tête (première ligne) et les données
echo        - Extrait les métadonnées (BORNIER, PAGE, etc.) via _extract_meta()
echo        - Retourne un dict identique au format OCR → compatible avec
echo          _fill_worksheet()
echo.
echo  ── MODÈLES DE TABLEAU (template.py) ──
echo.
echo  Un modèle définit la structure attendue d'un tableau bornier :
echo.
echo    COLONNES        : liste ordonnée des noms (ex: BORNE, COULEUR, ...)
echo    LARGEURS        : largeur en caractères de chaque colonne dans Excel
echo    SÉPARATEUR      : mot-clé des lignes de section (ex: NOM DU CABLE)
echo    PIED DE PAGE    : activation ON/OFF
echo    FORMAT PIED L1  : "{PET} BORNIER : {BORNIER}" (placeholders)
echo    FORMAT PIED L2  : "NO PLAN : {NO_PLAN}  INDICE : {INDICE}  PAGE : {PAGE}"
echo    ÉTIQUETTE GAUCHE: label de la cellule gauche fusionnée (ex: M T I)
echo.
echo  L'utilisateur peut créer, modifier et supprimer des modèles
echo  directement depuis l'interface graphique (bouton "+ Nouveau modèle").
echo  Les modèles sont sauvegardés dans un fichier JSON local.
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   9/10 — INTERFACE GRAPHIQUE ET CONFIGURATION
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  ── INTERFACE GRAPHIQUE (interface.py) ──
echo.
echo  L'interface est construite avec Tkinter (bibliothèque graphique
echo  standard Python). Elle comprend :
echo.
echo    SECTION FICHIERS :
echo      Doc.1 : fichier Word source contenant les IMAGES de borniers
echo      Doc.2 : fichier Word optionnel avec TABLEAUX structurés
echo      Destination : dossier de sortie pour les fichiers générés
echo.
echo    SECTION MODÈLE :
echo      Sélecteur de modèle de tableau (liste déroulante)
echo      Boutons : Nouveau modèle / Modifier / Supprimer
echo.
echo    BARRE DE PROGRESSION :
echo      Affiche le pourcentage d'avancement et le message d'étape courante
echo      Mise à jour depuis un thread séparé via une file d'attente (Queue)
echo.
echo    JOURNAL D'EXÉCUTION :
echo      Zone de texte scrollable affichant tous les événements :
echo      images extraites, OCR en cours, tableaux trouvés, erreurs...
echo      Les messages sont colorés : vert (succès), rouge (erreur),
echo      jaune (avertissement), gris (information)
echo.
echo    BOUTONS DE RÉSULTAT (actifs après conversion) :
echo      Excel  : ouvre le fichier tous_les_borniers.xlsx
echo      Word   : ouvre le fichier tous_les_borniers.docx
echo      Dossier: ouvre le dossier de destination dans l'Explorateur
echo.
echo  ── CONFIGURATION (config.py) ──
echo.
echo    TESSERACT_PATH  : chemin vers tesseract.exe
echo                      ex: C:\Tesseract\TesseractOCR\tesseract.exe
echo    OCR_LANGUAGE    : langue OCR (fra = français)
echo    STATION_NAME    : nom P.E.T. de repli si l'OCR échoue
echo    PAGE_SIZE       : lignes par page A4 (défaut: 48)
echo    MIN_DATA_ROWS   : lignes minimum pour valider un bornier (défaut: 1)
echo.
pause >nul

cls
echo.
echo  ═══════════════════════════════════════════════════════════════════════
echo   10/10 — COMMANDES CLAUDE CODE (SKILLS)
echo  ═══════════════════════════════════════════════════════════════════════
echo.
echo  Des commandes slash sont disponibles dans Claude Code pour ce projet.
echo  Elles s'utilisent en tapant /nom-de-la-commande dans le chat.
echo.
echo  ── MAINTENANCE QUOTIDIENNE ──
echo.
echo    /corriger-ocr        Ajouter une correction dans data_dictionary.json
echo                         ex: colonne COULEUR, "ROUSE" → "ROUGE"
echo.
echo    /nouveau-template    Créer un nouveau modèle de tableau pas-à-pas
echo                         (colonnes, pied de page, séparateur de section)
echo.
echo    /changer-config      Modifier un paramètre de config.py
echo                         (Tesseract, PAGE_SIZE, STATION_NAME, etc.)
echo.
echo    /debug-bornier       Analyser pourquoi une image est mal lue par l'OCR
echo.
echo    /nettoyer-projet     Supprimer fichiers temporaires (3 niveaux)
echo.
echo  ── AGENT INGÉNIEUR — ANALYSE ET DIAGNOSTIC ──
echo.
echo    /analyser-qualite-ocr  Évalue toutes les images : flou, résolution,
echo                           métadonnées manquantes. Classe par priorité.
echo.
echo    /valider-classeur      Vérifie l'intégrité de l'Excel : pagination,
echo                           pieds de page, zones d'impression, feuilles.
echo.
echo    /diagnostiquer-env     Contrôle Python, dépendances, Tesseract,
echo                           langue fra.traineddata, fichiers critiques.
echo.
echo    /audit-borniers        Cohérence métier : doublons de PAGE, séquence,
echo                           codes BORNIER, station P.E.T. uniforme.
echo.
echo    /optimiser-tesseract   Mesure flou/contraste/résolution des images
echo                           et propose des ajustements Tesseract ciblés.
echo.
echo    /alimenter-dictionnaire Import corrections depuis un Excel corrigé
echo                           manuellement vers data_dictionary.json.
echo.
echo  ── LIVRAISON ET VERSION ──
echo.
echo    /rapport-livraison    Rapport complet avant remise au client
echo                          (stats, contrôles qualité, fichiers produits).
echo.
echo    /build-exe            Compile TriosSeconverter.exe avec PyInstaller.
echo.
echo    /tester               Lance pytest et analyse les échecs en français.
echo.
echo    /nouvelle-version     Badge UI + historique CLAUDE.md + tag Git + exe.
echo.
echo  Les définitions de ces commandes sont dans : .claude\commands\
echo.
pause >nul

cls
echo.
echo  ╔══════════════════════════════════════════════════════════════════════╗
echo  ║                        RÉSUMÉ DU PIPELINE                          ║
echo  ╚══════════════════════════════════════════════════════════════════════╝
echo.
echo   [Word source] ──► ImageExtractor ──► images_borniers/
echo         │                                      │
echo         │                                      ▼
echo         │                            BornierTableExtractor
echo         │                              _preprocess()
echo         │                              _ocr_elements()      ← Tesseract
echo         │                              _group_lines()
echo         │                              _find_header_idx()
echo         │                              _col_boundaries()
echo         │                              _classify_line()
echo         │                              _line_to_cells()
echo         │                              _extract_meta()
echo         │                                      │
echo   [Word tableaux] ──► WordTableImporter ───────┤
echo                       (Doc.2 optionnel)         │
echo                                                 ▼
echo                                         generer_excel()
echo                                          Feuille "Borniers"      ← OCR
echo                                          Feuille "tableaux word" ← Word
echo                                                 │
echo                                         generer_word()
echo                                          tous_les_borniers.docx  ← OCR
echo.
echo  ══════════════════════════════════════════════════════════════════════
echo   Fichiers générés dans le dossier de destination :
echo     tous_les_borniers.xlsx   → classeur Excel (2 feuilles)
echo     tous_les_borniers.docx   → document Word combiné
echo     images_borniers/         → images extraites du document source
echo  ══════════════════════════════════════════════════════════════════════
echo.
echo   Documentation complète : PROCESSUS_OCR.md
echo.
echo   Appuyez sur une touche pour fermer...
pause >nul
