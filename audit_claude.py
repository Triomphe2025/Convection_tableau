"""
Audit automatique du classeur Excel de borniers.

Deux modes :
  - Hors ligne : règles métier électrotechniques (doublons, cellules vides, continuité)
  - En ligne   : analyse approfondie via API Claude (nécessite une clé API)

Format de retour :
  {
    'ok': bool,
    'stats': { 'borniers': int, 'lignes': int, 'problemes': int },
    'problemes': [
        {
          'severite': 'critique' | 'attention' | 'info',
          'code': str,               # ex: 'DOUBLON_JARRETIERE'
          'message': str,
          'bornier': str,            # identifiant du bornier concerné
          'lignes': [int],           # numéros de lignes Excel concernées
          'correction': str,         # correction proposée (peut être vide)
        }, ...
    ],
    'analyse_ia': str,               # texte libre de l'analyse Claude (vide en mode hors ligne)
    'mode': 'hors_ligne' | 'claude_api',
  }
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Lecture du classeur Excel
# ──────────────────────────────────────────────────────────────────────────────

def _lire_excel(excel_path: Path) -> List[Dict]:
    """
    Lit la feuille 'Borniers' et retourne une liste de borniers.

    Chaque bornier = {
      'nom': str,              # identifiant (PET + BORNIER)
      'pet': str,
      'bornier': str,
      'no_plan': str,
      'page': str,
      'lignes': [              # lignes de données
          {'excel_row': int, 'cells': {col_name: str, ...}}, ...
      ],
      'colonnes': [str],       # noms de colonnes dans ce bornier
    }
    """
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl non disponible — impossible de lire l'Excel")

    wb = openpyxl.load_workbook(str(excel_path), data_only=True)
    if "Borniers" not in wb.sheetnames:
        raise ValueError("Feuille 'Borniers' introuvable dans le classeur")

    ws = wb["Borniers"]
    borniers: List[Dict] = []
    current: Optional[Dict] = None
    header_cols: List[str] = []

    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        vals = [str(c).strip() if c not in (None, '') else '' for c in row]
        if not any(vals):
            continue

        # Ligne d'en-tête : contient des noms de colonnes électrotechniques connus
        _col_kws = {'BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERE', 'CABLE', 'TYPE',
                    'SECTEUR', 'FONCTION', 'EQUIPEMENT'}
        non_empty = [v for v in vals if v]
        if non_empty and sum(
            1 for v in non_empty
            if any(kw in v.upper() for kw in _col_kws)
        ) >= max(1, len(non_empty) // 2):
            header_cols = [v for v in non_empty]
            current = {
                'nom': '', 'pet': '', 'bornier': '', 'no_plan': '', 'page': '',
                'lignes': [], 'colonnes': header_cols,
            }
            borniers.append(current)
            continue

        # Ligne de pied de page : contient P.E.T. ou BORNIER :
        joined = ' '.join(vals).upper()
        if 'P.E.T' in joined or 'BORNIER :' in joined or 'BORNIER:' in joined:
            if current is not None:
                # Extraire les métadonnées du pied
                for v in vals:
                    if not v:
                        continue
                    mu = v.upper()
                    m = re.search(r'P\.E\.T\s*[:\-]?\s*(.+)', mu)
                    if m:
                        current['pet'] = m.group(1).strip()
                    m = re.search(r'BORNIER\s*[:\-]?\s*([A-Z0-9\-]+)', mu)
                    if m:
                        current['bornier'] = m.group(1).strip()
                    m = re.search(r'N[°O]\.?\s*PLAN\s*[:\-]?\s*([A-Z0-9\s]+)', mu)
                    if m:
                        current['no_plan'] = m.group(1).strip()
                    m = re.search(r'PAGE\s*[:\-]?\s*(\d+)', mu)
                    if m:
                        current['page'] = m.group(1).strip()
                current['nom'] = (
                    f"{current['pet']} / {current['bornier']}"
                    if current['pet'] or current['bornier']
                    else f"Bornier ligne {row_idx}"
                )
            continue

        # Ligne de séparateur (NOM DU CABLE, etc.) → début nouveau bornier dans le même bloc
        _sep_kws = ('NOM DU CABLE', 'CABLE', 'SEPARATION', '───', '---')
        if any(kw in joined for kw in _sep_kws) and current and not any(vals[1:]):
            continue

        # Ligne de données
        if current is not None and header_cols:
            cells = {}
            for i, col in enumerate(header_cols):
                cells[col] = vals[i] if i < len(vals) else ''
            if any(cells.values()):
                current['lignes'].append({'excel_row': row_idx, 'cells': cells})

    # Nettoyer les borniers vides
    borniers = [b for b in borniers if b['lignes']]
    return borniers


# ──────────────────────────────────────────────────────────────────────────────
# Règles métier hors ligne
# ──────────────────────────────────────────────────────────────────────────────

def _regle_cellules_vides(borniers: List[Dict]) -> List[Dict]:
    """Détecte les cellules BORNE ou SIGNAL entièrement vides."""
    problems = []
    cols_critiques = {'BORNE', 'SIGNAL'}
    for b in borniers:
        for lig in b['lignes']:
            for col in b['colonnes']:
                if col.upper() in cols_critiques and not lig['cells'].get(col, '').strip():
                    problems.append({
                        'severite': 'attention',
                        'code': f'CELLULE_VIDE_{col.upper()}',
                        'message': f"Cellule {col} vide dans le bornier {b['nom']}",
                        'bornier': b['nom'],
                        'lignes': [lig['excel_row']],
                        'correction': f"Vérifier manuellement la colonne {col} à cette ligne.",
                    })
    return problems


def _regle_doublons_borne(borniers: List[Dict]) -> List[Dict]:
    """Détecte les codes BORNE dupliqués dans le même bornier."""
    problems = []
    for b in borniers:
        col_borne = next((c for c in b['colonnes'] if 'BORNE' in c.upper()), None)
        if not col_borne:
            continue
        seen: Dict[str, List[int]] = defaultdict(list)
        for lig in b['lignes']:
            val = lig['cells'].get(col_borne, '').strip()
            if val:
                seen[val].append(lig['excel_row'])
        for val, rows in seen.items():
            if len(rows) > 1:
                problems.append({
                    'severite': 'critique',
                    'code': 'DOUBLON_BORNE',
                    'message': f"Borne '{val}' apparaît {len(rows)} fois dans {b['nom']}",
                    'bornier': b['nom'],
                    'lignes': rows,
                    'correction': f"Garder une seule occurrence de la borne '{val}'.",
                })
    return problems


def _regle_doublons_signal(borniers: List[Dict]) -> List[Dict]:
    """Détecte les codes SIGNAL dupliqués dans le même bornier."""
    problems = []
    for b in borniers:
        col_sig = next((c for c in b['colonnes'] if 'SIGNAL' in c.upper()), None)
        if not col_sig:
            continue
        seen: Dict[str, List[int]] = defaultdict(list)
        for lig in b['lignes']:
            val = lig['cells'].get(col_sig, '').strip()
            if val and val not in ('-', 'NC', 'N/C', 'N.C.'):
                seen[val].append(lig['excel_row'])
        for val, rows in seen.items():
            if len(rows) > 1:
                problems.append({
                    'severite': 'attention',
                    'code': 'DOUBLON_SIGNAL',
                    'message': f"Signal '{val}' apparaît {len(rows)} fois dans {b['nom']}",
                    'bornier': b['nom'],
                    'lignes': rows,
                    'correction': f"Vérifier si le signal '{val}' est vraiment câblé en boucle.",
                })
    return problems


def _regle_couleurs_invalides(borniers: List[Dict]) -> List[Dict]:
    """Détecte des couleurs de câble suspectes (devraient être des codes couleur standard)."""
    _couleurs_valides = {
        'NOIR', 'BLANC', 'ROUGE', 'BLEU', 'VERT', 'JAUNE', 'ORANGE', 'MARRON',
        'VIOLET', 'GRIS', 'ROSE', 'TURQUOISE',
        'BK', 'WH', 'RD', 'BU', 'GN', 'YE', 'OG', 'BN', 'VT', 'GY',
        'NO', 'BL', 'RG', 'VE', 'GR', 'MA',
        '01A', '01B', '11A', '11B',                      # codes numériques courants
    }
    problems = []
    for b in borniers:
        col_coul = next((c for c in b['colonnes'] if 'COULEUR' in c.upper()), None)
        if not col_coul:
            continue
        for lig in b['lignes']:
            val = lig['cells'].get(col_coul, '').strip().upper()
            if not val:
                continue
            # Un code couleur standard a 2–5 caractères ou correspond à la liste
            if len(val) > 8 and val not in _couleurs_valides:
                problems.append({
                    'severite': 'info',
                    'code': 'COULEUR_SUSPECTE',
                    'message': f"Couleur suspecte '{val}' dans {b['nom']}",
                    'bornier': b['nom'],
                    'lignes': [lig['excel_row']],
                    'correction': "Vérifier si la valeur OCR est correcte (confusion possible).",
                })
    return problems


def _regle_jarretieres_format(borniers: List[Dict]) -> List[Dict]:
    """Détecte des codes JARRETIERES de format inhabituel."""
    problems = []
    for b in borniers:
        col_jar = next(
            (c for c in b['colonnes']
             if 'JARRETIERE' in c.upper() or 'JARR' in c.upper()),
            None
        )
        if not col_jar:
            continue
        # Format attendu : lettre(s) + chiffres + lettre(s), ex: B48DNA, AC, B337
        _pattern = re.compile(r'^[A-Z][A-Z0-9]{1,12}$')
        for lig in b['lignes']:
            val = lig['cells'].get(col_jar, '').strip().upper()
            if not val:
                continue
            # Plusieurs codes peuvent être séparés par des espaces
            codes = val.split()
            for code in codes:
                if not _pattern.match(code) and len(code) > 2:
                    problems.append({
                        'severite': 'info',
                        'code': 'JARRETIERE_FORMAT',
                        'message': f"Code jarretière '{code}' de format inhabituel dans {b['nom']}",
                        'bornier': b['nom'],
                        'lignes': [lig['excel_row']],
                        'correction': "Vérifier le code jarretière (OCR a pu confondre des caractères).",
                    })
                    break
    return problems


def _regle_coherence_pages(borniers: List[Dict]) -> List[Dict]:
    """Détecte des numéros de page manquants ou en doublon."""
    problems = []
    pages_vues: Dict[str, List[str]] = defaultdict(list)
    for b in borniers:
        if b['page']:
            pages_vues[b['page']].append(b['nom'])
        else:
            problems.append({
                'severite': 'info',
                'code': 'PAGE_MANQUANTE',
                'message': f"Numéro de page manquant pour {b['nom']}",
                'bornier': b['nom'],
                'lignes': [],
                'correction': "Le pied de page n'a pas pu être extrait — vérifier l'image source.",
            })
    for page, noms in pages_vues.items():
        if len(noms) > 1:
            problems.append({
                'severite': 'attention',
                'code': 'PAGE_DOUBLON',
                'message': f"Page {page} apparaît pour {len(noms)} borniers : {', '.join(noms)}",
                'bornier': noms[0],
                'lignes': [],
                'correction': "Vérifier si deux borniers ont vraiment le même numéro de page.",
            })
    return problems


# ──────────────────────────────────────────────────────────────────────────────
# Audit hors ligne
# ──────────────────────────────────────────────────────────────────────────────

def auditer_hors_ligne(borniers: List[Dict]) -> List[Dict]:
    """Lance toutes les règles métier et retourne la liste des problèmes."""
    problems: List[Dict] = []
    problems += _regle_doublons_borne(borniers)
    problems += _regle_doublons_signal(borniers)
    problems += _regle_cellules_vides(borniers)
    problems += _regle_couleurs_invalides(borniers)
    problems += _regle_jarretieres_format(borniers)
    problems += _regle_coherence_pages(borniers)
    return problems


# ──────────────────────────────────────────────────────────────────────────────
# Analyse Claude API (mode en ligne)
# ──────────────────────────────────────────────────────────────────────────────

def _resumer_pour_claude(borniers: List[Dict], max_borniers: int = 20) -> str:
    """
    Construit un résumé textuel compact des borniers pour l'envoi à Claude.
    Limite à max_borniers pour rester dans la fenêtre de contexte.
    """
    lines = [
        f"Classeur de borniers électriques — {len(borniers)} borniers au total.",
        f"Seuls les {min(len(borniers), max_borniers)} premiers sont détaillés ci-dessous.",
        "",
    ]
    for b in borniers[:max_borniers]:
        lines.append(
            f"BORNIER: {b['nom']} | PAGE: {b['page']} | "
            f"PET: {b['pet']} | {len(b['lignes'])} lignes"
        )
        cols = b['colonnes']
        header = " | ".join(f"{c:14}" for c in cols)
        lines.append(f"  {header}")
        for lig in b['lignes'][:8]:
            row_vals = " | ".join(
                f"{lig['cells'].get(c, ''):14}" for c in cols
            )
            lines.append(f"  {row_vals}")
        if len(b['lignes']) > 8:
            lines.append(f"  ... ({len(b['lignes']) - 8} lignes supplémentaires)")
        lines.append("")
    return "\n".join(lines)


def _appeler_claude(resume: str, api_key: str, model: str) -> str:
    """Envoie le résumé à Claude et retourne l'analyse textuelle."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "Package 'anthropic' non installé.\n"
            "Lancez : pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Tu es un expert en électrotechnique industrielle spécialisé dans les borniers de câblage.
