"""
Moteur OCR Claude Vision — extraction de tableaux via l'API Anthropic.

Activer avec Config.OCR_MODE = "claude".
Retourne le même format que BornierTableExtractor.extract().
"""

import base64
import datetime
import json
import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_api_log_path: Optional[Path] = None


def set_api_log_path(path: Optional[Path]) -> None:
    """Définit le fichier JSONL où les réponses brutes Claude seront consignées."""
    global _api_log_path
    _api_log_path = path


def _write_api_log(entry: dict) -> None:
    if _api_log_path is None:
        return
    try:
        with open(_api_log_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


_MEDIA_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png',  '.gif':  'image/gif',
    '.webp': 'image/webp',
}


def _encode_image(image_path: Path):
    """Retourne (base64_data, media_type) pour l'image."""
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower(), 'image/png')
    with open(image_path, 'rb') as f:
        return base64.standard_b64encode(f.read()).decode('utf-8'), media_type


def _preparer_image_claude(image_path: Path, max_px: int):
    """Image prête pour Claude : PNG, grand côté ≤ max_px. Retourne (base64, media_type).

    Séparée de _encode_image, que partagent Ollama et l'agent : seuls les envois
    à Claude sont réduits et convertis.
    """
    import io

    from PIL import Image
    with Image.open(image_path) as img:
        if img.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA'):
            img = img.convert('RGB')
        if max(img.size) > max_px:
            rapport = max_px / max(img.size)
            taille = (max(1, round(img.width * rapport)), max(1, round(img.height * rapport)))
            img = img.resize(taille, Image.LANCZOS)
        tampon = io.BytesIO()
        img.save(tampon, format='PNG')
    return base64.standard_b64encode(tampon.getvalue()).decode('utf-8'), 'image/png'


_EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')


def _parametres_modele(model: str) -> dict:
    """Paramètres de réflexion et d'effort à passer pour ce modèle.

    Décidés par Config.CLAUDE_CAPACITES_MODELES. Lève ValueError, avec un
    message clair, pour un modèle absent de la table ou une combinaison que
    l'API refuserait par une erreur 400.
    """
    from config import Config
    capacites = getattr(Config, 'CLAUDE_CAPACITES_MODELES', {}).get(model)
    if capacites is None:
        connus = ', '.join(getattr(Config, 'CLAUDE_CAPACITES_MODELES', {}))
        raise ValueError(
            f"Modèle {model!r} absent de CLAUDE_CAPACITES_MODELES (config.py) : "
            f"ajoutez-le à la table ou choisissez parmi : {connus}."
        )
    parametres: dict = {}
    reflexion = getattr(Config, 'CLAUDE_THINKING', 'disabled')
    effort = getattr(Config, 'CLAUDE_EFFORT', 'medium')
    if capacites.get('effort'):
        if effort not in _EFFORTS:
            raise ValueError(
                f"CLAUDE_EFFORT = {effort!r} non reconnu : "
                f"valeurs possibles {', '.join(_EFFORTS)}."
            )
        parametres['output_config'] = {'effort': effort}
    if capacites.get('thinking'):
        if reflexion not in ('disabled', 'adaptive'):
            raise ValueError(
                f"CLAUDE_THINKING = {reflexion!r} non reconnu : "
                "utilisez \"disabled\" ou \"adaptive\"."
            )
        if reflexion == 'disabled' and effort in ('xhigh', 'max'):
            raise ValueError(
                f"CLAUDE_EFFORT = \"{effort}\" est refusé quand CLAUDE_THINKING = \"disabled\" "
                "(l'API répondrait par une erreur 400). Mettez CLAUDE_EFFORT à \"high\" ou "
                "moins, ou CLAUDE_THINKING à \"adaptive\"."
            )
        parametres['thinking'] = {'type': reflexion}
    return parametres


def _limite_tokens(parametres: dict) -> int:
    """max_tokens de la requête : relevé à effort xhigh / max (réponse plus longue)."""
    from config import Config
    effort = parametres.get('output_config', {}).get('effort')
    if effort in ('xhigh', 'max'):
        return getattr(Config, 'CLAUDE_MAX_TOKENS_EFFORT_ELEVE', 64000)
    return getattr(Config, 'CLAUDE_MAX_TOKENS', 16000)


