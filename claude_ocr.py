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
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _erreur_reseau(exc) -> bool:
    """Erreur transitoire justifiant une nouvelle tentative : connexion, 429, 5xx, 529."""
    statut = getattr(exc, 'status_code', None)
    if statut in (429, 500, 502, 503, 529):
        return True
    return type(exc).__name__ in (
        'APIConnectionError', 'APITimeoutError', 'RateLimitError',
        'InternalServerError', 'OverloadedError', 'ServiceUnavailableError',
    )


def _enregistrer_cache(source, cache_actif, cle_cache, raw, modele_servi, id_reponse, usage):
    """Garde une lecture Claude RÉUSSIE (vrai appel seulement), page par page, de façon atomique.

    Une lecture servie par le cache (source != 'api') n'est pas réécrite. Jamais d'erreur
    bloquante : un échec d'écriture laisse simplement la page hors cache.
    """
    if source != 'api' or not cache_actif or not cle_cache:
        return
    import cache_claude
    cache_claude.ecrire(cle_cache, {
        'raw': raw,
        'model': modele_servi,
        'id_origine': id_reponse,
        'date': datetime.datetime.now().isoformat(timespec='seconds'),
        'usage_origine': usage,
        'stop_reason': 'end_turn',
    })


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

    jetons = {
        '⟦COL_ZONES⟧': col_zones, '⟦RULES⟧': rules_str, '⟦EXAMPLE⟧': example_line,
        '⟦MARQUEUR⟧': marqueur, '⟦FOOTER_KWS⟧': footer_kws_str,
        '⟦SECTION_KW⟧': section_kw, '⟦META_JSON⟧': meta_json,
    }
    gabarit = _charger_gabarit()
    for jeton, valeur in jetons.items():
        gabarit = gabarit.replace(jeton, valeur)
    return gabarit


def _charger_gabarit() -> str:
    """Gabarit de la consigne Claude : .dat encodé dans l'exe, .txt lisible en développement."""
    if getattr(sys, 'frozen', False):
        from config import chemin_ressource
        from textes_proteges import decoder_fichier
        return decoder_fichier(chemin_ressource('prompt_claude.dat'))
    return (Path(__file__).parent / 'ressources' / 'prompt_claude.txt').read_text('utf-8')


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
    logo = ''
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
        if line.upper().startswith('LOGO:'):
            logo = line[len('LOGO:'):].strip()
            continue
        if line.upper().startswith('REVISIONS:'):
            revisions = line[len('REVISIONS:'):].split()
            continue
        # Avant le filtre de pied : « NOM DU CABLE : X » contient le marqueur « CABLE : ».
        if line.upper().startswith('SECTION:'):
            texte = line[len('SECTION:'):].strip()
            if texte:
                rows.append({'type': 'section', 'text': texte})
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
        metadata = _structurer_pied(pied_brut, metadata, template, logo)
    elif logo:
        metadata['LOGO'] = logo
    if revisions:
        metadata['REVISIONS'] = revisions
    return rows, metadata, page_type