Analyse ce classeur de borniers extrait par OCR et identifie :

1. Les problèmes électrotechniques : doublons de bornes/signaux, incohérences de câblage, codes erreurs
2. Les erreurs OCR probables : confusions de caractères (0↔O, 1↔l, etc.), codes incomplets
3. La cohérence globale : séquences de bornes logiques, codes de jarretières cohérents
4. Les points à vérifier en priorité

Sois précis et concis. Indique toujours le bornier concerné et la ligne.
Utilise le format :
- [CRITIQUE/ATTENTION/INFO] Bornier X — description du problème → correction proposée

DONNÉES DU CLASSEUR :
{resume}

ANALYSE :"""

    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ──────────────────────────────────────────────────────────────────────────────
# Point d'entrée principal
# ──────────────────────────────────────────────────────────────────────────────

def auditer(
    excel_path: Path,
    api_key: str = "",
    model: str = "claude-haiku-4-5-20251001",
) -> Dict:
    """
    Lance l'audit complet du classeur Excel.

    - Sans api_key : audit hors ligne uniquement (règles métier).
    - Avec api_key : audit hors ligne + analyse Claude API.

    Retourne le dict décrit dans l'en-tête du module.
    """
    if not excel_path.exists():
        return {
            'ok': False, 'stats': {}, 'problemes': [],
            'analyse_ia': '', 'mode': 'erreur',
            'erreur': f"Fichier introuvable : {excel_path}",
        }

    # Lecture du classeur
    try:
        borniers = _lire_excel(excel_path)
    except Exception as exc:
        return {
            'ok': False, 'stats': {}, 'problemes': [],
            'analyse_ia': '', 'mode': 'erreur',
            'erreur': f"Impossible de lire le classeur : {exc}",
        }

    if not borniers:
        return {
            'ok': False, 'stats': {}, 'problemes': [],
            'analyse_ia': '', 'mode': 'erreur',
            'erreur': "Aucun bornier trouvé dans la feuille 'Borniers'.",
        }

    total_lignes = sum(len(b['lignes']) for b in borniers)
    logger.info(f"Audit — {len(borniers)} borniers, {total_lignes} lignes lues")

    # Règles hors ligne
    problemes = auditer_hors_ligne(borniers)

    # Analyse Claude API (optionnelle)
    analyse_ia = ""
    mode = "hors_ligne"
    if api_key:
        try:
            resume = _resumer_pour_claude(borniers)
            analyse_ia = _appeler_claude(resume, api_key, model)
            mode = "claude_api"
            logger.info("Analyse Claude API terminée")
        except Exception as exc:
            analyse_ia = f"Analyse IA indisponible : {exc}"
            logger.warning(f"Audit Claude API : {exc}")

    return {
        'ok': True,
        'stats': {
            'borniers': len(borniers),
            'lignes': total_lignes,
            'problemes': len(problemes),
        },
        'problemes': problemes,
        'analyse_ia': analyse_ia,
        'mode': mode,
    }