def _texte_reponse(response) -> str:
    """Concatène les blocs texte : le premier bloc peut être un bloc de réflexion."""
    return ''.join(b.text for b in response.content if b.type == 'text')


def _consommation(response) -> dict:
    """Tokens consommés par un appel, pour le journal."""
    usage = response.usage
    return {
        'input_tokens': getattr(usage, 'input_tokens', 0) or 0,
        'output_tokens': getattr(usage, 'output_tokens', 0) or 0,
        'cache_read_input_tokens': getattr(usage, 'cache_read_input_tokens', 0) or 0,
        'cache_creation_input_tokens': getattr(usage, 'cache_creation_input_tokens', 0) or 0,
    }


def _build_prompt(template) -> str:
    """
    Construit le prompt pipe-séparé pour tous les templates.

    Format de sortie attendu de Claude :
      val1 | val2 | val3 | val4
      META: {"PAGE": "", "BORNIER": "", ...}

    L'assignation est PUREMENT POSITIONNELLE :
    - avant la 1ère barre  → colonne 1
    - entre barre 1 et 2   → colonne 2
    - ...
    - après la dernière    → colonne N
    Aucune interprétation sémantique, aucune correction post-API.
    """
    from config import Config
    marqueur = getattr(Config, 'MARQUEUR_ILLISIBLE', '??')
    columns = template.columns
    n_cols = len(columns)

    footer_fields = getattr(template, 'footer_extract_fields', [])
    footer_keys = [fd.get('key', '') for fd in footer_fields if fd.get('key')]
    base_meta = ['PAGE', 'BORNIER', 'PET', 'NO_PLAN', 'INDICE']
    all_meta_keys = base_meta + [k for k in footer_keys if k not in base_meta]
    meta_json = ', '.join(f'"{k}": ""' for k in all_meta_keys)

    section_kw = getattr(template, 'section_keyword', 'NOM DU CABLE')
    footer_kws_str = "SIEMENS, ALSTOM, MTI, CABLE, N° PLAN, NO PLAN, INDICE, PAGE, P.E.T, BORNIER"
    footer_detect = getattr(template, 'footer_detect_keywords', [])
    if footer_detect:
        footer_kws_str += ', ' + ', '.join(footer_detect[:6])

    col_zones = ' | '.join(columns)
    example_line = ' | '.join('valeur_' + c for c in columns)

    # Règles positionnelles explicites selon le nombre de colonnes du template
    rules = []
    for i, col in enumerate(columns):
        if i == 0:
            rules.append(f"  • AVANT la 1ère barre verticale            → colonne 1 : {col}")
        elif i == n_cols - 1:
            rules.append(f"  • APRÈS la {i}{'ère' if i == 1 else 'ème'} barre verticale"
                         f"             → colonne {i+1} : {col}")
        else:
            rules.append(f"  • Entre la {i}ère et {i+1}ème barre verticale"
                         f"       → colonne {i+1} : {col}")
    rules_str = '\n'.join(rules)

    return (
        "Tu analyses une image issue d'un document électrique industriel.\n\n"
        "ÉTAPE 1 — TYPE DE PAGE (première ligne obligatoire) :\n"
        "  TYPE_PAGE: listing      ← la page contient un tableau de câblage /\n"
        "                             bornier avec des colonnes de données électriques\n"
        "  TYPE_PAGE: non-listing  ← page de garde, feuille de modifications /\n"
        "                             révisions, table des matières, schéma,\n"
        "                             texte descriptif sans tableau de données\n"
        "En cas de doute, choisis listing.\n"
        "Si non-listing : écris uniquement la ligne META ci-dessous,"
        " sans aucune ligne de données. Si la page porte un tableau des révisions"
        " (indices, éditions), ajoute une ligne REVISIONS: suivie des indices lus"
        " dans sa 1re colonne, séparés par des espaces (ex : REVISIONS: 00 A 02 R R1 TP1)."
        "\n\n"
        "ÉTAPE 2 — EXTRACTION (seulement si TYPE_PAGE: listing) :\n"
        f"Colonnes dans l'ordre visuel (de gauche à droite) : {col_zones}\n\n"
        "RÈGLE FONDAMENTALE — INSERTION PAR POSITION :\n"
        "Les colonnes sont délimitées par les barres verticales visibles dans l'image. et non les trop rand espace visible \n"
        "Recopie EXACTEMENT ce que tu lis dans chaque colonne, sans interpréter ni corriger :\n"
        f"{rules_str}\n\n"
        f"Pour chaque ligne de données visible, écris sur une seule ligne :\n"
        f"  {example_line}\n\n"
        "Règles :\n"
        f"- Si un caractère est illisible, écris {marqueur} à sa place. Ne devine jamais,"
        " ne corrige jamais un mot, recopie exactement.\n"
        "- Une ligne visuelle = une ligne de sortie\n"
        "- Cellule vide = rien entre les pipes (ex : \"val1 | | val3 | val4\")\n"
        "- Si une cellule contient plusieurs sous-parties visuelles,"
        " concatène-les avec un espace\n"
        f"- Ne pas inclure l'en-tête ni les lignes de pied de page ({footer_kws_str})\n"
        f"- Ne pas inclure les lignes de séparation '{section_kw}'\n\n"
        f"Après TOUTES les lignes de données, ajoute une ligne :\n"
        f"META: {{{meta_json}}}\n"
        "avec les valeurs trouvées dans le pied de page.\n"
        "PAGE : recopie le numéro exactement comme imprimé, lettre finale comprise"
        " (ex : 122a, 44B) ; ne le déduis jamais des pages voisines.\n"
        "Puis recopie le pied de page exactement comme il est imprimé, une ligne de"
        " sortie par ligne du document, chacune précédée de PIED_BRUT: — tous les"
        " libellés, toutes les valeurs et tout texte libre (ex : REF CE 8707905, 8/10),"
        " sans rien omettre, corriger ni réordonner :\n"
        "PIED_BRUT: <1re ligne du pied>\n"
        "PIED_BRUT: <2e ligne du pied>\n"
    )