def _structurer_pied(pied_brut: List[str], meta_json: Dict, template,
                     logo: str = '') -> Dict:
    """Pied recopié par Claude, structuré localement comme une page vectorielle.

    Claude recopie, le code structure : les paires du pied recopié priment. Le
    JSON META ne complète que les libellés absents du pied recopié ; un
    désaccord n'est jamais tranché en silence, il devient une alerte.
    """
    from pied_page import analyser_pied, logo_pied, mots_decor, nettoyer_lignes_pied
    gauche = getattr(template, 'footer_left_label', '')
    propres = nettoyer_lignes_pied(pied_brut, gauche)
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
    logo_recopie = logo_pied(pied_brut, gauche)
    # Forme comparée sans les espaces : seul un texte différent est un désaccord.
    if logo and logo_recopie and _sans_espaces(logo) != _sans_espaces(logo_recopie):
        alertes.append(f"LOGO : ligne LOGO « {logo} », pied recopié « {logo_recopie} »"
                       " — ligne LOGO retenue")
    if logo or logo_recopie:
        fusion['LOGO'] = logo or logo_recopie
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

    def _prompt_page(self, feedback=None, context_data=None) -> str:
        """Prompt envoyé pour une page (mode hybride Ollama, feedback, ou standard)."""
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
            return (
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
        if feedback:
            # Le feedback est placé EN TÊTE du prompt : Claude lit de haut en bas
            # et donne plus de poids aux instructions placées en premier.
            return (
                "⚠ CORRECTION REQUISE — À LIRE EN PRIORITÉ ABSOLUE :\n"
                f"{feedback}\n"
                "Applique cette correction sur l'image avant toute autre règle.\n\n"
                + _build_prompt(self._tpl)
            )
        return _build_prompt(self._tpl)

    def cle_cache(self, image_path: Path, feedback=None, context_data=None):
        """Clé de cache de cette page (sans appel API), ou None si elle ne peut être calculée.

        Sert au pré-scan de reprise : compter les pages déjà en cache avant de lancer la lecture.
        """
        from config import Config
        try:
            import cache_claude
            model = getattr(Config, 'CLAUDE_OCR_MODEL', 'claude-opus-5')
            parametres = _parametres_modele(model)
            image_data, media_type = _preparer_image_claude(
                image_path, getattr(Config, 'CLAUDE_IMAGE_MAX_PX', 2576))
            prompt = self._prompt_page(feedback, context_data)
            return cache_claude.cle(image_data, media_type, prompt, model,
                                    parametres, _limite_tokens(parametres))
        except Exception:
            return None

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

        prompt = self._prompt_page(feedback, context_data)
        if context_data:
            logger.info(
                f"Claude Vision — mode correction Ollama "
                f"({len(context_data.splitlines())} lignes) : {image_path.name}"
            )
        elif feedback:
            logger.info(
                f"Claude Vision — feedback inclus "
                f"({len(feedback)} car.) : {image_path.name}"
            )

        max_tokens = _limite_tokens(parametres)
        bloc_image = {
            'type': 'image',
            'source': {'type': 'base64', 'media_type': media_type, 'data': image_data},
        }
        requete = dict(model=model, max_tokens=max_tokens, **parametres)
        # Consigne commune mise en cache : la page standard (ni feedback, ni données Ollama)
        # envoie la consigne EN TÊTE, en bloc `system` stable avec cache_control ; l'image suit.
        # Lecture en cache ≈ 0,05× (Opus 5.5 / Sonnet 5.5) : les pages d'un même document la
        # partagent. Feedback et mode hybride (prompt variable) gardent la structure d'avant.
        if not feedback and not context_data:
            requete['system'] = [{
                'type': 'text', 'text': prompt, 'cache_control': {'type': 'ephemeral'},
            }]
            requete['messages'] = [{'role': 'user', 'content': [bloc_image]}]
        else:
            requete['messages'] = [{
                'role': 'user',
                'content': [bloc_image, {'type': 'text', 'text': prompt}],
            }]
        # Cache : si la même demande exacte a déjà une lecture réussie, on la réutilise
        # sans appel ni coût (relance d'un document, reprise après coupure).
        cache_actif = (getattr(Config, 'CLAUDE_CACHE_LECTURES', False)
                       and not getattr(Config, 'CLAUDE_FORCER_RELECTURE', False))
        cle_cache = None
        entree_cache = None
        if cache_actif:
            import cache_claude
            cle_cache = cache_claude.cle(image_data, media_type, prompt, model,
                                         parametres, max_tokens)
            entree_cache = cache_claude.lire(cle_cache)

        source = 'api'
        id_origine = ''
        if entree_cache is not None:
            raw = entree_cache['raw']
            usage = {'input_tokens': 0, 'output_tokens': 0,
                     'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}
            modele_servi = entree_cache.get('model', model)
            id_reponse = ''                       # pas de vrai appel : « id » reste vide
            id_origine = entree_cache.get('id_origine', '')
            stop_reason = 'end_turn'
            source = 'cache'
            logger.info(f"Claude — lecture réutilisée (cache) : {image_path.name}")
        else:
            response = None
            derniere_erreur = None
            delais = list(getattr(Config, 'CLAUDE_RETRY_DELAIS', ()))
            for tentative in range(len(delais) + 1):
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
                    derniere_erreur = None
                    break
                except Exception as e:
                    derniere_erreur = e
                    if _erreur_reseau(e) and tentative < len(delais):
                        attente = delais[tentative]
                        logger.warning(
                            f"Claude indisponible ({type(e).__name__}) — nouvelle tentative "
                            f"dans {attente} s ({image_path.name})"
                        )
                        time.sleep(attente)
                        continue
                    break
            if derniere_erreur is not None:
                reseau = _erreur_reseau(derniere_erreur)
                _write_api_log({
                    'ts':      datetime.datetime.now().isoformat(timespec='seconds'),
                    'image':   image_path.name,
                    'model':   getattr(Config, 'CLAUDE_OCR_MODEL', '?'),
                    'error':   str(derniere_erreur),
                    'source':  'api',
                    'success': False,
                })
                res = {'success': False,
                       'error': f"Appel API Claude échoué : {derniere_erreur}"}
                if reseau:
                    # Coupure persistante : la conversion doit s'arrêter proprement
                    # (converter.py compose le message et conserve les pages déjà lues).
                    res['connexion_perdue'] = True
                return res

            raw = _texte_reponse(response)
            usage = _consommation(response)
            modele_servi = getattr(response, 'model', model)
            # Identifiant de la réponse : prouve qu'un passage a fait de vrais appels
            # (deux passages ne peuvent pas partager un même identifiant).
            id_reponse = getattr(response, 'id', '') or ''
            stop_reason = response.stop_reason
        logger.info(
            f"Claude {modele_servi} — {image_path.name} : "
            f"{usage['input_tokens']} tokens en entrée, {usage['output_tokens']} en sortie"
        )
        if stop_reason == 'refusal':
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
                'id':     id_reponse,
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
        if stop_reason == 'max_tokens':
            # Les dernières lignes de la page manqueraient sans que rien ne le signale.
            logger.error(
                f"Réponse tronquée (limite de {max_tokens} tokens atteinte) : {image_path.name}"
            )
            _write_api_log({
                'ts':         datetime.datetime.now().isoformat(timespec='seconds'),
                'image':      image_path.name,
                'model':      modele_servi,
                'id':      id_reponse,
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
                'id':   id_reponse,
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
            _enregistrer_cache(source, cache_actif, cle_cache, raw, modele_servi,
                               id_reponse, usage)
            _write_api_log({
                'ts':       datetime.datetime.now().isoformat(timespec='seconds'),
                'image':    image_path.name,
                'model':    modele_servi,
                'id':    id_reponse,
                'id_origine': id_origine,
                'source':   source,
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
                'lecture_cache': source == 'cache',
                'api_usage': dict(usage, model=modele_servi),
            }

        logger.info(
            f"✓ Claude Vision : {len(rows)} lignes depuis {image_path.name} "
            f"(modèle {modele_servi})"
        )
        _enregistrer_cache(source, cache_actif, cle_cache, raw, modele_servi,
                           id_reponse, usage)
        _write_api_log({
            'ts':        datetime.datetime.now().isoformat(timespec='seconds'),
            'image':     image_path.name,
            'model':     modele_servi,
            'id':     id_reponse,
            'id_origine': id_origine,
            'source':    source,
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
            'lecture_cache':    source == 'cache',
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
