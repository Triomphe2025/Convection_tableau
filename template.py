"""
Système de modèles de tableaux pour TriosSeconverter.

Permet de définir des structures de tableaux personnalisées
(colonnes, séparateur de section, pied de page).
"""

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List
import json
import logging

logger = logging.getLogger(__name__)

TEMPLATES_FILE = Path(__file__).parent / "templates.json"


@dataclass
class TableTemplate:
    """Définit la structure d'un tableau à reconnaître par OCR."""

    name: str
    columns: List[str]

    # Mot-clé qui identifie une ligne de séparation (ex: "NOM DU CABLE")
    section_keyword: str = "NOM DU CABLE"

    # Pied de page
    has_footer: bool = True
    footer_left_label: str = "M  T  I"

    # Formats du pied (utilisés uniquement comme repli si render_* échoue)
    footer_row1_format: str = "P.E.T.   :     {PET}    BORNIER :    {BORNIER}"
    footer_row2_format: str = (
        "NO PLAN    :   {NO_PLAN}  |  INDICE : {INDICE}  |  PAGE :   {PAGE}"
    )

    # Mots-clés pour détecter les lignes de pied en OCR
    footer_detect_keywords: List[str] = field(
        default_factory=lambda: ['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :']
    )
    footer_mti_tokens: List[str] = field(
        default_factory=lambda: ['M', 'T', 'I']
    )

    # Champs à extraire du pied de page : {"label": "...", "key": "..."}
    # - label : mot-clé recherché dans le texte du pied (insensible à la casse)
    # - key   : nom de la clé dans le dict metadata (et placeholder {KEY} dans les formats)
    # Les 5 champs standard (PET, BORNIER, NO_PLAN, INDICE, PAGE) ont des patterns
    # affinés codés en dur ; les champs supplémentaires utilisent un pattern générique.
    footer_extract_fields: List[Dict[str, str]] = field(
        default_factory=lambda: [
            {"label": "P.E.T.",  "key": "PET"},
            {"label": "BORNIER", "key": "BORNIER"},
            {"label": "NO PLAN", "key": "NO_PLAN"},
            {"label": "INDICE",  "key": "INDICE"},
            {"label": "PAGE",    "key": "PAGE"},
        ]
    )

    # Largeurs Excel par nom de colonne (0 = largeur auto 20)
    col_widths: Dict[str, float] = field(default_factory=dict)

    description: str = ""

    def col_width(self, col_name: str) -> float:
        """Retourne la largeur Excel d'une colonne (défaut 20)."""
        return self.col_widths.get(col_name, 20.0)

    def _build_safe_meta(self, meta: Dict) -> Dict:
        """
        Construit le dict de substitution pour format_map().
        Toutes les clés de meta sont incluses (champs standards ET champs
        personnalisés comme CABLE, TYPE…). Les clés manquantes retournent ''.
        INDICE vaut '0' par défaut.
        """
        safe: Dict = defaultdict(str)
        for k, v in meta.items():
            safe[k] = str(v or '').strip()
        safe.setdefault('PET',     '')
        safe.setdefault('BORNIER', '')
        safe.setdefault('PAGE',    '')
        safe.setdefault('NO_PLAN', '')
        safe.setdefault('INDICE',  meta.get('INDICE', '0') or '0')
        return safe

    def render_footer_row1(self, meta: Dict) -> str:
        """
        Rend la ligne 1 du pied depuis footer_row1_format.
        Tous les placeholders présents dans le format sont résolus depuis meta
        (champs standards ET champs personnalisés définis dans footer_extract_fields).
        """
        safe = self._build_safe_meta(meta)
        try:
            return self.footer_row1_format.format_map(safe)
        except Exception:
            return f"P.E.T.   :     {safe['PET']:<50}BORNIER :    {safe['BORNIER']}"

    def render_footer_row2(self, meta: Dict) -> str:
        """
        Rend la ligne 2 du pied depuis footer_row2_format.
        Tous les placeholders présents dans le format sont résolus depuis meta
        (champs standards ET champs personnalisés définis dans footer_extract_fields).
        """
        safe = self._build_safe_meta(meta)
        try:
            return self.footer_row2_format.format_map(safe)
        except Exception:
            return (f"NO PLAN    :   {safe['NO_PLAN']:<37}"
                    f"|  INDICE : {safe['INDICE']:<8}"
                    f"|  PAGE :   {safe['PAGE']}")

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "TableTemplate":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Modèle par défaut (bornier standard) ─────────────────────────────