_FOOTER_MARKERS = frozenset([
    'SIEMENS', 'ALSTOM', 'SCHNEIDER', 'ABB', 'LEGRAND', 'MTI',
    'CABLE :', 'CABLE:', 'N° PLAN', 'NO PLAN', 'NO.PLAN',
    'INDICE :', 'INDICE:', 'PAGE :', 'PAGE:',
    'P.E.T', 'PET :', 'BORNIER :',
])


def _is_footer_row(cells: List[str]) -> bool:
    """Retourne True si la ligne ressemble à un pied de page plutôt qu'à une donnée."""
    joined = ' '.join(cells).upper()
    # Une ligne pied de page a typiquement beaucoup de colonnes vides
    non_empty = [c for c in cells if c.strip()]
    if len(non_empty) == 1 and len(cells) >= 3:
        val = non_empty[0].upper()
        # Valeur unique qui contient un marqueur de pied
        if any(m in val for m in _FOOTER_MARKERS):
            return True
    # Deux valeurs dont l'une contient "CABLE :" ou "N° PLAN"
    if any(m in joined for m in _FOOTER_MARKERS):
        return True
    return False


def _detect_ambiguous_segments(raw: str, n_cols: int) -> Optional[List[str]]:
    """Retourne les segments de la 1ère ligne de données avec plus de
    segments pipe que de colonnes template, ou None si aucune ambiguïté."""
    for line in raw.splitlines():
        line = line.strip()
        if not line or '|' not in line:
            continue
        if line.upper().startswith(('TYPE_PAGE:', 'META:')):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) > n_cols:
            return parts
    return None


