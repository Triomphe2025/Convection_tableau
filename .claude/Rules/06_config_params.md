# Règle 06 — Configuration et paramètres

## Règle absolue : tout passe par config.py

**Ne jamais coder un paramètre en dur dans un autre fichier.**

```python
# INTERDIT
TESSERACT_PATH = r"C:\Tesseract\TesseractOCR\tesseract.exe"  # dans ocr_processor.py

# CORRECT
from config import Config
Config.TESSERACT_PATH   # référencer uniquement
```

## Paramètres actuels (config.py)

| Paramètre | Valeur actuelle | Rôle |
|-----------|----------------|------|
| `TESSERACT_PATH` | `C:\Tesseract\TesseractOCR\tesseract.exe` | Chemin Tesseract |
| `OCR_LANGUAGE` | `fra` | Langue Tesseract |
| `PAGE_SIZE` | `48` | Lignes par page A4 dans Excel |
| `STATION_NAME` | `EPEULE` | Nom de station des rapports ; ne remplit plus jamais le pied (P.E.T. absent = vide + alerte) |
| `MIN_DATA_ROWS` | `1` | Seuil minimal de lignes pour valider un bornier ; un tableau vide (0 ligne sous l'en-tête) est conservé |
| `PAGE_DENSITE_MIN` | `0.15` | Part minimale de cellules lisibles ; en dessous la page est écartée (gribouillage) |
| `MARQUEUR_ILLISIBLE` | `??` | Écrit par Claude à la place d'un caractère illisible (prompt) ; gardé dans l'Excel |
| `COULEUR_ILLISIBLE` | `FFC7CE` | Fond des cellules contenant le marqueur (distinct du jaune « confiance basse ») |
| `PIED_LIBELLES_UN_MOT` | `TYPE, CABLE, INDICE, PAGE, BORNIER` | Libellés à valeur d'un mot ; la suite va dans COMPLEMENT (les autres gardent tout leur segment) |
| `PIED_LIBELLES_COMPTEUR` | `PAGE, FOLIO` | Seuls libellés où « n/m » est un compteur ; ailleurs « 6/10 » est un diamètre → COMPLEMENT |
| `PIED_ENTETES_REVISIONS` | `INDICE, RÉVISION, EDITION…` | En-têtes d'un tableau des révisions (page de garde) |
| `CHAMPS_CONSTANTS_DEFAUT` | `("PET",)` | Champs constants d'un document (case vide reprise des autres pages si elles sont unanimes) |
| `CHAMPS_CONSTANTS_PAR_MODELE` | `{}` | Par nom de modèle de tableau : sa propre liste (ex. `{"REPARTITEUR": ("PET", "NO_PLAN")}`) |
| `PIED_CHAMPS_JAMAIS_DEDUITS` | `INDICE, PAGE, TYPE, CABLE` | Varient d'une page à l'autre : jamais repris, même listés |
| `COULEUR_DEDUIT` | `DDEBF7` | Fond d'une case de pied reprise des autres pages (commentaire « déduit des autres pages du document ») |
| `PIED_INDICE_MOTIF` | `[A-Z]{0,2}\d{1,2}\|[A-Z]` | Forme d'un indice de révision (A, R, 00, R10, TP2) |
| `IMAGES_FOLDER_NAME` | `VD23111 PE 162` | Nom du dossier de sortie des images |
| `OCR_MODE` | `tesseract` | Mode OCR par défaut |
| `CLAUDE_API_KEY` | `""` | Clé API Anthropic |
| `CLAUDE_AGENT_SESSION_ID` | `""` | ID session agent (le modèle de l'agent se règle côté Anthropic) |
| `CLAUDE_OCR_MODEL` | `claude-opus-5-5` | Modèle des modes claude et hybrid ; doit figurer dans `CLAUDE_CAPACITES_MODELES` |
| `CLAUDE_CAPACITES_MODELES` | table | Par modèle : `thinking` (champ envoyé selon `CLAUDE_THINKING`, ou omis) et `effort` (envoyé ou non). Haiku 4.5 : ni l'un ni l'autre ; Opus 5, Sonnet 5 : les deux ; Opus 5.5, Fable 5.1 : thinking omis (réflexion toujours active), effort envoyé |
| `CLAUDE_THINKING` | `disabled` | Réflexion des modèles où elle se règle : `disabled` ou `adaptive` |
| `CLAUDE_EFFORT` | `medium` | `low`…`max` ; `xhigh`/`max` refusés si la réflexion est envoyée désactivée |
| `CLAUDE_MAX_TOKENS` | `16000` | Limite de la réponse, réflexion comprise |
| `CLAUDE_PRIX_MODELES` | table | Prix $ par million de tokens (entrée, sortie) par modèle, pour `campagne_mesure.py` |
| `CAMPAGNE_BUDGET_MAX_USD` | `10` | Plafond d'une campagne : arrêt avant un passage si le coût cumulé l'atteint |
| `CLAUDE_MAX_TOKENS_EFFORT_ELEVE` | `64000` | Limite à effort `xhigh`/`max` (appel en streaming) ; une réponse tronquée met toujours la page en erreur |
| `CLAUDE_IMAGE_MAX_PX` | `2576` | Grand côté maximal des images envoyées à Claude (PNG) |

## Vérification de conversion (section « VÉRIFICATION DE CONVERSION »)

| Paramètre | Valeur défaut | Rôle |
|-----------|--------------|------|
| `VERIF_SEUIL_PAGE` | `0.30` | Similarité minimale pour apparier deux pages |
| `VERIF_SEUIL_LIGNE` | `0.55` | Similarité minimale pour apparier deux lignes lues différemment |
| `VERIF_DISTANCE_BENIGNE` | `2` | Écart d'au plus N caractères bénin si la confiance reste sous `VERIF_CONFIANCE_SURE` |
| `VERIF_CONFIANCE_SURE` | `90` | Confiance OCR de la référence au-delà de laquelle un écart est suspect |
| `VERIF_FUSION_ECARTS` | `3` | Zones qui diffèrent séparées de moins de N caractères identiques = un seul écart |
| `VERIF_SEUIL_PAGE_EXACTE` | `0.9` | Similarité de lignes identiques au-delà de laquelle deux pages sont appariées directement |
| `VERIF_LIGNE_BRUIT_MIN_CARS` | `3` | En dessous de N caractères alphanumériques, une ligne orpheline est du bruit |
| `VERIF_CONFUSIONS_OCR` | `0O, 1IL, 5S, T7, 8B, 2Z, .,` | Groupes de caractères repliés avant comparaison |
| `VERIF_PONCTUATION_PARASITE` | `|!‘’`"_;:` | Ponctuation ajoutée par l'OCR, ignorée avant comparaison |
| `VERIF_RELECTURE_DPI` | `300` | Rendu des pages pour la relecture indépendante du scan |
| `VERIF_RELECTURE_PSM` | `6` | Mode de segmentation Tesseract de la relecture (bloc uniforme) |
| `VERIF_RELECTURE_TOL_LIGNE` | `12` | Écart vertical (pixels) sous lequel deux mots sont sur la même ligne |
| `VERIF_MOTIF_CLE` | `^[A-Z]?[0-9]{1,3}[A-Z]?$` | Forme d'une clé de ligne : en dessous, en-tête / section / pied |
| `VERIF_REPLI_CLE` | `O→0, Q→0, I→1, L→1` | Repli des lettres lues pour des chiffres dans une clé, pour le seul test du motif |
| `VERIF_MOTS_PIED` | `P.E.T, PET, NO PLAN…` | Ligne sans clé lue écartée si elle porte un libellé de pied |
| `VERIF_SEUIL_CONCORDANCE` | `0.98` | Concordance au-dessus de laquelle la conversion est jugée fidèle |

La confiance basse réutilise `OCR_REOCR_THRESHOLD` (pas de paramètre dédié).

## Routage PDF par page (section « ROUTAGE PDF PAR PAGE »)

Dans tous les modes OCR, chaque page d'un PDF est classée (`pdf_extractor.diagnostiquer_page`) :
texte vectoriel exploitable → grille ; sinon images cumulées ≥ `PDF_SEUIL_IMAGE` → pipeline
scan ; sinon page ignorée (motif et part d'images journalisés).

| Paramètre | Valeur défaut | Rôle |
|-----------|--------------|------|
| `PDF_ROUTAGE_VECTORIEL` | `True` | `False` = comportement v1.7 |
| `PDF_SEUIL_IMAGE` | `0.10` | Images cumulées (part de page) à partir desquelles une page sans texte exploitable part en pipeline scan ; en dessous elle est ignorée |
| `PDF_SEUIL_IMAGE_PLEINE_PAGE` | `0.8` | Au-delà, un texte posé sur l'image n'est pas lu en grille (couche OCR, pas le document) |
| `PDF_MIN_CARS_VECTORIEL` | `20` | Caractères visibles minimum pour lire la page en couche texte |
| `PDF_GRILLE_TOLERANCE_Y` | `2.0` | Écart vertical (pt) sous lequel deux spans sont sur la même ligne de la grille |

## Mesure de précision (section « MESURE DE PRÉCISION »)

Outil de QA distinct de la vérification de conversion : compare une sortie à une
référence organisée à l'avance (PDF vectoriel ou Excel de vérité terrain), pas à
une relecture indépendante. Seuils **séparés** de `VERIF_*` pour ne pas perturber
le calibrage déjà fait sur `verificateur.py`.

| Paramètre | Valeur défaut | Rôle |
|-----------|--------------|------|
| `MESURE_SEUIL_PAGE` | `0.30` | Similarité minimale pour apparier deux pages par contenu |
| `MESURE_SEUIL_PAGE_EXACTE` | `0.9` | Au-delà, deux pages sont appariées sans chercher les lignes proches |
| `MESURE_CANDIDATS_PAGE` | `3` | Pages converties (les plus proches en mots) comparées finement à chaque page de référence |
| `MESURE_PENALITE_GAP` | `-0.35` | Pénalité par trou dans l'alignement Needleman-Wunsch |
| `MESURE_BONUS_APPARIEMENT` | `0.5` | Bonus retranché à la similarité de deux lignes appariées (NW) |
| `MESURE_NW_MAX_PAIRES` | `250000` | Au-delà, repli sur un appariement 1-pour-1 (NW trop coûteux) |
| `MESURE_CONFUSIONS_OCR` | paires de caractères confondus | Classification "Confusion de caractère" |
| `MESURE_CSV_PATH` | `mesures.csv` | Historique des mesures (une ligne par exécution) |
| `MESURE_LIBELLES_A_COMPLEMENT` | `("TYPE",)` | Libellés de pied suivis d'un complément en texte libre, comparé comme un champ à part au « Complement » d'une vérité |

## Ajouter un nouveau paramètre

1. Ajouter dans `Config` (class dans config.py) avec valeur par défaut
2. Documenter dans le tableau ci-dessus
3. Mettre à jour CLAUDE.md section "Configuration"
4. Utiliser `/changer-config` pour modifier via Claude Code

## Paramètres de mise en forme Excel

| Paramètre | Valeur défaut |
|-----------|--------------|
| `FORMAT_ROW_HEIGHT` | `12.6` (pt) |
| `FORMAT_COL_WIDTH_DEFAULT` | `19` (car) |
| `FORMAT_COL_WIDTH_SIGNAL` | `33` (car) |
| `FORMAT_MARGIN_TOP/BOTTOM` | `0.9` (cm) |
| `FORMAT_MARGIN_LEFT/RIGHT` | `1.75` (cm) |
| `FORMAT_MARGIN_HEADER/FOOTER` | `0.0` (cm) |

## Ressources dans l'exe PyInstaller

```python
def _resource(name: str) -> Path:
    """Résout le chemin d'une ressource — fonctionne en mode dev et en exe."""
    if hasattr(sys, '_MEIPASS'):         # Mode exe PyInstaller
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name  # Mode dev
```

Toujours passer par cette fonction pour `icon.ico` et les ressources statiques.

## Variables d'environnement Python

Configurées dans `.claude/settings.json` :
- `PYTHONIOENCODING=utf-8` — encodage obligatoire pour les PDFs et logs
- `PYTHONPATH=.` — permet d'importer les modules locaux
- `PYTHONUTF8=1` — mode UTF-8 global Python 3.7+