DEFAULT_TEMPLATE = TableTemplate(
    name="Bornier standard",
    columns=["BORNE", "COULEUR", "SIGNAL", "JARRETIERES"],
    section_keyword="NOM DU CABLE",
    has_footer=True,
    footer_left_label="M  T  I",
    footer_row1_format="P.E.T.   :     {PET:<50}BORNIER :    {BORNIER}",
    footer_row2_format="NO PLAN    :   {NO_PLAN:<37}|  INDICE : {INDICE:<8}|  PAGE :   {PAGE}",
    footer_detect_keywords=['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :'],
    footer_mti_tokens=['M', 'T', 'I'],
    col_widths={"BORNE": 8, "COULEUR": 12, "SIGNAL": 50, "JARRETIERES": 15},
    description="Tableau de bornier électrique standard",
)


REPARTITEUR_TEMPLATE = TableTemplate(
    name="Répartiteur",
    columns=["TENANT", "JAR", "ABOUTISSANT", "SIGNAL"],
    section_keyword="NOM DU CABLE",
    has_footer=True,
    footer_left_label="M  T  I",
    # "JARRETIERAGE" est un element fixe du document, pas une donnee variable
    footer_row1_format="P.E.T.   :     {PET:<50}JARRETIERAGE",
    footer_row2_format="NO PLAN    :   {NO_PLAN:<37}|  INDICE : {INDICE:<8}|  PAGE :   {PAGE}",
    footer_detect_keywords=['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :'],
    footer_mti_tokens=['M', 'T', 'I'],
    col_widths={"TENANT": 22, "JAR": 10, "ABOUTISSANT": 22, "SIGNAL": 36},
    description="Tableau répartiteur : TENANT / JAR / ABOUTISSANT / SIGNAL",
)


# ── Gestionnaire de modèles ───────────────────────────────────────────

class TemplateManager:
    """Charge, sauvegarde et liste les modèles de tableaux."""

    def __init__(self):
        self._templates: Dict[str, TableTemplate] = {}
        self._load()

    # ── Persistance ───────────────────────────────────────────────────

    def _load(self) -> None:
        self._templates = {
            "Bornier standard": DEFAULT_TEMPLATE,
            "Répartiteur":      REPARTITEUR_TEMPLATE,
        }
        if TEMPLATES_FILE.exists():
            try:
                with open(TEMPLATES_FILE, encoding='utf-8') as f:
                    data = json.load(f)
                for name, td in data.items():
                    if name != "Bornier standard":
                        self._templates[name] = TableTemplate.from_dict(td)
            except Exception as e:
                logger.warning(f"Impossible de charger templates.json : {e}")

    def save(self) -> None:
        try:
            # "Bornier standard" est toujours chargé depuis le code → jamais dans le fichier.
            # Tous les autres (y compris "Répartiteur" modifié) sont persistés dans JSON.
            data = {
                name: t.to_dict()
                for name, t in self._templates.items()
                if name != "Bornier standard"
            }
            with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde templates : {e}")

    # ── CRUD ─────────────────────────────────────────────────────────

    def add_or_update(self, template: TableTemplate) -> None:
        self._templates[template.name] = template
        self.save()

    def delete(self, name: str) -> None:
        if name in ("Bornier standard", "Répartiteur"):
            return
        self._templates.pop(name, None)
        self.save()

    def get(self, name: str) -> TableTemplate:
        return self._templates.get(name, DEFAULT_TEMPLATE)

    def names(self) -> List[str]:
        return list(self._templates.keys())

    def all(self) -> List[TableTemplate]:
        return list(self._templates.values())