def _parse_pipe_response(raw: str, template, column_mapping: dict = None) -> tuple:
    """
    Parse une réponse Claude au format pipe-separated.

    Format attendu :
      TYPE_PAGE: listing
      val1 | val2 | val3 | val4
      ...
      META: {"PAGE": "77", "BORNIER": "...", ...}

    Retourne (rows, metadata, page_type).
    page_type vaut 'listing' (défaut) ou 'non-listing'.
    """
    col_names = template.columns
    n_cols = len(col_names)
    rows: List[Dict] = []
    metadata: Dict = {}
    pied_brut: List[str] = []
    revisions: List[str] = []
    page_type = 'listing'  # défaut : on extrait

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ligne de classification de page (étape 1 du prompt)
        if line.upper().startswith('TYPE_PAGE:'):
            val = line[10:].strip().lower()
            if 'non' in val or 'autre' in val or 'cover' in val or 'modif' in val:
                page_type = 'non-listing'
            continue
        # Avant le test du « | » : une ligne de pied recopiée peut en contenir.
        if line.upper().startswith('PIED_BRUT:'):
            pied_brut.append(line[len('PIED_BRUT:'):].strip())
            continue
        if line.upper().startswith('REVISIONS:'):
            revisions = line[len('REVISIONS:'):].split()
            continue
        # Ligne métadonnées
        if line.upper().startswith('META:'):
            meta_str = line[5:].strip()
            try:
                parsed_meta = json.loads(meta_str)
                metadata = {k: str(v).strip() for k, v in parsed_meta.items() if v}
            except Exception:
                # Tentative de parse partiel si JSON invalide
                try:
                    # Chercher un objet JSON dans la ligne
                    m = re.search(r'\{.*\}', meta_str, re.DOTALL)
                    if m:
                        parsed_meta = json.loads(m.group(0))
                        metadata = {k: str(v).strip() for k, v in parsed_meta.items() if v}
                except Exception:
                    pass
            continue
        # Ligne de données : doit contenir au moins un |
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < n_cols:
            # Trop peu de segments : compléter avec des vides
            while len(parts) < n_cols:
                parts.append('')
            cells = parts[:n_cols]
        elif len(parts) == n_cols:
            cells = parts
        elif column_mapping:
            # Mapping validé par l'utilisateur (segment→colonne) — remplace
            # l'heuristique de fusion automatique ci-dessous.
            cells = [
                ' '.join(
                    parts[i] for i in column_mapping.get(col, [])
                    if 0 <= i < len(parts)
                ).strip()
                for col in col_names
            ]
        else:
            # Plus de segments que de colonnes : surplus dans l'avant-dernière colonne.
            # Règle physique : col[0..n-3] mapping direct,
            #                  col[n-2] (SIGNAL) absorbe tous les segments intermédiaires,
            #                  col[n-1] (JARRETIERES) reçoit le dernier segment.
            # Exemple 5 segs / 4 cols :
            #   B16T 01A | 0057R | B702A | 01H | FSa22-38
            #   → BORNE='B16T 01A' COULEUR='0057R'
            #     SIGNAL='B702A 01H'  JARRETIERES='FSa22-38'
            cells = list(parts[:n_cols - 2])
            mid = parts[n_cols - 2:-1]
            cells.append(' '.join(p for p in mid if p))
            cells.append(parts[-1])
        if not any(cells):
            continue
        if _is_footer_row(cells):
            continue
        rows.append({
            'type': 'data',
            'cells': cells,
            'confidence': [100] * n_cols,
            'raw': line,  # segments originaux conservés pour le mode hybride
        })

    if pied_brut:
        metadata = _structurer_pied(pied_brut, metadata, template)
    if revisions:
        metadata['REVISIONS'] = revisions
    return rows, metadata, page_type


def _structurer_pied(pied_brut: List[str], meta_json: Dict, template) -> Dict:
    """Pied recopié par Claude, structuré localement comme une page vectorielle.

    Claude recopie, le code structure : les paires du pied recopié priment. Le
    JSON META ne complète que les libellés absents du pied recopié ; un
    désaccord n'est jamais tranché en silence, il devient une alerte.
    """
    from pied_page import analyser_pied, mots_decor, nettoyer_lignes_pied
    propres = nettoyer_lignes_pied(pied_brut, getattr(template, 'footer_left_label', ''))
    decor = mots_decor([getattr(template, 'footer_row1_format', ''),
                        getattr(template, 'footer_row2_format', '')])
    structure = analyser_pied(propres, decor=decor)
    alertes = []
    for cle, valeur in meta_json.items():
        if cle not in structure:
            continue
        lu, recopie = _sans_espaces(valeur), _sans_espaces(structure[cle])
        # « TYPE : 2P.279 8/10 » dans le JSON = TYPE + COMPLEMENT du pied recopié.
        avec_complement = recopie + _sans_espaces(structure.get('COMPLEMENT', ''))
        if lu not in (recopie, avec_complement):
            alertes.append(f"{cle} : META « {valeur} », pied recopié « {structure[cle]} »"
                           " — pied recopié retenu")
    fusion = {k: v for k, v in meta_json.items() if k not in structure}
    fusion.update(structure)
    fusion['PIED_BRUT'] = propres
    if alertes:
        fusion['ALERTES_PIED'] = alertes
    return fusion


