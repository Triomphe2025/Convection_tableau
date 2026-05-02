"""
Système de modèles de tableaux pour TriosSeconverter.

Permet de définir des structures de tableaux personnalisées
(colonnes, séparateur de section, pied de page).
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
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

    # Formats du pied — utilisent les clés extraites par l'OCR ({PET}, {BORNIER}…)
    footer_row1_format: str = "P.E.T. : {PET}   BORNIER : {BORNIER}"
    footer_row2_format: str = "NO PLAN : {NO_PLAN}  |  INDICE : {INDICE}  |  PAGE : {PAGE}"

    # Mots-clés pour détecter les lignes de pied en OCR
    footer_detect_keywords: List[str] = field(
        default_factory=lambda: ['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :']
    )
    footer_mti_tokens: List[str] = field(
        default_factory=lambda: ['M', 'T', 'I']
    )

    # Largeurs Excel par nom de colonne (0 = largeur auto 20)
    col_widths: Dict[str, float] = field(default_factory=dict)

    description: str = ""

    def col_width(self, col_name: str) -> float:
        """Retourne la largeur Excel d'une colonne (défaut 20)."""
        return self.col_widths.get(col_name, 20.0)

    def render_footer_row1(self, meta: Dict) -> str:
        try:
            return self.footer_row1_format.format_map(
                {k: meta.get(k, '') for k in
                 ['PET', 'BORNIER', 'NO_PLAN', 'INDICE', 'PAGE']}
            )
        except Exception:
            return self.footer_row1_format

    def render_footer_row2(self, meta: Dict) -> str:
        try:
            return self.footer_row2_format.format_map(
                {k: meta.get(k, '') for k in
                 ['PET', 'BORNIER', 'NO_PLAN', 'INDICE', 'PAGE']}
            )
        except Exception:
            return self.footer_row2_format

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
    footer_row1_format="P.E.T. : {PET}   BORNIER : {BORNIER}",
    footer_row2_format="NO PLAN : {NO_PLAN}  |  INDICE : {INDICE}  |  PAGE : {PAGE}",
    footer_detect_keywords=['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :'],
    footer_mti_tokens=['M', 'T', 'I'],
    col_widths={"BORNE": 8, "COULEUR": 12, "SIGNAL": 50, "JARRETIERES": 15},
    description="Tableau de bornier électrique standard",
)


# ── Gestionnaire de modèles ───────────────────────────────────────────

class TemplateManager:
    """Charge, sauvegarde et liste les modèles de tableaux."""

    def __init__(self):
        self._templates: Dict[str, TableTemplate] = {}
        self._load()

    # ── Persistance ───────────────────────────────────────────────────

    def _load(self) -> None:
        self._templates = {"Bornier standard": DEFAULT_TEMPLATE}
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
            data = {
                name: t.to_dict()
                for name, t in self._templates.items()
                if name != "Bornier standard"   # le défaut n'est pas persisté
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
        if name == "Bornier standard":
            return
        self._templates.pop(name, None)
        self.save()

    def get(self, name: str) -> TableTemplate:
        return self._templates.get(name, DEFAULT_TEMPLATE)

    def names(self) -> List[str]:
        return list(self._templates.keys())

    def all(self) -> List[TableTemplate]:
        return list(self._templates.values())