def _sans_espaces(valeur) -> str:
    return re.sub(r'\s+', '', str(valeur or '')).upper()


class ClaudeVisionExtractor:
    """Extracteur de tableaux via Claude Vision API (Anthropic)."""

    def __init__(self, template, on_column_mapping: Optional[Callable] = None):
        self._tpl = template
        # Mapping manuel segment→colonne — demandé quand Claude renvoie plus
        # de segments pipe que de colonnes template. Mis en cache par run
        # (même clé de segments) pour ne pas resolliciter à chaque page.
        self._on_column_mapping = on_column_mapping
        self._cached_column_mapping: Optional[dict] = None
        self._cached_mapping_key = None

    def _resoudre_mapping_segments(self, raw: str, image_path) -> Optional[dict]:
        """Déclenche (ou réutilise depuis le cache) le mapping manuel
        segment→colonne quand la réponse a plus de segments que de colonnes."""
        n_cols = len(self._tpl.columns)
        ambiguous = _detect_ambiguous_segments(raw, n_cols)
        if not ambiguous or self._on_column_mapping is None:
            return None
        cache_key = (tuple(self._tpl.columns), len(ambiguous))
        if cache_key == self._cached_mapping_key:
            return self._cached_column_mapping
        candidate_blocks = [
            {'text': seg, 'x': i, 'x2': i + 1} for i, seg in enumerate(ambiguous)
        ]
        mapping = self._on_column_mapping(
            candidate_blocks, list(self._tpl.columns), image_path
        )
        self._cached_column_mapping = mapping
        self._cached_mapping_key = cache_key
        return mapping

    def extract(
        self,
        image_path: Path,
        feedback: str = None,
        context_data: str = None,
    ) -> Dict:
        """
        Envoie l'image à Claude Vision et retourne le dict structuré.

        Même format de retour que BornierTableExtractor.extract() :
          success, headers, rows, metadata, image_path, detection_method

        feedback     : commentaire de l'utilisateur, ajouté en tête de prompt.
        context_data : données Ollama déjà classées en colonnes (mode hybride v4).
                       Claude corrige uniquement les erreurs de caractères —
                       il ne reclassifie pas les colonnes.
        """
        from config import Config

        try:
            import anthropic
        except ImportError:
            return {
                'success': False,
                'error': (
                    "Package 'anthropic' non installé.\n"
                    "Lancez : pip install anthropic"
                ),
            }

        api_key = getattr(Config, 'CLAUDE_API_KEY', '').strip()
        if not api_key:
            return {
                'success': False,
                'error': (
                    "Clé API Claude manquante.\n"
                    "Renseignez votre clé dans l'interface ou dans config.py"
                    " (CLAUDE_API_KEY)."
                ),
            }

        model = getattr(Config, 'CLAUDE_OCR_MODEL', 'claude-opus-5')
        try:
            parametres = _parametres_modele(model)
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        try:
            image_data, media_type = _preparer_image_claude(
                image_path, getattr(Config, 'CLAUDE_IMAGE_MAX_PX', 2576),
            )
        except Exception as e:
            return {'success': False, 'error': f"Lecture image impossible : {e}"}

        if context_data:
            # Mode hybride v4 : Ollama a déjà classé les colonnes.
            # Claude corrige uniquement les caractères mal lus.
            col_names = ' | '.join(self._tpl.columns)
            n_cols = len(self._tpl.columns)
            all_meta = ['PAGE', 'BORNIER', 'PET', 'NO_PLAN', 'INDICE']
            footer_fields = getattr(self._tpl, 'footer_extract_fields', [])
            for fd in footer_fields:
                k = fd.get('key', '')
                if k and k not in all_meta:
                    all_meta.append(k)
            meta_json = ', '.join(f'"{k}": ""' for k in all_meta)
            prompt = (
                "TYPE_PAGE: listing\n\n"
                "DONNÉES EXTRAITES PAR OLLAMA "
                "(classification visuelle des colonnes déjà réalisée) :\n"
                "──────────────────────────────────────────────────────────\n"
                f"{context_data}\n"
                "──────────────────────────────────────────────────────────\n\n"
                "TON RÔLE UNIQUE — CORRECTION DES CARACTÈRES :\n"
                "La classification des colonnes d'Ollama est DÉJÀ CORRECTE.\n"
                "Ne change ni l'ordre ni l'attribution des colonnes.\n\n"
                "Pour chaque ligne, regarde l'image et corrige uniquement les\n"
                "erreurs de lecture OCR :\n"
                "  • confusion de caractères (O↔0, l↔1, S↔5, B↔8, rn↔m…)\n"
                "  • caractères manquants ou en trop\n"
                "  • casse si clairement visible\n\n"
                "Règles de sortie OBLIGATOIRES :\n"
                f"1. Il y a exactement {n_cols} colonnes : {col_names}\n"
                "2. UNE ligne de sortie par ligne de données, dans le MÊME ORDRE.\n"
                "3. Format pipe strict :  val1 | val2 | val3 | val4\n"
                "4. Si Ollama a omis une ligne visible dans l'image, ajoute-la.\n"
                "5. Après TOUTES les lignes de données, ajoute :\n"
                f"   META: {{{meta_json}}}\n"
                "   avec les valeurs lues dans le pied de page de l'image.\n"
            )
            logger.info(
                f"Claude Vision — mode correction Ollama "
                f"({len(context_data.splitlines())} lignes) : {image_path.name}"
            )
        elif feedback:
            # Le feedback est placé EN TÊTE du prompt : Claude lit de haut en bas
            # et donne plus de poids aux instructions placées en premier.
            prompt = (
                "⚠ CORRECTION REQUISE — À LIRE EN PRIORITÉ ABSOLUE :\n"
                f"{feedback}\n"
                "Applique cette correction sur l'image avant toute autre règle.\n\n"
                + _build_prompt(self._tpl)
            )
            logger.info(
                f"Claude Vision — feedback inclus "
                f"({len(feedback)} car.) : {image_path.name}"
            )
        else:
            prompt = _build_prompt(self._tpl)

        max_tokens = _limite_tokens(parametres)
        requete = dict(
            model=model,
            max_tokens=max_tokens,
            **parametres,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type':       'base64',
                            'media_type': media_type,
                            'data':       image_data,
                        },
                    },
                    {'type': 'text', 'text': prompt},
                ],
            }],
        )
        try:
            client = anthropic.Anthropic(api_key=api_key)
            # Ni temperature, ni top_p, ni top_k : refusés (erreur 400) par Opus 5.
            if max_tokens > getattr(Config, 'CLAUDE_MAX_TOKENS', 16000):
                # Le SDK refuse sans streaming une requête estimée à plus de 10 min
                # (au-delà de ~21 000 tokens) ; le message final est le même objet.
                with client.messages.stream(**requete) as flux:
                    response = flux.get_final_message()
            else:
                response = client.messages.create(**requete)
        except Exception as e:
            _write_api_log({
                'ts':      datetime.datetime.now().isoformat(timespec='seconds'),
                'image':   image_path.name,
                'model':   getattr(Config, 'CLAUDE_OCR_MODEL', '?'),
                'error':   str(e),
                'success': False,
            })
            return {'success': False, 'error': f"Appel API Claude échoué : {e}"}

        raw = _texte_reponse(response)
        usage = _consommation(response)
        modele_servi = getattr(response, 'model', model)
        logger.info(
            f"Claude {modele_servi} — {image_path.name} : "
            f"{usage['input_tokens']} tokens en entrée, {usage['output_tokens']} en sortie"
        )
        if response.stop_reason == 'refusal':
            details = getattr(response, 'stop_details', None)
            categorie = getattr(details, 'category', None) or 'non précisée'
            explication = getattr(details, 'explanation', None) or ''
            logger.warning(
                f"Claude a refusé {image_path.name} — catégorie : {categorie}"
                + (f" ({explication})" if explication else '')
            )
            _write_api_log({
                'ts':        datetime.datetime.now().isoformat(timespec='seconds'),
                'image':     image_path.name,
                'model':     modele_servi,
                'usage':     usage,
                'error':     'refus du modèle',
                'categorie': categorie,
                'explication': explication,
                'success':   False,
            })
            return {
                'success': False,
                'error': f"Claude a refusé la page {image_path.name} (catégorie : {categorie})",
                'api_usage': dict(usage, model=modele_servi),
            }
        if response.stop_reason == 'max_tokens':
            # Les dernières lignes de la page manqueraient sans que rien ne le signale.
            logger.error(
                f"Réponse tronquée (limite de {max_tokens} tokens atteinte) : {image_path.name}"
            )
            _write_api_log({
                'ts':         datetime.datetime.now().isoformat(timespec='seconds'),
                'image':      image_path.name,
                'model':      modele_servi,
                'usage':      usage,
                'max_tokens': max_tokens,
                'raw':        raw,
                'error':      'reponse tronquee',
                'success':    False,
            })
            return {
                'success': False,
                'error': (
                    f"Réponse tronquée pour {image_path.name} : limite de {max_tokens} "
                    "tokens atteinte, page non convertie"
                ),
                'api_usage': dict(usage, model=modele_servi),
            }
        # Parseur pipe-séparé unique — insertion positionnelle pour tous les templates
        try:
            column_mapping = self._resoudre_mapping_segments(raw, image_path)
            rows, metadata, page_type = _parse_pipe_response(
                raw, self._tpl, column_mapping=column_mapping
            )
        except ValueError as e:
            _write_api_log({
                'ts':      datetime.datetime.now().isoformat(timespec='seconds'),
                'image':   image_path.name,
                'model':   modele_servi,
                'usage':   usage,
                'error':   str(e),
                'success': False,
            })
            return {'success': False, 'error': str(e)}

        # Page de garde / modifications / sommaire → ignorer proprement
        if page_type == 'non-listing':
            logger.info(
                f"⊘ Page non-listing ignorée : {image_path.name}"
            )
            _write_api_log({
                'ts':       datetime.datetime.now().isoformat(timespec='seconds'),
                'image':    image_path.name,
                'model':    modele_servi,
                'usage':    usage,
                'raw':      raw,
                'rows':     0,
                'metadata': metadata,
                'success':  False,
                'error':    'non-listing',
            })
            return {
                'success': False,
                'error':   'Page ignorée (page de garde / modifications / sommaire)',
                'image_path': str(image_path),
                'metadata': metadata,
                'detection_method': 'claude-vision',
                'api_usage': dict(usage, model=modele_servi),
            }

        logger.info(
            f"✓ Claude Vision : {len(rows)} lignes depuis {image_path.name} "
            f"(modèle {modele_servi})"
        )
        _write_api_log({
            'ts':        datetime.datetime.now().isoformat(timespec='seconds'),
            'image':     image_path.name,
            'model':     modele_servi,
            'usage':     usage,
            'raw':       raw,
            'rows':      len(rows),
            'rows_data': rows,      # données déjà parsées — utilisées par LogReplayer
            'metadata':  metadata,
            'success':   True,
        })
        return {
            'success':          True,
            'headers':          self._tpl.columns,
            'rows':             rows,
            'metadata':         metadata,
            'image_path':       str(image_path),
            'blur_pct':         0.0,
            'detection_method': 'claude-vision',
            'api_usage':        dict(usage, model=modele_servi),
        }


class LogReplayer:
    """
    Rejoue un fichier claude_api_log.jsonl sans appeler l'API Claude.

    Lit les réponses brutes enregistrées lors d'une conversion précédente,
    les re-parse avec _parse_pipe_response() et retourne des résultats
    dans le même format que ClaudeVisionExtractor.extract().
    Permet de régénérer l'Excel sans dépenser de tokens.
    """

    def __init__(self, log_path: Path, template):
        self._log_path = Path(log_path)
        self._tpl = template

    def load_entries(self) -> List[Dict]:
        """Lit toutes les entrées JSONL (succès et erreurs)."""
        entries = []
        try:
            with open(self._log_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as exc:
            logger.error(f"Impossible de lire le log : {exc}")
        return entries

    def replay_all(self) -> List[Dict]:
        """Retourne la liste de résultats depuis le log, sans appeler l'API.

        Déduplication par image : si une page a fait l'objet de N retries,
        le log contient N entrées pour le même fichier image. On conserve
        uniquement la DERNIÈRE entrée réussie par image — c'est celle que
        l'utilisateur a validée (le retry final).

        Priorité des sources de données (de la plus fidèle à la moins fidèle) :
          1. rows_data  — données déjà parsées lors de l'extraction originale.
                          Résultat IDENTIQUE à l'Excel d'origine garanti.
          2. raw        — réponse brute re-parsée (fallback pour anciens logs
                          qui ne contiennent pas rows_data).
        """
        # Grouper par image : clé = nom du fichier image.
        # On parcourt le log dans l'ordre chronologique. Pour chaque image,
        # on écrase l'entrée précédente dès qu'une nouvelle entrée réussie
        # apparaît → à la fin, chaque clé pointe vers la dernière tentative
        # réussie (= le résultat accepté par l'utilisateur).
        seen: Dict[str, dict] = {}     # image_name → dernière entrée success
        seen_fail: Dict[str, dict] = {}  # image_name → dernière entrée failed
        _idx = [0]

        for entry in self.load_entries():
            # Clé unique : nom du fichier image, ou indice séquentiel si absent
            img_key = entry.get('image') or f'__seq_{_idx[0]}'
            _idx[0] += 1
            if entry.get('success'):
                seen[img_key] = entry
            else:
                # Garder l'échec seulement s'il n'y a pas d'entrée réussie
                if img_key not in seen:
                    seen_fail[img_key] = entry

        # Reconstruire une liste ordonnée : toutes les clés dans l'ordre
        # d'apparition (première occurrence), en privilégiant le succès
        ordered_keys: list = []
        key_order: dict = {}
        for i, entry in enumerate(self.load_entries()):
            img_key = entry.get('image') or f'__seq_{i}'
            if img_key not in key_order:
                key_order[img_key] = i
                ordered_keys.append(img_key)

        results = []
        for img_key in ordered_keys:
            entry = seen.get(img_key) or seen_fail.get(img_key)
            if entry is None:
                continue

            if not entry.get('success'):
                results.append({
                    'success':          False,
                    'error':            entry.get('error', 'Erreur inconnue'),
                    'image_path':       entry.get('image', ''),
                    'metadata':         entry.get('metadata', {}),
                    'detection_method': 'log-replay',
                })
                continue

            metadata = entry.get('metadata', {})

            # ── Chemin 1 : données traitées stockées directement ──────
            rows_data = entry.get('rows_data')
            if rows_data:
                results.append({
                    'success':          True,
                    'headers':          self._tpl.columns,
                    'rows':             rows_data,
                    'metadata':         metadata,
                    'image_path':       entry.get('image', ''),
                    'blur_pct':         0.0,
                    'detection_method': 'log-replay',
                })
                continue

            # ── Chemin 2 : re-parsing de la réponse brute (anciens logs) ─
            raw = entry.get('raw', '')
            if not raw:
                continue
            try:
                rows, metadata, page_type = _parse_pipe_response(raw, self._tpl)
                if page_type == 'non-listing':
                    results.append({
                        'success': False,
                        'error':   'Page ignorée (page de garde / modifications / sommaire)',
                        'image_path': entry.get('image', ''),
                        'metadata': metadata,
                        'detection_method': 'log-replay',
                    })
                    continue
                results.append({
                    'success':          True,
                    'headers':          self._tpl.columns,
                    'rows':             rows,
                    'metadata':         metadata,
                    'image_path':       entry.get('image', ''),
                    'blur_pct':         0.0,
                    'detection_method': 'log-replay',
                })
            except Exception as exc:
                results.append({
                    'success':          False,
                    'error':            str(exc),
                    'image_path':       entry.get('image', ''),
                    'detection_method': 'log-replay',
                })
        return results
